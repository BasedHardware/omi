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
the hosted production URL and Stripe cart require separate device acceptance.

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
| JPY manage | [v1](054-mobile-android-en-us-jpy-manage.png), [v2](055-mobile-android-en-us-jpy-v2-manage.png) | [v1](001-mobile-android-en-ca-jpy-manage.png), [v2](002-mobile-android-en-ca-jpy-v2-manage.png) |
| V2 monthly / yearly | [Monthly](029-mobile-android-en-us-v2-plans-month.png), [Yearly](030-mobile-android-en-us-v2-plans-year.png) | [Monthly](027-mobile-android-en-ca-v2-plans-month.png), [Yearly](028-mobile-android-en-ca-v2-plans-year.png) |

## Native Android verification

API 36 dev emulator, source revision `7d9be9db6c82ca504c1b6d902224641c95e46fa9`, offline fixture data and a loopback API endpoint. Inspected/operated with agent-flutter. The web paywall loads the unchanged static HTML source with the production URL builder parameters; its remote decorative image is unavailable offline. Its PNG uses adb screencap because Flutter capture omits native platform views. The remaining PNGs use agent-flutter screenshot. No checkout session, payment, retention acceptance or cancellation was performed. The dev emulator was closed after capture. These captures verify rendering, not installed-release or hosted-Stripe-cart acceptance.

- [031-mobile-android-native-en-ca-jpy-manage.png](031-mobile-android-native-en-ca-jpy-manage.png)
- [032-mobile-android-native-en-ca-outline.png](032-mobile-android-native-en-ca-outline.png)
- [033-mobile-android-native-en-ca-plans.png](033-mobile-android-native-en-ca-plans.png)
- [034-mobile-android-native-en-ca-retention.png](034-mobile-android-native-en-ca-retention.png)
- [035-mobile-android-native-en-ca-trial-month.png](035-mobile-android-native-en-ca-trial-month.png)
- [036-mobile-android-native-en-ca-trial-year.png](036-mobile-android-native-en-ca-trial-year.png)
- [037-mobile-android-native-en-ca-upsell.png](037-mobile-android-native-en-ca-upsell.png)
- [038-mobile-android-native-en-ca-v2-month.png](038-mobile-android-native-en-ca-v2-month.png)
- [039-mobile-android-native-en-ca-v2-year.png](039-mobile-android-native-en-ca-v2-year.png)
- [040-mobile-android-native-en-ca-web.png](040-mobile-android-native-en-ca-web.png)
- [041-mobile-android-native-en-us-outline.png](041-mobile-android-native-en-us-outline.png)
- [042-mobile-android-native-en-us-plans.png](042-mobile-android-native-en-us-plans.png)
- [043-mobile-android-native-en-us-retention.png](043-mobile-android-native-en-us-retention.png)
- [044-mobile-android-native-en-us-trial-month.png](044-mobile-android-native-en-us-trial-month.png)
- [045-mobile-android-native-en-us-trial-year.png](045-mobile-android-native-en-us-trial-year.png)
- [046-mobile-android-native-en-us-upsell.png](046-mobile-android-native-en-us-upsell.png)
- [047-mobile-android-native-en-us-v2-month.png](047-mobile-android-native-en-us-v2-month.png)
- [048-mobile-android-native-en-us-v2-year.png](048-mobile-android-native-en-us-v2-year.png)
- [049-mobile-android-native-en-us-web.png](049-mobile-android-native-en-us-web.png)

Plan & Usage follow-up: both capped and uncapped USD chat budgets were inspected with agent-flutter, including native accessibility text. These four captures include the subsequent chat-usage formatter/copy update.

- [050-mobile-android-native-en-ca-usage-capped.png](050-mobile-android-native-en-ca-usage-capped.png)
- [051-mobile-android-native-en-ca-usage-uncapped.png](051-mobile-android-native-en-ca-usage-uncapped.png)
- [052-mobile-android-native-en-us-usage-capped.png](052-mobile-android-native-en-us-usage-capped.png)
- [053-mobile-android-native-en-us-usage-uncapped.png](053-mobile-android-native-en-us-usage-uncapped.png)
