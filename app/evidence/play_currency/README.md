# Currency presentation evidence

Rendered production Flutter widgets with hermetic catalog/retention fixtures,
430 logical pixels wide, in en_US and en_CA. PNGs use real fonts. They are
render evidence, not installed-build or Stripe-hosted-cart acceptance.

Reproduce from app/ after the documented test bootstrap:

```sh
flutter test --dart-define=OMI_BILLING_EVIDENCE_DIR=../.agent-artifacts/playcur/ui test/widgets/billing_currency_surfaces_test.dart
```

The regression also exercises en_IN and de_DE, exact checkout price IDs,
monthly/yearly trial terms, poisoned server-formatted strings, promo codes,
retention and v1/v2 JPY management. The hosted web bridge is asserted in tests;
the hosted HTML and Stripe cart require separate device acceptance.

| Surface | en_US | en_CA |
|---|---|---|
| Trial slides | [1](en_US_trial_slide_1.png), [2](en_US_trial_slide_2.png), [3](en_US_trial_slide_3.png), [4](en_US_trial_slide_4.png), [5](en_US_trial_slide_5.png) | [1](en_CA_trial_slide_1.png), [2](en_CA_trial_slide_2.png), [3](en_CA_trial_slide_3.png), [4](en_CA_trial_slide_4.png), [5](en_CA_trial_slide_5.png) |
| Monthly trial card/terms | [PNG](en_US_trial_month_card.png) | [PNG](en_CA_trial_month_card.png) |
| Annual trial card/terms | [PNG](en_US_trial_year_card.png) | [PNG](en_CA_trial_year_card.png) |
| Outline | [PNG](en_US_outline.png) | [PNG](en_CA_outline.png) |
| 30-day upsell | [PNG](en_US_trial_upsell.png) | [PNG](en_CA_trial_upsell.png) |
| Plans | [PNG](en_US_plans.png) | [PNG](en_CA_plans.png) |
| Promo entry | [PNG](en_US_promo.png) | [PNG](en_CA_promo.png) |
| Retention | [PNG](en_US_retention.png) | [PNG](en_CA_retention.png) |
| JPY manage | — | [v1](en_CA_jpy_manage.png), [v2](en_CA_jpy_v2_manage.png) |
