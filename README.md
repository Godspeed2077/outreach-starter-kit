# Outreach Starter Kit

A self-hosted, end-to-end outreach pipeline for solo founders.

Discovery -> verification -> drafting -> sending -> logging, all in one invocation. Built around Claude skills with a hallucination guardrail so drafts can't fabricate metrics. Paired with a Python inbox agent that watches Gmail, GitHub, and dev.to for replies.

**Paid subscription product.** See [PRICING.md](PRICING.md) for terms.

## How to use the pipeline

The primary flow is the `outreach-pipeline` skill. One invocation processes candidates end-to-end:

```
You: "Run the pipeline on @jdoe from dev.to"

Pipeline:
  1. Verifies jdoe is real, alive, persona-fit.
  2. Drafts a personalized message using verified specifics.
  3. Runs the hallucination filter on the draft.
  4. Sends via the channel's API (Tier 1) or queues to your phone (Tier 2).
  5. Logs the send to your canonical state file.

Output: status summary pushed to your Telegram.
```

Three input forms:

- **Single candidate:** "Process @jdoe on dev.to."
- **Discovery output file:** "Run the pipeline on outputs/persona-c-discovery-2026-05-24.md."
- **Persona-derived query:** "Find and process 10 data-API founders this week." (The pipeline runs discovery internally first.)

Flags:

- `--dry-run` — produce drafts only. No sends. No logs. For first-run safety on a new config.
- `--max N` — cap candidates processed in this run.

## What's in the box

**Five Claude skills** (the orchestrator plus four components):

1. **`outreach-pipeline`** — the primary entry point. Chains the four components end-to-end with no per-step approval gates.
2. **`persona-c-discover`** — searches HN/IH/dev.to/GitHub for candidates matching your persona. Outputs a list with verbatim hook snippets.
3. **`persona-c-verify`** — checks a candidate is real, alive, persona-fit. Pulls personalization specifics.
4. **`persona-c-draft`** — generates the outreach message. Hallucination filter built in.
5. **`outreach-state-update`** — logs every send/reply/chase/close through a Python script with preservation checks.

**A canonical state file template** (`state_file_template.md`) — your single source of truth. Append-only, structured sections.

**Two scheduled tasks:**

- `daily-priorities` — morning briefing of today's 3-7 highest-leverage actions.
- `outreach-inbox-agent` — hourly poll of Gmail/GitHub/dev.to for new replies, drafts responses, pushes to Telegram for Send/Edit/Skip approval.

**A Python inbox agent package** (`inbox_agent/`) — the engine behind the hourly task. Per-channel polling clients, OAuth-based send, Telegram approval handshake, queue-and-notify for non-API channels.

## Drafts can't hallucinate

The `persona-c-draft` skill runs every output through a configurable claims filter. You write your allowed claims (verified facts about your product) and forbidden patterns (categories you can't substantiate). The drafter scans each output. The first hallucinated metric flags the whole draft and proposes a fix using only allowed claims.

This is the LLM's hallucination guardrail. Claude is the author of every draft and could fabricate metrics that sound plausible. The filter prevents that. Drafts only use facts you've verified.

```
=== BLUFF FILTER REPORT ===
Status: FLAGGED

Violation: "we've seen agents pay $X per query"

Rules triggered:
  - Forbidden phrase: "we've seen" (implies customer data you don't have)
  - Fabricated price: $X is not in allowed_claims

Proposed replacement (uses only allowed claims):
  "[your verified price] - volume's still low, but the rails work"
```

The replacement is shorter and weaker-sounding than the bluff. That's the point.

## Components — invoke individual skills directly

The pipeline is the primary flow, but every skill is independently invocable if you want to run just one step.

### `persona-c-discover`

Triggers: "find candidates," "discover prospects," "mine the pool."
Output: candidate list to `{reports_dir}/persona-c-discovery-{date}.md`, ready to feed into the pipeline or verify-by-hand.

### `persona-c-verify`

Triggers: "verify @jdoe," "check if this candidate is real," "is this post still live."
Output: one-page verification report with persona fit, commercial intent tier, recommended channel, recommended hook angle.

### `persona-c-draft`

Triggers: "draft a send for X," "write a chase to Y," "personalize this message."
Output: DRAFT MESSAGE + BLUFF FILTER REPORT + PRE-SEND CHECKLIST.

### `outreach-state-update`

Triggers: "log this send," "mark X as replied," "move Y to closed-loop," "add a pattern note about Z."
Output: confirmation summary via deterministic Python script with preservation checks.

## Channel send infrastructure

Three tiers:

**Tier 1 — API-programmatic (default for these channels):**
- Gmail (OAuth send)
- GitHub (issue/PR comments via PAT)
- dev.to (comment API)

**Tier 2 — Queue-and-notify (default for these channels):**
- HN comments, IndieHackers comments/DMs, X DMs, site contact forms.
- Pipeline pushes the draft + destination URL to Telegram with Confirm Sent / Skip buttons. You post manually, tap Confirm Sent, the state file logs automatically.

**Tier 3 — Optional Playwright (advanced opt-in, not bundled by default):**
- Headless browser automation for the Tier 2 channels. Requires cookie export from your authenticated session. ToS/breakage caveats apply. Available as a separate module documented in `inbox_agent/README.md`.

**Reddit is excluded** from all tiers per the kit's channel discipline rules (banned domains, karma walls, AI content filter). If your Reddit account passes your own friction test, you can add a Reddit client yourself, but the kit doesn't ship with one.

## What this is not

This is not Apollo, ZoomInfo, Clay, or any other contact database. There is no cached list of contacts. Discovery runs against live public posts in real-time.

It is not marketing automation. It does not blast. It does not "scale personalization" by templating someone's first name.

If you're a solo founder running cold outreach to other founders or operators and you want institutional sales-motion discipline without the headcount, this is for you.

If you want to send 1000 emails a day to a scraped list, this kit will actively work against you.

## Setup

This is a paid subscription product. See [PRICING.md](PRICING.md) for pricing and onboarding.

### 1. Subscribe
Pay via the Stripe payment link in PRICING.md. After payment, send your GitHub username to randyrockwell05@gmail.com to receive a collaborator invitation.

### 2. Clone the repo (after your invitation is accepted)
```bash
gh repo clone Godspeed2077/outreach-starter-kit ~/outreach-starter-kit
```
Or use HTTPS clone with your GitHub credentials.

### 3. Drop the skills into your Claude environment
Copy `~/outreach-starter-kit/skills/*` to your Claude skills folder:
- Claude Code: `~/.claude/skills/`
- Claude Desktop with Cowork (Windows): `%APPDATA%/Claude/skills/`

Reload Claude so the skills appear.

### 4. Fill in your state file and kit config
Copy `state_file_template.md` to wherever you want your live state file. Create `outreach_kit_config.json` in your outreach folder. Schema:

```json
{
  "state_file_path": "<absolute path to your validation_state.md>",
  "signature": "<your name, used in state file headers>",
  "operator_product_name": "<your product>",
  "operator_product_url": "<your product URL>",
  "operator_wedge_sentence": "<what you uniquely offer>",
  "operator_proof_template": "<two-sentence canonical proof, verified facts only>",
  "operator_close_template": "<one-sentence soft ask>",
  "operator_persona_descriptor": "<short phrase describing your target>",
  "allowed_claims": ["<every verified fact about your product>"],
  "forbidden_claims_patterns": ["<categories you cannot substantiate>"],
  "voice_rules": {"no_em_dashes": true, "lowercase_friendly": true, "observation_first": true, "additional_rules": []},
  "persona_label": "C",
  "persona_description": "<who you target>",
  "persona_disqualifiers": ["<red flags>"],
  "commercial_intent_tiers": {"tier_1": "<strongest>", "tier_2": "<moderate>", "tier_3": "<weak>"},
  "reports_dir": "<where reports go>",
  "discovery_platforms": ["HN", "IH", "devto", "GitHub"]
}
```

### 5. Set up the inbox agent (optional but recommended)
`pip install -r inbox_agent/requirements.txt`, fill in credentials in `.credentials/` for Telegram + any channels you use.

### 6. Wire the scheduled tasks
Install the `daily-priorities` and `outreach-inbox-agent` SKILL.md files as scheduled tasks in your environment.

### 7. Set the state file env var
```bash
export OUTREACH_STATE_FILE="<absolute path to your validation_state.md>"
```
Make it permanent via your shell profile.

## First-run safety

When you set up a fresh config, run the pipeline in `--dry-run` mode on the first 5-10 candidates. Pipeline produces all the drafts to a single file; nothing sends; nothing logs. Review the drafts. If they look right, re-run live. If they have problems, you found them at zero cost.

## What discipline this enforces

- Single source of truth: `validation_state.md`. Every action lives there.
- No skill writes to the state file outside the deterministic Python script with preservation checks. The file never loses content silently.
- No outreach without verification. The draft skill asks for a verified specific detail before drafting. Generic openers blocked at the input layer.
- No hallucination. Drafts can only use facts you've verified. The bluff filter is non-negotiable.
- Channel friction is a hard filter. Channels requiring karma climbs, AI-content bans, or banned-domain workarounds get dropped, not worked around.

## Support

This kit ships as-is. The code is plain Python and plain markdown; read it, fork it locally, change what you need (per the license, no public redistribution).

Issues + questions: randyrockwell05@gmail.com

## License

See [LICENSE](LICENSE). Proprietary, subscriber-only. Use locally, modify locally, do not redistribute.
