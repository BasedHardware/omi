import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/paywall/paywall_checkout.dart';
import 'package:omi/pages/paywall/web_paywall_page.dart';

void main() {
  final base = Uri.parse('https://omi-paywall.vercel.app/');
  const offer = PaywallOffer(
    tierId: 'unlimited_v2',
    monthly: PaywallPrice(priceId: 'price_m', interval: 'month', amountMinor: 2999, currency: 'usd'),
    yearly: PaywallPrice(priceId: 'price_y', interval: 'year', amountMinor: 26991, currency: 'usd'),
  );

  Uri build({String? distinctId, bool analyticsEnabled = true}) => WebPaywallPage.buildUrl(
        base,
        source: 'onboarding',
        platform: 'ios',
        locale: 'en',
        name: 'Ada',
        freeMinutes: 300,
        offer: offer,
        distinctId: distinctId,
        analyticsEnabled: analyticsEnabled,
      );

  test('carries the reader, prices and the analytics identity', () {
    final q = build(distinctId: 'user-123').queryParameters;
    expect(q['source'], 'onboarding');
    expect(q['tier'], 'unlimited_v2');
    expect(q['month_amount'], '2999');
    expect(q['year_amount'], '26991');
    expect(q['distinct_id'], 'user-123');
    expect(q.containsKey('analytics'), isFalse);
  });

  test('omits the identity until one has settled', () {
    expect(build().queryParameters.containsKey('distinct_id'), isFalse);
  });

  test('a reader who turned analytics off sends no identity and tells the page', () {
    final q = build(distinctId: 'user-123', analyticsEnabled: false).queryParameters;
    expect(q['analytics'], 'off');
    expect(q.containsKey('distinct_id'), isFalse);
  });
}
