"""Outreach Inbox Agent watcher — multi-channel deterministic post-processor."""
from __future__ import annotations

import json
import pathlib
import sys
import traceback
from datetime import datetime, timezone

import telegram_client

HERE = pathlib.Path(__file__).resolve().parent
PENDING_PATH = HERE / "pending_drafts.json"
ACTION_LOG_PATH = HERE / "action_log.jsonl"

SUPPORTED_CHANNELS = ("gmail", "github", "devto", "manual")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_pending() -> dict:
    if not PENDING_PATH.exists():
        return {"pending": []}
    return json.loads(PENDING_PATH.read_text())


def _save_pending(pending: dict) -> None:
    PENDING_PATH.write_text(json.dumps(pending, indent=2))


def _log_action(entry: dict) -> None:
    entry = {"ts": _now_iso(), **entry}
    with ACTION_LOG_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def _find_draft(pending: list[dict], draft_id: str) -> dict | None:
    for d in pending:
        if d.get("draft_id") == draft_id:
            return d
    return None


def _dispatch_send(draft: dict, body: str) -> dict:
    channel = draft.get("channel", "gmail")
    if channel == "gmail":
        return _send_gmail(draft, body)
    if channel == "github":
        return _send_github(draft, body)
    if channel == "devto":
        return _send_devto(draft, body)
    if channel == "manual":
        return _send_manual(draft, body)
    raise RuntimeError("Unknown channel: " + channel)


def _send_manual(draft: dict, body: str) -> dict:
    """Tier 2: the operator already posted manually. This 'send' is log-only."""
    p = draft.get("send_params", {})
    return {
        "ok": True,
        "channel": "manual",
        "destination_url": p.get("destination_url"),
        "response": "operator_confirmed_manual_send",
    }


def _send_gmail(draft: dict, body: str) -> dict:
    import gmail_client
    p = draft.get("send_params", {})
    resp = gmail_client.send_reply(
        to=p["to_email"],
        subject=draft.get("subject", ""),
        body=body,
        thread_id=p.get("gmail_thread_id"),
        in_reply_to_message_id=p.get("gmail_in_reply_to_message_id"),
        references=p.get("gmail_references"),
    )
    return {"ok": True, "channel": "gmail", "response": resp}


def _send_github(draft: dict, body: str) -> dict:
    import github_client
    p = draft.get("send_params", {})
    resp = github_client.send_reply(
        repo_full_name=p["repo_full_name"],
        issue_number=int(p["issue_number"]),
        body=body,
    )
    if p.get("notification_thread_id"):
        try:
            github_client.mark_notification_read(p["notification_thread_id"])
        except Exception:
            pass
    return {"ok": True, "channel": "github", "response": resp}


def _send_devto(draft: dict, body: str) -> dict:
    import devto_client
    p = draft.get("send_params", {})
    resp = devto_client.send_reply(parent_comment_id=p["parent_comment_id"], body=body)
    if resp == "manual":
        telegram_client.push_text(
            "dev.to comment send refused by API. Post manually:\n\n" + body
            + "\n\nParent: " + str(p.get("parent_comment_id"))
        )
        return {"ok": False, "channel": "devto", "fallback": "manual_paste"}
    return {"ok": True, "channel": "devto", "response": resp}


def process_telegram_responses() -> dict:
    pending_doc = _load_pending()
    pending_list = pending_doc.get("pending", [])

    try:
        responses = telegram_client.poll_responses()
    except Exception as e:
        return {
            "ok": False,
            "stage": "poll_telegram",
            "error": type(e).__name__ + ": " + str(e),
            "trace": traceback.format_exc(),
        }

    summary = {
        "ok": True,
        "now": _now_iso(),
        "responses_processed": 0,
        "sent": [],
        "skipped": [],
        "awaiting_edit_marked": [],
        "edits_sent": [],
        "noop_text": [],
        "errors": [],
    }

    for r in responses:
        summary["responses_processed"] += 1

        if r.kind == "callback":
            draft = _find_draft(pending_list, r.draft_id or "")
            if not draft:
                summary["errors"].append({
                    "reason": "unknown_draft_id",
                    "draft_id": r.draft_id,
                    "action": r.action,
                })
                continue

            if r.action == "send":
                try:
                    result = _dispatch_send(draft, draft["draft_body"])
                    _log_action({
                        "kind": "send",
                        "channel": draft.get("channel"),
                        "draft_id": draft["draft_id"],
                        "person": draft["person"],
                        "result": result,
                    })
                    pending_list.remove(draft)
                    telegram_client.push_text(
                        "Sent (" + str(draft.get("channel")) + ") to " + draft["person"] + "."
                    )
                    summary["sent"].append({
                        "draft_id": draft["draft_id"],
                        "person": draft["person"],
                        "channel": draft.get("channel"),
                    })
                except Exception as e:
                    summary["errors"].append({
                        "reason": "send_failed",
                        "draft_id": draft["draft_id"],
                        "channel": draft.get("channel"),
                        "error": type(e).__name__ + ": " + str(e),
                    })
                    try:
                        telegram_client.push_text(
                            "Send FAILED (" + str(draft.get("channel")) + ") for "
                            + draft["person"] + ": " + str(e)
                        )
                    except Exception:
                        pass

            elif r.action == "skip":
                _log_action({
                    "kind": "skip",
                    "channel": draft.get("channel"),
                    "draft_id": draft["draft_id"],
                    "person": draft["person"],
                })
                pending_list.remove(draft)
                summary["skipped"].append({"draft_id": draft["draft_id"]})

            elif r.action == "edit":
                draft["status"] = "awaiting_edit"
                draft["edit_requested_at"] = _now_iso()
                summary["awaiting_edit_marked"].append({
                    "draft_id": draft["draft_id"],
                    "person": draft["person"],
                })
                try:
                    telegram_client.push_text(
                        "Edit mode on for " + draft["person"]
                        + ". Reply here with your edited body; I will send it as-is."
                    )
                except Exception:
                    pass

        elif r.kind == "text":
            awaiting = [d for d in pending_list if d.get("status") == "awaiting_edit"]
            if not awaiting:
                summary["noop_text"].append({"text": (r.text or "")[:120]})
                continue
            awaiting.sort(key=lambda d: d.get("edit_requested_at", ""))
            target = awaiting[-1]
            try:
                result = _dispatch_send(target, r.text or "")
                _log_action({
                    "kind": "send_edited",
                    "channel": target.get("channel"),
                    "draft_id": target["draft_id"],
                    "person": target["person"],
                    "edited_body": r.text,
                    "result": result,
                })
                pending_list.remove(target)
                telegram_client.push_text(
                    "Sent edited reply (" + str(target.get("channel")) + ") to "
                    + target["person"] + "."
                )
                summary["edits_sent"].append({
                    "draft_id": target["draft_id"],
                    "person": target["person"],
                    "channel": target.get("channel"),
                })
            except Exception as e:
                summary["errors"].append({
                    "reason": "edit_send_failed",
                    "draft_id": target["draft_id"],
                    "error": type(e).__name__ + ": " + str(e),
                })

    pending_doc["pending"] = pending_list
    _save_pending(pending_doc)
    return summary


def append_pending_draft(draft: dict) -> None:
    if draft.get("channel") not in SUPPORTED_CHANNELS:
        raise ValueError("channel must be one of " + str(SUPPORTED_CHANNELS))
    pending_doc = _load_pending()
    draft.setdefault("status", "awaiting_approval")
    draft.setdefault("created_at", _now_iso())
    pending_doc.setdefault("pending", []).append(draft)
    _save_pending(pending_doc)


def list_pending() -> list[dict]:
    return _load_pending().get("pending", [])


def _cli() -> None:
    if len(sys.argv) < 2:
        print("Usage: python watcher.py process|list-pending|append-pending JSON")
        return
    cmd = sys.argv[1]
    if cmd == "process":
        summary = process_telegram_responses()
        print(json.dumps(summary, indent=2, default=str))
    elif cmd == "list-pending":
        print(json.dumps(list_pending(), indent=2))
    elif cmd == "append-pending":
        if len(sys.argv) < 3:
            print("Usage: python watcher.py append-pending JSON")
            return
        draft = json.loads(sys.argv[2])
        append_pending_draft(draft)
        print("appended")
    else:
        print("Unknown command: " + cmd)


if __name__ == "__main__":
    _cli()
