import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/billing_price.dart';
import 'package:omi/utils/checkout_currency_format.dart';
import 'package:omi/utils/storefront_region.dart';

// The offer page must show the string Stripe Checkout renders at the server-pinned locale.
// Samples come from ICU Intl.NumberFormat (backend/scripts/generate_checkout_currency_format.py);
// the backend's display_money is tested against the same file.
void main() {
  test('every Stripe currency renders exactly as the cart', () {
    final table =
        jsonDecode(File('../backend/config/checkout_currency_format.json').readAsStringSync()) as Map<String, dynamic>;
    final currencies = table['currencies'] as Map<String, dynamic>;
    expect(currencies.keys.toSet(), checkoutCurrencyFormat.keys.toSet());
    for (final MapEntry(key: code, value: row) in currencies.entries) {
      expect(formatBillingPrice(row['sample_minor'] as int, code), row['sample'], reason: code);
    }
  });

  test('USD and JPY render exactly as before', () {
    expect(formatBillingPrice(26991, 'usd'), 'US\$269.91');
    expect(formatBillingPrice(2999, 'USD'), 'US\$29.99');
    expect(formatBillingPrice(0, 'usd'), 'US\$0.00');
    expect(formatBillingPrice(43200, 'jpy'), '¥43,200');
  });

  test('local, zero-decimal and whole-hundreds currencies', () {
    expect(formatBillingPrice(20699, 'gbp'), '£206.99');
    expect(formatBillingPrice(24299, 'eur'), '€242.99');
    expect(formatBillingPrice(56900, 'mxn'), 'MX\$569.00');
    expect(formatBillingPrice(10999, 'aed'), 'AED 109.99');
    expect(formatBillingPrice(39000, 'krw'), '₩39,000');
    expect(formatBillingPrice(27990, 'clp'), 'CLP 27,990');
    expect(formatBillingPrice(1099000, 'huf'), 'HUF 10,990.00');
    expect(formatBillingPrice(99000, 'twd'), 'NT\$990.00');
    expect(formatBillingPrice(399900, 'isk'), 'ISK 3,999');
    expect(formatBillingPrice(11000000, 'ugx'), 'UGX 110,000');
  });

  test('device region is a two-letter code or nothing', () {
    expect(deviceStorefrontRegion('jp'), 'JP');
    expect(deviceStorefrontRegion('GB'), 'GB');
    expect(deviceStorefrontRegion('419'), isNull);
    expect(deviceStorefrontRegion(''), isNull);
  });
}
