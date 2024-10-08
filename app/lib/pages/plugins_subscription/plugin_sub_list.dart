import 'dart:convert';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/utils/purchase/store_config.dart';
import 'package:purchases_flutter/purchases_flutter.dart';

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
    configuration = PurchasesConfiguration(StoreConfig.instance.apiKey);
    await Purchases.configure(configuration);
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
                        offering!.availablePackages[index].identifier,
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
                          try {
                            CustomerInfo customerInfo =
                                await Purchases.purchasePackage(
                                    offering!.availablePackages[index]);
                            print(customerInfo);
                          } catch (e) {
                            print(e);
                          }
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
            : const CircularProgressIndicator(strokeWidth: 2, color: Colors.white,),
      ),
    );
  }
}
