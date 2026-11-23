import 'dart:math' as math;

import 'package:intl/intl.dart';
import 'package:omi/utils/checkout_currency_format.dart';

/// Purchase amounts use the catalog's currency and Stripe minor units. The string is
/// exactly what Stripe Checkout shows at the server-pinned locale for that currency
/// (checkoutCurrencyFormat: ICU symbol prefix, display decimals, Stripe exponent), so the
/// offer page and the cart match. The number is stable across device/app locales;
/// language around the amount is localized.
String formatBillingPrice(int amountMinor, String currency) {
  final code = currency.trim().toLowerCase();
  final (prefix, digits, exponent) = checkoutCurrencyFormat[code] ?? ('${code.toUpperCase()} ', 2, 2);
  return NumberFormat.currency(locale: 'en_US', name: code.toUpperCase(), symbol: prefix, decimalDigits: digits)
      .format(amountMinor / math.pow(10, exponent));
}
