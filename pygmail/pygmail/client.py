import threading
import webbrowser
from typing import List, Optional, Union
from urllib import parse
import http.server
import requests
from pathlib import Path
import time
import argparse

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
    def send_email(self, to: Union[str, List[str]], subject: str, body: Optional[str] = None, html: Optional[str] = None, cc: Optional[Union[str, List[str]]] = None, bcc: Optional[Union[str, List[str]]] = None, attachments: Optional[List[Union[str, Path]]] = None) -> dict:
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

    sub.add_parser("me", help="Show authenticated user info")
    init_p = sub.add_parser("init", help="Load session token from a file or paste token")
    init_p.add_argument("--token", help="Session token string (if not provided, loads default session file)")

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
        )
        print("Message sent:", resp)
    elif args.command == "me":
        client.init()
        print(client.me())
    elif args.command == "init":
        client.init(args.token)
        print("Token loaded.")
    else:
        parser.print_help()