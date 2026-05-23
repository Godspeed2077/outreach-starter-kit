"""
dev.to channel client for the Outreach Inbox Agent.

A note up front: dev.to's public API is read-rich but write-poor. The Forem
API at dev.to/api supports:
  - GET /articles - search/list articles by tag, username, etc.
  - GET /articles/me (auth) - my own articles
  - GET /comments?a_id={id} - all comments on an article
  - POST /articles (auth) - create an article
  - POST /comments (auth) - create a comment  [supported, but rate-limited]

For inbox-agent purposes we need "is someone replying to a comment I left on
SOMEONE ELSE'S article?" — and there is no clean notifications endpoint for
that. Workaround: track the article IDs the operator has commented on (from the
Sent Log) and poll their full comment trees for new replies to the operator's
specific comments.

This v1 implementation:
  - identifies the operator's dev.to user ID via /users/me on first call.
  - polls a configured list of article IDs (set by the runbook from sent-log
    entries) for new replies to the operator's comments.
  - posts replies via POST /api/comments (best-effort; if dev.to rejects it
    we fall back to Telegram "go reply manually" mode).

Credentials in .credentials/devto.json:
  {"api_key": "..."}

Article-watch list lives in state.json under "devto_watched_articles" — a
dict mapping article_id -> {"last_seen_comment_id": int}.

Public API:
  poll_new_replies() -> list[DevtoReply]
  send_reply(parent_comment_id, body) -> dict | "manual"
  identify_me() -> dict
"""
from __future__ import annotations

import json
import pathlib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

HERE = pathlib.Path(__file__).resolve().parent
CRED_DIR = HERE / ".credentials"
DEV_CRED = CRED_DIR / "devto.json"
STATE_PATH = HERE / "state.json"

API = "https://dev.to/api"


@dataclass
class DevtoReply:
    """A new reply on an article we're watching that responds to the operator's comment."""
    article_id: int
    article_title: str
    article_url: str
    incoming_comment_id: str
    incoming_author: str
    incoming_body: str
    parent_comment_id: str   # the operator's comment that they replied to
    parent_body: str


def _load_creds() -> dict:
    return json.loads(DEV_CRED.read_text())


def _request(method: str, path: str, *, body: dict | None = None) -> dict | list | None:
    url = API + path
    headers = {
        "api-key": _load_creds()["api_key"],
        "User-Agent": "outreach-inbox-agent/1.0",
        "Accept": "application/vnd.forem.api-v1+json",
    }
    data = json.dumps(body).encode() if body is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        raise RuntimeError(f"dev.to API {method} {path} -> {e.code}: {body_text}") from e


def _load_state() -> dict:
    return json.loads(STATE_PATH.read_text())


def _save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2))


def identify_me() -> dict:
    """Look up the operator's dev.to user info. Cached into state.json."""
    state = _load_state()
    if state.get("devto_me"):
        return state["devto_me"]
    me = _request("GET", "/users/me") or {}
    # Trim to what we need.
    info = {
        "id": me.get("id"),
        "username": me.get("username"),
        "name": me.get("name"),
    }
    state["devto_me"] = info
    _save_state(state)
    return info


def add_watched_article(article_id: int, my_comment_id: str | None = None) -> None:
    """Register an article whose comment tree should be polled each tick."""
    state = _load_state()
    watched = state.setdefault("devto_watched_articles", {})
    entry = watched.setdefault(str(article_id), {"last_seen_comment_id": None, "my_comment_ids": []})
    if my_comment_id and my_comment_id not in entry["my_comment_ids"]:
        entry["my_comment_ids"].append(my_comment_id)
    _save_state(state)


def poll_new_replies() -> list[DevtoReply]:
    """For each watched article, find replies to the operator's comments since last poll."""
    state = _load_state()
    watched = state.get("devto_watched_articles", {})
    if not watched:
        return []
    me = identify_me()
    my_username = me.get("username", "")

    out: list[DevtoReply] = []
    for article_id_str, entry in list(watched.items()):
        article_id = int(article_id_str)
        comments = _request("GET", f"/comments?a_id={article_id}") or []
        # The dev.to comments endpoint returns a tree of root comments; each has
        # a "children" list. Flatten and look for ones authored by someone other
        # than the operator whose parent is a comment the operator wrote.
        def walk(nodes, parent_chain):
            for c in nodes:
                user = (c.get("user") or {}).get("username")
                cid = str(c.get("id_code") or c.get("id"))
                parent_id = parent_chain[-1] if parent_chain else None
                yield {
                    "id": cid,
                    "author": user,
                    "body": c.get("body_html", "") or c.get("body_markdown", ""),
                    "parent": parent_id,
                }
                yield from walk(c.get("children", []) or [], parent_chain + [cid])

        all_comments = list(walk(comments, []))

        # Identify the operator's own comments on this article.
        my_comment_ids = {c["id"] for c in all_comments if c["author"] == my_username}
        my_comment_ids.update(entry.get("my_comment_ids", []))
        # Update the saved set.
        entry["my_comment_ids"] = sorted(my_comment_ids)

        last_seen = entry.get("last_seen_comment_id")
        latest_seen = last_seen
        for c in all_comments:
            if c["author"] == my_username:
                continue
            if c["parent"] in my_comment_ids and (last_seen is None or c["id"] > last_seen):
                # This is a new reply to the operator.
                parent = next((p for p in all_comments if p["id"] == c["parent"]), None)
                out.append(DevtoReply(
                    article_id=article_id,
                    article_title="",  # filled below
                    article_url="",
                    incoming_comment_id=c["id"],
                    incoming_author=c["author"],
                    incoming_body=c["body"],
                    parent_comment_id=c["parent"],
                    parent_body=parent["body"] if parent else "",
                ))
            if latest_seen is None or c["id"] > latest_seen:
                latest_seen = c["id"]
        entry["last_seen_comment_id"] = latest_seen

    _save_state(state)
    return out


def send_reply(parent_comment_id: str, body: str) -> dict | str:
    """
    Attempt to post a comment reply. dev.to's create-comment endpoint may not
    be enabled for all accounts; if we get a 4xx/501, fall back to "manual".
    """
    try:
        return _request("POST", "/comments", body={
            "comment": {
                "body_markdown": body,
                "parent_id": parent_comment_id,
            }
        }) or {}
    except RuntimeError as e:
        if any(code in str(e) for code in ("400", "401", "403", "404", "501")):
            return "manual"
        raise


def _cli() -> None:
    import sys
    if len(sys.argv) < 2:
        print("Usage: python devto_client.py whoami|watch ARTICLE_ID|poll|send PARENT_ID BODY")
        return
    cmd = sys.argv[1]
    if cmd == "whoami":
        print(json.dumps(identify_me(), indent=2))
    elif cmd == "watch":
        if len(sys.argv) < 3:
            print("Need article id")
            return
        add_watched_article(int(sys.argv[2]))
        print("watching", sys.argv[2])
    elif cmd == "poll":
        print(json.dumps([r.__dict__ for r in poll_new_replies()], indent=2))
    elif cmd == "send":
        if len(sys.argv) < 4:
            print("Usage: send PARENT_COMMENT_ID BODY")
            return
        print(send_reply(sys.argv[2], sys.argv[3]))
    else:
        print("Unknown command:", cmd)


if __name__ == "__main__":
    _cli()
