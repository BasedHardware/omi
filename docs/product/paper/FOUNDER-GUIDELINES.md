# Founder Operating Guidelines

Decision rules for consumer product work, distilled from the Cal AI / consumer-subscription
playbook and adapted to what we can actually verify. Used to frame PAPER (`SPEC.md`).

## Scope warning, read first

The source playbook is the **consumer subscription app** genre: App Store distribution,
paywall funnels, UGC and paid ads, web2app. It is battle-tested there. It does **not**
transfer 1:1 to B2B SaaS, developer tools, or hardware. Where a rule is genre-bound, it is
marked ⚠️. Applying ⚠️ rules outside the genre is how teams cargo-cult themselves into a
worse business.

---

## 1. The core mechanism

**Find a specific friction. Remove it completely. Do not improve it.**

This is the only rule that generalizes everywhere. Every other rule is downstream.

The test: can you state the friction in one sentence, in the user's own words, without
using your product's name? If you need a paragraph, you have a feature, not a product.

- ❌ "Makes news consumption more efficient."
- ✅ "I have to tell news apps what I care about, and I don't know what I care about."

## 2. Utility retains badly. Entertainment retains.

Every durable consumer app is an entertainment product wearing a utility costume. Utility
gets the download; the entertainment layer gets the 30th open. If nothing about opening
your product is *fun*, it churns regardless of how useful it is.

**Decision rule:** name the specific moment that is pleasurable, not merely useful. If you
can't name it, you haven't finished designing the product.

**Do not** bolt on badges, points, and confetti. That reads as manipulation and ages
badly. The entertainment must be *native to the form* — a mechanic that only makes sense
because of what the product is.

> Applied to PAPER: the issue number in the masthead (`NO. 47`) *is* the streak. It is
> gamification you cannot remove without the newspaper stopping being a newspaper.

## 3. Pick niches with identity, not need

Cult audiences convert and evangelize; "everyone needs this" converts nobody. The
qualifier is not passion, it is **identity** — does membership say something about who the
person is? Identity groups have gathering places, vocabulary, and status games, which is
what actually gives you cheap distribution.

**Decision rule:** can you name the three places this audience already gathers, and the
insult they'd use for the incumbent product? If not, it's not a cult, it's a demographic.

## 4. Price for mindshare first, margin second ⚠️

Becoming the default answer in a category is worth more than per-user revenue early. You
can raise prices on a category you own; you cannot buy back a category you priced yourself
out of.

**Caveat the playbook omits:** this only holds when retention is genuinely good and
marginal cost per user is near zero. If you have real COGS — inference spend, *paper and
shipping* — underpricing does not buy mindshare, it buys a fast death. Price to at least
cover variable cost, then optimize for share.

> Applied to PAPER: the PDF tier has near-zero marginal cost and should be priced for
> share. Anything involving physical paper has real COGS and must not be.

## 5. Own the whole funnel or you own nothing

Distribution, onboarding, and paywall are one system. Great traffic into a bad paywall is
just an expensive way to donate money to Meta. Optimize them together or don't buy traffic.

**Corollary:** when you don't own the distribution channel, you are renting your business
from whoever does. Budget for the day the rent goes up.

**Benchmarks to hold yourself to** (consumer subscription genre ⚠️):

| Metric | Target |
|---|---|
| View → download | 5 per 1,000 |
| Users reaching paywall | 75%+ |
| Paywall → paid | 10%+ |

Treat these as *diagnostics*, not goals. Missing view→download is a creative problem.
Missing paywall-reach is an onboarding problem. Missing paywall-conversion is a
positioning problem. Each has a different fix; the numbers tell you which one you have.

## 6. Skip lifetime plans ⚠️

Legal exposure, messy revenue recognition, and they complicate acquisition diligence — for
revenue that rarely beats annual. Annual is the ceiling.

## 7. The founder does the marketing first

Not forever, but first. If you are unwilling to learn distribution personally, the consumer
app space will not reward you. Delegating a function you have never done means you cannot
evaluate the person doing it.

**Corollary on hiring:** be skeptical of "Head of Growth at [big app]" résumés. People who
are genuinely great at growth get retained or go build their own thing. Test with paid
trial work on your actual funnel, not with interviews.

## 8. Creative is the highest-leverage hire

A great designer compounds every other channel simultaneously — ad creative, onboarding,
paywall, App Store screenshots, organic shareability. AI has raised the floor on design
but not the ceiling on taste. Taste is still the scarce input.

## 9. Earn distribution before buying it

UGC and slideshows are harder to run profitably than influencers and paid ads — and that
difficulty is exactly why they're underpriced. Big-name influencer spend mostly buys
vanity reach into an audience with no trust transfer to you.

**Sequence:** creator volume and velocity first, paid ads second, big names approximately
never.

## 10. Expect the grind, not the story

Cal AI made ~$800/month for its first year. The story compresses 18 months of unglamorous
work into a paragraph. Plan for the duration, not the highlight reel.

---

## Screening filter for new ideas

An idea has to clear all six to be worth building. Applied to PAPER:

| # | Filter | PAPER |
|---|---|---|
| 1 | **One-sentence friction, in the user's words** | "I don't want to tell an app what I care about." ✅ |
| 2 | **Cult niche with a gathering place** | Screen-fatigued / quantified-self / ambient-capture crowd. Already evangelizes physical objects. ✅ |
| 3 | **Native entertainment mechanic** | Issue number as streak; you are the protagonist of the front page. ✅ |
| 4 | **Not cloneable in a weekend** | Requires an ambient capture pipeline, not an API key. ✅ |
| 5 | **Believable acquirer** | Anyone building consumer hardware around memory or presence. ✅ |
| 6 | **Honest COGS story** | PDF tier ~free. Physical tier has real operational weight — *this is the open risk*. ⚠️ |

Filter 6 is why the build sequence is PDF-first. See `SPEC.md`.

## Idea bench

Ideas generated against the same filter, kept for later. Each is scored on the binding
constraint rather than on excitement.

| Idea | Friction removed | Binding constraint |
|---|---|---|
| **PAPER** (building) | Curating your own news | Print COGS at scale |
| **The Argument** | You never hear the best case against your own view | Needs stance history to be non-generic — same engine as PAPER |
| **Loose Ends** | Dropped threads with people you care about | Very close to PAPER's Open Loops; likely a feature, not a company |
| **Standing Orders** | Re-explaining your preferences to every new AI tool | Distribution is hard; it's infrastructure, not a cult product |
| **The Annual** | Your year exists only as camera roll scroll | Once-a-year purchase = no retention loop; a gift product, not a subscription |

Note the pattern: three of the four alternates are features of PAPER, not companies. That
is the strongest evidence that PAPER is the right unit of work — it is the smallest thing
that is genuinely a product rather than a feature.
