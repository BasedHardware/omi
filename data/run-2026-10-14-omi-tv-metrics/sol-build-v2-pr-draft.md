## Summary

Adds the isolated `omi-tv-v2` Direction A board and an admin-authenticated aggregate wall route. Qualified activity v2, UTC complete windows, primary-platform counts and entry-platform cohorts share definitions. Missing data stays null; proxy/partial/stale coverage and source timestamps stay visible. The three existing dashboards and `/dashboard` embed remain unchanged.

Shopify device sales and plan-prepay cash are separate. Billing uses its read-only aggregate mode. Stripe audits unmapped products, tiered prices and currencies without treating JPY as USD cents. Production ARPMAU requires a corrected same-cutoff snapshot; no historical close is invented from the live Stripe list. Local screenshots use recorded read-only aggregates and an explicitly labeled synthetic Stripe fixture.

## Validation

Full admin Vitest suite, TypeScript, ESLint, Grafana builder/apply contract tests, and repository preflight. Read-only PostHog/Shopify smoke queries and the complete local wall route exercised; stock Grafana 13.1.3 + Infinity 4.1.1 rendered at 1440 and 1920 pixels. Details and source prerequisites: `web/admin/grafana/README.md` and the slice run result.

![Direction A laptop](.agent-artifacts/ui-evidence/omi-tv-v2/001-web-direction-a-laptop.png)
![Direction A TV](.agent-artifacts/ui-evidence/omi-tv-v2/002-web-direction-a-tv.png)
