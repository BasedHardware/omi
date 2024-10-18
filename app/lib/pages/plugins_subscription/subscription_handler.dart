import 'dart:async';
import 'package:flutter/material.dart';
import 'package:friend_private/pages/plugins_subscription/purchase_demo.dart';
import 'package:in_app_purchase/in_app_purchase.dart';

class RCPurchaseController {
  final InAppPurchase _inAppPurchase = InAppPurchase.instance;
  StreamSubscription<List<PurchaseDetails>>? subscription;
  String? subscriptionComplete;

  purchaseFromAppStore(String productId) async {
    return onPurchase(productId: productId);
  }

  onPurchase({required String productId}) async {
    bool available = await _inAppPurchase.isAvailable();
    if (!available) {
      return "In-app purchases are not available.";
    }

    final ProductDetailsResponse response =
        await _inAppPurchase.queryProductDetails({productId});
    if (response.productDetails.isEmpty) {
      return "Product not found";
    }

    final PurchaseParam purchaseParam = PurchaseParam(
      productDetails: response.productDetails.first,
    );

    unawaited(_inAppPurchase.buyConsumable(purchaseParam: purchaseParam));
    PurchaseDetails? purchaseStatus = await managePurchase();
    cancelPurchaseStream();
    if (purchaseStatus != null) {
      return purchaseStatus;
    }

    return "something went wrong";
  }

  restorePurchases() async {
    bool available = await _inAppPurchase.isAvailable();
    if (!available) {
      return "In-app purchases are not available.";
    }

    unawaited(_inAppPurchase.restorePurchases());
    PurchaseDetails? purchaseStatus =
        await managePurchase(isRestorePurchases: true);
    cancelPurchaseStream();
    if (purchaseStatus != null) {
      // todo
    }

    return "No active subscription found!";
  }

  Future<PurchaseDetails?> managePurchase({
    bool isRestorePurchases = false,
  }) async {
    Completer<PurchaseDetails?> completer = Completer<PurchaseDetails?>();
    bool isCompleted = false;
    try {
      subscription = _inAppPurchase.purchaseStream.listen(
        (event) {
          PurchaseDemo.listenToPurchaseUpdated(
            event,
            onPurchased: (purchaseDetails) {
              debugPrint("call purchaseDetails purchased");
              if (!isCompleted) {
                isCompleted = true;
                completer.complete(purchaseDetails);
              }
            },
            onShowPremiumTransfers: () {
              debugPrint("need to transfer subscription");
              if (!isCompleted) {
                isCompleted = true;
                completer.complete(null);
              }
            },
            onCanceled: () {
              debugPrint("!!!!!!! onCanceled");
              if (!isCompleted) {
                isCompleted = true;
                completer.complete(null);
              }
            },
            onFailed: () {
              debugPrint("!!!!!!! onFailed");
              if (!isCompleted) {
                isCompleted = true;
                completer.complete(null);
              }
            },
          );
        },
        onDone: () {
          debugPrint("onDone onDone onDone");
          debugPrint("Stream is done");
        },
        onError: (error) {
          debugPrint("call on onError !!!!!!!");
          debugPrint(error.toString());
          if (!isCompleted) {
            isCompleted = true;
            completer.complete(null);
          }
        },
      ) as StreamSubscription<List<PurchaseDetails>>?;
    } catch (_) {
      debugPrint("^^^^^^^^^^^^ -> $_+");
    }

    return completer.future;
  }

  void cancelPurchaseStream() {
    subscription?.cancel();
    subscription = null;
  }
}

enum RCPurchaseStatus {
  pending,
  purchased,
  error,
  restored,
  canceled,
  transferPurchase
}
