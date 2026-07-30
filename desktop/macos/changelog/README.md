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
