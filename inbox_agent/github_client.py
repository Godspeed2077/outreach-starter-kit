"""
GitHub channel client for the Outreach Inbox Agent.

Reads:
  - GET /notifications?participating=true&since=<ts>
    Returns unread notifications on threads the operator is involved in
    (commented, opened, mentioned).
  - GET /repos/{owner}/{repo}/issues/{number}/comments
    Full comment list for an issue/PR thread we need context for.

Writes:
  - POST /repos/{owner}/{repo}/issues/{number}/comments
    Posts a reply on an issue or PR thread (works for both).
  - PATCH /notifications/threads/{id}
    Marks a notification thread as read (so it doesn't re-surface).

Auth: classic PAT loaded from .credentials/github.json.

Public API:
  poll_new_notifications() -> list[Notification]
  fetch_thread_context(notification) -> dict (full thread + latest incoming comment)
  send_reply(repo_full_name, issue_number, body) -> dict
  mark_notification_read(notification_thread_id) -> None
"""
from __future__ import annotations

import json
import pathlib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
CRED_DIR = HERE / ".credentials"
GH_CRED = CRED_DIR / "github.json"
STATE_PATH = HERE / "state.json"

API = "https://api.github.com"


@dataclass
class Notification:
    """A single GitHub notification."""
    thread_id: str
    title: str
    repo_full_name: str
    subject_type: str       # "Issue" / "PullRequest" / "Discussion" / ...
    subject_url: str        # API URL of the issue/PR itself
    latest_comment_url: str | None  # API URL of the latest comment (if applicable)
    updated_at: str
    reason: str             # "comment" / "mention" / "author" / ...


# ---------- low-level HTTP ----------

def _load_token() -> str:
    cred = json.loads(GH_CRED.read_text())
    return cred["token"]


def _request(method: str, url: str, *, body: dict | None = None) -> dict | list | None:
    headers = {
        "Authorization": f"token {_load_token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "outreach-inbox-agent",
    }
    data = json.dumps(body).encode() if body is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            if not raw:
                return None
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        raise RuntimeError(f"GitHub API {method} {url} -> {e.code}: {body_text}") from e


# ---------- state ----------

def _load_state() -> dict:
    return json.loads(STATE_PATH.read_text())


def _save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2))


# ---------- reads ----------

def poll_new_notifications() -> list[Notification]:
    """
    Return notifications on threads where the operator is participating, newer than
    last poll. Advances state.json's `github_last_check` on success.
    """
    state = _load_state()
    since = state.get("github_last_check")  # ISO 8601 string or None
    params = {"participating": "true", "all": "false"}
    if since:
        params["since"] = since
    url = API + "/notifications?" + urllib.parse.urlencode(params)
    raw = _request("GET", url) or []

    out: list[Notification] = []
    for item in raw:
        subject = item.get("subject", {}) or {}
        out.append(Notification(
            thread_id=str(item["id"]),
            title=subject.get("title", ""),
            repo_full_name=item.get("repository", {}).get("full_name", ""),
            subject_type=subject.get("type", ""),
            subject_url=subject.get("url", ""),
            latest_comment_url=subject.get("latest_comment_url"),
            updated_at=item.get("updated_at", ""),
            reason=item.get("reason", ""),
        ))

    # Bump the cursor only after a successful fetch.
    state["github_last_check"] = datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    _save_state(state)
    return out


def fetch_thread_context(n: Notification) -> dict:
    """
    Pull the issue/PR body + all comments + the latest incoming comment so the
    drafter has full context. Returns a dict the runbook prompt can consume.
    """
    subject = _request("GET", n.subject_url) or {}
    comments_url = subject.get("comments_url") or (n.subject_url + "/comments")
    comments = _request("GET", comments_url) or []

    # Latest comment by anyone other than the operator.
    me = _request("GET", API + "/user") or {}
    my_login = me.get("login", "")
    incoming = None
    for c in reversed(comments):
        if c.get("user", {}).get("login") != my_login:
            incoming = c
            break

    return {
        "thread_id": n.thread_id,
        "repo": n.repo_full_name,
        "title": n.title,
        "issue_number": subject.get("number"),
        "issue_url_html": subject.get("html_url"),
        "issue_body": subject.get("body", ""),
        "issue_author": subject.get("user", {}).get("login"),
        "comments": [
            {
                "id": c["id"],
                "author": c.get("user", {}).get("login"),
                "body": c.get("body", ""),
                "created_at": c.get("created_at"),
                "html_url": c.get("html_url"),
            }
            for c in comments
        ],
        "incoming": (
            {
                "id": incoming["id"],
                "author": incoming.get("user", {}).get("login"),
                "body": incoming.get("body", ""),
                "created_at": incoming.get("created_at"),
                "html_url": incoming.get("html_url"),
            }
            if incoming else None
        ),
        "my_login": my_login,
    }


# ---------- writes ----------

def send_reply(repo_full_name: str, issue_number: int, body: str) -> dict:
    """Post a comment on an issue or PR thread."""
    url = f"{API}/repos/{repo_full_name}/issues/{issue_number}/comments"
    return _request("POST", url, body={"body": body})


def mark_notification_read(thread_id: str) -> None:
    """Mark a notification thread as read so it doesn't re-surface."""
    _request("PATCH", f"{API}/notifications/threads/{thread_id}")


# ---------- CLI ----------

def _cli() -> None:
    import sys
    if len(sys.argv) < 2:
        print("Usage: python github_client.py whoami|poll|context THREAD_ID|send REPO ISSUE BODY")
        return
    cmd = sys.argv[1]
    if cmd == "whoami":
        me = _request("GET", API + "/user")
        print(json.dumps({"login": me.get("login"), "id": me.get("id"), "name": me.get("name")}))
    elif cmd == "poll":
        ns = poll_new_notifications()
        print(json.dumps([n.__dict__ for n in ns], indent=2))
    elif cmd == "context":
        if len(sys.argv) < 3:
            print("Need thread id")
            return
        # Build a minimal Notification by fetching the thread directly.
        info = _request("GET", f"{API}/notifications/threads/{sys.argv[2]}") or {}
        subject = info.get("subject", {})
        n = Notification(
            thread_id=str(info["id"]),
            title=subject.get("title", ""),
            repo_full_name=info.get("repository", {}).get("full_name", ""),
            subject_type=subject.get("type", ""),
            subject_url=subject.get("url", ""),
            latest_comment_url=subject.get("latest_comment_url"),
            updated_at=info.get("updated_at", ""),
            reason=info.get("reason", ""),
        )
        print(json.dumps(fetch_thread_context(n), indent=2))
    elif cmd == "send":
        if len(sys.argv) < 5:
            print("Usage: send OWNER/REPO ISSUE_NUMBER BODY")
            return
        repo, issue, body = sys.argv[2], int(sys.argv[3]), sys.argv[4]
        print(json.dumps(send_reply(repo, issue, body), indent=2))
    else:
        print("Unknown command:", cmd)


if __name__ == "__main__":
    _cli()
