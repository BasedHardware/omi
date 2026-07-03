# Desktop changelog

Add one JSON file per user-facing PR under `unreleased/`:

```json
{
  "change": "Fixed the user-visible behavior"
}
```

Use a unique kebab-case filename, for example `20260628-chat-scrolling.json`.
Release automation moves unreleased fragments into `releases/<version>.json` and regenerates `../CHANGELOG.json` for compatibility.

Stable/prod promotions can span many beta builds. Agents must build the curated stable release log from these per-build entries using `../docs/agent-prod-promotion-runbook.md` before asking for promotion approval.
