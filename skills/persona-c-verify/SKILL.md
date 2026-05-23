---
name: persona-c-verify
description: Verify an outreach candidate is real, alive, and a good persona fit before drafting outreach. Pulls canonical specifics for personalization and applies the operator's persona filter (defined in their kit config). Use whenever the operator says "verify this candidate," "check if this person is real," "is this post still live," "did this account go dormant," "is this candidate worth pursuing," or works from a list of candidates that haven't been individually verified yet. Also use proactively when revisiting old candidates whose status may have changed (Reddit accounts decay, HN items get deleted, founders pivot products), and any time outreach is about to be drafted to a person whose live status hasn't been confirmed in this session — never draft outreach to an unverified candidate.
---

# Persona Verify

Verify a candidate before drafting outreach. The goal is a one-page report the operator can scan in 30 seconds that tells them whether to pursue, skip, or hand-check the candidate, plus quotable specifics for personalization.

## When to use this skill

Use whenever the operator gives a candidate handle + platform — or a list of them — and wants to know whether the person is real, still around, and a fit. Also use proactively before drafting outreach: an unverified candidate gets verified first, every time. If a candidate has been verified earlier in the same conversation, skip re-verification unless the operator asks.

## Setup

Before first use, the operator must define their persona filter in `outreach_kit_config.json`:

```json
{
  "persona_label": "C",
  "persona_description": "<one or two sentences describing who you're targeting>",
  "persona_disqualifiers": [
    "<red flag 1>",
    "<red flag 2>"
  ],
  "commercial_intent_tiers": {
    "tier_1": "<strongest signals — explicit 'looking for customers,' 'how do I monetize,' etc.>",
    "tier_2": "<moderate signals — visible pricing, distribution hustle>",
    "tier_3": "<weakest signals — product exists, monetization unclear>"
  },
  "reports_dir": "<path where verification reports should be written>"
}
```

If the config is missing or any required field is empty, ask the operator before proceeding.

## Inputs

The user provides some or all of:

- `handle` — username on their platform
- `platform` — one of: `HN`, `Reddit`, `IndieHackers`, `dev.to`, `GitHub`, `ProductHunt`, `website`
- `claimed_product` — 1–2 sentence description of what they reportedly built
- `source_url` — optional, a specific HN item, Reddit thread, or post URL if already known

If `platform` is missing but `source_url` is given, infer the platform from the URL. If `handle` is missing but a source_url exists, parse it out of the URL (`?id=` on HN, `/user/` or `/u/` on Reddit, etc.).

## What to do

Work through these steps in order. The reasoning behind the order matters: you confirm life-signs first because there is no point pulling specifics from a dead source.

### 1. Build the canonical URL(s) to fetch

| Platform | URL pattern |
|---|---|
| HN user profile | `https://news.ycombinator.com/user?id={handle}` |
| HN user submitted | `https://news.ycombinator.com/submitted?id={handle}` |
| HN item | `https://news.ycombinator.com/item?id={ID}` |
| Reddit user (JSON) | `https://www.reddit.com/user/{handle}/submitted.json?limit=25` |
| Reddit user (HTML) | `https://old.reddit.com/user/{handle}/submitted/` |
| IndieHackers | use the URL provided |
| dev.to article | `https://dev.to/{handle}/{slug}` |
| GitHub | `https://github.com/{handle}` |
| ProductHunt | `https://www.producthunt.com/@{handle}` or the product URL provided |
| Website | use the URL provided |

### 2. Fetch the page

Try `WebFetch` (or `web_fetch`) first — it's faster and works for most public pages. If the response is empty, 403/blocked, a bot-check page, or obviously truncated (especially on Reddit, ProductHunt, or sites with heavy anti-bot measures), fall back to a scraping tool that handles JavaScript and bot detection. If none is available, mark the relevant field `NEEDS-MANUAL-CHECK` rather than guess.

When fetching directly via `curl` or similar (not preferred — use proper tools), use a realistic User-Agent: `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36`.

### 3. Parse the page

Pull the fields that matter for the report. What "matters" varies by platform:

- **HN item**: title (the text after `titleline`), poster, score, comment count, OP body (look inside `class="toptext"`), submission date.
- **HN user**: created date, karma, recent submissions list.
- **Reddit user (JSON)**: inspect `data.children`. If `children` is an empty array, the account has zero submissions — this is the canonical DEAD signal on Reddit. Otherwise, pull title, subreddit, score, num_comments, and selftext from each entry.
- **IndieHackers / dev.to**: post body, author byline, comment count, publish date.
- **GitHub**: pinned repos, recent commit dates, README of the product repo, stars.
- **Product website**: hero text, pricing section if any, "About" or "Team" section, contact options.

### 4. Apply the persona filter

Run the candidate through three gates in order; failing any one moves them to `SKIP`.

**Gate A — Alive?**
- Reddit `children` array is empty → DEAD.
- HN item returns the homepage / `<title>Hacker News</title>` shell with no story → DEAD (item deleted or never existed).
- Product site is a 404, parked domain, or "this domain is for sale" page → DEAD.
- User profile shows no submissions or activity in the last 12 months → ALIVE but mark as STALE in reasoning.

**Gate B — Right persona?**

Apply the operator's persona definition from config. The candidate must match `persona_description` and not trigger any `persona_disqualifiers`. If they're alive but wrong-persona, mark `WRONG-PERSONA` and stop — the persona check supersedes other checks for routing.

**Gate C — Commercial intent visible?**

Classify against the operator's commercial-intent tiers from config. Most candidates fall into Tier 2 or Tier 3. Tier 1 signals are rare and worth flagging clearly.

### 5. Pull specifics for personalization

Grab 2–4 quotable details the operator could drop into outreach to prove they actually read the thing. Good specifics:

- A specific feature, taxonomy, or column the product exposes.
- A specific number from the post (upvotes, comment count, signups mentioned).
- A specific challenge the OP described in their own words.
- A specific customer or use-case the OP named.

**Never invent.** If the source doesn't show a number, write "not stated in source." If body text won't parse, write "OP body not parseable, manual check needed."

### 6. Write the report

Save the report to `{reports_dir}/{handle}-{YYYY-MM-DD}.md` AND print it inline so the operator can scan it without opening the file. If `reports_dir` doesn't exist, create it.

Use this exact template — consistent structure is what makes these reports fast to read when the operator is processing many of them:

```
=== CANDIDATE VERIFICATION REPORT ===
Handle: {handle}
Platform: {platform}
Status: ALIVE | DEAD | WRONG-PERSONA | NEEDS-MANUAL-CHECK
Real name (if findable): {name or "not findable"}
Product URL: {url or "not findable"}
Most recent relevant post: {title} ({date}) — {url}
Engagement: {points/upvotes/comments, or "not stated in source"}

Verified specifics (for personalization):
- {Specific detail 1 — must be quotable from source}
- {Specific detail 2}
- {Specific detail 3}

Persona fit: TIER 1 | TIER 2 | TIER 3 | SKIP
Reasoning: {1–2 sentences}

Recommended channel: {DM | site contact form | platform comment | etc.}
Recommended hook angle: {1–2 sentences referencing a specific detail above}

Dropped-candidate flag (only if SKIP):
- Reason: {zero posts | wrong persona | public-good ethos | dead link | etc.}
```

## Critical rules

These exist because each one has burned someone in the past. Do not relax them.

**Bluff prevention.** If the source doesn't show a number, don't make one up. If you can't extract the body text, say so. Date stamps come from the source, not estimated. This is the single most important rule — a report with one fabricated detail is worse than no report, because the operator will quote it in outreach and look like a liar.

**Don't draft outreach in this skill.** This skill produces a verification report and a hook angle, nothing more. Outreach drafting is a separate step the operator runs explicitly via `persona-c-draft`.

**Status is a single value.** Pick one of ALIVE / DEAD / WRONG-PERSONA / NEEDS-MANUAL-CHECK. If a candidate is alive but wrong-persona, the status is WRONG-PERSONA (the persona check supersedes the alive check for routing purposes — the operator doesn't care if a misfit is alive).

**Be skeptical of the candidate, not the source.** If the post is live and the OP says X, treat X as a source-claim, not a verified fact about the world. The verification is "the candidate publicly claims X," not "X is true." This matters for hook angles: hook on what they said, not on inferred facts.

**One candidate per invocation.** If the operator hands you a list, process them one at a time and produce one report per candidate. Batching loses fidelity.

## Examples

**Example 1 — TIER 1, ALIVE**
Input: a HN candidate with an "Ask HN: how do I monetize X" post that's still live.
Expected status: ALIVE, Tier 1. Verified specifics should include the candidate's product taxonomy and the explicit monetization-question framing. Hook angle references the monetization question directly.

**Example 2 — WRONG-PERSONA, SKIP**
Input: a candidate whose bio triggers a persona disqualifier (e.g., enterprise founder when the operator targets bootstrapped solo).
Expected status: WRONG-PERSONA, SKIP. Reasoning cites the disqualifier specifically.

**Example 3 — DEAD, SKIP**
Input: a Reddit handle with zero submitted posts.
Expected status: DEAD, SKIP. Reasoning: Reddit user shows zero submitted posts (the JSON `children` array is empty). Account dormant or shadowbanned.
