import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:in_app_purchase_android/billing_client_wrappers.dart';
import 'package:in_app_purchase_android/in_app_purchase_android.dart';
import 'package:in_app_purchase_platform_interface/in_app_purchase_platform_interface.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/play_billing_api.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/utils/logger.dart';

/// Google Play Billing for new Android Omi Pro purchases. Prices, currency and cart come from Play;
/// the server verifies, acknowledges and grants. Nothing here runs unless the server sent
/// [PlayBillingConfig] for this build.
enum PlayPurchaseOutcome { purchased, pending, cancelled, failed }

/// Result of one purchase or restore, with the server refusal code when there is one.
@immutable
class PlayPurchaseResult {
  const PlayPurchaseResult(this.outcome, {this.code});

  final PlayPurchaseOutcome outcome;
  final String? code;
}

/// One base plan as Play sells it to this Google account, in its own currency.
@immutable
class PlayPlanOffer {
  const PlayPlanOffer({
    required this.basePlanId,
    required this.interval,
    required this.formattedPrice,
    required this.priceMicros,
    required this.currencyCode,
    required this.base,
    this.trial,
    this.trialDays,
    this.trialFormattedPrice,
  });

  final String basePlanId;

  /// 'month' | 'year'
  final String interval;

  /// Play's own price string for the recurring phase, e.g. "₹2,500.00".
  final String formattedPrice;
  final int priceMicros;
  final String currencyCode;
  final GooglePlayProductDetails base;

  /// The free-trial offer when Play lists it for this account (Play applies new-subscriber eligibility).
  final GooglePlayProductDetails? trial;
  final int? trialDays;

  /// Play's own string for the free-trial phase (e.g. "Free" or "₹0.00").
  final String? trialFormattedPrice;
}

@immutable
class PlayOffers {
  const PlayOffers({this.monthly, this.yearly});

  final PlayPlanOffer? monthly;
  final PlayPlanOffer? yearly;

  PlayPlanOffer? forInterval(String interval) => interval == 'year' ? yearly : monthly;

  bool get hasTrial => (monthly?.trial ?? yearly?.trial) != null;
}

/// Tokens paid for but not yet confirmed by the server; sent again on the next launch.
abstract class PlayPendingTokenStore {
  Future<List<Map<String, String>>> read();
  Future<void> write(List<Map<String, String>> tokens);
}

class _PrefsPendingTokenStore implements PlayPendingTokenStore {
  static const _key = 'playBilling/pendingTokens';

  @override
  Future<List<Map<String, String>>> read() async {
    final raw = (await SharedPreferences.getInstance()).getString(_key);
    if (raw == null) return [];
    try {
      return (jsonDecode(raw) as List).whereType<Map>().map((e) => Map<String, String>.from(e)).toList();
    } catch (_) {
      return [];
    }
  }

  @override
  Future<void> write(List<Map<String, String>> tokens) async =>
      (await SharedPreferences.getInstance()).setString(_key, jsonEncode(tokens));
}

typedef PlayVerifier = Future<PlayVerifyResult> Function(String purchaseToken, String productId);

class PlayBilling {
  PlayBilling({InAppPurchasePlatform Function()? platform, PlayVerifier? verify, PlayPendingTokenStore? store})
      : _platform = platform ?? androidPlayPlatform,
        _verify = verify ?? ((token, product) => verifyPlayPurchase(purchaseToken: token, productId: product)),
        _store = store ?? _PrefsPendingTokenStore();

  static PlayBilling instance = PlayBilling();

  static bool _registered = false;

  /// The plugin's Android platform, registered on first use. Not at startup: its client connects to
  /// Play when created, and only users the server put on Play Billing should pay that cost.
  static InAppPurchasePlatform androidPlayPlatform() {
    if (!_registered) {
      InAppPurchaseAndroidPlatform.registerPlatform();
      _registered = true;
    }
    return InAppPurchasePlatform.instance;
  }

  /// Starts listening for purchase updates so a purchase that finishes while no screen waits for it
  /// (slow payment, Play Store resubscribe, app restarted mid-purchase) still reaches the server.
  void startListening({required String obfuscatedAccountId}) {
    if (_accountId.isEmpty) _accountId = obfuscatedAccountId;
    _listen();
  }

  final InAppPurchasePlatform Function() _platform;
  final PlayVerifier _verify;
  final PlayPendingTokenStore _store;

  StreamSubscription<List<PurchaseDetails>>? _subscription;
  Completer<PlayPurchaseResult>? _purchase;
  final Set<Future<PlayPurchaseResult>> _deliveries = {};
  final Set<String> _delivering = {};
  String _accountId = '';

  void _listen() {
    _subscription ??= _platform().purchaseStream.listen(_onPurchases, onError: (Object error) {
      Logger.debug('Play purchase stream error: $error');
      _finish(const PlayPurchaseResult(PlayPurchaseOutcome.failed));
    });
  }

  void _finish(PlayPurchaseResult result) {
    final active = _purchase;
    _purchase = null;
    if (active != null && !active.isCompleted) active.complete(result);
  }

  /// Play's offers for the configured base plans; null when Play is unavailable or has no product.
  Future<PlayOffers?> loadOffers(PlayBillingConfig config) async {
    final platform = _platform();
    if (!await platform.isAvailable()) return null;
    final response = await platform.queryProductDetails({config.productId});
    if (response.error != null) Logger.debug('Play product query error: ${response.error}');
    PlayPlanOffer? monthly;
    PlayPlanOffer? yearly;
    final details = response.productDetails.whereType<GooglePlayProductDetails>();
    for (final entry in config.basePlans.entries) {
      GooglePlayProductDetails? base;
      GooglePlayProductDetails? trial;
      for (final item in details) {
        final offer = _offer(item);
        if (offer == null || item.id != config.productId || offer.basePlanId != entry.key) continue;
        if (offer.offerId == null) base = item;
        if (offer.offerId == config.trialOfferId) trial = item;
      }
      if (base == null) continue;
      final recurring = _offer(base)!.pricingPhases.last;
      final plan = PlayPlanOffer(
        basePlanId: entry.key,
        interval: entry.value,
        formattedPrice: recurring.formattedPrice,
        priceMicros: recurring.priceAmountMicros,
        currencyCode: recurring.priceCurrencyCode,
        base: base,
        trial: trial,
        trialDays: trial == null ? null : _trialDays(_offer(trial)!),
        trialFormattedPrice: trial == null ? null : _offer(trial)!.pricingPhases.first.formattedPrice,
      );
      if (entry.value == 'year') {
        yearly = plan;
      } else {
        monthly = plan;
      }
    }
    if (monthly == null && yearly == null) return null;
    return PlayOffers(monthly: monthly, yearly: yearly);
  }

  static SubscriptionOfferDetailsWrapper? _offer(GooglePlayProductDetails item) {
    final index = item.subscriptionIndex;
    final offers = item.productDetails.subscriptionOfferDetails;
    if (index == null || offers == null || index >= offers.length) return null;
    return offers[index];
  }

  static int? _trialDays(SubscriptionOfferDetailsWrapper offer) {
    for (final phase in offer.pricingPhases) {
      if (phase.priceAmountMicros != 0) continue;
      final match = RegExp(r'^P(\d+)([DW])$').firstMatch(phase.billingPeriod);
      if (match == null) return null;
      final count = int.parse(match.group(1)!);
      return match.group(2) == 'W' ? count * 7 : count;
    }
    return null;
  }

  /// Starts Play's purchase sheet for [offer] (its trial offer when [withTrial] and Play lists one) and
  /// completes once the server has confirmed the entitlement, or with why it did not.
  Future<PlayPurchaseResult> purchase({
    required PlayPlanOffer offer,
    required bool withTrial,
    required String obfuscatedAccountId,
  }) async {
    if (_purchase != null) return const PlayPurchaseResult(PlayPurchaseOutcome.failed);
    _accountId = obfuscatedAccountId;
    _listen();
    final details = withTrial && offer.trial != null ? offer.trial! : offer.base;
    final completer = Completer<PlayPurchaseResult>();
    _purchase = completer;
    try {
      final launched = await _platform().buyNonConsumable(
        purchaseParam: GooglePlayPurchaseParam(
          productDetails: details,
          offerToken: details.offerToken,
          applicationUserName: obfuscatedAccountId,
        ),
      );
      if (!launched) {
        // Play refuses to launch when this Google account already owns the subscription.
        _purchase = null;
        final restored = await restore(obfuscatedAccountId: obfuscatedAccountId);
        return restored.outcome == PlayPurchaseOutcome.purchased
            ? restored
            : const PlayPurchaseResult(PlayPurchaseOutcome.failed);
      }
    } catch (error) {
      Logger.debug('Play purchase launch failed: $error');
      _finish(const PlayPurchaseResult(PlayPurchaseOutcome.failed));
    }
    return completer.future;
  }

  /// Sends every Play subscription this Google account owns to the server; purchased when one is active.
  Future<PlayPurchaseResult> restore({required String obfuscatedAccountId}) async {
    _listen();
    _deliveries.clear();
    try {
      await _platform().restorePurchases(applicationUserName: obfuscatedAccountId);
    } catch (error) {
      Logger.debug('Play restore failed: $error');
      return const PlayPurchaseResult(PlayPurchaseOutcome.failed);
    }
    // Restored purchases arrive on the broadcast stream right after the call returns.
    await Future<void>.delayed(Duration.zero);
    final results = await Future.wait(_deliveries.toList());
    if (results.any((r) => r.outcome == PlayPurchaseOutcome.purchased)) {
      return const PlayPurchaseResult(PlayPurchaseOutcome.purchased);
    }
    if (results.any((r) => r.outcome == PlayPurchaseOutcome.pending)) {
      return const PlayPurchaseResult(PlayPurchaseOutcome.pending);
    }
    final refused = results.map((r) => r.code).whereType<String>();
    return PlayPurchaseResult(PlayPurchaseOutcome.cancelled, code: refused.isEmpty ? null : refused.first);
  }

  Future<void> _onPurchases(List<PurchaseDetails> purchases) async {
    for (final purchase in purchases) {
      switch (purchase.status) {
        case PurchaseStatus.pending:
          // Hand the token over now: the server records it (no access yet) and grants when Google clears
          // the payment, even if the app is never opened again.
          final token = purchase.verificationData.serverVerificationData;
          if (token.isNotEmpty) unawaited(_deliver(token, purchase.productID));
          _finish(const PlayPurchaseResult(PlayPurchaseOutcome.pending));
        case PurchaseStatus.canceled:
          _finish(const PlayPurchaseResult(PlayPurchaseOutcome.cancelled));
        case PurchaseStatus.error:
          if ((purchase.error?.message ?? '').contains('itemAlreadyOwned')) {
            final completer = _purchase;
            _purchase = null;
            final restored = await restore(obfuscatedAccountId: _accountId);
            if (completer != null && !completer.isCompleted) completer.complete(restored);
          } else {
            _finish(const PlayPurchaseResult(PlayPurchaseOutcome.failed));
          }
        case PurchaseStatus.purchased:
        case PurchaseStatus.restored:
          // Every owned subscription goes to the server, which refuses (and logs) retired products.
          final delivery = _deliver(purchase.verificationData.serverVerificationData, purchase.productID);
          _deliveries.add(delivery);
          final result = await delivery;
          if (purchase.status == PurchaseStatus.purchased) _finish(result);
      }
    }
  }

  Future<PlayPurchaseResult> _deliver(String token, String productId) async {
    if (token.isEmpty || !_delivering.add(token)) return const PlayPurchaseResult(PlayPurchaseOutcome.failed);
    try {
      final pending = await _store.read();
      if (!pending.any((t) => t['token'] == token)) {
        await _store.write([
          ...pending,
          {'token': token, 'product': productId},
        ]);
      }
      final result = await _verify(token, productId);
      if (!result.retryable) {
        await _store.write((await _store.read()).where((t) => t['token'] != token).toList());
      }
      return switch (result.status) {
        'active' => const PlayPurchaseResult(PlayPurchaseOutcome.purchased),
        'pending' => const PlayPurchaseResult(PlayPurchaseOutcome.pending),
        _ => PlayPurchaseResult(PlayPurchaseOutcome.failed, code: result.code),
      };
    } finally {
      _delivering.remove(token);
    }
  }

  /// Re-sends tokens paid for in an earlier session whose delivery failed. True when one became active.
  Future<bool> deliverPendingTokens() async {
    var activated = false;
    for (final entry in await _store.read()) {
      final token = entry['token'];
      final product = entry['product'];
      if (token == null || product == null) continue;
      if ((await _deliver(token, product)).outcome == PlayPurchaseOutcome.purchased) activated = true;
    }
    return activated;
  }

  @visibleForTesting
  Future<void> dispose() async {
    await _subscription?.cancel();
    _subscription = null;
    _purchase = null;
  }
}

/// Play's subscription center for this product.
Uri playManageSubscriptionUri(String productId, {String packageName = 'com.friend.ios'}) =>
    Uri.https('play.google.com', '/store/account/subscriptions', {'sku': productId, 'package': packageName});
