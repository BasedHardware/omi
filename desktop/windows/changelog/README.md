# Windows changelog fragments

Post-update "what's new" changelog, mirroring `desktop/macos/changelog/`.

## Authoring

Add one fragment per user-visible change under `unreleased/`, named
`YYYY-MM-<slug>.json`, using the same schema as the macOS app:

```json
{ "changes": ["Short, user-facing sentence.", "Another change."] }
```

`{ "change": "single line" }` is also accepted. Keep lines short — they render in
a 360×168 acrylic toast (`src/renderer/src/components/insight/InsightToast.tsx`),
with the full list one click away via "View release notes".

## Runtime

On launch, `src/main/whatsNew.ts` compares the running build to the last version
whose notes were shown (`lastShownChangelogVersion` in `app-settings.json`) and,
only when it increased (a real update — never a fresh install), surfaces the
current fragment(s) in the shared toast window. AUMID is set before the toast, so
packaged notifications attribute to Omi.

## Deferred (tracked follow-up)

The macOS `desktop-changelog.py` consolidation (fragments → `releases/<version>.json`
on release) and its CI check (`check-desktop-changelog.py`) are **not yet ported**.
Today `whatsNew.ts` imports the single unreleased fragment directly. When a Windows
release pipeline lands, port the consolidation script + a CI gate that fails a PR
whose user-visible change ships no fragment, and switch `whatsNew.ts` to read the
compiled per-version file.
