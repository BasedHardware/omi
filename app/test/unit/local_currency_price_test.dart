import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/billing_price.dart';
import 'package:omi/utils/storefront_region.dart';

// The offer page must render the same string Stripe Checkout shows for that currency
// (backend/utils/local_currency.py display_money; tests/unit/test_local_currency_offer.py).
void main() {
  test('USD and JPY render exactly as before', () {
    expect(formatBillingPrice(26991, 'usd'), 'US\$269.91');
    expect(formatBillingPrice(2999, 'USD'), 'US\$29.99');
    expect(formatBillingPrice(0, 'usd'), 'US\$0.00');
    expect(formatBillingPrice(43200, 'jpy'), '¥43,200');
  });

  test('local currencies use the cart glyph', () {
    expect(formatBillingPrice(20699, 'gbp'), '£206.99');
    expect(formatBillingPrice(24999, 'eur'), '€249.99');
    expect(formatBillingPrice(4499, 'aud'), 'A\$44.99');
    expect(formatBillingPrice(3999, 'cad'), 'CA\$39.99');
    expect(formatBillingPrice(54900, 'mxn'), 'MX\$549.00');
    expect(formatBillingPrice(14999, 'brl'), 'R\$149.99');
    expect(formatBillingPrice(10999, 'aed'), 'AED 109.99');
  });

  test('device region is a two-letter code or nothing', () {
    expect(deviceStorefrontRegion('jp'), 'JP');
    expect(deviceStorefrontRegion('GB'), 'GB');
    expect(deviceStorefrontRegion('419'), isNull);
    expect(deviceStorefrontRegion(''), isNull);
  });
}
