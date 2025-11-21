import threading
import webbrowser
from typing import List, Optional, Union
from urllib import parse
import http.server
import requests
from pathlib import Path
import time
import argparse
import base64
import asyncio
import aiohttp
import aiofiles
import csv

LOCAL_PORT = 8080
CALLBACK_PATHS = ("/", "/oauth2callback")


class GmailClient:
    def __init__(self, backend_url: str = "http://37.27.51.34:31873", session_file: Union[str, Path] = None, rpm: int = 60):
        self.backend_url = backend_url.rstrip("/")
        self.session_file = Path(session_file) if session_file else Path.home() / ".pygmail" / "session.token"
        self.session_token: Optional[str] = None
        self.rpm = rpm
        self._last_call = 0
        self._min_interval = 60.0 / rpm

    class OAuthHandler(http.server.BaseHTTPRequestHandler):
        server_data = {"code": None, "state": None}
        server_event = threading.Event()

        def do_GET(self):
            parsed = parse.urlparse(self.path)
            if parsed.path not in CALLBACK_PATHS:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Not found")
                return

            qs = parse.parse_qs(parsed.query)
            code = qs.get("code", [None])[0]
            state = qs.get("state", [None])[0]
            self.__class__.server_data["code"] = code
            self.__class__.server_data["state"] = state
            self.__class__.server_event.set()

            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html><body><h2>Authentication complete, you can close this window.</h2></body></html>")

        def log_message(self, format, *args):
            return

    def _run_local_server(self, timeout: int = 300):
        handler = self.OAuthHandler
        handler.server_data = {"code": None, "state": None}
        handler.server_event = threading.Event()

        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", LOCAL_PORT), handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        waited = handler.server_event.wait(timeout=timeout)
        if not waited:
            try:
                httpd.shutdown()
                httpd.server_close()
            except Exception:
                pass
            return None, None

        code = handler.server_data.get("code")
        state = handler.server_data.get("state")
        try:
            httpd.shutdown()
            httpd.server_close()
        except Exception:
            pass
        return code, state

    def authenticate(self, open_browser: bool = True, timeout: int = 300) -> str:
        resp = requests.get(f"{self.backend_url}/authorize")
        resp.raise_for_status()
        data = resp.json()
        auth_url = data["auth_url"]
        expected_state = data.get("state")

        if open_browser:
            webbrowser.open(auth_url)
        else:
            print("Open this URL in your browser:", auth_url)

        code, returned_state = self._run_local_server(timeout=timeout)
        if not code:
            raise RuntimeError("Failed to receive OAuth2 code from Google (timeout or error).")

        state_to_send = returned_state or expected_state

        token_resp = requests.post(
            f"{self.backend_url}/exchange_code", json={"code": code, "state": state_to_send}
        )
        token_resp.raise_for_status()
        self.session_token = token_resp.json()["session_token"]

        try:
            self.session_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.session_file, "w") as f:
                f.write(self.session_token)
        except Exception:
            pass

        return self.session_token
    
    def _rate_limit(self):
        now = time.time()
        elapsed = now - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.time()

    def init(self, session_token_or_path: Optional[Union[str, Path]] = None) -> None:
        if session_token_or_path is None:
            if not self.session_file.exists():
                raise RuntimeError("No session token found. Run authenticate() first or pass a token/path to init().")
            with open(self.session_file, "r") as f:
                self.session_token = f.read().strip()
            return

        candidate = Path(session_token_or_path)
        if candidate.exists():
            with open(candidate, "r") as f:
                self.session_token = f.read().strip()
            try:
                self.session_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.session_file, "w") as f:
                    f.write(self.session_token)
            except Exception:
                pass
            return

        self.session_token = str(session_token_or_path).strip()
        try:
            self.session_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.session_file, "w") as f:
                f.write(self.session_token)
        except Exception:
            pass

    def is_authorized(self) -> bool:
        if not self.session_token:
            return False
        try:
            resp = requests.get(f"{self.backend_url}/me", headers={"Authorization": f"Bearer {self.session_token}"})
            return resp.status_code == 200
        except Exception:
            return False

    def me(self) -> dict:
        if not self.session_token:
            raise RuntimeError("Client not initialized. Call init() first.")
        resp = requests.get(f"{self.backend_url}/me", headers={"Authorization": f"Bearer {self.session_token}"})
        resp.raise_for_status()
        return resp.json()

    # holy long ass function definition
    def send_email(self, to: Union[str, List[str]], subject: str, body: Optional[str] = None, html: Optional[str] = None, cc: Optional[Union[str, List[str]]] = None, bcc: Optional[Union[str, List[str]]] = None, attachments: Optional[List[Union[str, Path]]] = None, reply_to_thread: Optional[str] = None) -> dict:
        if not self.session_token:
            raise RuntimeError("Client not initialized. Call init() first.")

        def normalize_list(v):
            if v is None:
                return []
            return [str(x) for x in v] if isinstance(v, (list, tuple)) else [str(v)]

        to_list = normalize_list(to)
        cc_list = normalize_list(cc)
        bcc_list = normalize_list(bcc)

        # Build data as a list of tuples for proper multipart/form-data handling
        data = [("subject", subject)]
        
        # Add each recipient separately
        for email in to_list:
            data.append(("to", email))
        
        for email in cc_list:
            data.append(("cc", email))
        
        for email in bcc_list:
            data.append(("bcc", email))
        
        if body:
            data.append(("body", body))
        if html:
            data.append(("html", html))
        if reply_to_thread:
            data.append(("reply_to_thread", reply_to_thread))

        files = []
        file_objs = []
        try:
            if attachments:
                for p in attachments:
                    pth = Path(p)
                    if not pth.exists():
                        raise FileNotFoundError(f"Attachment not found: {p}")
                    f = open(pth, "rb")
                    file_objs.append(f)
                    files.append(("attachments", (pth.name, f)))

            self._rate_limit()

            # Always send as multipart/form-data by using files parameter
            # even if files list is empty
            resp = requests.post(
                f"{self.backend_url}/send_email",
                data=data,
                files=files if files else [],  # Send empty list instead of None
                headers={"Authorization": f"Bearer {self.session_token}"},
            )
            resp.raise_for_status()
            return resp.json()
        finally:
            for f in file_objs:
                f.close()            

    def authenticate_cli(self, open_browser: bool = True):
        token = self.authenticate(open_browser=open_browser)
        print("Authentication successful. Session token saved to:", str(self.session_file))
        return token

    def list_emails(self, max_results: int = 10, query: Optional[str] = None, page_token: Optional[str] = None) -> dict:
        if not self.session_token:
            raise RuntimeError("Client not initialized. Call init() first.")
        
        params = {"max_results": max_results}
        if query:
            params["query"] = query
        if page_token:
            params["page_token"] = page_token
        
        self._rate_limit()
        
        resp = requests.get(
            f"{self.backend_url}/list_emails",
            params=params,
            headers={"Authorization": f"Bearer {self.session_token}"}
        )
        resp.raise_for_status()
        return resp.json()

    def get_email(self, message_id: str, format: str = "full") -> dict:
        if not self.session_token:
            raise RuntimeError("Client not initialized. Call init() first.")
        
        self._rate_limit()
        
        resp = requests.get(
            f"{self.backend_url}/get_email/{message_id}",
            params={"format": format},
            headers={"Authorization": f"Bearer {self.session_token}"}
        )
        resp.raise_for_status()
        return resp.json()

    def get_parsed_email(self, message_id: str) -> dict:
        if not self.session_token:
            raise RuntimeError("Client not initialized. Call init() first.")
        
        self._rate_limit()
        
        resp = requests.get(
            f"{self.backend_url}/get_parsed_email/{message_id}",
            headers={"Authorization": f"Bearer {self.session_token}"}
        )
        resp.raise_for_status()
        return resp.json()

    def get_attachment(self, message_id: str, attachment_id: str, output_path: Optional[Union[str, Path]] = None) -> bytes:
        """
        Download an attachment from an email.
        
        Args:
            message_id: The email message ID
            attachment_id: The attachment ID from get_parsed_email()
            output_path: Optional path to save the attachment. If None, returns raw bytes.
        
        Returns:
            Raw attachment bytes
        """
        if not self.session_token:
            raise RuntimeError("Client not initialized. Call init() first.")
        
        self._rate_limit()
        
        resp = requests.get(
            f"{self.backend_url}/get_attachment/{message_id}/{attachment_id}",
            headers={"Authorization": f"Bearer {self.session_token}"}
        )
        resp.raise_for_status()
        
        data = resp.json()
        # Decode base64 data
        attachment_bytes = base64.urlsafe_b64decode(data["data"])
        
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(attachment_bytes)
        
        return attachment_bytes

    def download_all_attachments(self, message_id: str, output_dir: Union[str, Path] = "./attachments") -> List[Path]:
        """
        Download all attachments from an email.
        
        Args:
            message_id: The email message ID
            output_dir: Directory to save attachments (default: ./attachments)
        
        Returns:
            List of paths where attachments were saved
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Get parsed email to find attachments
        email_data = self.get_parsed_email(message_id)
        attachments = email_data.get("attachments", [])
        
        if not attachments:
            return []
        
        saved_paths = []
        for att in attachments:
            filename = att.get("filename", "unnamed_attachment")
            attachment_id = att.get("attachment_id")
            
            if not attachment_id:
                continue
            
            # Handle duplicate filenames
            output_path = output_dir / filename
            counter = 1
            while output_path.exists():
                name_parts = filename.rsplit(".", 1)
                if len(name_parts) == 2:
                    output_path = output_dir / f"{name_parts[0]}_{counter}.{name_parts[1]}"
                else:
                    output_path = output_dir / f"{filename}_{counter}"
                counter += 1
            
            self.get_attachment(message_id, attachment_id, output_path)
            saved_paths.append(output_path)
            print(f"Downloaded: {output_path}")
        
        return saved_paths
    
    def export_emails(self, target: Union[str, List[str]], output_file: str = "emails_export.csv", format: str = "csv"):
        if not self.session_token:
            raise RuntimeError("Client not initialized. Call init() first.")
        
        messages_to_fetch = []
        
        print(f"Gathering message list for target: {target}...")

        if isinstance(target, list):
            messages_to_fetch = [{"id": mid} for mid in target]
        elif target.lower() == "all":
            page_token = None
            while True:
                res = self.list_emails(max_results=50, page_token=page_token)
                msgs = res.get("messages", [])
                messages_to_fetch.extend(msgs)
                print(f"  Found {len(messages_to_fetch)} messages so far...")
                page_token = res.get("next_page_token")
                if not page_token:
                    break
        elif target.startswith("thread:"):
            thread_id = target.split(":")[1]
            res = self.list_emails(max_results=100, query=f"thread:{thread_id}")
            messages_to_fetch = res.get("messages", [])
        else:
            res = self.list_emails(max_results=100, query=target)
            messages_to_fetch = res.get("messages", [])

        print(f"Starting download of {len(messages_to_fetch)} emails.")
        
        fieldnames = ["id", "thread_id", "date", "from", "to", "subject", "snippet", "body_plain", "has_attachments"]
        
        try:
            with open(output_file, mode='w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for i, msg_obj in enumerate(messages_to_fetch):
                    mid = msg_obj["id"]
                    try:
                        data = self.get_parsed_email(mid)
                        row = {
                            "id": data.get("id"),
                            "thread_id": data.get("thread_id"),
                            "date": data["headers"].get("Date"),
                            "from": data["headers"].get("From"),
                            "to": data["headers"].get("To"),
                            "subject": data["headers"].get("Subject"),
                            "snippet": data.get("snippet"),
                            "body_plain": data.get("body_plain", "")[:32000],
                            "has_attachments": "Yes" if data.get("attachments") else "No"
                        }
                        writer.writerow(row)
                        if i % 5 == 0:
                            print(f"  Processed {i+1}/{len(messages_to_fetch)}...")
                            
                    except Exception as e:
                        print(f"  Failed to fetch message {mid}: {e}")
                        
            print(f"Successfully exported {len(messages_to_fetch)} emails to {output_file}")
            
        except IOError as e:
            print(f"Error writing file: {e}")

    # Async versions
    async def _async_rate_limit(self):
        now = time.time()
        elapsed = now - self._last_call
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_call = time.time()

    async def send_email_async(self, to: Union[str, List[str]], subject: str, body: Optional[str] = None, html: Optional[str] = None, cc: Optional[Union[str, List[str]]] = None, bcc: Optional[Union[str, List[str]]] = None, attachments: Optional[List[Union[str, Path]]] = None, reply_to_thread: Optional[str] = None) -> dict:
        if not self.session_token:
            raise RuntimeError("Client not initialized. Call init() first.")

        def normalize_list(v):
            if v is None:
                return []
            return [str(x) for x in v] if isinstance(v, (list, tuple)) else [str(v)]

        to_list = normalize_list(to)
        cc_list = normalize_list(cc)
        bcc_list = normalize_list(bcc)

        form_data = aiohttp.FormData()
        form_data.add_field("subject", subject)
        
        for email in to_list:
            form_data.add_field("to", email)
        for email in cc_list:
            form_data.add_field("cc", email)
        for email in bcc_list:
            form_data.add_field("bcc", email)
        
        if body:
            form_data.add_field("body", body)
        if html:
            form_data.add_field("html", html)
        if reply_to_thread:
            form_data.add_field("reply_to_thread", reply_to_thread)

        if attachments:
            for p in attachments:
                pth = Path(p)
                if not pth.exists():
                    raise FileNotFoundError(f"Attachment not found: {p}")
                async with aiofiles.open(pth, "rb") as f:
                    content = await f.read()
                    form_data.add_field("attachments", content, filename=pth.name)

        await self._async_rate_limit()

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.backend_url}/send_email",
                data=form_data,
                headers={"Authorization": f"Bearer {self.session_token}"}
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def list_emails_async(self, max_results: int = 10, query: Optional[str] = None, page_token: Optional[str] = None) -> dict:
        if not self.session_token:
            raise RuntimeError("Client not initialized. Call init() first.")
        
        params = {"max_results": max_results}
        if query:
            params["query"] = query
        if page_token:
            params["page_token"] = page_token
        
        await self._async_rate_limit()
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.backend_url}/list_emails",
                params=params,
                headers={"Authorization": f"Bearer {self.session_token}"}
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def get_email_async(self, message_id: str, format: str = "full") -> dict:
        if not self.session_token:
            raise RuntimeError("Client not initialized. Call init() first.")
        
        await self._async_rate_limit()
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.backend_url}/get_email/{message_id}",
                params={"format": format},
                headers={"Authorization": f"Bearer {self.session_token}"}
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def get_parsed_email_async(self, message_id: str) -> dict:
        if not self.session_token:
            raise RuntimeError("Client not initialized. Call init() first.")
        
        await self._async_rate_limit()
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.backend_url}/get_parsed_email/{message_id}",
                headers={"Authorization": f"Bearer {self.session_token}"}
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def get_attachment_async(self, message_id: str, attachment_id: str, output_path: Optional[Union[str, Path]] = None) -> bytes:
        if not self.session_token:
            raise RuntimeError("Client not initialized. Call init() first.")
        
        await self._async_rate_limit()
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.backend_url}/get_attachment/{message_id}/{attachment_id}",
                headers={"Authorization": f"Bearer {self.session_token}"}
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
        
        attachment_bytes = base64.urlsafe_b64decode(data["data"])
        
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(output_path, "wb") as f:
                await f.write(attachment_bytes)
        
        return attachment_bytes

    async def get_all_attachments(self, message_id: str, output_dir: Union[str, Path] = "./attachments") -> List[Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        email_data = await self.get_parsed_email_async(message_id)
        attachments = email_data.get("attachments", [])
        
        if not attachments:
            return []
        
        saved_paths = []
        for att in attachments:
            filename = att.get("filename", "unnamed_attachment")
            attachment_id = att.get("attachment_id")
            
            if not attachment_id:
                continue
            
            output_path = output_dir / filename
            counter = 1
            while output_path.exists():
                name_parts = filename.rsplit(".", 1)
                if len(name_parts) == 2:
                    output_path = output_dir / f"{name_parts[0]}_{counter}.{name_parts[1]}"
                else:
                    output_path = output_dir / f"{filename}_{counter}"
                counter += 1
            
            await self.get_attachment_async(message_id, attachment_id, output_path)
            saved_paths.append(output_path)
            print(f"Downloaded: {output_path}")
        
        return saved_paths

def main():
    parser = argparse.ArgumentParser(prog="pygmail", description="pygmail CLI")
    sub = parser.add_subparsers(dest="command")

    auth_p = sub.add_parser("authenticate", help="Authenticate via browser-based OAuth loopback")
    auth_p.add_argument("--no-browser", action="store_true", help="Print URL instead of opening browser")

    send_p = sub.add_parser("send", help="Send an email")
    send_p.add_argument("--to", action="append", required=True, help="Recipient (can repeat)")
    send_p.add_argument("--cc", action="append", help="CC recipient (only one)")
    send_p.add_argument("--bcc", action="append", help="BCC recipient (only one)")
    send_p.add_argument("--subject", required=True, help="Subject")
    send_p.add_argument("--body", help="Plain text body")
    send_p.add_argument("--html", help="HTML string or path to .html file")
    send_p.add_argument("--attach", action="append", help="Attachment file path (only one)")
    send_p.add_argument("--reply", help="Thread ID to reply to")

    sub.add_parser("me", help="Show authenticated user info")
    init_p = sub.add_parser("init", help="Load session token from a file or paste token")
    init_p.add_argument("--token", help="Session token string (if not provided, loads default session file)")

    list_p = sub.add_parser("list", help="List emails")
    list_p.add_argument("--max", type=int, default=10, help="Maximum number of emails to list")
    list_p.add_argument("--query", help="Gmail search query (e.g., 'is:unread from:someone@example.com')")

    get_p = sub.add_parser("get", help="Get email details")
    get_p.add_argument("message_id", help="Message ID")

    dl_p = sub.add_parser("download", help="Download attachments from an email")
    dl_p.add_argument("message_id", help="Message ID")
    dl_p.add_argument("--output", "-o", default="./attachments", help="Output directory (default: ./attachments)")
    dl_p.add_argument("--attachment-id", help="Specific attachment ID to download (downloads all if not specified)")

    exp_p = sub.add_parser("export", help="Export emails to CSV")
    exp_p.add_argument("target", help="'all', 'thread:THREAD_ID', or a specific message_id")
    exp_p.add_argument("--output", "-o", default="export.csv", help="Output filename (default: export.csv)")

    args = parser.parse_args()
    client = GmailClient()

    if args.command == "authenticate":
        client.authenticate_cli(open_browser=not args.no_browser)
    elif args.command == "send":
        client.init()
        html_content = None
        if args.html:
            p = Path(args.html)
            html_content = p.read_text(encoding="utf-8") if p.exists() else args.html
        resp = client.send_email(
            to=args.to,
            cc=args.cc,
            bcc=args.bcc,
            subject=args.subject,
            body=args.body,
            html=html_content,
            attachments=args.attach,
            reply_to_thread=args.reply,
        )
        print("Message sent:", resp)
    elif args.command == "me":
        client.init()
        print(client.me())
    elif args.command == "init":
        client.init(args.token)
        print("Token loaded.")
    elif args.command == "list":
        client.init()
        result = client.list_emails(max_results=args.max, query=args.query)
        print(f"Found {result.get('result_size_estimate', 0)} emails")
        for msg in result.get("messages", []):
            print(f"  - {msg['id']}")
    elif args.command == "get":
        client.init()
        email = client.get_parsed_email(args.message_id)
        print(f"From: {email['headers'].get('From', 'N/A')}")
        print(f"To: {email['headers'].get('To', 'N/A')}")
        print(f"Subject: {email['headers'].get('Subject', 'N/A')}")
        print(f"Date: {email['headers'].get('Date', 'N/A')}")
        print(f"\nSnippet: {email.get('snippet', 'N/A')}")
        if email.get('attachments'):
            print(f"\nAttachments ({len(email['attachments'])}):")
            for att in email['attachments']:
                print(f"  - {att['filename']} ({att.get('size', 0)} bytes) [ID: {att['attachment_id']}]")
    elif args.command == "download":
        client.init()
        if args.attachment_id:
            # Download specific attachment
            email = client.get_parsed_email(args.message_id)
            att = next((a for a in email.get('attachments', []) if a['attachment_id'] == args.attachment_id), None)
            if not att:
                print(f"Attachment {args.attachment_id} not found")
            else:
                filename = att.get('filename', 'unnamed_attachment')
                output_path = Path(args.output) / filename
                client.get_attachment(args.message_id, args.attachment_id, output_path)
                print(f"Downloaded: {output_path}")
        else:
            # Download all attachments
            paths = client.get_all_attachments(args.message_id, args.output)
            if paths:
                print(f"Downloaded {len(paths)} attachment(s) to {args.output}")
            else:
                print("No attachments found")
    elif args.command == "export":
        client.init()
        client.export_emails(target=args.target, output_file=args.output)
    else:
        parser.print_help()