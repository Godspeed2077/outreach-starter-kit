# I built an outreach kit for solo founders that won't let me bluff

Short version: three Claude skills plus a state file plus a Python inbox agent that watches Gmail/GitHub/dev.to for replies. Everything I built during my own validation sprint, generalized so anyone running a solo outreach push can drop it in.

The thing that's different about this kit isn't the automation. It's the discipline the automation enforces.

**Every send requires a verified specific hook.** The drafting skill asks for the personalization detail before it'll write the message. If the detail is vague, it asks again. Generic "Hi, I'm building a similar product" openers are blocked at the input layer.

**Every claim runs through a bluff filter.** You write your allowed claims and your forbidden claims patterns at setup. The drafter scans every output against them. The first fabricated metric flags the whole draft and proposes a fix using only allowed claims. I built this because I caught myself nearly sending "we've seen agents pay $0.30 per query" on a sprint where I had near-zero agent traffic and no comparative pricing data. The filter exists so that doesn't happen by accident.

**Every action gets logged through a Python script that does preservation checks.** The state file is append-only. It has structured sections (Sent Log, Active Conversations, Pattern Notes, Closed-loop). Every send, reply, chase, close is mediated by a script that verifies the file grew the way it should and aborts before writing if anything looks wrong. I built this after watching a naive LLM Edit silently truncate the trailing section of a long markdown file. Never again.

**The inbox agent watches three channels (Gmail, GitHub, dev.to) for new replies, drafts responses, and pushes them to Telegram for one-tap Send/Edit/Skip.** Every approval surface alternative is documented as a clear extension point.

## What the kit is not

It's not a marketing automation tool. It does not blast messages. It does not "scale personalization" by templating someone's first name. The kit's whole point is that personalization is real, not templated, and that you can't fake your way past technical readers who've seen a thousand pitches.

If you're a solo founder running cold outreach to other founders or operators, and you want the discipline of an institutional sales motion without the institutional headcount, this is for you.

If you're trying to send 1000 emails a day to a scraped list, this kit will actively work against you.

## How to use it

Five steps, roughly:

1. Drop the three skills into your Claude environment.
2. Copy the state file template and fill in your sections (your schedule, your voice rules, your channel discipline, your runway context).
3. Create the kit config with your product details, allowed claims, forbidden claims, and target persona definition.
4. Set up the inbox agent (optional but recommended): pip install requirements, fill in credentials for Telegram + whichever channels you use.
5. Wire up the scheduled tasks for the morning briefing and the hourly inbox watcher.

Full setup guide is in the README.

## Why I'm publishing this

I built it for myself, used it for two months, and an LLM advisor flagged that the kit might be more valuable than the product it was supporting. I'm not sure if that's true, so I'm publishing it as a 30-day test. The success criterion is concrete: at day 30, I look at downloads + feedback. If someone surfaced a concrete upgrade they'd pay for, I keep building. If not, I scratch it and go back to my own primary work.

If you try it and have thoughts, tell me. The kit is open source. The architecture is intentionally simple — read the code, fork it, change what you need.

## Links

- GitHub repo: [repo URL once published]
- Skill marketplace listing: [marketplace URL once submitted]
- Setup guide: see README.md in the repo
