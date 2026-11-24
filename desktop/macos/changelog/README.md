# Desktop changelog

Add one JSON file per user-facing PR under `unreleased/`:

```json
{
  "change": "Fixed the user-visible behavior"
}
```

Use a unique kebab-case filename, for example `20260628-chat-scrolling.json`.
Release automation moves unreleased fragments into `releases/<version>.json` and regenerates `../CHANGELOG.json` for compatibility.

Stable promotions can span many beta builds. Build the curated stable release log from these per-build entries before the explicit Stable promotion described in `../docs/release.md`.

## Guidelines

- Write from the user's perspective: "Fixed X", "Added Y", "Improved Z"
- One sentence, no period at the end
- Use a unique kebab-case filename so parallel PRs do not conflict
- Tests, generated Swift, e2e harness files, and listed release-infra paths are already exempt
- Internal-only **production** edits (dead-code deletion, refactors in `Sources/`) need an in-repo marker, not the `no-changelog-needed` PR label — that label is invisible after merge and reddens main. Add `{"kind": "none"}` under `unreleased/` instead
- HTML is allowed for links: `<a href='...'>text</a>`
- Do not edit `CHANGELOG.json` by hand; release automation regenerates it
- Commit the fragment with your other changes (same commit is fine)
