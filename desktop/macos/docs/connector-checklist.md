# Connector Fix Checklist

A short, mechanical checklist for fixing (or adding) a browser-cookie / agent /
config-file connector. It operationalizes `integrations-philosophy.md`. The
calendar fix (`CalendarReaderService.swift`) is the worked reference — copy its
shape.

Work top to bottom. Don't skip the probe or the fixture test.

## 1. Classify the surface

- [ ] Can code write a config file for this? → write it in Swift, idempotently.
      Do **not** send an agent. (philosophy §1)
- [ ] Is there an API/CLI? → call it in code.
- [ ] Only a human UI / browser session? → proceed, but everything below applies.

## 2. Aggregate diagnostics — never last-writer-wins

- [ ] If you loop over candidates (browsers, profiles, accounts), collect a
      **structured attempt per candidate** — `{who, stage, reason}` — instead of
      overwriting a single `last_error`. The calendar bug surfaced "Chrome
      (Profile 3)" only because it was tried last; six other profiles were
      silently discarded. (philosophy §2)
- [ ] Classify the *most actionable* failure, not the last one. Prefer
      "session expired" (had auth, got 401/403) over "not signed in" (an empty
      profile). See `classify()` in the Python helper.

## 3. Error taxonomy that reflects reality

- [ ] Map failures to distinct, honest cases — `notSignedIn`, `sessionExpired`,
      `noBrowserFound`, `network`, … — never a catch-all. A login problem must
      not render as "Network error". (philosophy §3)
- [ ] Each case's user message says **what to do next** (e.g. "Open
      calendar.google.com in Chrome and sign in"), not just what failed.

## 4. Pure, testable parsing seam

- [ ] Put the "raw payload → classified outcome" step in a **pure function**
      (`CalendarOutcomeParser.parse`). No I/O, no Process, no browser.
- [ ] Add a fixture test with one payload per real failure mode. These are the
      captured observations the eval flywheel runs on. When a new failure shape
      appears in the wild, add its payload here. (philosophy §7)

## 5. Functional probe — "connected" means verified now

- [ ] Add a `verifyConnection()` that exercises the **real** path over a tiny
      window and returns a live status (`connected` / `needsSignIn` / `error`).
      A green result must guarantee the whole chain works end-to-end.
      (philosophy §3, §4)
- [ ] Drive UI status and any "Connected" badge off this probe, never off a
      stored one-time-success latch.

## 6. Sanitized diagnostics for the corpus

- [ ] Log a structured, **non-sensitive** one-liner of the attempts (names,
      stages, reasons). Never cookie values, tokens, or response bodies.
      (philosophy §7)

## 7. Ship hygiene

- [ ] Add a changelog fragment under `desktop/macos/changelog/unreleased/`.
- [ ] Keep the change scoped to this connector — don't let it reach into a
      shared god-module that could regress other connectors. (philosophy §8)

---

**Known follow-up:** `GmailReaderService.swift` duplicates the exact
browser-cookie + Python-decrypt + last-writer-wins pattern this checklist fixes
for calendar. It has the same class of bug and is the next candidate. A shared
`BrowserGoogleSession` helper (cookie discovery + decrypt + classify) would let
both connectors share the hardened path — worth doing once a second consumer
justifies the extraction.
