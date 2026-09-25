# Mobile changelog

Add one JSON file per user-facing mobile PR under `unreleased/`:

```json
{
  "change": "One user-friendly sentence"
}
```

Use a unique kebab-case filename, for example `20260924-chat-scrolling.json`.

## When a fragment is required

Every PR that changes production code under `app/` must add a fragment, except
the small fixed set of internal release-control paths allowlisted in
`check-mobile-changelog.py`. The gate compares the PR diff — and the same diff
again on the post-merge push to `main`, where PR labels do not exist — so the
fragment is the only durable exemption.

Internal-only changes (CI, dependencies, release plumbing, refactors with no
user-visible effect) add an explicit exemption fragment instead of notes:

```json
{
  "kind": "none"
}
```

## Style

Write what the user can now do or what got better — impact first, no jargon.
Never say "refactor", "state management", "endpoint", or "cache layer". Keep a
release to a handful of short lines rather than an exhaustive list.

Good fragments:

- "Search across all your memories"
- "Export or delete multiple tasks at once"
- "Drag a task sideways to nest it under another"
- "Calls now show live transcription"

Fragments are stored verbatim: no compression or rewriting happens at authoring
or aggregation time. Fitting the App Store and Play character budgets happens
only when store submission text is derived at release time, and that derived
text is never written back into `releases/<version>.json`.

## Release flow

`python3 .github/scripts/mobile-changelog.py collect --version X.Y.Z` validates
every `unreleased/` fragment, writes `releases/<version>.json` (merging into an
existing release file when the marketing version is collected again), and
removes the consumed fragments. `store-notes --version X.Y.Z --store ios|android`
derives the submission text on demand; a release collected from only `none`
fragments yields "Bug fixes and improvements".
