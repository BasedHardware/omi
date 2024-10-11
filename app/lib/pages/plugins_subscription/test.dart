import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:in_app_purchase/in_app_purchase.dart';
import 'package:purchases_flutter/purchases_flutter.dart';
import 'package:uuid/uuid.dart';

import '../../backend/preferences.dart';
import '../../utils/purchase/store_config.dart';

class RCPurchaseController {
  final InAppPurchase _inAppPurchase = InAppPurchase.instance;
  StreamSubscription<List<PurchaseDetails>>? subscription;
  String? subscriptionComplete;



  Future<void> restorePurchases() async {
    // Ensure the same App User ID is used across both devices
    await Purchases.logIn(SharedPreferencesUtil().email);
    bool available = await _inAppPurchase.isAvailable();
    if (!available) {
      return ;
    }

    unawaited(_inAppPurchase.restorePurchases());
    RCPurchaseStatus purchaseStatus =
    await managePurchase(isRestorePurchases: true);
    cancelPurchaseStream();
    debugPrint("----------??????? ${purchaseStatus}");

  }



  Future<RCPurchaseStatus> managePurchase({
    bool isRestorePurchases = false,
  }) async {
    Completer<RCPurchaseStatus> completer = Completer<RCPurchaseStatus>();
    subscription = _inAppPurchase.purchaseStream.listen(
          (event) {
        debugPrint("event event isEmpty:- ${event.isEmpty}");
        for (var element in event) {
          debugPrint("element :- ${element.status}");
        }
      },
      onDone: () {
        debugPrint("onDone onDone onDone");
      },
      onError: (error) {
        debugPrint("call on onError");
        debugPrint(error.toString());
        completer.complete(RCPurchaseStatus.error);
      },
    ) as StreamSubscription<List<PurchaseDetails>>?;

    return completer.future;
  }

  void cancelPurchaseStream() {
    subscription?.cancel();
    subscription = null;
  }


  CustomerInfo? customerInfo;
  Future<void> initPlatformState() async {
    await Purchases.setLogLevel(LogLevel.debug);
    PurchasesConfiguration configuration;

    // Retrieve PurchaserInfo and check if the user is subscribed
    configuration = PurchasesConfiguration(StoreConfig.instance.apiKey);
    await Purchases.configure(configuration);
    // Ensure the same App User ID is used across both devices
    await Purchases.logIn("mobidev412@gmail.com");
    await Purchases.enableAdServicesAttributionTokenCollection();
    final customerInfoTemp = await Purchases.getCustomerInfo();
    Purchases.addReadyForPromotedProductPurchaseListener(
            (productID, startPurchase) async {
          debugPrint("Received readyForPromotedProductPurchase event for "
              "productID: $productID");
          try {
            final purchaseResult = await startPurchase.call();
            debugPrint("Promoted purchase for productID "
                "${purchaseResult.productIdentifier} completed, or product was "
                "already purchased. customerInfo returned is:"
                " ${purchaseResult.customerInfo}");
          } on PlatformException catch (e) {
            debugPrint("Error purchasing promoted product: ${e.message}");
          }
        });

    debugPrint("customerInfoTemp : $customerInfoTemp");
    SharedPreferencesUtil().activeSubscriptionPluginList = customerInfoTemp.activeSubscriptions;
    customerInfo = customerInfoTemp;
  }

  Future<void> restorePurchasesFlutterPurchase() async {
    try {
      CustomerInfo restoredInfo = await Purchases.restorePurchases();
      print('*** restoredInfo ***');
      print(restoredInfo);
      print(restoredInfo.entitlements);

    } on PlatformException catch (e) {
      // Handle errors specific to RevenueCat using PurchasesErrorHelper
      var errorCode = PurchasesErrorHelper.getErrorCode(e);

      switch (errorCode) {
        case PurchasesErrorCode.purchaseCancelledError:
          print("Restore cancelled by the user.");
          break;
        case PurchasesErrorCode.networkError:
          print("Network error occurred while restoring purchases.");
          break;
        case PurchasesErrorCode.purchaseNotAllowedError:
          print("Purchases are not allowed on this device.");
          break;
        case PurchasesErrorCode.purchaseInvalidError:
          print("Invalid purchase data during restore.");
          break;
        case PurchasesErrorCode.unknownError:
        default:
          print("An unknown error occurred during restore: ${e.message}");
          //scaffoldMessage("An unexpected error occurred. Please try again.");
          break;
      }
    } catch (e) {
      // Handle any other unexpected errors
      print("An unexpected error occurred: $e");
      //scaffoldMessage("An unexpected error occurred. Please try again.");
    }
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
