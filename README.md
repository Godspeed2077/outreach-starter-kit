# Outreach Starter Kit

An operator-grade kit for running a structured outreach sprint. Built and battle-tested by one solo founder doing validation outreach; generalized so any solo founder can drop it in.

## What's in the box

**Three Claude skills** that mediate every outreach action:

- `persona-c-verify` — verifies a candidate is real, alive, and a persona fit before you draft anything. Produces a one-page report with personalization specifics.
- `persona-c-draft` — generates first-contact and chase messages following a four-move structural spine. Applies a bluff-prevention filter using your own allowed/forbidden claims. Never invents customer/volume/pricing data.
- `outreach-state-update` — applies every change to your canonical state file through a deterministic Python script that does preservation checks before writing. Prevents the LLM-truncation failure mode that kills naive Edit-based state files.

**A canonical state file template** (`state_file_template.md`) — your single source of truth. Append-only log, structured sections, machine-readable by the skills.

**Two scheduled tasks:**

- `daily-priorities` — runs each morning, computes your 3-7 highest-leverage outreach actions for the day, pushes them to your configured messaging surface.
- `outreach-inbox-agent` — runs every tick during your working hours, polls Gmail/GitHub/dev.to for new replies, drafts responses, pushes them to you for one-tap approval.

**A Python inbox agent package** (`inbox_agent/`) — the engine behind the hourly task. Per-channel polling clients, OAuth-based send, Telegram-based approval handshake.

## What this is not

This is not a marketing automation tool. It does not blast messages. It does not "personalize at scale" by templating in someone's first name. Every send still requires a verified specific hook, structured drafting, and manual approval. The kit's value is discipline, not volume.

## Folder structure

```
outreach_starter_kit/
├── README.md                        (this file)
├── LAUNCH_POST.md                   (the announce post)
├── outreach_kit_config.json         (you create this — see Setup below)
├── skills/
│   ├── persona-c-verify/SKILL.md
│   ├── persona-c-draft/SKILL.md
│   └── outreach-state-update/
│       ├── SKILL.md
│       └── scripts/apply_event.py
├── state_file_template.md           (starter for your validation_state.md)
├── inbox_agent/                     (the Python package + runbook)
│   ├── README.md                    (subsystem-specific README)
│   ├── runbook.md
│   ├── *.py
│   ├── requirements.txt
│   └── .credentials/.template/      (empty shells — fill in real files alongside)
└── scheduled_tasks/
    ├── daily-priorities/SKILL.md
    └── outreach-inbox-agent/SKILL.md
```

## Prerequisites

- A Claude account with skills enabled (Claude Code, Claude Desktop with Cowork, or any environment that loads SKILL.md files).
- Python 3.10 or newer.
- A messaging surface for the approval handshake. v1 supports Telegram out of the box; the architecture is built to accept other surfaces (see `inbox_agent/runbook.md` "Notifier-add checklist").
- API credentials for whichever inbox-agent channels you plan to use (Gmail, GitHub, dev.to). You don't need all three — disable the ones you don't use by removing them from the runbook's Step 2.

## Setup

### 1. Drop the skills into your Claude environment

Copy the three skill folders from `skills/` to wherever your Claude environment loads skills:

- Claude Code: `~/.claude/skills/`
- Claude Desktop with Cowork (Windows): `%APPDATA%\Claude\skills\`
- Other: check your environment's docs.

After copying, restart Claude (or reload skills) so the three new skills appear in the available skills list.

### 2. Create your state file

Copy `state_file_template.md` to wherever you want your live state file to live. The conventional location:

```
<your outreach folder>/validation_state.md
```

Open it and fill in:
- Your weekly schedule (which days are full-output vs partial).
- Your "Material context" (the constraints that shape urgency — money, deadlines, life pressure).
- Your "Voice & Style Rules" (your no-go phrases, preferred punctuation, opening patterns).
- Your "Outreach Channel Discipline" (which channels pass your friction test).
- Your "Runway context" (financial dimension — income, deadline if any).

Leave the table and bullet sections empty; the skill writes to them.

### 3. Create the kit config

Create `outreach_kit_config.json` in your outreach folder:

```json
{
  "state_file_path": "<absolute path to your validation_state.md>",
  "signature": "<your name, used in state file headers>",
  "operator_product_name": "<your product>",
  "operator_product_url": "<your product URL>",
  "operator_wedge_sentence": "<one sentence describing what you uniquely offer>",
  "operator_proof_template": "<two-sentence canonical proof, using only verified facts>",
  "operator_close_template": "<one-sentence soft ask, a real question not a CTA>",
  "operator_persona_descriptor": "<short phrase describing your target>",
  "allowed_claims": [
    "<every verified fact you can repeat about your product, exactly as you'd say it>"
  ],
  "forbidden_claims_patterns": [
    "<every category of claim you cannot substantiate — customer counts, retention, etc.>"
  ],
  "voice_rules": {
    "no_em_dashes": true,
    "lowercase_friendly": true,
    "observation_first": true,
    "additional_rules": []
  },
  "persona_label": "C",
  "persona_description": "<one or two sentences describing who you're targeting>",
  "persona_disqualifiers": [
    "<red flag that disqualifies a candidate>"
  ],
  "commercial_intent_tiers": {
    "tier_1": "<strongest commercial-intent signals>",
    "tier_2": "<moderate signals>",
    "tier_3": "<weakest signals>"
  },
  "reports_dir": "<path where verification reports should be written>"
}
```

Both skills read this config at invocation time. The skills will ask you for missing fields before running, but it's faster to fill them all in upfront.

### 4. Set the state file env var

The inbox agent reads `OUTREACH_STATE_FILE` to find your state file:

```bash
# macOS / Linux — add to .bashrc / .zshrc
export OUTREACH_STATE_FILE="<absolute path to validation_state.md>"

# Windows — set permanently via System Properties → Environment Variables
# or per-session in PowerShell:
$env:OUTREACH_STATE_FILE = "<absolute path>"
```

### 5. Set up the inbox agent (optional but recommended)

If you want the hourly reply-detection loop, follow `inbox_agent/README.md` to:

- `pip install -r inbox_agent/requirements.txt`
- Fill in `.credentials/` files for each channel you plan to use (Telegram is required; Gmail/GitHub/dev.to are per-channel optional).
- Run the one-time OAuth flows.

If you skip this, you'll still get the skills + state file + daily priorities task — just without auto-detection of incoming replies.

### 6. Set up the scheduled tasks (optional)

- `daily-priorities` — install the SKILL.md as a scheduled task with your preferred cadence (typically once per morning). The skill embeds your state inline; refresh the embedded state periodically (manually or via a script you write).
- `outreach-inbox-agent` — install the SKILL.md as a scheduled task with your working-hours cadence (typically every 15-60 minutes from morning to evening).

Both tasks assume your environment supports scheduled Claude invocations (Cowork's scheduling, cron + a Claude CLI wrapper, etc.).

## Daily flow once running

1. Morning: daily-priorities task fires. You get a Telegram (or email/Slack) message with today's 3-7 outreach actions.
2. Throughout the day: you draft outreach in a Claude session using `persona-c-verify` and `persona-c-draft`. Every send gets logged via `outreach-state-update`.
3. Throughout the day: the inbox agent ticks. When someone replies, you get a Telegram message with the original reply + a drafted response + Send/Edit/Skip buttons. Tap Send and the reply goes out; tap Edit and you type the corrected version; tap Skip and nothing happens.
4. End of week: open your state file, read the Pattern Notes section, write a new pattern note if you learned something. Decide what to keep doing, what to change.

## What discipline this enforces

- **One single source of truth.** Every action lives in `validation_state.md`. No scattered notes, no Trello, no "I'll remember." The state file is the operating system.
- **No skill can write to the state file outside the script.** The script does preservation checks before every write. The file never loses content silently.
- **No outreach without verification.** The draft skill asks for the verified specific detail before drafting. Generic openers are blocked at the input layer.
- **No bluffing.** The draft skill applies a configurable allowed/forbidden claims filter to every output. One fabricated metric flags the whole draft.
- **Channel friction is a hard filter.** Channels that require fighting platform rules (karma walls, AI-content bans, new-account gates) are dropped, not worked around.
- **Voice consistency.** Voice rules live in the state file and are read by every drafting invocation. No drift across sessions.

## Methodology references

The kit's design is grounded in two patterns worth naming:

- **State file as canonical operating system.** A markdown file with structured sections, mediated by skills that do preservation checks, used as the read/write substrate for a multi-week sprint. The pattern is general beyond outreach — it works anywhere you have a long-running structured process that needs to survive across sessions.
- **Bluff-prevention as a non-negotiable filter.** The draft skill's allowed/forbidden claims architecture is the operator's only durable advantage in any outreach channel. Once a single claim doesn't survive a sanity check, the whole message is dead. The filter exists to protect that advantage.

## Support

This kit ships as-is. The code is plain Python and plain markdown; read it, fork it, change it. Issues and PRs welcome on the repo (if you're reading from GitHub).

If something breaks, the most likely culprit is a state-file structure drift — the `outreach-state-update` script depends on the section headers and table format in `state_file_template.md`. If you reshape the template, update the script's regexes to match.

## License

MIT. See `LICENSE` file (if present) or assume MIT.
