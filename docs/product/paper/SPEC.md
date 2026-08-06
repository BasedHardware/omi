# PAPER — Product Spec

> One page. Once a day. Built from what you lived, not what you clicked.

Framed against `FOUNDER-GUIDELINES.md`. Engineering detail lives in the module docstrings
under `backend/utils/paper/`, starting with the package `__init__.py`.

---

## The friction

Stated in the user's words, without the product name:

> "I have to tell news apps what I care about. I don't actually know what I care about, and
> the things I actually thought about today never make it in."

Every personalization system on the market reads **stated preference** (topics you picked)
or **revealed preference by click** (what you tapped, which is mostly what was loudest).
Nothing reads **lived context** — the thing you brought up four times today, the question
you asked and never answered, the person you keep meaning to call.

## The product

Each morning, one finite page. Built from what Omi and Context for Claude already captured:
conversations, unresolved questions, decisions, people, recurring preoccupations.

Over time it learns your **views**, not just your topics — and starts printing the strongest
argument *against* you when you've been one-sided, and following up on threads you dropped.

No feed. No scroll. No infinite anything. It ends.

## ICP

Not "people who like news." Specifically:

**The over-contexted operator.** 24–38, works in tech or adjacent, talks for a living
(calls, meetings, walks). Already runs ambient capture, or is one nudge away — owns an Omi,
Limitless, or runs Context for Claude. Has more context about their own life than they can
hold, and no way to see it.

Identity markers, which is what makes them a cult rather than a demographic:

- Has deleted an algorithmic app and reinstalled it. More than once.
- Pays for The Browser, Stratechery, Perfectly Imperfect, or all three.
- Owns physical objects as identity signals: Field Notes, Remarkable, a film camera.
- Calls the incumbent **"slop"** or **"the feed."** That vocabulary is the tell.

**Where they already gather:** r/quantifiedself, Hacker News, the ambient-hardware Discords
(Omi / Limitless / Bee), digital-minimalism TikTok, the Analog/Field Notes ecosystem.

**Explicitly not the ICP:** general news readers, productivity-tool collectors, and anyone
who wants *more* information. This product's promise is less.

## Positioning

**Every other news app reads what you click. This one reads what you lived.**

| | Reads | Ends? | Physical |
|---|---|---|---|
| gpt-newspaper, Actualia | topics you typed | no | no |
| Artifact, Google Discover | what you clicked | never | no |
| paper-console, daily-report | RSS/calendar you configured | yes | yes |
| **PAPER** | **what you lived** | **yes** | **yes** |

The gap nobody occupies: **ambient input + finite output + longitudinal view-learning.**
Cluster 1 personalizes off stated preference. Cluster 2 prints, but off config files.
Neither reads a life.

## The edition

Five sections. Hard stop. This is the whole product and it does not grow.

| Section | What it is | Source |
|---|---|---|
| **Yesterday** | Where the day went, what you decided, and the idea you raised and dropped. | Conversations + screen activity + daily summary |
| **Today** | What is actually on you, before anyone asks. | Google Calendar + open action items |
| **Newsletters** | Everything you subscribed to, deduplicated to one line per story. | Gmail bulk mail |
| **For you** | The papers and tools that move what you are working on. | arXiv + web, ranked against the interest profile |
| **The photo** | One real moment from yesterday, drawn. | The day's own record |

**Context is the ranking function, not the content.** Every personalization system reads
stated preference — topics you typed, links you clicked. The interest profile is derived
from what you actually discussed and had on screen, so the queries move when your work
moves and nobody edits a config file. That is the whole difference from a feed reader.

**No source, no print.** Anything asserted about the outside world carries where it came
from, enforced in the types rather than asked for in a prompt. A photo with no real moment
behind it is decoration, and decoration presented as memory is a fabrication.

**A dead source costs one section, never the edition.** Every run reports per-source
health and prints what failed, because a paper that has quietly had no Gmail for a
fortnight looks exactly like a paper about a quiet fortnight.

Then: `END OF EDITION`. The rule at the bottom is a feature.

**Length is a hard constraint, not a target.** One page. If a block has nothing worth
printing, it is omitted — never padded. A short edition is a good edition.

## The entertainment layer

Per guideline 2: named, native, and unremovable.

1. **You are the protagonist.** Your day, set in a masthead, in a typeface that means
   "this is the record." The pleasure is being taken seriously by an object.
2. **The issue number is the streak.** `NO. 47` means forty-seven editions. It is a streak
   counter that is also just what newspapers have always printed. Cannot be removed without
   the newspaper stopping being a newspaper. No badges, no confetti, no points.
3. **The photo makes it an object.** One drawn moment from a real day, captioned with the
   thing it depicts. It is the part people screenshot, and it is the reason the page reads
   as a paper rather than a report.

**The shareable unit** is the masthead + your headline + the photo — screenshot-native by construction,
which is the distribution mechanism. Nobody screenshots a dashboard.

## Pricing

Gate on **personalization depth**, not volume or feature count.

| | Free — *The Brief* | Paid — *The Edition* |
|---|---|---|
| Yesterday | ✅ | ✅ |
| Today | — | ✅ |
| Newsletters | — | ✅ |
| For you | — | ✅ |
| The photo | — | ✅ |
| Longitudinal view tracking | — | ✅ |

**$12/mo, or $96/yr.** No lifetime plan (guideline 6). Priced for mindshare, which is
defensible here only because the PDF tier's marginal cost is near zero (guideline 4).

The free tier is deliberately a *real* product, not a crippled demo: your day, one block.
It is the proof that the capture works, which is the only thing the paywall needs to sell.

## CTAs

One primary CTA site-wide. No competing asks.

- **Primary:** `Get tomorrow's edition` — time-anchored, unambiguous, no noun to decode.
- **Secondary:** `See what's in one` → the five blocks, named. (A real sample edition is the
  stronger version of this and is the next iteration — it is not shipped yet because the only
  real editions available contain personal data, and a fabricated one would violate the
  never-fabricate rule on the marketing surface as much as in the product.)
- **Paywall moment:** after the third free edition, on the page itself:
  `Today's edition is ready. →` — the ask arrives as content, not as an interstitial.

Rejected: "Get started" (says nothing), "Sign up free" (leads with the transaction),
"Learn more" (an admission the page failed).

## Build sequence

Guideline 6 — the honest COGS story — dictates the order.

1. **PDF/HTML edition, delivered by email.** Near-zero marginal cost. Validates the
   personalization, which is the only genuinely uncertain part. ← **this PR**
2. **Measure whether people print it themselves.** That is the demand signal for hardware.
   Not a survey — actual print events.
3. **Thermal printer** only after (2) is positive. Fork paper-console; swap its channel
   system for one feed.
4. **Mail delivery** only if (3) proves out. This carries real operational weight and is
   the last thing to commit to, not the first.

The renderer emits plaintext alongside HTML from day one so step 3 is a driver swap, not a
rewrite. That is the only concession made to unbuilt hardware.

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| **Print logistics** — paper, supply, delivery | High, real | Deferred to step 3–4. Also the moat: nobody clones this in a weekend. |
| **Cold start** — a new user has no history, so the interest profile is unusable and For you is empty | High | Sections are omitted, never faked. The edition is honestly short until there is signal, and the profile reports itself unusable rather than ranking against a guess. |
| **Creepiness** — the paper knows too much | Medium | Print only what the user said. Every claim traces to a conversation. No inference presented as fact. |
| **Ambient capture dependency** | Medium | Real constraint, and also filter 4 — it's why this isn't cloneable. |

## Non-negotiables

- **Never fabricate.** Every line traces to captured context. An empty block is omitted.
  A wrong claim about someone's life destroys the product permanently.
- **Finite.** No block that grows. No "read more." No archive scroll on the page itself.
- **No purple** anywhere (`INV-UI-1`). This product is black ink on paper white regardless.
