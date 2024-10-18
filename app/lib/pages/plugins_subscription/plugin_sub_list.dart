import 'dart:convert';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/pages/plugins_subscription/subscription_handler.dart';
import 'package:friend_private/utils/purchase/store_config.dart';
import 'package:in_app_purchase/in_app_purchase.dart';
import 'package:purchases_flutter/purchases_flutter.dart';

import '../../backend/preferences.dart';

class PluginSubscriptionList extends StatefulWidget {
  const PluginSubscriptionList({super.key});

  @override
  State<PluginSubscriptionList> createState() => _PluginSubscriptionListState();
}

class _PluginSubscriptionListState extends State<PluginSubscriptionList> {
  CustomerInfo? customerInfo;
  Offering? offering;

  @override
  void initState() {
    super.initState();
    initPlatformState().then((value) {
      fetchData().then((value) {
        setState(() {});
      });
    });
  }

  Future<void> initPlatformState() async {
    await Purchases.setLogLevel(LogLevel.debug);
    PurchasesConfiguration configuration;

    // Retrieve PurchaserInfo and check if the user is subscribed
    configuration = PurchasesConfiguration(StoreConfig.instance.apiKey);
    await Purchases.configure(configuration);
    // Ensure the same App User ID is used across both devices
    await Purchases.logIn(SharedPreferencesUtil().email);
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
    SharedPreferencesUtil().activeSubscriptionPluginList =
        customerInfoTemp.activeSubscriptions;
    customerInfo = customerInfoTemp;
  }

  Future<void> fetchData() async {
    late Offerings offeringsTemp;
    try {
      offeringsTemp = await Purchases.getOfferings();
    } on PlatformException catch (e) {
      debugPrint(e.toString());
    }
    try {
      offering = offeringsTemp.getOffering("Luca");
      for (var i = 0; i < (offering?.availablePackages.length ?? 0); i++) {
        final element = offering!.availablePackages[i];
        debugPrint(
          "element subscriptionOffering || ${i + 1} || ${jsonEncode(element.toJson())}",
        );
      }
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.primary,
        automaticallyImplyLeading: true,
        title: const Text('Plugin Subscriptions'),
        centerTitle: true,
        elevation: 0,
      ),
      bottomNavigationBar: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10.0),
        child: ElevatedButton(
          onPressed: () async {
            await restorePurchases();
          },
          style: ElevatedButton.styleFrom(
            backgroundColor: Colors.deepPurple,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(8.0),
            ),
          ),
          child: const Text(
            'RESTORE SUBSCRIPTION',
            style: TextStyle(
              fontWeight: FontWeight.w400,
              fontSize: 16,
              color: Colors.white,
            ),
          ),
        ),
      ),
      body: Center(
        child: offering != null
            ? ListView.builder(
                itemCount: offering!.availablePackages.length,
                itemBuilder: (context, index) {
                  return Container(
                    padding: const EdgeInsets.fromLTRB(8, 8, 0, 8),
                    decoration: BoxDecoration(
                      shape: BoxShape.rectangle,
                      borderRadius:
                          const BorderRadius.all(Radius.circular(16.0)),
                      color: Colors.grey.shade900,
                    ),
                    margin: EdgeInsets.only(
                        bottom: 12,
                        top: index == 0 ? 24 : 0,
                        left: 16,
                        right: 16),
                    child: ListTile(
                      onTap: () async {},
                      leading: CachedNetworkImage(
                        imageUrl: '',
                        imageBuilder: (context, imageProvider) => CircleAvatar(
                          backgroundColor: Colors.white,
                          maxRadius: 28,
                          backgroundImage: imageProvider,
                        ),
                        placeholder: (context, url) =>
                            const CircularProgressIndicator(),
                        errorWidget: (context, url, error) =>
                            const Icon(Icons.error),
                      ),
                      title: Text(
                        offering!.availablePackages[index].storeProduct.title,
                        maxLines: 1,
                        style: const TextStyle(
                            fontWeight: FontWeight.w600,
                            color: Colors.white,
                            fontSize: 16),
                      ),
                      trailing: ElevatedButton(
                        style: ElevatedButton.styleFrom(
                            backgroundColor: Colors.deepPurple,
                            shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(8.0))),
                        onPressed: () async {
                          await purchasePluginSubscription(
                              offeringId: offering!.availablePackages[index]);
                        },
                        child: const Text(
                          'Subscribe',
                          style: TextStyle(
                              color: Colors.white,
                              fontSize: 12,
                              fontWeight: FontWeight.w500),
                        ),
                      ),
                    ),
                  );
                },
              )
            : const CircularProgressIndicator(
                strokeWidth: 2,
                color: Colors.white,
              ),
      ),
    );
  }

  purchasePluginSubscription({required Package offeringId}) async {
    try {
      debugPrint(
          "SharedPreferencesUtil().uid :- ${SharedPreferencesUtil().uid} -? ${FirebaseAuth.instance.currentUser?.uid}");
      debugPrint(
          "offeringId.storeProduct.identifier :- ${offeringId.storeProduct.defaultOption?.productId}");
      RCPurchaseController rCPurchaseController = RCPurchaseController();
      var data = await rCPurchaseController.onPurchase(
          productId: offeringId.storeProduct.defaultOption?.productId ?? "");

      if (data is String) {
        /// error
        debugPrint("dadadxgacgafcgh -> $data");
        scaffoldMessage(data);
      } else if (data is PurchaseDetails) {
        // todo api

        var mainHeaders = {"Content-Type": "application/json; charset=UTF-8"};

        debugPrint(
            "SharedPreferencesUtil().uid :- ${SharedPreferencesUtil().uid} -? ${FirebaseAuth.instance.currentUser?.uid}");

        Map<String, dynamic> passDate = {
          'userId': SharedPreferencesUtil().uid,
          'receipt': data.verificationData.serverVerificationData,
          'platform': "android",
          'productId': data.productID,
          'purchaseId': data.purchaseID,
          'pluginId': offeringId.identifier
        };

        debugPrint("-????????? $passDate");

        var response = await makeApiCall(
          url:
              "https://us-central1-ai-wearable.cloudfunctions.net/purchaseComplete",
          method: 'POST',
          headers: mainHeaders,
          body: json.encode(passDate),
        );

        debugPrint("response response :- ${response?.body}");

        debugPrint("data :- ${data.purchaseID}");
        debugPrint("data :- ${data.verificationData.serverVerificationData}");
      }
    } on PlatformException catch (e) {
      // Handle error based on RevenueCat error codes
      var errorCode = PurchasesErrorHelper.getErrorCode(e);

      switch (errorCode) {
        case PurchasesErrorCode.purchaseCancelledError:
          scaffoldMessage("User canceled the purchase");
          break;
        case PurchasesErrorCode.networkError:
          scaffoldMessage("Network error occurred during purchase");
          break;
        case PurchasesErrorCode.purchaseNotAllowedError:
          scaffoldMessage("User is not allowed to make purchases");
          break;
        case PurchasesErrorCode.purchaseInvalidError:
          scaffoldMessage("The purchase is invalid");
          break;
        default:
          print("Unknown error occurred: ${e.message}");
          scaffoldMessage("An unexpected error occurred. Please try again.");
          break;
      }
    } catch (e) {
      // Handle any other errors
      scaffoldMessage("An unexpected error occurred. Please try again.");
    }
  }

  Future<void> restorePurchases() async {
    /*await RCPurchaseController().restorePurchases();
    return;*/
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
          scaffoldMessage("Restore cancelled by the user.");
          break;
        case PurchasesErrorCode.networkError:
          scaffoldMessage("Network error occurred while restoring purchases.");
          break;
        case PurchasesErrorCode.purchaseNotAllowedError:
          scaffoldMessage("Purchases are not allowed on this device.");
          break;
        case PurchasesErrorCode.purchaseInvalidError:
          scaffoldMessage("Invalid purchase data during restore.");
          break;
        case PurchasesErrorCode.unknownError:
        default:
          print("An unknown error occurred during restore: ${e.message}");
          scaffoldMessage("An unexpected error occurred. Please try again.");
          break;
      }
    } catch (e) {
      // Handle any other unexpected errors
      print("An unexpected error occurred: $e");
      scaffoldMessage("An unexpected error occurred. Please try again.");
    }
  }

  scaffoldMessage(String message) {
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(message)));
  }
}
