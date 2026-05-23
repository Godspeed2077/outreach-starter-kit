---
name: outreach-state-update
description: Apply structured updates to a canonical validation_state.md file via a deterministic Python script. Use whenever the operator says "log this send," "update the state file," "mark X as replied," "move Y to closed-loop," "add a pattern note about Z," or "log the chase to W," or finishes any outreach action that needs to be recorded. Routes through a bundled Python helper that performs the file mutation atomically and aborts on any preservation failure (file shrank, pattern note lost, tail anchor lost, row delta wrong). Triggers proactively at the end of any outreach session — even when the operator doesn't say "log it" explicitly, if a send/reply/chase/close-loop just happened in conversation, this skill should run.
---

# outreach-state-update

## Why this skill exists

The operator keeps a single canonical state file (default location set in their config — typically `validation_state.md` in their outreach project folder). Every outreach action — sends, replies, chases, closes, patterns — gets logged here. It's a permanent append-only log. The single worst failure mode is silently dropping old content, which has actually been observed when an LLM-driven `Edit` on a long markdown file truncates the trailing section.

To eliminate that class of bug, this skill never touches the file directly. It routes every event through `scripts/apply_event.py`, which does the table-row prepend, bullet management, count updates, and Pattern Notes insertion in pure Python — and aborts before writing if any preservation check fails (file shrank when it shouldn't have, a Pattern Notes subsection went missing, the tail anchor was lost, row count delta doesn't match the event).

Your job in this skill is the *parsing* step: take the operator's free-form English, build a clean event payload, hand it to the script, and relay the script's confirmation back.

## Setup

Before first use, the operator must set two values in their kit config (typically `outreach_kit_config.json` in their project root):

```json
{
  "state_file_path": "<absolute path to your validation_state.md>",
  "signature": "<your name, used in the 'last updated' header line>"
}
```

The skill reads these at invocation time. If the config is missing or either field is empty, ask the operator before running the script.

## How to use

1. Read the operator's request and figure out which of the five event types applies.
2. Build the JSON payload for that event (fields listed below).
3. Run the script via `Bash`:
   ```bash
   python3 "<skill-dir>/scripts/apply_event.py" \
     --file "<state_file_path from config>" \
     --signature "<signature from config>" \
     --event <TYPE> \
     --payload '<json>'
   ```
   The skill directory path is the directory containing this SKILL.md. The script prints a confirmation summary on success or an `ABORT` message on a preservation failure.
4. If the script aborts, **don't try to patch the file directly.** Surface the abort message to the operator and ask how they want to proceed (usually: restore from backup, then re-run with corrected payload).
5. On success, relay the script's confirmation to the operator verbatim — that's their audit trail.

## The five event types

### NEW_SEND
Fields: `date` (ISO), `person`, `persona` (operator-defined label, e.g. A/B/C/D or a domain-specific tag), `channel`, `hook_used`, `notes_for_followup`.
What it does: prepends a row to the Sent Log table (under the `|---|` separator), appends a bullet to Active Conversations, increments the `(N)` count, updates the top header date.

### REPLY_RECEIVED
Fields: `person`, `reply_type` (operator-defined — common values include peer-frame / buyer-frame / no-thanks / clarifying), `reply_summary`, `today` (ISO, optional — defaults to today).
What it does: finds the person's most-recent Sent Log row (matching on the Person column specifically — prevents false matches when a person's name appears in another row's Channel or Notes), flips the Reply column from `—` to `✅ M/D`, updates their Active Conversations bullet, updates the header.

### CLOSE_LOOP
Fields: `person`, `close_reason`, `lesson_captured`, `today` (optional).
What it does: removes the person's Active Conversations bullet, decrements the count, appends to the inline `**Closed-loop:**` line under Active Conversations, appends to the Chase Queue `**Archived:**` line, updates the header.

### PATTERN_NOTE
Fields: `date` (ISO), `pattern_observed`, `signal_value`, `implications_for_next_week`, `label` (optional short heading suffix).
What it does: prepends a new `### [date] — [label]` subsection directly under `## Pattern Notes`, above the existing first subsection. Body has `**Pattern:** ... **Signal value:** ... **Implications for next week:** ...`. Existing subsections are preserved by construction — the script verifies every previous `###` heading still appears in the file before writing.

### CHASE_SENT
Fields: `person`, `original_send_date` (ISO), `fresh_hook_used`, `chase_date` (ISO).
What it does: counts existing chase rows for the person to determine N, prepends a Sent Log row with channel `<original> chase #N`, updates their Active Conversations bullet to chase status, updates the header.

## Parsing the operator's English into a payload

When the operator says something like:

> Log a new send for me. Today is 2026-05-17 (Sunday). I just sent jdoe a Persona C dev.to comment using the structured-data-shape hook. It's a public thread — watch for replies plus ancillary engagement.

You build:

```json
{
  "date": "2026-05-17",
  "person": "jdoe",
  "persona": "C",
  "channel": "dev.to comment",
  "hook_used": "structured data shape (specific to candidate's product)",
  "notes_for_followup": "Public thread, watch for replies + ancillary engagement"
}
```

…then invoke the script with `--event NEW_SEND --payload '<that JSON>'`.

If a field is missing from the operator's request, **ask before inventing.** The script's preservation checks will catch structural mistakes, but they won't catch you putting a fabricated `hook_used` into the row.

## When the script aborts

The script exits non-zero with an `ABORT` message in these cases:

- **File did not grow** — append-only events must increase file size. If the file is the same size or smaller, something got overwritten.
- **Pattern Notes subsection lost** — a `###` heading that existed before is gone. This is the original failure mode the script exists to prevent. The script catches it before writing; the file on disk is untouched.
- **Tail anchor lost** — the file's previous last non-empty line is no longer in the file. Same defense.
- **Sent Log delta wrong** — `NEW_SEND`/`CHASE_SENT` should add exactly 1 row; other events should add 0. A mismatch means the prepend regex didn't fire or fired twice.
- **Active Conversations count delta wrong** — the `(N)` count drift doesn't match the event.
- **Duplicate row detected (NEW_SEND only)** — a Sent Log row already exists for that person on that date. Ask the operator: update existing row or add a separate one?

In all these cases, the file on disk is **unchanged**. Re-run with a corrected payload or surface the issue to the operator.

## Critical rules

- **Path comes from config**, not hardcoded. Don't write to alternative paths even if the operator asks in passing — confirm first.
- **Never use the `Write` or `Edit` tool on the state file directly.** Always go through the script. The script is the single point of write authority.
- **Date formats:** ISO (`2026-05-17`) in payloads. The script handles conversion to prose dates (`5/17`) and day-of-week headers internally.
- **One event at a time.** If the operator says "log a few sends," collect each one separately, confirm the parse back to them, then run the script per event.

## Example confirmation summary

After a successful NEW_SEND, the script prints something like:

```
✅ NEW_SEND applied to validation_state.md
  new_row: | 2026-05-17 | jdoe | C | dev.to comment | — | ... |
  new_bullet: - jdoe — Persona C dev.to comment, first send 5/17
  active_conv: 12 → 13
  bytes: 18832 → 19068 (+236)
  sent_log: 26 → 27
  pattern_notes: 2 → 2
  tail_anchor_preserved: - Most useful next signal: ...
```

Relay this to the operator as their audit trail. The byte-count delta, the row-count delta, and the tail anchor confirmation together prove the file grew the way it should have, nothing got lost.
