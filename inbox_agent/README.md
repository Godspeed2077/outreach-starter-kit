# Outreach Inbox Agent (v1)

A scheduled watcher that monitors **Gmail, GitHub, and dev.to** for replies from
people in the operator's Sent Log, drafts responses using the `persona-c-draft`
skill, and routes them through an approval handshake (Telegram in v1) before
sending via each channel's native API.

## The loop

Every tick (the scheduled task fires the cadence — typically every 15-60
minutes during the operator's working hours), `watcher.py` runs:

1. Process any approvals from the previous tick (Send/Edit/Skip taps on
   pushed drafts).
2. For each channel, parse `validation_state.md` Sent Log → list of people the
   operator is awaiting replies from. Query the channel for new replies from
   those people since the last check.
3. For each new reply: pull the full thread, build context (original send +
   their reply + operator's voice rules from validation_state.md), run the
   `persona-c-draft` skill to produce a reply draft with bluff filter status.
4. Push the draft to the approval surface (Telegram) with inline Send / Edit /
   Skip buttons. Persist the pending approval in `pending_drafts.json`.
5. Wait for the operator's approval (processed on the next tick). When approved,
   send via the channel's API. Log the send back to `validation_state.md` via
   the `outreach-state-update` skill.

## Files

- `watcher.py` — entrypoint, processes approvals + orchestrates the loop
- `state_parser.py` — parses validation_state.md Sent Log into structured Python
- `gmail_client.py` — Gmail API send helper (OAuth-based, free)
- `github_client.py` — GitHub API polling and send (Personal Access Token)
- `devto_client.py` — dev.to API polling and send (API key)
- `telegram_client.py` — Telegram bot helper (reference notifier implementation)
- `runbook.md` — the per-tick playbook the scheduled task follows
- `state.json` — last_check_ts per channel, Telegram offset, etc.
- `pending_drafts.json` — drafts awaiting operator approval
- `.credentials/` — bot tokens + OAuth JSON. **Never commit, never share, never
  put under any sync that leaves the machine.** A `.gitignore` and a
  `.template/` directory ship inside for reference.

## Scope (v1)

In scope: detecting replies from people in the Sent Log across Gmail, GitHub,
and dev.to; drafting responses; approval handshake (Telegram); sending via
each channel; state-file update.

Out of scope for v1 (planned for later):

- Additional channels (X, Reddit, Slack, IndieHackers).
- Additional approval surfaces beyond Telegram (email digest, Slack DM).
- First-contact / chase generation (this v1 is reply-only; first sends are
  drafted by the operator in a normal Claude session via `persona-c-draft`).
- Multi-account Gmail.

## Adding more channels or approval surfaces

See `runbook.md` — the "Channel-add checklist" and "Notifier-add checklist"
sections at the bottom describe the contract each new module must satisfy.
The architecture is intentionally simple: one Python module per channel,
one per notifier, and the watcher dispatches by name.

## Credentials needed

Set up each credential file using the empty shells in `.credentials/.template/`:

- **Telegram** (`telegram.json`): bot token from `@BotFather`, chat ID
  (auto-discovered after first message to the bot — run
  `python telegram_client.py resolve`).
- **Gmail** (`gmail_oauth.json` + `gmail_token.json`): OAuth client credentials
  JSON from Google Cloud Console; refresh token cache generated on first run
  by `python gmail_client.py authorize`.
- **GitHub** (`github.json`): a classic Personal Access Token with `notifications`
  + `public_repo` (or `repo` for private) scope.
- **dev.to** (`devto.json`): an API key from your dev.to settings page.

Set the state-file location:

```bash
export OUTREACH_STATE_FILE="<absolute path to your validation_state.md>"
```

Make it permanent by adding it to your shell profile (`.bashrc`, `.zshrc`, or
Windows environment variables).

## Setup walkthrough

1. Copy each template file from `.credentials/.template/` to `.credentials/`,
   filling in your real credentials.
2. Run the OAuth / chat-ID resolution steps (one-time):
   - `python gmail_client.py authorize`
   - `python telegram_client.py resolve` (after messaging your bot once)
3. Test each client individually:
   - `python gmail_client.py send-test <your-email>`
   - `python telegram_client.py hello`
   - `python github_client.py whoami`
   - `python devto_client.py whoami`
4. Set `OUTREACH_STATE_FILE` env var as above.
5. Test the watcher: `python watcher.py process` should run cleanly with no
   pending approvals.
6. Wire up the scheduled task (see `../scheduled_tasks/outreach-inbox-agent/`
   for the SKILL.md to install).
