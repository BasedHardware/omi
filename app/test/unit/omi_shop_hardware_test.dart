// Google Play-billed Android readers see only the Omi device in the store: its page (on the
// app-hardware template, without Omi Pro prices), cart and checkout, plus the payment pages checkout
// hands off to. Never Omi Pro, gift cards or post-purchase upsells sold outside Google Play.
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/apps/widgets/omi_web_page.dart';
import 'package:omi/pages/shop/omi_shop.dart';

final _product = Uri.parse('https://www.omi.me/products/omi?view=app-hardware&_ref=x');
final _cart = Uri.parse('https://www.omi.me/cart');
final _checkout = Uri.parse('https://www.omi.me/checkouts/cn/abc/en-us');

WebNavigation _go(Uri? from, String to) => omiHardwareNavigation(from, Uri.parse(to));

void main() {
  test('the store opens on the device page with the app-hardware template', () {
    expect(omiHardwareUrl('onboarding_not_ordered').toString(),
        'https://www.omi.me/products/omi?view=app-hardware&_ref=onboarding_not_ordered');
    expect(_go(null, omiHardwareUrl('x').toString()), WebNavigation.allow);
  });

  test('the device page without the template, or with another view, is replaced by the template', () {
    for (final url in [
      'https://www.omi.me/products/omi',
      'https://omi.me/products/omi/?variant=123',
      'https://www.omi.me/products/omi?view=default&variant=123',
    ]) {
      final decision = _go(_cart, url);
      expect(decision.kind, WebNavigationKind.replace, reason: url);
      expect(decision.replacement!.queryParameters['view'], 'app-hardware', reason: url);
      expect(decision.replacement!.path, Uri.parse(url).path, reason: url);
    }
    expect(
        _go(_cart, 'https://www.omi.me/products/omi?view=default&variant=123').replacement!.queryParameters['variant'],
        '123');
  });

  test('cart, cart permalinks, checkout and policies are allowed on the store', () {
    for (final url in [
      'https://www.omi.me/cart',
      'https://www.omi.me/cart/53310207000868:1',
      'https://www.omi.me/checkout',
      'https://www.omi.me/checkouts/cn/abc',
      'https://www.omi.me/123456/checkouts/abc/thank-you',
      'https://www.omi.me/policies/refund-policy',
    ]) {
      expect(_go(_product, url), WebNavigation.allow, reason: url);
    }
  });

  test('Omi Pro, gift cards, other store pages and plain http are blocked', () {
    for (final url in [
      'https://www.omi.me/',
      'https://www.omi.me/pages/contact',
      'https://www.omi.me/products/omi-pro-first-3-months',
      'https://www.omi.me/products/omi-unlimited-1st-year',
      'https://www.omi.me/products/omi-gift-card',
      'https://www.omi.me/products/omi-gift-bundle-omi-12-months-of-unlimited',
      'https://www.omi.me/collections/all',
      'https://www.omi.me/search?q=pro',
      'http://www.omi.me/products/omi',
    ]) {
      expect(_go(_product, url), WebNavigation.block, reason: url);
    }
  });

  test('off-site pages open only from checkout or an off-site payment page', () {
    for (final url in [
      'https://accounts.shop.app/login',
      'https://www.paypal.com/checkoutnow?token=1',
      'https://portal.afterpay.com/checkout',
      'https://payments.amazon.com/checkout',
      'https://acs.bank.example/3ds/challenge',
    ]) {
      expect(_go(_checkout, url), WebNavigation.allow, reason: url);
      expect(_go(Uri.parse('https://checkout.shopify.com/123/checkouts/abc'), url), WebNavigation.allow, reason: url);
      expect(_go(Uri.parse('https://www.paypal.com/checkoutnow?token=1'), url), WebNavigation.allow, reason: url);
      // From the product, cart and policy pages they stay blocked.
      expect(_go(_product, url), WebNavigation.block, reason: url);
      expect(_go(_cart, url), WebNavigation.block, reason: url);
      expect(_go(Uri.parse('https://www.omi.me/policies/refund-policy'), url), WebNavigation.block, reason: url);
      expect(_go(null, url), WebNavigation.block, reason: url);
    }
    // Coming back to the store goes through its path allow-list again.
    final paypal = Uri.parse('https://www.paypal.com/checkoutnow?token=1');
    expect(_go(paypal, 'https://www.omi.me/checkouts/cn/abc/en-us'), WebNavigation.allow);
    expect(_go(paypal, 'https://www.omi.me/products/omi-gift-card'), WebNavigation.block);
  });

  test('a post-purchase page on the store checkout closes the store (the payment is already taken)', () {
    for (final url in [
      'https://www.omi.me/checkouts/cn/abc/post-purchase',
      'https://www.omi.me/123/checkouts/abc/post_purchase',
      'https://omi.me/checkouts/cn/abc/post-purchase',
      'https://checkout.shopify.com/123/checkouts/abc/post_purchase',
    ]) {
      expect(_go(_checkout, url), WebNavigation.finish, reason: url);
    }
  });

  test('post-purchase words outside the store checkout are not an order', () {
    // Blocked pages get the normal "not available" message, never "Order placed".
    for (final url in [
      'https://blog.example.com/post-purchase-tips',
      'https://www.omi.me/blogs/news/post_purchase',
      'https://www.omi.me/pages/post-purchase',
      'https://app.omi.me/checkouts/post-purchase',
    ]) {
      expect(_go(_product, url), WebNavigation.block, reason: url);
      expect(_go(_checkout, url).kind, isNot(WebNavigationKind.finish), reason: url);
    }
    // An off-site page from checkout keeps the normal off-site rule, not a close.
    expect(_go(_checkout, 'https://blog.example.com/post-purchase-tips'), WebNavigation.allow);
  });

  test('every other Omi host is blocked from the product page and from checkout', () {
    final paypal = Uri.parse('https://www.paypal.com/checkoutnow?token=1');
    for (final url in [
      'https://app.omi.me/',
      'https://app.omi.me/checkouts/cn/abc',
      'https://h.omi.me/apps',
      'https://random-subdomain.omi.me/products/omi',
      'https://a.b.omi.me/cart',
    ]) {
      for (final from in [_product, _cart, _checkout, paypal, null]) {
        expect(_go(from, url), WebNavigation.block, reason: '$from -> $url');
      }
    }
    // Look-alike hosts are not Omi hosts: from checkout they are ordinary off-site pages.
    expect(_go(_checkout, 'https://notomi.me/'), WebNavigation.allow);
  });

  test('the device page is shown only when the app-hardware marker is present', () {
    expect(omiHardwarePageCheck.appliesTo(_product), isTrue);
    expect(omiHardwarePageCheck.appliesTo(Uri.parse('https://www.omi.me/products/omi')), isTrue);
    expect(omiHardwarePageCheck.appliesTo(_cart), isFalse);
    expect(omiHardwarePageCheck.script, "document.getElementById('omi-app-hardware') !== null");
    // Android returns a bool, some engines a string.
    expect(omiHardwarePageVerified(true), isTrue);
    expect(omiHardwarePageVerified('true'), isTrue);
    expect(omiHardwarePageVerified(false), isFalse);
    expect(omiHardwarePageVerified('false'), isFalse);
    expect(omiHardwarePageVerified(null), isFalse);
  });
}
