// Google Play-billed Android readers see only the Omi device in the store: its page, cart and
// checkout, never Omi Pro, gift cards or post-purchase upsells sold outside Google Play.
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/shop/omi_shop.dart';

void main() {
  test('the store opens on the device page', () {
    expect(omiHardwareUrl('onboarding_not_ordered').toString(),
        'https://www.omi.me/products/omi?_ref=onboarding_not_ordered');
  });

  test('device page, cart and checkout are allowed', () {
    for (final url in [
      'https://www.omi.me/products/omi?_ref=x&variant=123',
      'https://www.omi.me/cart',
      'https://www.omi.me/cart/123:1',
      'https://www.omi.me/checkout',
      'https://www.omi.me/checkouts/cn/abc',
      'https://www.omi.me/123456/checkouts/abc/thank-you',
      'https://www.omi.me/policies/refund-policy',
      'https://checkout.shopify.com/123/checkouts/abc',
      'https://shop.app/pay/abc',
      'https://pay.shopify.com/x',
      'https://www.paypal.com/checkoutnow?token=1',
    ]) {
      expect(omiHardwareNavigationAllowed(Uri.parse(url)), isTrue, reason: url);
    }
  });

  test('Omi Pro, gift cards, other pages and post-purchase upsells are blocked', () {
    for (final url in [
      'https://www.omi.me/',
      'https://www.omi.me/products/omi-pro-first-3-months',
      'https://www.omi.me/products/omi-unlimited-1st-year',
      'https://www.omi.me/products/omi-unlimited-yearly-plan-bundle',
      'https://www.omi.me/products/omi-gift-card',
      'https://www.omi.me/products/omi-gift-bundle-omi-12-months-of-unlimited',
      'https://www.omi.me/collections/all',
      'https://www.omi.me/search?q=pro',
      'https://www.omi.me/pages/pricing',
      'https://www.omi.me/checkouts/cn/abc/post-purchase',
      'https://www.omi.me/123/checkouts/abc/post_purchase',
      'http://www.omi.me/products/omi',
      'https://example.com/',
    ]) {
      expect(omiHardwareNavigationAllowed(Uri.parse(url)), isFalse, reason: url);
    }
  });
}
