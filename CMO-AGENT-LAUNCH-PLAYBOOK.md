# Product Launch Playbook → CMO Agent Feature Spec

A reusable system for generating a 1-week go-to-market launch plan for *any*
new product. Part methodology (how the decision actually gets made), part
template, part implementation spec for building it as a feature in a CMO
agent.

stackd.cc is used throughout as the worked example, but everything here is
product-agnostic.

---

## PART 0 — The core insight

**A launch plan is not a checklist. It's a decision tree that hangs off one
classification: what kind of product is this?**

Get the product *type* right and everything else (growth engine → success
metric → channels → sequencing → what to avoid) falls out deterministically.
Get it wrong and you produce confident, generic, useless advice ("post on
all your socials!").

The agent's job is: **classify → derive → sequence → instrument → decide.**

---

## PART 1 — What I actually did (the reasoning chain, worked example)

This is the exact sequence of decisions for stackd.cc, so the agent can
learn the *shape* of the reasoning, not just the output.

1. **Classified the product.** stackd.cc = "pick your AI tools, rank them,
   get a shareable card." That's a *viral-artifact / generator* product
   (same family as Spotify Wrapped, "rate my setup"). NOT a retention app.

2. **Derived the growth engine from the type.** Viral-artifact → growth
   comes from the *artifact spreading*, not from the founder's audience or
   from ads. The shared card IS the advertisement.

3. **Derived the success metric from the growth engine.** If growth =
   artifact spread, the metric is the **viral coefficient K = new artifacts
   created per artifact shared.** Retention/DAU is the *wrong* yardstick —
   flagged this explicitly so the founder wouldn't feel like a failure when
   traffic decays (which is expected, by design).

4. **Killed the wrong channels early.** Derived that **paid ads are
   irrational** here: free + one-time-use = no LTV = spend never recovers.
   Removed it before the founder could waste money. (A B2B SaaS would get
   the opposite advice.)

5. **Neutralized the founder's stated weakness.** Founder said "low Twitter
   reach." For a viral-artifact product that *doesn't matter* — Reddit/HN
   don't weight follower count, and the artifact spreads on its own. Turned
   a perceived weakness into a non-issue and redirected energy to the
   channel they CAN win (they said they can make video → Instagram/TikTok).

6. **Sequenced channels by three rules** (see Part 4): forgiving-first,
   preserve one-shots, avoid crowd saturation. Produced: Reddit soft →
   Instagram → Show HN → Product Hunt → niche → amplify → retro.

7. **Instrumented before launch.** UTM scheme per channel + the events that
   map to the metric (already wired: card_created, card_remixed) + a manual
   daily scorecard + a pre-launch "does the link unfurl" gate (the single
   point of failure for a share product).

8. **Wrote decision rules** so the data drives the next move: high K → keep
   pushing the winning channel; high traffic + low conversion → fix the
   funnel, not the channel; quiet everywhere → pivot to SEO long-tail.

That 8-step chain is the reusable algorithm. The rest of this doc
generalizes each step.

---

## PART 2 — Intake (what the agent must learn before planning)

The agent cannot plan until it has these. Ask them up front (or infer from
a provided URL / description, then confirm).

```yaml
product:
  one_liner: "what it does in one sentence"
  category: "free text — the agent classifies in Part 3"
  pricing: "free | freemium | one-time | subscription | usage-based"
  has_retention_loop: true|false      # does a user have a reason to return?
  primary_artifact: "the thing a user produces/shares, if any"
audience:
  who: "role / demographic"
  where_they_gather: ["subreddits, communities, platforms"]
  trigger: "what makes them look for this"
founder:
  reach: { twitter: low|mid|high, other: "..." }
  can_produce: ["video", "writing", "design", ...]
  time_per_day: "hours available during launch week"
  budget: "0 | small | funded"
assets_ready:
  landing_page: true|false
  og_unfurl_works: true|false          # CRITICAL for any share product
  analytics_installed: true|false
  demo_or_video: true|false
goal:
  primary: "signups | cards | stars | revenue | awareness"
  timeline: "launch date"
```

**Rule:** if `og_unfurl_works` is unknown and the product has a
`primary_artifact`, the agent must make verifying it the #1 pre-launch task.
A share product with a broken unfurl is dead on arrival.

---

## PART 3 — Product-type → strategy map (the core IP)

The lookup table. The agent classifies the product into one row, and the
row dictates engine, metric, channels, and anti-patterns.

| Type | Growth engine | North-star metric | Loop/secondary metric | Primary channels (in order) | Skip / avoid |
|---|---|---|---|---|---|
| **Viral artifact / generator** (Wrapped-style, "rate my X") | Artifact spreads on share | Total artifacts created | Viral coefficient K = re-creates ÷ creates | Reddit → short-form video (IG/TikTok) → Show HN → Product Hunt → niche communities | Paid ads, retention/DAU metrics, follower-count dependence |
| **Dev tool / API / library** | Content + community + DX word-of-mouth | Signups → activation (first successful use) | Time-to-first-value | Show HN → Reddit (niche tech subs) → docs/SEO → dev Discords → DevRel content | Consumer social, influencer spend, hype with no docs |
| **B2B SaaS** | Outbound + content + demos | Trials → paid conversion | CAC : LTV ratio | LinkedIn → SEO/comparison content → targeted communities → cold outreach → webinars | Reddit self-promo (gets nuked), TikTok, mass PH reliance |
| **Consumer app** | Virality + influencer + app-store | Installs → D1/D7 retention | K-factor + retention curve | TikTok/IG/Reels → influencer seeding → Product Hunt → app-store optimization | HN (wrong crowd), long-form blog SEO early |
| **Open source** | Community + GitHub gravity | Stars → contributors | Issues/PRs from outside | Show HN → Reddit (r/opensource, lang subs) → GitHub trending → Discord → conference talks | Paid ads, "growth hacks", closed roadmap |
| **Marketplace / network** | Seed the constrained side first | Liquidity (match rate) | Repeat transactions | Direct/manual supply seeding → niche communities → targeted content | Broad paid acquisition before liquidity exists |

**How the agent uses this:** pick the closest row. If the product spans two
(e.g. an open-source dev tool), merge: union the channels, take the
stricter anti-patterns, and let the *monetization* model decide the metric
(no revenue → engagement/spread metric; revenue → conversion metric).

---

## PART 4 — Channel selection + sequencing logic

Picking channels is Part 3. *Ordering* them is its own skill. Three rules:

1. **Forgiving-first.** Open in a high-feedback, low-stakes channel
   (r/SideProject, a small community) to catch bugs and bank social proof
   *before* spending irreplaceable shots. You want testimonials in hand
   before the big day.

2. **Preserve one-shot channels.** Some channels you realistically fire
   *once* per product: **Show HN and Product Hunt.** A given URL gets one
   good HN run; PH launches once. Never spend these on an unproven funnel.
   Sequence them *after* the funnel is validated (good landing→action %).

3. **Avoid crowd saturation.** If the same people see you on Reddit, then
   PH, then HN within 48h, the later posts get "seen this already" fatigue.
   Order so non-overlapping crowds come first (e.g. Instagram audience ≠ HN
   audience), keeping each one-shot channel *fresh* to its crowd.

**Founder-reach modifier:** if founder reach is low, weight toward
no-follower-required channels (Reddit, HN, community posts) and the artifact
loop. If reach is high, front-load owned audience (their list, their
Twitter) on Day 1 for an early spike.

**Repeatable vs one-shot tag** (the agent should label every channel):
- *Repeatable* (use weekly forever): Reddit, short-form video, content/SEO,
  community engagement, newsletters.
- *One-shot* (spend deliberately): Show HN, Product Hunt, big launch email,
  press embargo.

---

## PART 5 — The Week-1 template (parameterized)

The agent renders this skeleton, filling `{{...}}` from Parts 2–4. Keep the
*structure* constant; vary the *content* by product type.

```
DAY 0 (pre-launch gate):
  - Verify {{artifact}} unfurls correctly across share surfaces (if share product)
  - Verify mobile flow end-to-end
  - Verify analytics fires the {{north_star_event}}
  - Confirm cold-visitor view looks alive (seed data if needed)
  - Build UTM links + the {{n}} analytics insights

DAY 1 — {{forgiving_channel}}:
  - Goal: catch bugs, first {{X}} {{artifact}}s, 2–3 testimonials
  - {{post_format}}; reply to every comment <3h

DAY 2 — {{founder_strength_channel}}:
  - Lean on what the founder CAN do (video/writing/design)
  - {{format}} that ends in the share-loop CTA

DAY 3 — {{primary_one_shot}} (usually Show HN or PH):
  - Fire the big swing once funnel is proven + you have proof
  - Camp the thread; never ask for upvotes

DAY 4 — {{secondary_one_shot}}:
  - Ride momentum from Day 3 into the controlled/schedulable channel

DAY 5 — niche communities + newsletters:
  - High-intent pockets the big channels missed

DAY 6 — amplify the winner:
  - Read analytics → pour fuel on whatever minted the most {{north_star}}

DAY 7 — retrospective post (is itself content):
  - "What happened in 7 days" with real numbers; apply decision rules
```

---

## PART 6 — Tracking system

### Metric selection (by product type — from Part 3)
The agent picks ONE north-star + ONE funnel + ONE loop metric. Don't track
20 things. Examples:
- Viral artifact: north-star = artifacts created; funnel = visit→create;
  loop = K (re-create ÷ create).
- B2B SaaS: north-star = trials; funnel = visit→trial→paid; loop = CAC:LTV.

### Instrumentation
- **UTM scheme:** `?utm_source={channel}&utm_medium={surface}&utm_campaign=launch`,
  one tagged link per channel. Analytics that capture initial UTM/referrer
  as person properties (PostHog, etc.) let you break the north-star event
  down by *what actually drove creators*, not just clicks.
- **Events:** instrument the funnel steps + the loop event *before* launch.
- **Daily scorecard (manual, 2 min/night):** `day | channel | visits |
  {{north_star}} | {{loop_metric}} | top_referrer`.

### Decision rules (this is what makes it an *agent*, not a doc)
```
if loop_metric (K) >= threshold_high:        # self-sustaining
    → keep cadence on the winning channel; reduce manual push
elif traffic_high and funnel_pct < threshold_low:
    → DON'T push more traffic; fix the landing→action handoff first
elif all_channels_quiet:
    → pivot from push to pull: publish SEO/comparison content, let
      search/LLM citation accrue (slow-burn annuity)
else:
    → repeat the best repeatable channel; re-test a one-shot only with a
      materially new angle
```

---

## PART 7 — Universal guardrails (don't-do list)

- ❌ Paid ads for a no-LTV product (free/one-time). Never recovers.
- ❌ Mass cross-posting the same link to many subreddits at once → shadowban.
- ❌ Asking for upvotes on HN/PH → flagged.
- ❌ Buying followers/engagement → vanity, zero conversions.
- ❌ Firing all channels Day 1 → wastes one-shots on an unproven funnel.
- ❌ Tracking retention on a one-time-use product → wrong yardstick.
- ❌ Launching with a broken OG unfurl on a share product → instant death.

---

## PART 8 — Building this as a CMO-agent feature

How to turn the above into a shipped feature. This is the spec.

### 8.1 Feature shape
A `launch_plan` capability that runs a short **workflow**, not a single
prompt:

```
State machine:
  INTAKE  → collect/confirm the Part 2 schema (ask only what's missing)
  CLASSIFY→ map to a Part 3 row (+ merge logic for hybrids)
  PLAN    → render positioning + channel sequence + Week-1 template + tracking spec
  ASSETS  → (on demand) generate per-channel copy (Reddit post, Show HN, PH listing, video script)
  TRACK   → daily check-in: ingest scorecard / analytics, apply Part 6 decision rules,
            output "today's move"
```

### 8.2 Inputs / outputs
- **Input:** the Part 2 YAML (or a URL the agent scrapes + a few confirm Qs).
- **Outputs (structured, so the UI can render + the agent can act on them):**
  ```json
  {
    "classification": "viral_artifact",
    "growth_engine": "...",
    "north_star": "cards_created",
    "loop_metric": "K = remix/create",
    "positioning": { "tagline": "...", "one_liner": "...", "share_hook": "..." },
    "channels": [ { "name": "reddit", "type": "repeatable", "day": 1, "why": "..." }, ... ],
    "tracking": { "utms": {...}, "insights": [...], "scorecard_fields": [...] },
    "decision_rules": [...],
    "guardrails": [...]
  }
  ```

### 8.3 Tools the feature should call
- **Analytics read** (PostHog/GA/Plausible API) → power the daily TRACK
  state with real numbers instead of asking the human.
- **Scheduler** → drop the Week-1 plan into a calendar / send daily nudges.
- **Draft generator** → the ASSETS state writes channel-native copy.
- **Web search** → find the right subreddits/communities + their rules per
  product (don't hardcode; communities change).

### 8.4 System-prompt seed for the launch sub-agent
> You are a launch strategist. Before giving any advice, classify the
> product into one growth archetype (viral-artifact, dev-tool, B2B SaaS,
> consumer, open-source, marketplace). Everything you recommend —
> success metric, channels, sequencing, what to avoid — must follow from
> that classification, not from generic best practice. Be specific and
> opinionated. Kill channels that don't fit (e.g. paid ads when there's no
> LTV). Never recommend firing one-shot channels (Show HN, Product Hunt) on
> an unvalidated funnel. Always instrument tracking before launch, and tie
> every recommendation to one north-star metric. State plainly when the
> founder's stated weakness (e.g. low follower count) doesn't actually
> matter for their product type.

### 8.5 Human-in-the-loop gates
- After CLASSIFY: confirm the archetype with the user (one wrong
  classification poisons the whole plan).
- Before ASSETS go out: human approves copy (brand voice, claims).
- TRACK state proposes the next move; human executes (the agent shouldn't
  auto-post).

### 8.6 What makes this defensible vs "ChatGPT, write me a launch plan"
- It's **archetype-driven**, so the output is non-generic.
- It **closes the loop**: plan → instrument → ingest data → next move.
  Most "launch plan" tools stop at the plan.
- It **kills bad spend** (the don't-do list is enforced, not optional).
- It's **constraint-aware**: adapts to founder reach, budget, skills.

---

## TL;DR for the agent build

1. Make `CLASSIFY` the first real step — it's the whole lever.
2. Ship the Part 3 table as structured data the agent reasons over.
3. The killer feature isn't the plan, it's the **daily TRACK loop** with
   decision rules wired to real analytics.
4. Enforce the guardrails as hard rules, not suggestions.
5. Always confirm the classification with a human before planning.
