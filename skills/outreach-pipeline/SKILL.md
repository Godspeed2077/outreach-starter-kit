---
name: outreach-pipeline
description: Run the full outreach pipeline end-to-end with no per-step approval gates. Takes a candidate handle, a discovery output file, or a persona-derived query and processes candidates through verify -> draft -> send -> log automatically. Sends via Tier 1 API (Gmail/GitHub/dev.to) when available, falls back to Tier 2 queue-and-notify (Telegram with destination URL) for channels without programmatic sends. Dry-run mode produces drafts only. Use whenever the operator says "run the pipeline," "process this batch," "send to these candidates," "run outreach for the day," or wants the full discovery-to-send flow in one invocation.
---

# Outreach Pipeline

End-to-end orchestrator for the outreach starter kit. One invocation. Five steps per candidate (verify -> draft -> bluff-check -> send -> log). No per-step approval prompts.

## When to use this skill

The primary entry point. Whenever the operator wants to process candidates end-to-end. Common triggers: "run the pipeline," "process this batch," "run outreach," "send to these candidates."

If the operator wants to run only one step (just verify, just draft, just log), they can invoke the individual skill directly — those are still independently invocable. The pipeline is additive, not replacing.

## Setup

Reads `outreach_kit_config.json` for all the usual fields. Additionally:

- `pipeline_send_concurrency` (optional, default 1) — how many candidates to send in parallel. Keep at 1 unless your API rate limits are comfortable.
- `pipeline_max_batch` (optional, default 25) — cap on candidates processed per invocation.
- `tier2_notifier` (optional, default `"telegram"`) — where to push queue-and-notify drafts.

If anything required is missing, ask the operator before starting.

## Inputs at invocation

The pipeline accepts one of three input forms:

1. **Single candidate:** operator says "process @jdoe on dev.to" or similar.
2. **Discovery output file:** operator points at the most recent `persona-c-discovery-{date}.md` file.
3. **Persona-derived query:** operator says "find and process N data-API founders this week." The pipeline runs `persona-c-discover` internally as step 0, then proceeds.

Flags:

- `--dry-run` — pipeline produces drafts but does not send or log. Output goes to a `pipeline-dryrun-{timestamp}.md` file. Default is live mode.
- `--max N` — override `pipeline_max_batch` for this invocation.

## What to do

### Step 0 (only if input is a query): Run persona-c-discover

Invoke the discovery skill with the operator's query. Take the resulting candidate list as input to Step 1+.

### Step 1: Initialize pipeline state

Write a fresh state file at `{reports_dir}/pipeline-state-{timestamp}.json`:

```json
{
  "started_at": "<ISO timestamp>",
  "candidates": [<list of input candidates>],
  "mode": "live" or "dryrun",
  "completed": [],
  "skipped": [],
  "failed": [],
  "queued_manual_send": []
}
```

This is the resumability anchor. If the pipeline crashes or is killed mid-run, the next invocation can pick up where it stopped by reading this file.

### Step 2: Process each candidate (in series unless concurrency > 1)

For each candidate:

#### 2a. Verify

Invoke `persona-c-verify` with the candidate's handle + platform. Capture the verification report.

- If status is **DEAD**, **WRONG-PERSONA**, or **NEEDS-MANUAL-CHECK**: append to `skipped` with the reason. Move to the next candidate.
- If status is **ALIVE** and persona fit is **TIER 1/2/3**: continue to 2b.

#### 2b. Draft

Invoke `persona-c-draft` with the verified candidate. Use the verified specifics from 2a as the personalization hook. Pick `send_type` based on whether the candidate is in the operator's Sent Log already:
- Not in Sent Log: `FIRST_CONTACT`
- In Sent Log with no reply, eligible for chase: `CHASE_1`
- In Sent Log with reply: skip — already in conversation

#### 2c. Bluff-filter check

If the draft skill's output has `Status: FLAGGED`, append the candidate to `skipped` with reason `bluff-filter-tripped` and the flagged span. Do NOT auto-fix. Operator reviews skipped candidates later, not in the pipeline run.

If Status is `PASS`, continue.

#### 2d. Send (live mode only — dry-run stops here)

If `--dry-run`: append the draft to `{reports_dir}/pipeline-dryrun-{timestamp}.md` and continue to the next candidate.

If live mode:

Pick the send tier based on the candidate's channel:

**Tier 1 — API-programmatic:**
- Gmail (channel = "email"): use `inbox_agent/gmail_client.py send_reply`. Pull operator's Gmail credentials from `.credentials/gmail_token.json`.
- GitHub (channel = "GitHub issue" or "GitHub comment"): use `inbox_agent/github_client.py send_reply`. Pull credentials from `.credentials/github.json`.
- dev.to (channel = "dev.to comment"): use `inbox_agent/devto_client.py send_reply`. Pull credentials from `.credentials/devto.json`. If dev.to API refuses the send, fall back to Tier 2 for this candidate.

**Tier 2 — Queue-and-notify:**
- Any channel without a programmatic API: HN comments, IndieHackers comments/DMs, X DMs, site contact forms.
- Push to the operator's configured notifier (Telegram by default) with:
  - Candidate name + handle
  - Destination URL (where to post the message)
  - Full draft body
  - Subject line if applicable (e.g., contact forms)
- Mark the candidate as `queued_manual_send` in pipeline state.
- The operator manually pastes and posts via their phone or browser, then confirms back via Telegram.

**Send-execution rule:** never auto-send to a channel that the operator's `validation_state.md` "Outreach Channel Discipline" marks as DEAD. If a candidate's only channel is dead, append them to `skipped` with reason `channel-dead-no-alternative`.

#### 2e. Log

If a Tier 1 send succeeded, invoke `outreach-state-update` with a `NEW_SEND` (or `CHASE_SENT`) event. Pass the date, person, persona, channel, hook used, and notes.

If Tier 2 was queued, don't log yet — the log fires when the operator confirms manual send. Track `queued_manual_send` candidates in pipeline state; the next pipeline invocation checks for any new confirmations and logs them.

Append the candidate to `completed` in pipeline state.

### Step 3: Status summary

After processing all candidates, push a one-message summary to the configured notifier:

```
Pipeline run complete (<live|dryrun>).
Processed: N
Sent (Tier 1): X
Queued manual (Tier 2): Y
Skipped: Z (breakdown: A verification-failed, B bluff-filter, C channel-dead)
Failed: W
```

### Step 4: Persist pipeline state for resumability

Write the final pipeline state file (with `completed_at` timestamp added) so the next pipeline run can read it and handle any pending `queued_manual_send` confirmations.

## Resumability

On every invocation, before starting Step 0, check `{reports_dir}/pipeline-state-*.json` for any state files with `queued_manual_send` entries that haven't been logged yet. For each, check Telegram for a confirmation message containing the candidate's draft_id. If found, run `outreach-state-update` to log the send, and remove the entry from the queued list.

## Critical rules

**No per-step approval prompts in live mode.** The pipeline runs end-to-end automatically. The operator approves once at invocation by running the pipeline; per-candidate decisions are governed by the kit's configured rules (persona filter, bluff filter, channel discipline).

**Bluff filter trips are skips, not auto-fixes.** A flagged draft means the candidate gets skipped. The operator can review and re-process later. Auto-fixing in the pipeline would hide real signal about persona mismatch.

**Channel discipline is enforced.** Candidates whose only channel is marked dead get skipped automatically. Don't ask the operator — the rules are the contract.

**Verification is not optional.** Every candidate goes through verify before draft. If verify is skipped (e.g., candidate marked already-verified earlier in the session), the pipeline still runs the bluff-filter check on the draft output.

**Tier 1 send is preferred. Tier 2 is fallback.** If a channel has both options (e.g., Gmail with a contact form alternative), default to Tier 1.

**Pipeline state is persistent and gitignored.** Pipeline state files in `{reports_dir}` are operator-local; never commit them to the repo.

## Dry-run safety

When you run a new operator-config combination for the first time, use `--dry-run`. The pipeline produces every draft to a single file. Operator reviews. If drafts look right, re-run live. If drafts have problems, the operator finds them at zero cost.

Recommendation in README: first 5-10 candidates of any new config -> dry-run. After confidence is established -> live.

## Examples

**Example 1 — single candidate, live mode:**

Operator: "Run the pipeline on @jdoe on dev.to."

Pipeline: verifies jdoe (ALIVE, TIER 1) -> drafts -> bluff filter PASS -> sends via dev.to API -> logs NEW_SEND. Done.

**Example 2 — discovery output, dry-run:**

Operator: "Run the pipeline on outputs/persona-c-discovery-2026-05-24.md, dry-run."

Pipeline: reads the discovery file (15 candidates), processes each through verify + draft + bluff-check, writes all 15 drafts to pipeline-dryrun-{timestamp}.md, no sends, no logs. Final summary: 15 processed, 0 sent, 0 queued, 3 skipped (1 verification-failed, 2 bluff-filter), 12 drafts ready in dry-run file.

**Example 3 — persona-derived query, live mode:**

Operator: "Find and process 10 data-API founders this week."

Pipeline: runs persona-c-discover with derived queries (Step 0) -> 10 candidates returned -> verifies each -> drafts -> sends Tier 1 where possible, queues Tier 2 manual sends to Telegram for any that need it -> logs -> summary push.

**Example 4 — bluff filter trip:**

A candidate's draft includes a phrase that hits the operator's forbidden_claims_patterns. The pipeline catches it, appends to skipped with reason `bluff-filter-tripped`, includes the flagged span in the skip note, and moves on. Operator reviews the skip log later and decides whether to manually fix and resend.
