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
| Trial slides | [1](020-mobile-android-en-us-trial-slide-1.png), [2](021-mobile-android-en-us-trial-slide-2.png), [3](022-mobile-android-en-us-trial-slide-3.png), [4](023-mobile-android-en-us-trial-slide-4.png), [5](024-mobile-android-en-us-trial-slide-5.png) | [1](008-mobile-android-en-ca-trial-slide-1.png), [2](009-mobile-android-en-ca-trial-slide-2.png), [3](010-mobile-android-en-ca-trial-slide-3.png), [4](011-mobile-android-en-ca-trial-slide-4.png), [5](012-mobile-android-en-ca-trial-slide-5.png) |
| Monthly trial card/terms | [PNG](019-mobile-android-en-us-trial-month-card.png) | [PNG](007-mobile-android-en-ca-trial-month-card.png) |
| Annual trial card/terms | [PNG](026-mobile-android-en-us-trial-year-card.png) | [PNG](014-mobile-android-en-ca-trial-year-card.png) |
| Outline | [PNG](015-mobile-android-en-us-outline.png) | [PNG](003-mobile-android-en-ca-outline.png) |
| 30-day upsell | [PNG](025-mobile-android-en-us-trial-upsell.png) | [PNG](013-mobile-android-en-ca-trial-upsell.png) |
| Plans | [PNG](016-mobile-android-en-us-plans.png) | [PNG](004-mobile-android-en-ca-plans.png) |
| Promo entry | [PNG](017-mobile-android-en-us-promo.png) | [PNG](005-mobile-android-en-ca-promo.png) |
| Retention | [PNG](018-mobile-android-en-us-retention.png) | [PNG](006-mobile-android-en-ca-retention.png) |
| JPY manage | — | [v1](001-mobile-android-en-ca-jpy-manage.png), [v2](002-mobile-android-en-ca-jpy-v2-manage.png) |
