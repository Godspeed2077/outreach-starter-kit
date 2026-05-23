---
name: persona-c-draft
description: Generate a personalized outreach first-contact or chase message for the operator's target persona. Auto-applies a bluff-prevention filter using the operator's own allowed/forbidden claims (configured at setup) and follows a four-move structural spine. Use this skill whenever the operator says "draft a send for X," "write a chase to Y," "personalize a message for Z," "draft the batch," or is preparing outreach to a verified candidate. The skill always follows the established structural spine and never fabricates customer/volume/pricing claims. Trigger even if the operator doesn't say "draft" explicitly — if they're preparing outreach to a verified candidate, this is the skill.
---

# Persona Draft

This skill produces ready-to-send outreach drafts. The audience is whoever the operator targets — their persona definition lives in `outreach_kit_config.json`.

This is a high-trust, low-volume channel. One fabricated metric kills credibility for the whole batch. The bluff-prevention filter in this skill is the most important part — it is non-negotiable.

## Setup

Before first use, the operator must populate `outreach_kit_config.json` with:

```json
{
  "operator_product_name": "<your product name>",
  "operator_product_url": "<your product URL>",
  "operator_wedge_sentence": "<one sentence describing your wedge — what you uniquely offer that the candidate's current setup misses>",
  "operator_proof_template": "<two-sentence template describing what you've already shipped, using only verified facts; will be reused verbatim in every send>",
  "operator_close_template": "<one-sentence soft ask, a real question not a CTA; will be reused verbatim>",
  "operator_persona_descriptor": "<short phrase describing your target — used in conversational framing>",
  "allowed_claims": [
    "<every verified fact you can repeat about your product, exactly as you'd say it>"
  ],
  "forbidden_claims_patterns": [
    "<every category of claim you cannot substantiate — e.g., customer counts, retention numbers, agent-call volumes>"
  ],
  "voice_rules": {
    "no_em_dashes": true,
    "lowercase_friendly": true,
    "observation_first": true,
    "additional_rules": ["<any voice rules specific to you>"]
  }
}
```

If any required field is empty, ask the operator before drafting.

## When to invoke

The operator invokes this skill any time they're about to send outreach. Triggers include:

- "draft a send for [name]"
- "write a chase to [name]"
- "personalize a message for [handle]"
- "draft the batch"
- "write the first-contact for [candidate]"
- Implied: they paste a verification report and ask for the message

If the upstream verification step (the `persona-c-verify` skill or a manual verification report) hasn't been done, ask for the verified specific detail before drafting. **Do not draft from a generic description of the candidate's product** — the opener has to be a real, verified hook.

## Required inputs

Before drafting, confirm the skill has:

- `candidate_name` — handle or real name
- `product_summary` — one or two sentences about what they ship
- `specific_detail` — the verified personalization hook, quoted or paraphrased from the actual source. **This is the most important input.** If it's missing or vague, ask for it. Don't fabricate one.
- `channel` — the surface the message goes through (email / platform comment / DM / contact form)
- `send_type` — `FIRST_CONTACT` or `CHASE_1`
- `prior_hook` — only when `send_type=CHASE_1`. The hook the original send used, so the chase doesn't repeat the same angle.
- `subject_line_needed` — boolean; true when channel is a site contact form or email

If any required input is missing, ask one short question to get it. Don't guess.

## Output format

Always emit three blocks, in this order:

```
=== DRAFT MESSAGE ===
To: [candidate_name] via [channel]
[Subject: ...]   (only when subject_line_needed)

[Message body]

=== BLUFF FILTER REPORT ===
Status: PASS | FLAGGED
Flagged content (if any): "[quoted span]" — Reason: [which rule it violated]
Recommended fix: [concrete replacement using only allowed claims]

=== PRE-SEND CHECKLIST ===
[ ] Source URL still live (verify before send)
[ ] Your product URL still up
[ ] Specific detail still matches source
```

Word counts (count the body — the part between the `To:` line and `=== BLUFF FILTER REPORT ===`):

- FIRST_CONTACT body: **150–180 words. Target the middle of that range (~165).** If a draft comes out at 190+, cut a scene-setting sentence before emitting — most overshoots happen in the bridge move, which tends to want a third explanatory sentence the message doesn't need.
- CHASE_1 body: **100–130 words. Target ~115.** Chases overshoot when they re-explain the candidate's product instead of trusting that the original send already did that work. Trim re-explanation; lead with the new angle.

Before emitting, count words and check against the range. If over, cut — don't ship long. Outreach readers skim; every sentence past the range loses one. The discipline is part of the format.

The checklist always appears, even on PASS — it's a reminder, not a conditional warning.

## Structural spine — FIRST_CONTACT

Every first-contact message has exactly four moves, in this order. The point isn't to be rigid; it's that this sequence is what makes the message read as "founder talking to founder" instead of "vendor pitching prospect."

**1. Opener (1–2 sentences) — the verified specific detail.**

Lead with something only someone who actually read their post/site could say. The opener should make the reader think "wait, this person actually looked at my work."

What kills the opener: generic "Hi, I'm [Name] and I run a similar product." Cut anything that could have been written without reading the source.

**2. Bridge (2–3 sentences) — their shape fits a buyer they're not selling to.**

The thesis: their product is exactly the shape some buyer wants, but their current setup doesn't serve that buyer. Cite a *specific* use case for *their* product — not a generic claim. The specificity matters because it shows you've actually thought about who their underserved buyer is.

Use `operator_wedge_sentence` from config as the anchor for this section. The wedge is what you uniquely offer; the bridge applies it to this specific candidate.

**3. Proof sentence (1–2 sentences) — what you've already shipped.**

Use `operator_proof_template` from config verbatim. This is the canonical, bluff-clean sentence the operator has pre-written. Do not rewrite it on the fly. Do not embellish. The proof sentence's job is to land the credibility claim cleanly without overclaiming.

If the operator's proof template includes a candid admission (e.g., "volume's still low"), keep it. That admission signals you're not bluffing, which makes the rest of the message land harder.

**4. Soft ask (1–2 sentences) — light, optional, founder-to-founder.**

Use `operator_close_template` from config verbatim. The close should be cheap for the candidate to say yes to and equally cheap to ignore. Don't replace with "Worth a 15-min call?" or similar boilerplate that sounds like every other vendor pitch.

## Structural spine — CHASE_1

Same four moves, but compressed (100–130 words) and — critically — using a **different angle** than the original send. If the first send opened with the candidate's structured taxonomy, the chase opens with their distribution problem, or whatever other verified hook exists.

The reason: a chase that repeats the original framing reads like a template re-send. A chase that hits a fresh angle reads like the operator actually thought about why the first message might not have landed.

`prior_hook` tells the skill what *not* to do. Whatever angle that hook used, pick a different one from the verified specifics.

## Bluff-prevention filter — the most important section

Before emitting the draft, scan the body against the rules below. If anything in the draft violates a rule, set Status to FLAGGED, quote the violation, name the rule, and propose a concrete fix using only allowed claims.

The reason this matters: the operator's only durable advantage in this outreach is that they're not bluffing. Outreach readers have heard a thousand pitches with fabricated metrics. The moment a single claim doesn't survive a sanity check, the whole message is dead — and worse, the operator looks like every other founder who lies. The filter exists to protect that advantage.

### Allowed claims

Pull from `allowed_claims` in the operator's config. These are facts the operator has verified about themselves and their product. Use only these.

Plus universally allowed framings:
- Subjective statements about *the operator's own* experience ("the pattern is identical," "the rails work," "cleaner than I expected").
- First-person singular construction (the operator is one person talking to another person).

### Forbidden claims

Pull from `forbidden_claims_patterns` in the operator's config. These are categories the operator cannot substantiate.

Plus universally forbidden patterns:
- Specific volume numbers without a verified source ("X customers," "N calls/day," "$Y MRR").
- Retention or churn data the operator doesn't track.
- Comparative observations across customers ("our users prefer X").
- Any claim in first-person plural that implies a team or customer base when neither exists. The operator is one founder talking to another — "we" is almost always wrong.
- Specific timing claims about other people's results ("founders who did this saw X within Y weeks").

### Phrases to scan for and flag

Run a literal search over the draft body for these substrings. Any hit is an automatic FLAGGED status:

- "we've seen"
- "our data shows"
- "we're seeing"
- "customers tell us"
- "% of"
- "MRR" / "ARR"
- "[number] users / customers / agents"
- "[number] calls per"
- "founders who" (when followed by a results claim about them)
- Any dollar amount that isn't in `allowed_claims`
- Any percentage that isn't in `allowed_claims`

When something flags, propose a fix that uses only allowed claims.

### Example fix pattern

- Bad (flagged): "we've seen agents pay $0.30 per query for this kind of data"
- Fix: "[use operator's verified single price] — volume's still low, but the rails work"

The replacement will usually be shorter and weaker-sounding than the bluff. That's the point. A bluff that breaks the operator's credibility costs more than a true claim that lands flat.

## Examples

### Example 1 — FIRST_CONTACT structural example

**Input:**
- candidate_name: a verified candidate from `persona-c-verify`
- product_summary: their one-line product description
- specific_detail: the verified personalization hook from the verification report
- channel: their preferred channel
- send_type: FIRST_CONTACT

**Expected output structure:**

```
=== DRAFT MESSAGE ===
To: [candidate] via [channel]

[Opener: the verified specific detail, in the operator's voice. 1-2 sentences.]

[Bridge: their shape fits an underserved buyer. Use operator's wedge sentence. Name the specific use case. 2-3 sentences.]

[Proof: operator's canonical proof template, verbatim from config. 1-2 sentences.]

[Soft ask: operator's canonical close template, verbatim from config. 1-2 sentences.]

=== BLUFF FILTER REPORT ===
Status: PASS

=== PRE-SEND CHECKLIST ===
[ ] Source URL still live (verify before send)
[ ] Your product URL still up
[ ] Specific detail still matches source
```

### Example 2 — BLUFF FILTER TRIP

**Input includes a draft claim:** "we've seen [N] users pay $X per query for this kind of data"

**Expected behavior:** FLAGGED. Quote the violating span, cite each rule it triggers, and propose a replacement that uses only allowed claims.

**Skill's output:**

```
=== DRAFT (not sent — flagged) ===
[draft body suppressed — flagged before emission]

=== BLUFF FILTER REPORT ===
Status: FLAGGED

Violation: "we've seen [N] users pay $X per query for this kind of data"

Rules triggered:
  - Forbidden phrase: "we've seen" (implies customer/volume data the operator doesn't have)
  - Fabricated price: $X is not in operator's allowed_claims
  - Fabricated volume claim: "[N] users pay" implies a customer base the operator isn't operating

Proposed replacement (uses only allowed claims):
  "[operator's verified price claim from config] — volume's still low, but the rails work"

Why this replacement is safe:
  - Verified price is in allowed_claims
  - "volume's still low" is an explicit allowed candid admission
  - "the rails work" is allowed subjective framing about operator's own experience
  - No customer count, no comparative observation, no first-person plural
```

The replacement is shorter and weaker-sounding than the bluff — and that's the point. A bluff that breaks the operator's credibility costs more than a true claim that lands flat.
