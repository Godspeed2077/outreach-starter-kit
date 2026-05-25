"""
Telegram bot client for the Outreach Inbox Agent.

Two responsibilities:
  1. Push a draft to the operator with inline Send / Edit / Skip buttons.
  2. Poll for callback responses (which button they tapped) and free-text replies
     (their edited versions of drafts).

Reads bot_token + chat_id from .credentials/telegram.json. Persists the
Telegram update offset in state.json so we don't reprocess updates.

This is the reference notifier implementation. To add another approval surface
(email, Slack, Discord), build a module with the same public API: push_draft,
push_text, poll_responses. The watcher imports `telegram_client` by name today;
swap that import to wire in a different notifier.

Public API:
  push_draft(draft_id, to_person, to_email, reply_snippet, draft_body,
             bluff_status) -> telegram_message_id
  push_text(text) -> telegram_message_id
  poll_responses() -> list[Response]
"""
from __future__ import annotations

import json
import pathlib
import urllib.parse
import urllib.request
from dataclasses import dataclass

HERE = pathlib.Path(__file__).resolve().parent
CRED_DIR = HERE / ".credentials"
TG_CRED = CRED_DIR / "telegram.json"
STATE_PATH = HERE / "state.json"


@dataclass
class Response:
    """One actionable response from the operator — either a button tap or a text edit."""
    kind: str           # "callback" or "text"
    draft_id: str | None  # which draft this responds to (for callbacks; None for free text)
    action: str | None    # "send" / "edit" / "skip" for callbacks; None for text
    text: str | None      # body text for "text" kind
    chat_id: int
    update_id: int


# ---------- low-level HTTP ----------

def _load_creds() -> dict:
    return json.loads(TG_CRED.read_text())


def _api(method: str, *, params: dict | None = None, body: dict | None = None,
         timeout: int = 20) -> dict:
    """Call the Telegram Bot API. GET if no body, POST JSON if body provided."""
    creds = _load_creds()
    token = creds["bot_token"]
    url = f"https://api.telegram.org/bot{token}/{method}"
    if body is not None:
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}
        )
    else:
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.loads(r.read())
    if not resp.get("ok"):
        raise RuntimeError(f"Telegram API error on {method}: {resp}")
    return resp["result"]


# ---------- state ----------

def _load_state() -> dict:
    return json.loads(STATE_PATH.read_text())


def _save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2))


# ---------- push ----------

def _format_draft(to_person: str, to_email: str, reply_snippet: str,
                  draft_body: str, bluff_status: str) -> str:
    snippet = reply_snippet.strip()
    if len(snippet) > 400:
        snippet = snippet[:400].rstrip() + "..."
    return (
        f"<b>New reply: {to_person}</b>\n"
        f"<code>{to_email}</code>\n\n"
        f"<b>Their reply (snippet):</b>\n<i>{_escape(snippet)}</i>\n\n"
        f"<b>Draft reply:</b>\n<pre>{_escape(draft_body)}</pre>\n\n"
        f"<b>Bluff filter:</b> {bluff_status}"
    )


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def push_draft(
    draft_id: str,
    to_person: str,
    to_email: str,
    reply_snippet: str,
    draft_body: str,
    bluff_status: str,
) -> int:
    """Push a draft to the operator with Send / Edit / Skip inline buttons."""
    creds = _load_creds()
    chat_id = creds["chat_id"]
    if chat_id is None:
        raise RuntimeError("chat_id not resolved yet; run resolve_chat_id() first.")
    text = _format_draft(to_person, to_email, reply_snippet, draft_body, bluff_status)
    keyboard = {
        "inline_keyboard": [[
            {"text": "Send", "callback_data": f"send:{draft_id}"},
            {"text": "Edit", "callback_data": f"edit:{draft_id}"},
            {"text": "Skip", "callback_data": f"skip:{draft_id}"},
        ]]
    }
    result = _api("sendMessage", body={
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": keyboard,
    })
    return result["message_id"]


def push_text(text: str) -> int:
    """Push a plain text message (e.g. status pings, errors)."""
    creds = _load_creds()
    chat_id = creds["chat_id"]
    if chat_id is None:
        raise RuntimeError("chat_id not resolved yet.")
    result = _api("sendMessage", body={"chat_id": chat_id, "text": text})
    return result["message_id"]


# ---------- poll ----------

def poll_responses() -> list[Response]:
    """
    Fetch new updates from Telegram. Acks them by bumping the offset stored in
    state.json. Returns a list of Response objects ready for the watcher to act on.
    """
    state = _load_state()
    offset = state.get("telegram_update_offset", 0)
    raw = _api("getUpdates", params={"offset": offset, "timeout": 0, "limit": 50})

    responses: list[Response] = []
    max_update_id = offset - 1
    for u in raw:
        max_update_id = max(max_update_id, u["update_id"])

        cb = u.get("callback_query")
        if cb:
            data = cb.get("data", "")
            chat_id = cb["message"]["chat"]["id"]
            if ":" in data:
                action, draft_id = data.split(":", 1)
                responses.append(Response(
                    kind="callback",
                    draft_id=draft_id,
                    action=action,
                    text=None,
                    chat_id=chat_id,
                    update_id=u["update_id"],
                ))
            # Tell Telegram we handled the callback so the button stops spinning.
            try:
                _api("answerCallbackQuery", body={"callback_query_id": cb["id"]})
            except Exception:
                pass
            continue

        msg = u.get("message")
        if msg and msg.get("text"):
            responses.append(Response(
                kind="text",
                draft_id=None,
                action=None,
                text=msg["text"],
                chat_id=msg["chat"]["id"],
                update_id=u["update_id"],
            ))

    if max_update_id >= offset:
        state["telegram_update_offset"] = max_update_id + 1
        _save_state(state)
    return responses


def resolve_chat_id() -> int | None:
    """One-time helper: read the first message sent to the bot to learn chat_id."""
    creds = _load_creds()
    if creds.get("chat_id"):
        return creds["chat_id"]
    raw = _api("getUpdates", params={"limit": 20, "timeout": 0})
    for u in raw:
        msg = u.get("message") or u.get("edited_message")
        if msg and msg.get("chat", {}).get("id"):
            chat_id = msg["chat"]["id"]
            creds["chat_id"] = chat_id
            TG_CRED.write_text(json.dumps(creds, indent=2))
            return chat_id
    return None



def push_manual_send_request(
    draft_id: str,
    to_person: str,
    destination_url: str,
    draft_body: str,
    notes: str = "",
) -> int:
    """Tier 2 queue-and-notify: push a draft that the operator must post manually.

    The destination_url is where they should post (the candidate's HN thread, IH
    forum, X DM page, etc). The body is the draft to copy-paste. The operator
    submits manually, then taps Confirm Sent below to trigger logging.
    """
    creds = _load_creds()
    chat_id = creds["chat_id"]
    if chat_id is None:
        raise RuntimeError("chat_id not resolved yet.")

    note_block = f"\n\n<b>Notes:</b> {_escape(notes)}" if notes else ""
    text_body = (
        f"<b>Manual send needed: {to_person}</b>\n"
        f"<b>Post here:</b> <code>{_escape(destination_url)}</code>\n\n"
        f"<b>Draft body (copy-paste):</b>\n<pre>{_escape(draft_body)}</pre>"
        + note_block
        + "\n\nAfter you post, tap Confirm Sent to log it."
    )

    keyboard = {
        "inline_keyboard": [[
            {"text": "Confirm Sent", "callback_data": f"send:{draft_id}"},
            {"text": "Skip", "callback_data": f"skip:{draft_id}"},
        ]]
    }
    result = _api("sendMessage", body={
        "chat_id": chat_id,
        "text": text_body,
        "parse_mode": "HTML",
        "reply_markup": keyboard,
    })
    return result["message_id"]


# ---------- CLI ----------

def _cli() -> None:
    import sys
    if len(sys.argv) < 2:
        print("Usage: python telegram_client.py {resolve|hello|poll}")
        return
    cmd = sys.argv[1]
    if cmd == "resolve":
        cid = resolve_chat_id()
        print("chat_id:", cid)
    elif cmd == "hello":
        msg_id = push_text("Inbox agent reporting in — Telegram client is wired.")
        print("sent message id:", msg_id)
    elif cmd == "poll":
        resps = poll_responses()
        print(f"{len(resps)} new response(s)")
        for r in resps:
            print(" ", r)
    else:
        print(f"Unknown command: {cmd}")


if __name__ == "__main__":
    _cli()
