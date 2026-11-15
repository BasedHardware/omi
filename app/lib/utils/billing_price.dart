import 'dart:math' as math;

import 'package:intl/intl.dart';

/// Purchase amounts use the catalog's currency and Stripe minor units. Keep the
/// currency unambiguous and the number stable across device/app locales, just
/// like the fixed-currency checkout. Language around the amount is localized.
String formatBillingPrice(int amountMinor, String currency) {
  final code = currency.trim().toUpperCase();
  final digits = _zeroDecimal.contains(code) ? 0 : (_threeDecimal.contains(code) ? 3 : 2);
  final symbol = switch (code) {
    'USD' => 'US\$',
    'JPY' => '¥',
    _ => '$code ',
  };
  return NumberFormat.currency(locale: 'en_US', name: code, symbol: symbol, decimalDigits: digits)
      .format(amountMinor / math.pow(10, digits));
}

// Stripe's charge units, rather than CLDR's cash/payout units (notably ISK/UGX).
const _zeroDecimal = {
  'BIF',
  'CLP',
  'DJF',
  'GNF',
  'JPY',
  'KMF',
  'KRW',
  'MGA',
  'PYG',
  'RWF',
  'VND',
  'VUV',
  'XAF',
  'XOF',
  'XPF'
};
const _threeDecimal = {'BHD', 'JOD', 'KWD', 'OMR', 'TND'};
