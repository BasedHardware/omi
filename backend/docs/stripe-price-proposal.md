# Ladder price proposal dry run

Run `python backend/scripts/plan_prices_dry_run.py --environment dev` (or `prod`).
The output is offline tooling; the presentation config does not change live
names, recommendations, entitlements, or MCP caps. Released macOS still relies
on the existing Operator title. The v2 contract in #21367 owns new display copy.

`catalog_diff` appends recognized rows and the same IDs to
`plan_catalog.json`'s `ladder_v1_stripe_prices` list introduced by W3 #21351.
Its `entitlement_version: ladder_v1` row field requires W3's generator; the old
four-field generator cannot activate this ladder. Do not register only the
recognized rows or modify the observability module's private ID list.

`price_W5PLACEHOLDER...` IDs are explicitly synthetic, schema-valid placeholders.
Replace every one with its real Stripe create result in both lists before
registration, then regenerate the catalog. The concrete environment defaults to
`dev`; select `prod` explicitly for a production proposal. No write is executed.

Product mappings must be unambiguous for each proposed plan. Existing legacy
plans with multiple products are untouched; proposing one fails until a product
is explicitly resolved. Duplicate ladder plan rows also fail.

The checked-in `backend/tests/unit/fixtures/storefront/price_proposal.json` pins
all four exact creates. Use `--inventory-fixture` with this fixture to verify the
proposal; an `expected_create_calls` mismatch fails before printing. Plain
inventory exports without that field remain inventory evidence only and do not
prove completeness or that a price is absent in Stripe.
