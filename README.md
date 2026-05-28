# Outreach Starter Kit

> **Archived 2026-05-28.** No longer a paid product. Open source under MIT. No support, no updates, no further development. Kept here as a portfolio artifact.

A self-hosted, end-to-end outreach pipeline for solo founders.

Discovery → verification → drafting → sending → logging, all in one invocation. Built around Claude skills with a hallucination guardrail so drafts can't fabricate metrics. Paired with a Python inbox agent that watches Gmail, GitHub, and dev.to for replies.

## Why archived

Built and shipped May 2026 as a paid subscription product ($5/mo) targeting solo founders running cold outreach in the x402 / MCP space.

Closed it three days post-launch because the niche collapsed under our feet:

- **AWS Bedrock AgentCore Payments** (launched 5/7/2026) made x402 a one-line API call inside AWS, eating most of the "implementation help" buyer pool.
- **x402 Linux Foundation absorption** removed the "spec stability" objection the kit's whole positioning was built around.
- **Real x402 commerce volume is ~$28K/day** despite a $7B ecosystem valuation — adoption is real on paper but the buyers wiring x402 today are speculating about future revenue, not chasing real revenue.
- **Two months of validation outreach** (28 sends, 1 buyer-frame signal from a Reddit second-touch, 0 paying customers) showed the cold-email channel was producing peer-frame, not buyer-frame.

The pivot to a narrower niche (founders wiring x402 outside AWS) was real but too slow and too thin to bet a December housing deadline on. Better to release it as a public artifact than pretend it's still a live product.

Strategic review that led to this decision: lives in the author's notes, not in the repo.

## What's in the box

**Five Claude skills** (the orchestrator plus four components):

1. `outreach-pipeline` — end-to-end orchestrator. Chains the four components with no per-step approval gates.
2. `persona-c-discover` — searches HN/IH/dev.to/GitHub for candidates matching your persona. Outputs a list with verbatim hook snippets.
3. `persona-c-verify` — checks a candidate is real, alive, persona-fit. Pulls personalization specifics.
4. `persona-c-draft` — generates the outreach message. Hallucination filter built in.
5. `outreach-state-update` — logs every send/reply/chase/close through a Python script with preservation checks.

**A canonical state file template** (`state_file_template.md`) — your single source of truth. Append-only, structured sections.

**Two scheduled tasks:** `daily-priorities` and `outreach-inbox-agent`.

**A Python inbox agent package** (`inbox_agent/`) — per-channel polling clients (Gmail/GitHub/dev.to), OAuth-based send, Telegram approval handshake, queue-and-notify for non-API channels.

## Use it

Setup walkthrough is the same as before — see the SKILL.md files for each skill. The kit will still work; it just isn't being actively maintained.

If you fork it and make it useful, good. If you want to email the author to say what you built with it: randyrockwell05@gmail.com.

## What I'd build differently next time

- **Don't position around a single rail/standard you don't control.** When the rail standardized and a hyperscaler shipped the managed version, the kit's positioning collapsed. The discipline pattern is more general than the niche it shipped against.
- **Discovery is the missing piece on day one, not v0.2.** Outreach without a candidate list is half a product. Should have shipped discovery as v0.1.
- **Test the demand before building the kit.** Should have run a "would you pay $5/mo for X" survey against 50 candidates before writing 1500 lines of Python and markdown.

## License

MIT. See [LICENSE](LICENSE).
