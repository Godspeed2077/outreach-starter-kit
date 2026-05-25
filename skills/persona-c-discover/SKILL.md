---
name: persona-c-discover
description: Discover outreach candidates matching the operator's persona by searching public posts on HN, IndieHackers, dev.to, and GitHub. Extracts handle, platform, source URL, and a verbatim hook snippet for each hit. Applies a soft persona filter and scores commercial intent. Dedupes across runs. Outputs a candidate list ready to feed into the outreach-pipeline skill or persona-c-verify. Use whenever the operator says "find candidates," "mine the pool," "discover new prospects," "run the persona search," or starts a new sprint and needs candidates to process. Triggers proactively at the start of any outreach session where the candidate queue is empty.
---

# Persona Discover

Discover outreach candidates by searching public posts that match the operator's persona definition. Feeds the rest of the pipeline.

## When to use this skill

Use whenever the operator wants to find new candidates. Common triggers: "find candidates," "discover new prospects," "mine the pool," "run the persona search," or any session where the operator wants to expand the candidate queue.

Discovery is upstream of verification, drafting, and sending. It does NOT verify candidates fully; that's the persona-c-verify skill's job. Discovery's job is to surface a list of plausibly-fit candidates with quotable hooks, deduped against prior runs.

## Setup

Reads from `outreach_kit_config.json`:

- `persona_label` — operator's label for the target persona (e.g., "C")
- `persona_description` — one or two sentences describing who you're targeting
- `persona_disqualifiers` — list of red flags that disqualify a candidate (e.g., "ex-CEO of YC company that raised $5M+")
- `commercial_intent_tiers` — `tier_1`, `tier_2`, `tier_3` descriptors for what counts as strong/moderate/weak commercial intent
- `reports_dir` — where to write the discovery output and dedupe file
- `discovery_platforms` (optional) — list of platforms to search (default: `["HN", "IH", "devto", "GitHub"]`). Operator can omit platforms they don't want to search.

If any required field is missing, ask the operator before proceeding. Do not invent values.

## Inputs at invocation

The operator provides some or all of:

- `seed_queries` — optional list of search query strings the operator wants to use directly. If absent, generate queries from `persona_description` + `commercial_intent_tiers`.
- `max_candidates` — optional cap on how many candidates to return (default 25).
- `time_window` — optional, default "last 30 days." Searches restricted to posts within the window.

If `seed_queries` is missing, generate 3-5 queries that would surface candidates matching the persona. The queries should target the OP's pain language ("looking for first users," "how do I monetize"), not generic product descriptions.

## What to do

### 1. Load the dedupe set

Read `{reports_dir}/persona-c-discovery-seen.md` if it exists. It's a markdown list of `handle@platform` strings of every candidate previously surfaced. Use this set to filter out repeats.

If the file doesn't exist, treat the dedupe set as empty.

### 2. Generate queries (if not provided)

Pull `persona_description` and `commercial_intent_tiers.tier_1` from config. Compose 3-5 search queries that would surface candidates matching that description, biased toward tier-1 commercial-intent language.

Example: persona is "solo bootstrapped data-product founder with visible monetization intent." Tier-1 intent is "explicit 'looking for first customers' or 'how do I monetize' language." Generated queries might be:
- "Ask HN how do I monetize"
- "indiehackers api looking for first users"
- "dev.to startup distribution struggle"
- "github.io pricing per-call agent"

Show the generated queries to the operator inline before running them.

### 3. Search each platform

Use `WebSearch` (or available web search tool). For each query, search across the configured platforms with appropriate site filters:

- HN: `site:news.ycombinator.com {query}`
- IH: `site:indiehackers.com {query}`
- dev.to: `site:dev.to {query}`
- GitHub: `site:github.com {query} type:issue` (for issues/PRs/discussions)

Combine the queries with the time window. Collect raw hit URLs.

### 4. Fetch each hit

For each URL, use web fetch to retrieve the page. Parse out:

- `handle` — the OP's username on that platform (HN user, Reddit handle (skip Reddit per channel discipline), IH handle, dev.to author, GitHub user)
- `platform` — the platform name
- `source_url` — the canonical URL of the post
- `post_date` — when the post was published
- `hook_snippet` — a verbatim quote (or close paraphrase) of the OP's pain or claim. Must be from the actual post body, not invented.

If a snippet can't be extracted cleanly (page won't parse, body is empty, snippet is generic boilerplate), mark `snippet_unavailable: true` and skip — don't fabricate.

If the Bright Data plugin tools (`mcp__brightdata__*`) are available in this session, prefer them for any hit that returns blocked/empty content via standard web fetch. Bright Data is optional; if unavailable, just skip the blocked hit.

### 5. Apply the persona filter (soft pass)

For each hit, do a quick yes/no/maybe check against the operator's `persona_description` and `persona_disqualifiers`. This is NOT full verification — it's a rough fit signal so the candidate list isn't full of obvious misfits.

Score commercial intent against `commercial_intent_tiers`:
- TIER 1: matches tier_1 descriptor (strongest)
- TIER 2: matches tier_2 descriptor
- TIER 3: matches tier_3 descriptor
- SKIP: triggers a persona_disqualifier or has no commercial-intent signal at all

### 6. Apply channel-discipline awareness

Read the operator's `validation_state.md` "Outreach Channel Discipline" section (path is `{state_file_path}` from config). For each candidate, if their platform is marked DEAD in the operator's channel rules, append a `channel_dead: true` warning to the candidate's row. Don't drop them — let the operator decide — just warn.

If a candidate has NO platform that passes the operator's friction test, drop them per the channel discipline hard rule.

### 7. Dedupe

Remove any candidates whose `handle@platform` already appears in the dedupe set from step 1.

Cap the remaining list at `max_candidates`.

### 8. Append to the dedupe file

Append every surfaced candidate's `handle@platform` (including ones dropped by the filter) to `{reports_dir}/persona-c-discovery-seen.md`. This prevents next-run from re-surfacing them.

### 9. Write the output

Save to `{reports_dir}/persona-c-discovery-{YYYY-MM-DD}.md` AND print inline. Use this template:

```
=== DISCOVERY OUTPUT — {YYYY-MM-DD} ===
Persona: {persona_label} — {persona_description}
Queries run: {list of queries}
Total hits across all queries: {N}
Surviving candidates after filter + dedupe: {M}

--- Candidate list ---

| # | Handle | Platform | URL | Fit | Intent Tier | Channel Status | Hook Snippet |
|---|--------|----------|-----|-----|-------------|---------------|--------------|
| 1 | jdoe | dev.to | https://... | YES | TIER 1 | OK | "I'm trying to figure out how to charge for automated access..." |
| 2 | asmith | HN | https://... | MAYBE | TIER 2 | channel-dead (HN) | "Made my API but nobody's paying yet..." |
| ... | ... | ... | ... | ... | ... | ... | ... |

--- Dropped ---
- @goldbloom (HN): triggers disqualifier "ex-CEO YC $5M+"
- ...

--- Next step ---
Feed this list to the outreach-pipeline skill to process candidates end-to-end,
or to persona-c-verify to verify them one at a time.
```

## Critical rules

**Bluff prevention.** Every hook snippet must be quoted/paraphrased from the actual source. Never invent. If extraction fails, mark `snippet_unavailable` and skip the candidate.

**Reddit is excluded.** The kit's channel discipline rules explicitly forbid Reddit (banned domains, karma walls, AI content filter). Discovery never searches Reddit. If a candidate URL points to reddit.com, drop them with the reason "Reddit excluded per channel discipline."

**Soft filter, not full verification.** The persona check here is fast (yes/no/maybe). The persona-c-verify skill does the full life-signs + persona + commercial-intent check before drafting. Discovery's job is to narrow the funnel cheaply.

**Dedupe is non-optional.** Always read the seen file, always append to it. Re-running discovery should produce overlapping but not redundant results.

**One platform per candidate.** If the same person posts on multiple platforms, dedupe on `handle@platform` not just `handle` — they may have different account standings on each platform.

## Examples

**Example 1 — discovery on a "data-API founder" persona:**

Input: persona = "solo or small-team data API founder with visible monetization intent."
Queries (auto-generated): ["Ask HN how do I monetize my API", "indiehackers data API pricing", "dev.to charging for agent traffic"]
Hits: 14 across all queries.
After filter + dedupe: 6 surviving candidates.

Output: 6-row table with handles, platforms, URLs, tier-1/2/3 intent scoring, hook snippets quoted verbatim. Dropped list shows the 8 that didn't survive (5 dedupes from prior run, 2 disqualified by persona rules, 1 snippet unavailable).

**Example 2 — discovery hits a Reddit URL:**

A search result returns a reddit.com URL. The skill drops the candidate immediately with reason "Reddit excluded per channel discipline" and continues processing other hits.

**Example 3 — discovery hits an X / Twitter URL:**

X posts can sometimes match queries. The skill keeps them, marks `platform: X`, but applies channel-discipline check: if X is in the operator's allowed channels with verified-open DMs, keep as TIER 1; if X is marked dead in their state file, mark `channel-dead` warning but don't drop. Operator decides.
