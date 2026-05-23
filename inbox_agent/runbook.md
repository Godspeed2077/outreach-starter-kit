# Inbox Agent Runbook (multi-channel)

The per-tick playbook the scheduled task follows. Every tick is a fresh Claude
session with no memory of previous ticks. Run order matters.

Channels: **Gmail, GitHub, dev.to.** Each channel has the same draft-and-approve
loop; only the polling, send mechanism, and dedupe key differ.

---

## Step 0 — Folder access

If you are running this scheduled task **inside Cowork mode**, the working
folder must already be pinned to the operator's outreach folder (e.g.
`<outreach folder>/inbox_agent`). **DO NOT** call
`mcp__cowork__request_cowork_directory` from inside the scheduled task — that
triggers a redundant approval prompt every tick.

If you are running this outside Cowork (e.g. cron + standalone Claude session),
no folder mounting is needed — the script paths use absolute paths.

Inside bash on Cowork, the folder appears at `/sessions/<session>/mnt/<folder name>/`.
Use the absolute Windows/macOS/Linux path for `Read`/`Write`/`Edit`; the Linux
session path for `bash`. The session name varies per tick; resolve it with
`realpath` or `echo /sessions/*/mnt/<folder name>` if needed.

---

## Step 1 — Process pending approval responses

```
bash: cd <inbox_agent dir> && python3 watcher.py process
```

Parse the JSON. Key fields:

- `sent[]` — drafts sent this tick. Each has `channel`. **Must be logged to
  validation_state.md in Step 4.**
- `edits_sent[]` — drafts sent with the operator's edited body. Same logging duty.
- `skipped[]` — drafts the operator skipped. Don't re-draft these (already removed
  from `pending_drafts.json`).
- `errors[]` — push first error to the approval surface, keep going.

---

## Step 2 — Poll each channel for new replies

For each channel, dedupe rule: **skip if a pending draft already exists with
the same `dedupe_key`.** Read `pending_drafts.json` once at the start of this
step, build the set of dedupe keys in pending, then check each new reply
against that set before drafting.

### 2a — Gmail

Get the awaiting watch-list:

```
bash: OUTREACH_STATE_FILE=<absolute path to validation_state.md> python3 -c "
import json, state_parser
print(json.dumps([e.to_dict() for e in state_parser.awaiting_email_entries(state_parser.load_from_disk())]))
"
```

Search Gmail (MCP connector) for unread threads from or to the awaiting
emails, OR'd in batches of ~10:

```
mcp__<gmail-connector-id>__search_threads
  query: "(from:a OR from:b OR to:a OR to:b ...) is:unread in:inbox newer_than:7d"
```

For each matched thread, call `get_thread` with `messageFormat: FULL_CONTENT`.
The latest message whose sender is NOT the operator's own email address (read
from the operator's kit config) is the new incoming reply.

**Dedupe key:** `gmail_thread_id` (the thread `id` from the API).

**`send_params` for pending_drafts.json:**

```json
{
  "to_email": "<sender of the incoming message>",
  "gmail_thread_id": "<thread id>",
  "gmail_in_reply_to_message_id": "<rfc822 Message-ID header of incoming>",
  "gmail_references": "<full References chain or just the incoming msg id>"
}
```

### 2b — GitHub

```
bash: python3 github_client.py poll
```

Returns a JSON list of new notifications. For each one whose `subject_type`
is `Issue` / `PullRequest`, call `python3 github_client.py context <thread_id>`
to get the full thread + latest incoming comment.

Skip notifications whose `incoming` is null (no comment yet, e.g. a new issue
opened with no follow-ups) and skip ones where the operator hasn't actually
participated in the thread (cross-reference repos+issue against the operator's
validation_state.md Sent Log if you want a tighter filter).

**Dedupe key:** `github_thread_id`.

**`send_params`:**

```json
{
  "repo_full_name": "owner/repo",
  "issue_number": <int>,
  "notification_thread_id": "<thread id, so watcher can mark read after send>"
}
```

### 2c — dev.to

```
bash: python3 devto_client.py poll
```

Returns new replies on articles the operator has commented on. Note this
requires the article-watch list to be populated. On first run only, register
the articles from validation_state.md that the operator has commented on:

```
bash: python3 devto_client.py watch <article_id>
```

Article IDs need to be looked up via `GET dev.to/api/articles?username=<author>`.

**Dedupe key:** `devto_incoming_comment_id`.

**`send_params`:**

```json
{
  "parent_comment_id": "<the dev.to id_code or id of the comment being replied to>",
  "article_id": <int>
}
```

---

## Step 3 — Draft a reply per new incoming reply

Same logic for every channel:

1. Read `validation_state.md` sections for voice rules and any operator-specific
   guidance.
2. Read the `persona-c-draft` skill at the path the operator's kit is installed
   to. Glob if the version hash shifts.
3. Generate a draft adapted for **reply-to-reply** context (not first-contact,
   not chase): engage with what they specifically said, skip the proof sentence,
   apply the bluff filter.
4. Word count: aim for ~100-150 words for reply-to-replies.
5. Channel-specific formatting notes:
   - **Gmail**: plain text, operator's voice rules apply verbatim.
   - **GitHub**: Markdown supported. Don't lean on it; keep it conversational.
   - **dev.to**: Markdown supported. Light hand on links (their spam filter is tetchy).
6. Generate a UUID for `draft_id`.
7. Push to the approval surface (Telegram in v1):

```
bash: python3 -c "
import telegram_client
mid = telegram_client.push_draft(
    draft_id='<uuid>',
    to_person='<canonical name>',
    to_email='<channel-appropriate identifier: email, github user, devto username>',
    reply_snippet='<their reply, trimmed to ~400 chars>',
    draft_body='<your draft>',
    bluff_status='PASS|FLAGGED: ...',
)
print(mid)
"
```

8. Append to pending_drafts.json:

```
bash: python3 watcher.py append-pending '<json>'
```

Full JSON shape (the `channel` and `send_params` fields are channel-specific
per Step 2):

```json
{
  "draft_id": "<uuid>",
  "telegram_message_id": <int from step 7>,
  "channel": "gmail" | "github" | "devto",
  "person": "<canonical name from sent log>",
  "subject": "<email subject or empty for non-gmail>",
  "draft_body": "<the body>",
  "dedupe_key": "<channel-specific key>",
  "send_params": { ... see Step 2 per channel ... }
}
```

---

## Step 4 — Log sent items to validation_state.md

For every entry in `sent[]` and `edits_sent[]` from Step 1, append a new row
to the Sent Log table via the `outreach-state-update` skill. Pattern:

```
| YYYY-MM-DD PM | <person> — reply #N | <persona> | <channel> reply | — | <one-line note> |
```

Channel name conventions:
- Gmail: `email reply`
- GitHub: `GitHub reply` + repo/issue link if helpful
- dev.to: `dev.to reply`

Use the skill, not direct Edit. It preserves the file's invariants.

---

## Step 5 — Status ping to the approval surface

```
bash: python3 -c "import telegram_client; telegram_client.push_text('Tick HH:MM: <N> sent, <M> new drafts pushed across [channels], <E> errors.')"
```

Include first error string if errors[] was non-empty.

---

## Failure handling

- Catch exceptions per channel step. One channel failing should not block the
  others.
- Push an alert per failure: `"Inbox agent error in step <N>: <error>"`.
- Never silently swallow.
- If `watcher.py process` itself crashes, push one alert and exit. State is
  unknown after that point.

---

## Channel-add checklist

When adding a fourth channel later:

1. Write `<channel>_client.py` with `poll_*`, `fetch_*_context`, `send_reply`,
   and (if available) `mark_read`.
2. Add credentials JSON to `.credentials/<channel>.json`.
3. Add a dispatch branch in `watcher.py` `_dispatch_send`.
4. Add a Step 2x section in this runbook.
5. Add the channel name to `SUPPORTED_CHANNELS` in `watcher.py`.

## Notifier-add checklist

To add an alternative approval surface (email digest, Slack, Discord) alongside
Telegram:

1. Write `<surface>_notifier.py` exposing `push_draft`, `push_text`, and
   `poll_responses` with the same signatures as `telegram_client.py`.
2. Add credentials JSON to `.credentials/<surface>.json`.
3. Either replace the `import telegram_client` line in `watcher.py` with the
   new notifier, or build a thin dispatcher that picks based on operator config.
