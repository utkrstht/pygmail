"""
Usage:
uvicorn backend:app
"""
import os
import json
import secrets
import base64
import time
import datetime
from collections import deque
import threading
from typing import List, Optional, Union
import traceback

from fastapi import FastAPI, Request, HTTPException, Form, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from jose import JWTError, jwt
from pathlib import Path
from cryptography.fernet import Fernet
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

CLIENT_SECRETS_FILE = os.environ.get("CLIENT_SECRETS_FILE", "credentials.json")
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]
JWT_ALGORITHM = "HS256"
TOKEN_STORE_DIR = os.environ.get("TOKEN_STORE_DIR", "./tokens")
SECRETS_FILE = os.path.join(TOKEN_STORE_DIR, ".backend_secrets")

def _load_or_create_secrets():
    if os.path.exists(SECRETS_FILE):
        with open(SECRETS_FILE, "r") as f:
            return json.load(f)
    jwt_secret = secrets.token_urlsafe(32)
    fernet_key = Fernet.generate_key().decode()
    os.makedirs(os.path.dirname(SECRETS_FILE), exist_ok=True)
    data = {"jwt_secret": jwt_secret, "fernet_key": fernet_key}
    with open(SECRETS_FILE, "w") as f:
        json.dump(data, f)
    return data

_secrets = _load_or_create_secrets()
JWT_SECRET = os.environ.get("JWT_SECRET") or _secrets["jwt_secret"]
FERNET_KEY = (os.environ.get("FERNET_KEY") or _secrets["fernet_key"]).encode()
fernet = Fernet(FERNET_KEY)

os.makedirs(TOKEN_STORE_DIR, exist_ok=True)

app = FastAPI()
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

class ExchangeRequest(BaseModel):
    code: str
    state: Optional[str] = None
    allowed_ips: Optional[List[str]] = None


def encrypt_token(token_json: dict) -> bytes:
    return fernet.encrypt(json.dumps(token_json).encode())


def decrypt_token(data: bytes) -> dict:
    return json.loads(fernet.decrypt(data).decode())


def save_token(user_id: str, token_json: dict):
    path = os.path.join(TOKEN_STORE_DIR, f"{user_id}.token")
    with open(path, "wb") as f:
        f.write(encrypt_token(token_json))


def load_token(user_id: str) -> dict:
    path = os.path.join(TOKEN_STORE_DIR, f"{user_id}.token")
    if not os.path.exists(path):
        raise HTTPException(401, "Token not found for user")
    with open(path, "rb") as f:
        return decrypt_token(f.read())


def make_jwt(user_id: str, allowed_ips: Optional[List[str]] = None, expires_days: int = 365) -> str:
    exp_ts = int((datetime.datetime.utcnow() + datetime.timedelta(days=expires_days)).timestamp())
    payload = {"sub": user_id, "exp": exp_ts}
    if allowed_ips:
        payload["allowed_ips"] = allowed_ips
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_jwt(token: str, client_ip: Optional[str] = None) -> tuple:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload["sub"]
        allowed_ips = payload.get("allowed_ips")

        if allowed_ips and client_ip:
            if client_ip not in allowed_ips:
                raise HTTPException(403, f"Access denied: IP {client_ip} not in allowed list")

        return user_id, allowed_ips
    except JWTError:
        raise HTTPException(401, "Invalid session token")


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    return request.client.host if request.client else "unknown"


MAX_EMAILS = 10
WINDOW_SECONDS = 60
MAX_ATTACHMENTS = 10
ATTACHMENT_WINDOW_SECONDS = 60
RATE_LIMIT_STORE: dict = {}
ATTACHMENT_RATE_LIMIT_STORE: dict = {}
RATE_LIMIT_LOCK = threading.Lock()
ATTACHMENT_RATE_LIMIT_LOCK = threading.Lock()


def check_rate(user_id: str):
    now = time.time()
    with RATE_LIMIT_LOCK:
        dq = RATE_LIMIT_STORE.get(user_id)
        if dq is None:
            dq = deque()
            RATE_LIMIT_STORE[user_id] = dq
        while dq and now - dq[0] >= WINDOW_SECONDS:
            dq.popleft()
        if len(dq) >= MAX_EMAILS:
            retry_after = int(WINDOW_SECONDS - (now - dq[0])) + 1
            headers = {"Retry-After": str(retry_after)}
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: max {MAX_EMAILS} emails per {WINDOW_SECONDS} seconds",
                headers=headers,
            )
        dq.append(now)

def check_attachment_rate(user_id: str):
    now = time.time()
    with ATTACHMENT_RATE_LIMIT_LOCK:
        dq = ATTACHMENT_RATE_LIMIT_STORE.get(user_id)
        if dq is None:
            dq = deque()
            ATTACHMENT_RATE_LIMIT_STORE[user_id] = dq
        while dq and now - dq[0] >= ATTACHMENT_WINDOW_SECONDS:
            dq.popleft()
        if len(dq) >= MAX_ATTACHMENTS:
            retry_after = int(ATTACHMENT_WINDOW_SECONDS - (now - dq[0])) + 1
            headers = {"Retry-After": str(retry_after)}
            raise HTTPException(
                status_code=429,
                detail=f"Attachment rate limit exceeded: max {MAX_ATTACHMENTS} downloads per minute",
                headers=headers,
            )
        dq.append(now)

def parse_email_body(message: dict) -> dict:
    result = {
        "id": message.get("id"),
        "thread_id": message.get("threadId"),
        "snippet": message.get("snippet"),
        "headers": {},
        "body_plain": "",
        "body_html": "",
        "attachments": []
    }
    
    # Parse headers
    headers = message.get("payload", {}).get("headers", [])
    for header in headers:
        name = header.get("name")
        if name in ["From", "To", "Subject", "Date", "Cc", "Bcc"]:
            result["headers"][name] = header.get("value")
    
    # Parse body
    def parse_parts(parts):
        for part in parts:
            mime_type = part.get("mimeType")
            body = part.get("body", {})
            
            if mime_type == "text/plain":
                data = body.get("data")
                if data:
                    result["body_plain"] += base64.urlsafe_b64decode(data).decode("utf-8")
            elif mime_type == "text/html":
                data = body.get("data")
                if data:
                    result["body_html"] += base64.urlsafe_b64decode(data).decode("utf-8")
            elif "multipart" in mime_type:
                sub_parts = part.get("parts", [])
                parse_parts(sub_parts)
            elif body.get("attachmentId"):
                result["attachments"].append({
                    "filename": part.get("filename"),
                    "mime_type": mime_type,
                    "attachment_id": body.get("attachmentId"),
                    "size": body.get("size")
                })
    
    payload = message.get("payload", {})
    if "parts" in payload:
        parse_parts(payload["parts"])
    else:
        # Single part message
        body = payload.get("body", {})
        data = body.get("data")
        if data:
            mime_type = payload.get("mimeType")
            decoded = base64.urlsafe_b64decode(data).decode("utf-8")
            if mime_type == "text/html":
                result["body_html"] = decoded
            else:
                result["body_plain"] = decoded
    
    return result

OAUTH_STATE = {}
OAUTH_STATE_TIMEOUT = 600  # 10 minutes

def _prune_oauth_state():
    now = time.time()
    expired = [s for s, v in OAUTH_STATE.items() if now - v.get("timestamp", 0) > OAUTH_STATE_TIMEOUT]
    for s in expired:
        OAUTH_STATE.pop(s, None)

@app.get("/authorize")
def authorize():
    _prune_oauth_state()
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES, redirect_uri="http://127.0.0.1:8080/"
    )
    auth_url, state = flow.authorization_url(
        prompt="consent", access_type="offline", include_granted_scopes="true"
    )
    OAUTH_STATE[state] = {
        "timestamp": time.time(),
        "code_verifier": flow.code_verifier
    }
    return {"auth_url": auth_url, "state": state}


@app.post("/exchange_code")
def exchange_code(req: ExchangeRequest):
    if not req.state or req.state not in OAUTH_STATE:
        raise HTTPException(400, "Invalid or missing state")
    oauth_data = OAUTH_STATE.pop(req.state, None)
    code_verifier = oauth_data.get("code_verifier") if oauth_data else None

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES, redirect_uri="http://127.0.0.1:8080/"
    )
    flow.code_verifier = code_verifier
    flow.fetch_token(code=req.code)
    creds = flow.credentials
    token_json = json.loads(creds.to_json())
    user_id = secrets.token_urlsafe(16)
    save_token(user_id, token_json)
    session_token = make_jwt(user_id, allowed_ips=req.allowed_ips)
    return JSONResponse(content={"session_token": session_token})

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = [
        {
            "type": err["type"],
            "loc": err["loc"],
            "msg": err["msg"]
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"detail": errors}
    )

@app.post("/send_email")
async def send_email(
    request: Request,
    to: List[str] = Form(...),  
    cc: List[str] = Form(default=[]),
    bcc: List[str] = Form(default=[]),  
    subject: str = Form(...),
    body: Optional[str] = Form(None),
    html: Optional[str] = Form(None),
    reply: Optional[str] = Form(None),
    attachments: List[UploadFile] = File(default=[])
):
    # --- auth ---
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Missing session token")
    session_token = auth_header.split(" ")[1]
    client_ip = get_client_ip(request)
    user_id, _ = verify_jwt(session_token, client_ip)

    # --- rate limit ---
    check_rate(user_id)

    # --- credentials ---
    token_json = load_token(user_id)
    creds = Credentials.from_authorized_user_info(token_json, SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(GoogleRequest())
            save_token(user_id, json.loads(creds.to_json()))
        except Exception as e:
            raise HTTPException(401, f"Token refresh failed: {str(e)}")
    service = build("gmail", "v1", credentials=creds)

    # --- hi how's your day going ---
    to_list = to
    cc_list = cc
    bcc_list = bcc

    # --- build email ---
    if attachments:
        root = MIMEMultipart("mixed")
    elif html:
        root = MIMEMultipart("alternative")
    else:
        root = MIMEMultipart()

    root["To"] = ", ".join(to_list)
    if cc_list:
        root["Cc"] = ", ".join(cc_list)
    if bcc_list:
        root["Bcc"] = ", ".join(bcc_list)
    root["Subject"] = subject

    if html or body:
        if html and body:
            alt = MIMEMultipart("alternative")
            alt.attach(MIMEText(body, "plain"))
            alt.attach(MIMEText(html, "html"))
            root.attach(alt)
        elif html:
            root.attach(MIMEText(html, "html"))
        else:
            root.attach(MIMEText(body, "plain"))

    if attachments:
        for file in attachments:
            content = await file.read()
            part = MIMEBase("application", "octet-stream")
            part.set_payload(content)
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{file.filename}"')
            root.attach(part)

    raw = base64.urlsafe_b64encode(root.as_bytes()).decode()
    
    send_body = {"raw": raw}
    if reply:
        send_body["threadId"] = reply
    
    result = service.users().messages().send(userId="me", body=send_body).execute()
    return {"message_id": result["id"], "thread_id": result.get("threadId")}

@app.get("/me")
def me(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Missing session token")
    session_token = auth_header.split(" ", 1)[1]
    client_ip = get_client_ip(request)
    user_id, _ = verify_jwt(session_token, client_ip)

    token_json = load_token(user_id)
    creds = Credentials.from_authorized_user_info(token_json, SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(GoogleRequest())
            save_token(user_id, json.loads(creds.to_json()))
        except Exception as e:
            raise HTTPException(401, f"Token refresh failed: {str(e)}")

    oauth2 = build("oauth2", "v2", credentials=creds)
    user_info = oauth2.userinfo().get().execute()
    return {"user": user_info}

@app.get("/list_emails")
def list_emails(
    request: Request,
    max_results: int = 10,
    query: Optional[str] = None,
    page_token: Optional[str] = None
):
    # --- auth ---
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Missing session token")
    session_token = auth_header.split(" ")[1]
    client_ip = get_client_ip(request)
    user_id, _ = verify_jwt(session_token, client_ip)

    # --- credentials ---
    token_json = load_token(user_id)
    creds = Credentials.from_authorized_user_info(token_json, SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(GoogleRequest())
            save_token(user_id, json.loads(creds.to_json()))
        except Exception as e:
            raise HTTPException(401, f"Token refresh failed: {str(e)}")
    
    service = build("gmail", "v1", credentials=creds)
    
    # List messages
    max_results = min(max_results, 100)
    params = {"userId": "me", "maxResults": max_results}
    if query:
        params["q"] = query
    if page_token:
        params["pageToken"] = page_token
    
    results = service.users().messages().list(**params).execute()
    messages = results.get("messages", [])
    
    return {
        "messages": messages,
        "next_page_token": results.get("nextPageToken"),
        "result_size_estimate": results.get("resultSizeEstimate")
    }

@app.get("/get_email/{message_id}")
def get_email(request: Request, message_id: str, format: str = "full"):
    # --- auth ---
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Missing session token")
    session_token = auth_header.split(" ")[1]
    client_ip = get_client_ip(request)
    user_id, _ = verify_jwt(session_token, client_ip)

    # --- credentials ---
    token_json = load_token(user_id)
    creds = Credentials.from_authorized_user_info(token_json, SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(GoogleRequest())
            save_token(user_id, json.loads(creds.to_json()))
        except Exception as e:
            raise HTTPException(401, f"Token refresh failed: {str(e)}")
    
    service = build("gmail", "v1", credentials=creds)
    
    # Get message
    message = service.users().messages().get(
        userId="me", 
        id=message_id,
        format=format
    ).execute()
    
    return message


@app.get("/get_parsed_email/{message_id}")
def get_parsed_email(request: Request, message_id: str):
    # --- auth ---
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Missing session token")
    session_token = auth_header.split(" ")[1]
    client_ip = get_client_ip(request)
    user_id, _ = verify_jwt(session_token, client_ip)

    # --- credentials ---
    token_json = load_token(user_id)
    creds = Credentials.from_authorized_user_info(token_json, SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(GoogleRequest())
            save_token(user_id, json.loads(creds.to_json()))
        except Exception as e:
            raise HTTPException(401, f"Token refresh failed: {str(e)}")
    
    service = build("gmail", "v1", credentials=creds)
    
    # Get message
    message = service.users().messages().get(
        userId="me", 
        id=message_id,
        format="full"
    ).execute()
    
    return parse_email_body(message)


@app.get("/get_attachment/{message_id}/{attachment_id}")
def get_attachment(request: Request, message_id: str, attachment_id: str):
    # --- auth ---
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Missing session token")
    session_token = auth_header.split(" ")[1]
    client_ip = get_client_ip(request)
    user_id, _ = verify_jwt(session_token, client_ip)

    # --- rate limit for attachments ---
    check_attachment_rate(user_id)

    # --- credentials ---
    token_json = load_token(user_id)
    creds = Credentials.from_authorized_user_info(token_json, SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(GoogleRequest())
            save_token(user_id, json.loads(creds.to_json()))
        except Exception as e:
            raise HTTPException(401, f"Token refresh failed: {str(e)}")
    
    service = build("gmail", "v1", credentials=creds)
    
    # Get attachment
    attachment = service.users().messages().attachments().get(
        userId="me",
        messageId=message_id,
        id=attachment_id
    ).execute()
    
    # Return base64 encoded data
    return {
        "attachment_id": attachment_id,
        "data": attachment["data"],
        "size": attachment.get("size", 0)
    }