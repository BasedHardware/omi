import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:in_app_purchase_platform_interface/in_app_purchase_platform_interface.dart';

import 'package:omi/backend/http/api/play_billing_api.dart';
import 'package:omi/env/env.dart';
import 'package:omi/pages/paywall/paywall_checkout.dart';
import 'package:omi/services/billing/play_billing.dart';

import '../support/fake_play_billing.dart';

void main() {
  late FakePlayPlatform platform;
  late FakePlayServer server;
  late MemoryTokenStore store;
  late PlayBilling billing;

  setUp(() {
    platform = FakePlayPlatform();
    server = FakePlayServer();
    store = MemoryTokenStore();
    billing = PlayBilling(platform: () => platform, verify: server.call, store: store);
  });

  tearDown(() => billing.dispose());

  test('prices are Play strings for each base plan, with the trial offer when Play lists it', () async {
    final offers = (await billing.loadOffers(playConfig))!;
    expect(offers.monthly!.formattedPrice, '₹2,500.00');
    expect(offers.yearly!.formattedPrice, '₹22,500.00');
    expect(offers.yearly!.currencyCode, 'INR');
    expect(offers.monthly!.trialDays, 7);
    expect(offers.yearly!.trialDays, 7); // P1W
    expect(offers.hasTrial, isTrue);

    final paywall = PaywallOffer.fromPlay(offers)!;
    expect(paywall.yearly!.formatted, '₹22,500.00');
    expect(paywall.monthly!.formatted, '₹2,500.00');
    expect(paywall.monthly!.amountMinor, 250000);
    expect(paywall.yearly!.currency, 'inr');
  });

  test('an account Play does not offer the trial to gets no trial offer', () async {
    platform = FakePlayPlatform(details: omiProDetails(withTrial: false));
    final offers = (await billing.loadOffers(playConfig))!;
    expect(offers.hasTrial, isFalse);
    expect(offers.yearly!.trial, isNull);
  });

  test('Play unavailable yields no offers', () async {
    platform = FakePlayPlatform(available: false);
    expect(await billing.loadOffers(playConfig), isNull);
  });

  test('buy starts Play for the selected base plan and its trial offer, then waits for the server', () async {
    final offers = (await billing.loadOffers(playConfig))!;
    platform.onLaunch = [playPurchase(PurchaseStatus.purchased)];
    final result = await billing.purchase(offer: offers.yearly!, withTrial: true, obfuscatedAccountId: 'acct-hash');
    expect(result.outcome, PlayPurchaseOutcome.purchased);
    expect(platform.launched.single.offerToken, 'token-yearly-trial');
    expect(platform.launched.single.applicationUserName, 'acct-hash');
    expect(platform.launched.single.productDetails.id, 'omi_pro');
    expect(server.received, ['omi_pro:purchase-token']);
    expect(store.tokens, isEmpty);
  });

  test('without trial the base plan offer is bought', () async {
    final offers = (await billing.loadOffers(playConfig))!;
    platform.onLaunch = [playPurchase(PurchaseStatus.purchased)];
    await billing.purchase(offer: offers.monthly!, withTrial: false, obfuscatedAccountId: 'acct-hash');
    expect(platform.launched.single.offerToken, 'token-monthly');
  });

  test('a user cancel never reaches the server', () async {
    final offers = (await billing.loadOffers(playConfig))!;
    platform.onLaunch = [playPurchase(PurchaseStatus.canceled)];
    expect((await billing.purchase(offer: offers.monthly!, withTrial: false, obfuscatedAccountId: 'a')).outcome,
        PlayPurchaseOutcome.cancelled);
    expect(server.received, isEmpty);
  });

  test('a pending purchase hands its token to the server right away', () async {
    final offers = (await billing.loadOffers(playConfig))!;
    server.answer = (_, __) => const PlayVerifyResult('pending');
    platform.onLaunch = [playPurchase(PurchaseStatus.pending, token: 'slow-pay')];
    final result = await billing.purchase(offer: offers.monthly!, withTrial: false, obfuscatedAccountId: 'a');
    expect(result.outcome, PlayPurchaseOutcome.pending);
    await Future<void>.delayed(Duration.zero);
    expect(server.received, ['omi_pro:slow-pay']);
  });

  test('a purchase that finishes with no screen waiting still reaches the server once listening', () async {
    billing.startListening(obfuscatedAccountId: 'acct-hash');
    platform.controller.add([playPurchase(PurchaseStatus.purchased, token: 'cleared-later')]);
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);
    expect(server.received, ['omi_pro:cleared-later']);
  });

  test('network loss after payment keeps the token and sends it again on the next launch', () async {
    final offers = (await billing.loadOffers(playConfig))!;
    server.answer = (_, __) => const PlayVerifyResult('error', retryable: true);
    platform.onLaunch = [playPurchase(PurchaseStatus.purchased)];
    final result = await billing.purchase(offer: offers.monthly!, withTrial: false, obfuscatedAccountId: 'a');
    expect(result.outcome, PlayPurchaseOutcome.failed);
    expect(store.tokens.single['token'], 'purchase-token');

    final relaunch = PlayBilling(platform: () => platform, verify: server.call, store: store);
    server.answer = (_, __) => const PlayVerifyResult('active');
    expect(await relaunch.deliverPendingTokens(), isTrue);
    expect(store.tokens, isEmpty);
    expect(server.received, ['omi_pro:purchase-token', 'omi_pro:purchase-token']);
  });

  test('a server refusal is final and reported with its code', () async {
    final offers = (await billing.loadOffers(playConfig))!;
    server.answer = (_, __) => const PlayVerifyResult('error', code: 'stripe_subscription_active');
    platform.onLaunch = [playPurchase(PurchaseStatus.purchased)];
    final result = await billing.purchase(offer: offers.monthly!, withTrial: false, obfuscatedAccountId: 'a');
    expect(result.code, 'stripe_subscription_active');
    expect(store.tokens, isEmpty);
  });

  test('already owned restores the existing purchase instead of failing', () async {
    final offers = (await billing.loadOffers(playConfig))!;
    platform.launchResult = false;
    platform.owned = [playPurchase(PurchaseStatus.restored, token: 'owned-token')];
    final result = await billing.purchase(offer: offers.monthly!, withTrial: false, obfuscatedAccountId: 'a');
    expect(result.outcome, PlayPurchaseOutcome.purchased);
    expect(server.received, ['omi_pro:owned-token']);
  });

  test('restore sends every owned subscription; retired products are refused by the server, never granted', () async {
    platform.owned = [playPurchase(PurchaseStatus.restored, token: 'legacy', product: 'com.omi.app.plus')];
    server.answer = (token, product) => product == 'omi_pro'
        ? const PlayVerifyResult('active')
        : const PlayVerifyResult('error', code: 'legacy_product');
    final legacy = await billing.restore(obfuscatedAccountId: 'a');
    expect(legacy.outcome, PlayPurchaseOutcome.cancelled);
    expect(legacy.code, 'legacy_product');

    platform.owned = [playPurchase(PurchaseStatus.restored, token: 'current')];
    expect((await billing.restore(obfuscatedAccountId: 'a')).outcome, PlayPurchaseOutcome.purchased);
    expect(server.received, ['com.omi.app.plus:legacy', 'omi_pro:current']);
  });

  test('server answers map to keep-or-drop decisions for the stored token', () async {
    Env.overrideApiBaseUrl('http://127.0.0.1:1/');
    addTearDown(Env.clearApiBaseUrlOverrideForTesting);
    Future<PlayVerifyResult> answer(int status, String body) => verifyPlayPurchase(
          purchaseToken: 't',
          productId: 'omi_pro',
          send: (request) async {
            expect(request.url, endsWith('v1/payments/play/purchases'));
            expect(request.body, contains('"purchase_token":"t"'));
            return http.Response(body, status);
          },
        );
    expect((await answer(200, '{"status":"active"}')).status, 'active');
    final owned = await answer(409, '{"detail":"purchase_owned_elsewhere","message":"x"}');
    expect((owned.code, owned.retryable), ('purchase_owned_elsewhere', false));
    expect((await answer(503, '{"detail":"play_unavailable"}')).retryable, isTrue);
    expect((await answer(200, 'not json')).retryable, isTrue);
  });

  test('a token store error ends the purchase as failed instead of leaving it open', () async {
    billing = PlayBilling(platform: () => platform, verify: server.call, store: _BrokenTokenStore());
    final offers = (await billing.loadOffers(playConfig))!;
    platform.onLaunch = [playPurchase(PurchaseStatus.purchased)];
    final result = await billing.purchase(offer: offers.monthly!, withTrial: false, obfuscatedAccountId: 'a');
    expect(result.outcome, PlayPurchaseOutcome.failed);
    expect(billing.busy, isFalse);
  });

  test('a cleanup error after the server granted the plan still reports the purchase', () async {
    final failing = _FailingCleanupStore();
    billing = PlayBilling(platform: () => platform, verify: server.call, store: failing);
    final offers = (await billing.loadOffers(playConfig))!;
    platform.onLaunch = [playPurchase(PurchaseStatus.purchased)];
    final result = await billing.purchase(offer: offers.monthly!, withTrial: false, obfuscatedAccountId: 'a');
    expect(result.outcome, PlayPurchaseOutcome.purchased);
    expect(billing.busy, isFalse);
    expect(failing.tokens.single['token'], 'purchase-token'); // sent once more on the next launch
  });

  test('manage subscription opens Play subscription center for omi_pro', () {
    expect(
      playManageSubscriptionUri('omi_pro').toString(),
      'https://play.google.com/store/account/subscriptions?sku=omi_pro&package=com.friend.ios',
    );
  });
}

class _BrokenTokenStore implements PlayPendingTokenStore {
  @override
  Future<List<Map<String, String>>> read() async => throw StateError('store unavailable');

  @override
  Future<void> write(List<Map<String, String>> value) async => throw StateError('store unavailable');
}

/// Stores the token, then fails every later write.
class _FailingCleanupStore extends MemoryTokenStore {
  var _writes = 0;

  @override
  Future<void> write(List<Map<String, String>> value) async {
    if (++_writes > 1) throw StateError('store unavailable');
    await super.write(value);
  }
}
