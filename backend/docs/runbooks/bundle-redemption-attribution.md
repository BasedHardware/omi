# Bundle redemption attribution

`promotion_code_attribution` trusts only a server-resolved Stripe PromotionCode
with integer `max_redemptions=1`, schema `1`, source `shopify_bundle_code`, a
validated Shopify shop/order, and role `self|gift|unknown`. The line item is
optional: omitted means order-level evidence; present means a valid numeric ID
or LineItem GID. An explicit null is invalid. Syntax does not prove membership
of that line in the order.

Coupon metadata never supplies provenance. No issuance keys is neutral. A
partial coupon assertion is neutral only when every present issuance key is a
string exactly matching the validated code. A coupon with all five required
fields (schema, source, shop, order, role) must validate and agree completely,
including optional-line presence. Contradictory, malformed or null assertions
suppress optional attribution while code benefit and entitlement continue.

`redeemed_promotion_code_id` records the applied code. The retained
`bundle_promotion_code_id` belongs to historical order provenance. They can
differ: hosted completion and direct redemption retain the whole old tuple on
conflict, record the applied code separately, and preserve authoritative UID.
Their mismatch is not proof of an atomic code-to-order join. Do not overwrite
the old tuple or infer a new code's order from it.

`CONVERSION_BUNDLE_ATTRIBUTION_ENABLED` is on by default; `off`, `false`, `0`
or `no` (case/whitespace insensitive) restores the prior validator, including
conservative suppression of partial coupon metadata and its numeric equality
check. It does not revoke benefits or rewrite retained provenance. Disabling it
must use the normal authorized runtime configuration/release path.

Newly accepted direct attribution adds at most one best-effort Subscription
metadata request (five normal Stripe requests become six) and allowlisted
bytes in the existing single-use claim. Hosted metadata convergence keeps its
existing requests. Discount-free duplicate checkout adds no Stripe calls;
code-bearing duplicates can retry optional convergence, then must finish
unlock and fair-use clear before acknowledgement. Metadata failure is optional;
entitlement failure remains retryable. There is no new Shopify/PostHog call,
collection, metadata key or per-redemption event.

No bundle issuer was found in this repository at the SCA-2313 source diagnosis.
An operational issuer/owner and a synthetic issuance contract are still needed
before claiming live coverage. Existing conversion order-link diagnostics
cannot reconstruct all rejected/unknown redemptions or optional-write failures.
SCA-2313 stays open for approved aggregate evidence and independent production
READBACK; source tests, a merge or a deployment do not satisfy that requirement.
SCA-1872 remains the credential-path prerequisite for the existing producer.
