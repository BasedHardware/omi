import 'dart:ui' show PlatformDispatcher;

/// Sent on API calls so the server can price a new buyer's offer in their local
/// currency (backend/utils/local_currency.py). Builds without it keep today's catalog.
const storefrontRegionHeader = 'X-Omi-Storefront-Region';

final _region = RegExp(r'^[A-Z]{2}$');

/// The device region (ISO 3166-1 alpha-2) from the system locale, or null when it names none.
String? deviceStorefrontRegion([String? countryCode]) {
  final code = (countryCode ?? PlatformDispatcher.instance.locale.countryCode)?.trim().toUpperCase();
  return code != null && _region.hasMatch(code) ? code : null;
}
