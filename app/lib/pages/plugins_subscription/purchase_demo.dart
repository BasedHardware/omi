import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
// ignore: unused_import
import 'package:flutter/services.dart';
import 'package:in_app_purchase/in_app_purchase.dart';
import 'package:in_app_purchase_storekit/store_kit_wrappers.dart';

class PurchaseDemo {
  static final InAppPurchase inAppPurchase = InAppPurchase.instance;

  ///TODO [LISTEN BUY PURCHASE]
  static Future<void> listenToPurchaseUpdated(
    List<PurchaseDetails> purchaseDetailsList, {
    required Function(PurchaseDetails purchaseDetails) onPurchased,
    required Function() onShowPremiumTransfers,
    Function()? onCanceled,
    Function()? onFailed,
  }) async {
    debugPrint("purchaseDetailsList :- ${purchaseDetailsList.length}");
    for (var purchaseDetails in purchaseDetailsList) {
      debugPrint(
          "final -> ${purchaseDetails.error?.message} : ${purchaseDetails.status}");
      if (purchaseDetails.status == PurchaseStatus.pending) {
        debugPrint("pending");
      } else if (purchaseDetails.status == PurchaseStatus.canceled) {
        if (onCanceled != null) {
          onCanceled();
        }
      } else if (((purchaseDetails.error?.message ?? "")
                  .contains("billingUnavailable") ||
              (purchaseDetails.error?.message ?? "")
                  .contains("networkError")) &&
          purchaseDetails.status == PurchaseStatus.error) {
        //Failed to acknowledge the purchase!
        if (onFailed != null) {
          onFailed();
        }
      } else {
        if (purchaseDetails.pendingCompletePurchase) {
          await inAppPurchase.completePurchase(purchaseDetails);
          if (Platform.isIOS) {
            debugPrint("isIOS 4");
            final paymentWrapper = SKPaymentQueueWrapper();
            final transactions = await paymentWrapper.transactions();
            transactions.forEach((transaction) async {
              await paymentWrapper.finishTransaction(transaction);
            });
            debugPrint("isIOS 5");
          }
        }
        if (Platform.isIOS) {
          debugPrint("isIOS 6 -> ${purchaseDetails.status}");
          if (purchaseDetails.status == PurchaseStatus.error) {
            debugPrint("isIOS 7 -> ${purchaseDetails.error!.message}");
            debugPrint("Error during purchase :");
            debugPrint(purchaseDetails.error!.message);
          } else if (purchaseDetails.status == PurchaseStatus.purchased) {
            onPurchased(purchaseDetails);
          } else if (purchaseDetails.status == PurchaseStatus.restored) {
            debugPrint("isIOS error restored -> ${purchaseDetails.status}");
            onShowPremiumTransfers();
          }
        } else {
          if (purchaseDetails.purchaseID != null &&
              purchaseDetails.purchaseID!.isNotEmpty) {
            if (purchaseDetails.status == PurchaseStatus.restored) {
              onShowPremiumTransfers();
            } else {
              onPurchased(purchaseDetails);
            }
          } else {
            if ((purchaseDetails.error?.message ?? "")
                .contains("AlreadyOwned")) {
              onShowPremiumTransfers();
            }
          }
        }

        if (purchaseDetails.pendingCompletePurchase) {
          debugPrint("call pendingCompletePurchase");
          await inAppPurchase.completePurchase(purchaseDetails);
          if (Platform.isIOS) {
            final paymentWrapper = SKPaymentQueueWrapper();
            final transactions = await paymentWrapper.transactions();
            transactions.forEach((transaction) async {
              await paymentWrapper.finishTransaction(transaction);
            });
          }
        }
      }
    }
  }

}
