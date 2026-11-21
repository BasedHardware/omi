import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/onboarding/signup_offers.dart';

// The sign-up paywall and the 30-day downsell are offered once per onboarding run: a relaunch
// (or the forced relaunch after changing a permission in iOS Settings) never offers them again.

Future<void> _relaunch() async {
  final prefs = await SharedPreferences.getInstance();
  SharedPreferences.setMockInitialValues({for (final key in prefs.getKeys()) key: prefs.get(key)!});
  await SharedPreferencesUtil.init();
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('first time: the paywall opens once and its answer is returned unchanged', () async {
    var opens = 0;
    expect(await SignupOffers.paywall('u1', () async => (opens++, false).$2), isFalse);
    expect(opens, 1);
    expect(await SignupOffers.paywall('u2', () async => (opens++, true).$2), isTrue);
    expect(opens, 2);
  });

  test('a relaunch after closing the paywall does not open it again', () async {
    await SignupOffers.paywall('u1', () async => false);
    await _relaunch();
    var opens = 0;
    expect(await SignupOffers.paywall('u1', () async => (opens++, false).$2), isFalse);
    expect(opens, 0);
  });

  test('a relaunch after buying keeps the purchase, so no downsell follows', () async {
    await SignupOffers.paywall('u1', () async => true);
    await _relaunch();
    expect(await SignupOffers.paywall('u1', () async => fail('opened again')), isTrue);
  });

  test('when no paywall page was shown, the next launch decides again like the first', () async {
    var opens = 0;
    await SignupOffers.paywall('u1', () async => (opens++, null).$2);
    await _relaunch();
    await SignupOffers.paywall('u1', () async => (opens++, false).$2);
    expect(opens, 2);
  });

  test('killed with the paywall still open: it shows again on relaunch', () async {
    unawaited(SignupOffers.paywall('u1', () => Completer<bool?>().future));
    await _relaunch();
    var opens = 0;
    await SignupOffers.paywall('u1', () async => (opens++, false).$2);
    expect(opens, 1);
  });

  test('the downsell is offered once, and not again after a relaunch', () async {
    var opens = 0;
    await SignupOffers.upsell('u1', () async => (opens++, false).$2);
    expect(opens, 1);
    await _relaunch();
    await SignupOffers.upsell('u1', () async => (opens++, false).$2);
    expect(opens, 1);
  });

  test('offline or no plans: the downsell showed nothing, so the next launch offers it', () async {
    var opens = 0;
    await SignupOffers.upsell('u1', () async => (opens++, null).$2);
    await _relaunch();
    await SignupOffers.upsell('u1', () async => (opens++, false).$2);
    expect(opens, 2);
    expect(SharedPreferencesUtil().getBool(SignupOffers.upsellKey('u1')), isTrue);
  });

  test('per account, and cleared when onboarding completes', () async {
    await SignupOffers.paywall('u1', () async => false);
    await SignupOffers.upsell('u1', () async => false);
    var opens = 0;
    await SignupOffers.paywall('u2', () async => (opens++, false).$2);
    await SignupOffers.upsell('u2', () async => (opens++, false).$2);
    expect(opens, 2);

    SignupOffers.clear('u1');
    await SignupOffers.paywall('u1', () async => (opens++, false).$2);
    await SignupOffers.upsell('u1', () async => (opens++, false).$2);
    expect(opens, 4);
  });
}
