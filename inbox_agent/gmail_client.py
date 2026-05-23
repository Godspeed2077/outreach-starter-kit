"""
Gmail send helper for the Outreach Inbox Agent.

One-time authorize flow:
    python gmail_client.py authorize

After that, send replies with:
    from gmail_client import send_reply
    send_reply(to='someone@example.com',
               subject='Re: ...',
               body='...',
               thread_id='...',
               in_reply_to_message_id='<...@mail.gmail.com>')

OAuth credentials JSON lives at .credentials/gmail_oauth.json.
The refresh token cache lives at .credentials/gmail_token.json.
Neither file should ever be shared or committed.

Reads on Gmail (search, get thread) go through the MCP connector — only
sends use this module's OAuth credentials.
"""
from __future__ import annotations

import base64
import json
import pathlib
import sys
from email.mime.text import MIMEText
from email.utils import make_msgid

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

HERE = pathlib.Path(__file__).resolve().parent
CRED_DIR = HERE / ".credentials"
OAUTH_JSON = CRED_DIR / "gmail_oauth.json"
TOKEN_JSON = CRED_DIR / "gmail_token.json"

# gmail.send is the minimum scope to send mail. We intentionally do not request
# gmail.readonly — Gmail reads go through the MCP connector, not this module.
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def _load_or_refresh_credentials() -> Credentials:
    """Return a valid Credentials object, refreshing the token if needed."""
    if not TOKEN_JSON.exists():
        raise RuntimeError(
            "No gmail_token.json yet. Run `python gmail_client.py authorize` "
            "to do the one-time OAuth flow."
        )
    creds = Credentials.from_authorized_user_file(str(TOKEN_JSON), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            TOKEN_JSON.write_text(creds.to_json())
        else:
            raise RuntimeError(
                "Stored Gmail credentials are invalid and cannot refresh. "
                "Re-run `python gmail_client.py authorize`."
            )
    return creds


def authorize() -> None:
    """Run the one-time OAuth flow. Opens the user's browser."""
    if not OAUTH_JSON.exists():
        raise FileNotFoundError(f"Missing {OAUTH_JSON}")
    flow = InstalledAppFlow.from_client_secrets_file(str(OAUTH_JSON), SCOPES)
    # port=0 picks an open port; redirect URI must be http://localhost in
    # Google Cloud Console (we already set this when creating the credential).
    creds = flow.run_local_server(port=0, open_browser=True)
    TOKEN_JSON.write_text(creds.to_json())
    print(f"Authorize OK. Token cached at {TOKEN_JSON}")


def _build_service():
    creds = _load_or_refresh_credentials()
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def send_reply(
    *,
    to: str,
    subject: str,
    body: str,
    thread_id: str | None = None,
    in_reply_to_message_id: str | None = None,
    references: str | None = None,
    from_addr: str | None = None,
) -> dict:
    """
    Send an email reply via Gmail API.

    `thread_id` is Gmail's thread ID (the same one MCP `search_threads` returns).
    `in_reply_to_message_id` should be the original message's Message-ID header
    (with angle brackets), which makes Gmail (and most clients) thread the reply
    correctly. `references` should be the chain of prior Message-IDs.

    Returns the Gmail API response dict (contains the sent message id + threadId).
    """
    mime = MIMEText(body, "plain", "utf-8")
    mime["To"] = to
    mime["Subject"] = subject
    if from_addr:
        mime["From"] = from_addr
    if in_reply_to_message_id:
        mime["In-Reply-To"] = in_reply_to_message_id
        mime["References"] = references or in_reply_to_message_id
    # Give the outgoing message its own Message-ID so future replies thread.
    mime["Message-ID"] = make_msgid(domain="gmail.com")

    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
    payload: dict = {"raw": raw}
    if thread_id:
        payload["threadId"] = thread_id

    service = _build_service()
    return service.users().messages().send(userId="me", body=payload).execute()


def _cli() -> None:
    if len(sys.argv) < 2:
        print("Usage: python gmail_client.py {authorize|send-test EMAIL}")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "authorize":
        authorize()
    elif cmd == "send-test":
        if len(sys.argv) < 3:
            print("Usage: python gmail_client.py send-test EMAIL")
            sys.exit(1)
        to = sys.argv[2]
        resp = send_reply(
            to=to,
            subject="Outreach Inbox Agent — Gmail send test",
            body=(
                "If you got this, the OAuth-based send path works.\n\n"
                "This is a one-off test from the inbox agent. Reply not needed.\n"
            ),
        )
        print("Send response:", json.dumps(resp, indent=2))
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    _cli()
