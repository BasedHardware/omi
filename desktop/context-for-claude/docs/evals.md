# Answer-quality eval

```bash
python3 scripts/eval.py            # build if needed, run, print a summary, write dist/eval-results.json
python3 scripts/eval.py --only ranking
python3 scripts/eval.py --strict   # every failing critical check gates, including tracked ones
```

Stdlib only. About a quarter of a second. Exit `0` pass · `1` regression · `2` the harness could not
run.

## Why this exists alongside `swift test`

The unit suite proves the code does what it was written to do. It says nothing about whether the
*answers* are any good — and this product's central claim is epistemic: that a model reading a tool
result can tell **"this did not happen"** from **"this was not captured"**. That can only be checked
by asking the shipping binary real questions against a known corpus and reading what comes back.

So `scripts/eval.py` drives the real `context-for-claude-mcp` over stdio. It is the artifact users
get, not a reimplementation of it: if a change to `Queries`, `Tools`, or the renderer alters what a
model would read, the eval moves.

## How it stays hermetic

- **Its own temp home, seeded from scratch, deleted afterwards.** Never
  `~/Library/Application Support/ContextForClaude`.
- **`CFFIXED_USER_HOME` is what actually redirects the binary.** `HOME` alone does *not*:
  `FileManager.urls(for: .applicationSupportDirectory)` resolves the real home through the password
  database and ignores `HOME`. The first thing the run does is make the binary *print* the database
  path it opened (`status` reports it) and abort with exit `2` unless that path is inside the temp
  root. There is no mode in which this eval scores against real capture.
- **The child gets an explicitly built environment**, never the parent's, so no
  `CONTEXT_OMI_MCP_KEY` can leak in. With no credential reachable the Omi half never runs, which
  makes the run offline — and is itself the "one half could not be searched" condition several
  checks are about.
- **The fixture database is written directly** against the schema in `Sources/ContextCore/Store.swift`
  (migrations v1, v3, v4), in rollback-journal mode. Not WAL: GRDB's reader opens read-only, and a
  WAL database with no live writer has no `-shm` file that a read-only connection may create, so
  SQLite answers `error 14`. In production the app is the writer holding those sidecars open.

Four fixtures, because the interesting failures are about which of them a reader can tell apart:

| fixture | what it is |
|---|---|
| `main` | the seeded corpus, capture running, all permissions granted |
| `empty` | a valid database with zero rows, screen recording denied |
| `broken` | a real SQLite file with none of the tables — it *opens*, then every query fails |
| `nodb` | no database and no heartbeat: the honest first-run state |

## The corpus

Two disjoint time regions, both in the past, anchored to the run's own clock.

**Region A** is the content corpus — speech with a spread of confidence scores, a ranking cluster,
findability terms, and a dedup cluster. Its text is kept clean so nothing distorts bm25.

**Region B** is filter probes. Every row carries a unique nonce token, so `since` / `until` / `app`
are scored as exact set equality against rows the script placed itself rather than eyeballed from
prose.

## The classes

Weights say what the product is for. Filter integrity and confabulation are doubled because both
make a reader believe something false about the user's life; findability is the price of admission.

### `findability` (weight 1.5)
Seeded facts must come back. Terms appearing exactly once, terms in a window title versus buried
mid-OCR, terms matched only through the app name, multi-word queries, porter-stemmed inflections,
punctuated identifiers, possessives, trailing punctuation. **Chosen because** it is the floor: every
honesty property below is worthless on a corpus the tool cannot reach into.

### `no_confabulation` (weight 2.0)
Ask about things that were never captured and check the tool does not present nearest neighbours as
matches; check that "searched and found nothing" is worded differently from "could not search";
check that absence is never asserted outside the coverage window. Run against all four fixtures,
because *no database*, *unreadable database*, *empty database* and *populated database* are four
different amounts of evidence and only one of them licenses a negative result. **Chosen because** it
is the product claim. If this class regresses, the tool is actively worse than not existing —
a model will state as fact that something never happened.

### `ranking` (weight 1.0)
Relevance decides **which** hits survive `limit`; the page is then printed newest-first, which
`recall`'s own description promises. Both halves are checked, and the probe is a tight `limit` —
what survives it is what the ranker actually preferred. **Chosen because** of a real regression: a
window titled `SCA-219: Parity Pack v0` was buried under three browser bookmark bars whose only tie
to the query was the word "pack". A true match pushed past `limit` turns a ranking bug into a
confident false statement, since an empty answer inside the coverage window reads as proof.

Two scenarios: one where the decoys are floored away entirely (tests the floor) and one where four
decoys share two of three query words, clear the floor, and are *newer* than a genuine match that is
the oldest frame in the corpus (tests that relevance beats recency).

### `dedup` (weight 1.0)
Twelve near-identical consecutive frames of one window collapse into one moment that says how many
frames it stands for; a genuinely different frame in the same window does **not** collapse into it;
identical frames either side of the ten-minute moment gap stay separate; differently-titled windows
of one app stay distinct. **Chosen because** screen capture runs every three seconds — without
collapsing, `limit` is spent on one editor, and with over-eager collapsing a real change disappears.
Both directions are failures, and the second is silent.

### `uncertainty` (weight 1.0)
Low confidence must be marked, nil must not, high must not — plus the boundary: exactly at the floor
(unmarked, the test is strictly below), just under (marked), `0.0` (marked), `1.0` (unmarked), and
scores outside `0…1` such as a log-probability (unmarked, because that is not a probability on this
scale). The legend appears exactly once and only when a marked line survived. Screen text is never
marked. **Chosen because** the recogniser once wrote song lyrics into the transcript as first-person
speech, typographically identical to things the user really said. Both directions are lies: an
unmarked guess, and a mark on an unknown score that would empty the marker of meaning.

### `filter_integrity` (weight 2.0)
Every filter the output *claims* must be the filter that ran, and every filter asked for must be
applied or the call must fail. Scored as exact nonce sets, plus a check that the printed boundary is
the requested boundary to the minute. Covers `since`, `until`, both together, `app`, `app` combined
with a range, substring app matching, `conversations`, `activity`, a reversed range, and a range
containing nothing. **Chosen because** it is the worst failure class here: a printed filter that was
not applied means a reader is looking at a different slice of the user's day than it believes, and
nothing in the output can reveal that.

### `bad_input` (weight 1.0)
Unparseable dates, hostile FTS input (`"`, `*`, `AND`, `NEAR(a b)`, emoji, a 4,000-character query),
out-of-range limits, wrong argument types, array-shaped arguments, unknown tool names. Nothing may
crash; every rejection must be explicit and quote the offending value; and the server must still be
answering afterwards. **Chosen because** the failure mode is not a crash, it is a call that runs
anyway with the bad part quietly dropped.

### `coherence` (weight 1.0)
Two answers about the same facts must not contradict each other. `status` counts match the corpus
exactly; the coverage window is the window that was captured; the line count `conversations` prints
matches the `transcript` it points at; the same question twice gives the same answer; collapsed
frame counts never exceed the frames that exist; activity blocks never total more time than their
range; truncation is disclosed. **Chosen because** a model reads several of these tools in one turn.
If two of them disagree, whichever it believes it is believing something false and has no way to
find out which.

### `protocol` (weight 0.75)
Handshake, `tools/list` shape, notifications taking no reply, JSON-RPC error codes for malformed and
non-UTF-8 frames, and — aggregated over every process the run spawns — that **stdout carries
JSON-RPC and nothing else**. **Chosen because** a single stray `print` anywhere in the binary
corrupts the stream and Claude silently drops the connection; no amount of answer quality survives
that.

### `traceability` (weight 0.75)
An id printed by `conversations` resolves in `transcript`; an unknown local id is refused rather
than answered with a neighbouring conversation; an Omi UUID with no account configured reads as
"unreachable", never as "does not exist". **Chosen because** a citation that resolves to the wrong
record is worse than no citation.

## Reading the score

```
overall  94.9%   floor 93.0%
         159/166 checks passed  (7 tracked failure(s) not gating)
```

`overall` is the class scores weighted by the table above — **not** the raw pass rate, so a class
with few checks cannot be diluted by a class with many. Each class score is its own weighted pass
rate.

The run diffs itself against the previous `dist/eval-results.json` and prints what regressed and
what was fixed. That diff is the answer to "did quality go up or down", and it is more useful than
the number.

### `KNOWN_FAILURES`

Checks that fail today are listed in `KNOWN_FAILURES` at the top of `scripts/eval.py`, each with the
defect behind it. A known failure **still scores zero** — the overall number tells the truth and
rises when one is fixed — but it does not turn the build red, so the gate stays usable while they
are worked through. Anything failing that is *not* listed is a new regression and does fail. When a
known failure starts passing the run prints a nudge to delete its entry; do that in the same PR.

`--strict` ignores the list entirely, which is the mode to use while fixing one.

## Interpreting a regression

1. **A critical check that is not in `KNOWN_FAILURES` fails.** Stop. These are the ones where a
   reader is misled rather than underserved: a filter that did not apply, a nearest neighbour served
   as a match, a search that did not run reported as a negative result, an uncertain line rendered
   as fact. Do not add it to `KNOWN_FAILURES` to get green — that list is for defects already
   accepted and tracked, not a place to put new ones.
2. **The overall number drops but no critical fails.** Read the per-class scores. A drop confined to
   one class is usually a deliberate trade (a ranking tweak that costs findability); the eval's job
   is to make you state it rather than discover it in production.
3. **`findability` drops while `no_confabulation` holds.** The tool got quieter, not more honest.
   Check the relevance floor and the FTS expression first.
4. **`no_confabulation` drops while `findability` holds.** Almost always a wording change in
   `Tools.swift`: the empty-answer sentences carry load-bearing distinctions ("was **not** searched",
   "could not be read", "recorded nothing"). If a rewrite is genuinely better, update the check's
   accepted phrasings *and say so in the PR* — silently loosening a check is how this class rots.
5. **The harness exits 2.** Isolation could not be proven, or the build failed. Never a product
   verdict; fix the harness or the tree and re-run.

## What it does not cover

- **The Omi half.** No credential is reachable by design, so every account-side path — the semantic
  search caveat, the history-depth probe, screen watermarks derived from real rows — is exercised
  only in its "not configured" branch. Those paths need a live account and stay out of this eval.
- **Capture.** Audio, transcription, OCR, and permissions are upstream of the database this seeds.
- **Whether Claude actually reaches for the tools.** That is what `scripts/testbench.py` is for.
