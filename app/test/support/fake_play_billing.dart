import 'dart:async';

import 'package:in_app_purchase_android/billing_client_wrappers.dart';
import 'package:in_app_purchase_android/in_app_purchase_android.dart';
import 'package:in_app_purchase_platform_interface/in_app_purchase_platform_interface.dart';

import 'package:omi/backend/http/api/play_billing_api.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/services/billing/play_billing.dart';

const playConfig = PlayBillingConfig(
  productId: 'omi_pro',
  basePlans: {'monthly': 'month', 'yearly': 'year'},
  trialOfferId: 'trial-7d',
  obfuscatedAccountId: 'acct-hash',
);

PricingPhaseWrapper _phase(String price, int micros, String period, {String currency = 'INR'}) => PricingPhaseWrapper(
      billingCycleCount: 0,
      billingPeriod: period,
      formattedPrice: price,
      priceAmountMicros: micros,
      priceCurrencyCode: currency,
      recurrenceMode: RecurrenceMode.infiniteRecurring,
    );

/// Play's answer for omi_pro in a non-US currency: both base plans plus the 7-day trial offer on each.
List<GooglePlayProductDetails> omiProDetails({bool withTrial = true}) {
  final offers = <SubscriptionOfferDetailsWrapper>[
    SubscriptionOfferDetailsWrapper(
      basePlanId: 'monthly',
      offerTags: const [],
      offerIdToken: 'token-monthly',
      pricingPhases: [_phase('₹2,500.00', 2500000000, 'P1M')],
    ),
    SubscriptionOfferDetailsWrapper(
      basePlanId: 'yearly',
      offerTags: const [],
      offerIdToken: 'token-yearly',
      pricingPhases: [_phase('₹22,500.00', 22500000000, 'P1Y')],
    ),
    if (withTrial) ...[
      SubscriptionOfferDetailsWrapper(
        basePlanId: 'monthly',
        offerId: 'trial-7d',
        offerTags: const [],
        offerIdToken: 'token-monthly-trial',
        pricingPhases: [_phase('Free', 0, 'P7D'), _phase('₹2,500.00', 2500000000, 'P1M')],
      ),
      SubscriptionOfferDetailsWrapper(
        basePlanId: 'yearly',
        offerId: 'trial-7d',
        offerTags: const [],
        offerIdToken: 'token-yearly-trial',
        pricingPhases: [_phase('Free', 0, 'P1W'), _phase('₹22,500.00', 22500000000, 'P1Y')],
      ),
    ],
  ];
  return GooglePlayProductDetails.fromProductDetails(
    ProductDetailsWrapper(
      description: 'Omi Pro',
      name: 'Omi Pro',
      productId: 'omi_pro',
      productType: ProductType.subs,
      subscriptionOfferDetails: offers,
      title: 'Omi Pro (Omi)',
    ),
  );
}

PurchaseDetails playPurchase(PurchaseStatus status, {String token = 'purchase-token', String product = 'omi_pro'}) {
  final purchase = PurchaseDetails(
    productID: product,
    verificationData: PurchaseVerificationData(
      localVerificationData: '{}',
      serverVerificationData: token,
      source: 'google_play',
    ),
    transactionDate: '0',
    status: status,
  );
  return purchase;
}

/// Fake Play Billing client: records purchase params; tests push purchase updates.
class FakePlayPlatform extends InAppPurchasePlatform {
  FakePlayPlatform({List<GooglePlayProductDetails>? details, this.available = true})
      : details = details ?? omiProDetails();

  final List<GooglePlayProductDetails> details;
  final bool available;
  final controller = StreamController<List<PurchaseDetails>>.broadcast();
  final List<GooglePlayPurchaseParam> launched = [];
  bool launchResult = true;
  List<PurchaseDetails> owned = [];

  /// What the Play sheet does after launch; null leaves the purchase open.
  List<PurchaseDetails>? onLaunch;

  @override
  Stream<List<PurchaseDetails>> get purchaseStream => controller.stream;

  @override
  Future<bool> isAvailable() async => available;

  @override
  Future<ProductDetailsResponse> queryProductDetails(Set<String> identifiers) async =>
      ProductDetailsResponse(productDetails: details, notFoundIDs: const []);

  @override
  Future<bool> buyNonConsumable({required PurchaseParam purchaseParam}) async {
    launched.add(purchaseParam as GooglePlayPurchaseParam);
    final update = onLaunch;
    if (launchResult && update != null) scheduleMicrotask(() => controller.add(update));
    return launchResult;
  }

  @override
  Future<void> restorePurchases({String? applicationUserName}) async {
    if (owned.isNotEmpty) controller.add(owned);
  }
}

class MemoryTokenStore implements PlayPendingTokenStore {
  List<Map<String, String>> tokens = [];

  @override
  Future<List<Map<String, String>>> read() async => List.of(tokens);

  @override
  Future<void> write(List<Map<String, String>> value) async => tokens = List.of(value);
}

/// Server double for POST /v1/payments/play/purchases.
class FakePlayServer {
  final List<String> received = [];
  PlayVerifyResult Function(String token, String product) answer = (_, __) => const PlayVerifyResult('active');

  Future<PlayVerifyResult> call(String token, String product) async {
    received.add('$product:$token');
    return answer(token, product);
  }
}
