# `@omi-core/i18n`

Wave 0 provides the typed production-surface message contract. `EN_MESSAGES` is
the canonical English catalog for memories, conversations/detail, tasks, shared
sync chrome, navigation, and QA preview chrome. It is intentionally a small
surface catalog rather than a copy of the legacy 3,018-key Flutter catalog.

`SUPPORTED_LOCALES` is exactly the legacy English plus 48 locale IDs. Only
`en` is translated in this scaffold. Every other supported ID resolves to the
English catalog, and `resolveLocale()` / `getTranslationCoverage()` make that
fallback debt explicit. Do not label the fallback as translated.

Use `t(locale, key, variables)` or its `formatMessage` alias. Placeholder names
are inferred into the `MessageVariables` type. Use `formatDate`, `formatNumber`,
and `formatDuration` for values supplied by the caller; none reads the wall
clock. `scripts/check-i18n-parity.mjs` verifies the catalog and fallback report.
