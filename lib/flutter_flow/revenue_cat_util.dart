import 'dart:io' show Platform;
import 'package:purchases_flutter/purchases_flutter.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/services.dart';

Offerings? _offerings;
CustomerInfo? _customerInfo;
String? _loggedInUid;

Offerings? get offerings => _offerings;
CustomerInfo? get customerInfo => _customerInfo;

set customerInfo(CustomerInfo? customerInfo) => _customerInfo = customerInfo;

Future initialize(
  String appStoreKey,
  String playStoreKey, {
  bool debugLogEnabled = false,
  bool loadDataAfterLaunch = false,
}) async {
  if (kIsWeb) {
    print('RevenueCat is not supported on web.');
    return;
  }
  try {
    if (Platform.isIOS) {
      await Purchases.setDebugLogsEnabled(debugLogEnabled);
      await Purchases.setup(appStoreKey);
    } else if (Platform.isAndroid) {
      await Purchases.setDebugLogsEnabled(debugLogEnabled);
      await Purchases.setup(playStoreKey);
    } else {
      print("RevenueCat is not supported on this platform.");
      return;
    }

    if (loadDataAfterLaunch) {
      loadCustomerInfo();
      loadOfferings();
    } else {
      await loadCustomerInfo();
      await loadOfferings();
    }

    Purchases.addCustomerInfoUpdateListener((info) {
      customerInfo = info;
    });
  } on Exception catch (e) {
    // This should happen only in the web run mode.
    print("RevenueCat initialization failed: $e");
  }
}

// Purchase a package.
Future<bool> purchasePackage(String package) async {
  try {
    final revenueCatPackage = offerings?.current?.getPackage(package);
    if (revenueCatPackage == null) {
      return false;
    }
    customerInfo = await Purchases.purchasePackage(revenueCatPackage);
    return true;
  } catch (_) {
    return false;
  }
}

List<String> get activeEntitlementIds => _customerInfo != null
    ? _customerInfo!.entitlements.active.values
        .map((e) => e.identifier)
        .toList()
    : [];

Future loadOfferings() async {
  try {
    _offerings = await Purchases.getOfferings();
  } on PlatformException catch (e) {
    print("Error loading offerings info: $e");
  }
}

Future loadCustomerInfo() async {
  try {
    _customerInfo = await Purchases.getCustomerInfo();
  } on PlatformException catch (e) {
    print("Error loading purchaser info: $e");
  }
}

// Return if the user has the entitlement.
// Return null on errors.
Future<bool?> isEntitled(String entitlementId) async {
  try {
    customerInfo = await Purchases.getCustomerInfo();
    return customerInfo!.entitlements.all[entitlementId]?.isActive ?? false;
  } on Exception catch (e) {
    print("Unable to check RevenueCat entitlements: $e");
    return null;
  }
}

// https://docs.revenuecat.com/docs/user-ids
Future login(String? uid) async {
  if (kIsWeb || uid == _loggedInUid) {
    return;
  }
  try {
    if (uid != null) {
      customerInfo = (await Purchases.logIn(uid)).customerInfo;
    } else {
      customerInfo = await Purchases.logOut();
    }
    _loggedInUid = uid;
  } on Exception catch (e) {
    print("Unable to logIn or logOut user in RevenueCat: $e");
  }
}

// https://docs.revenuecat.com/docs/restoring-purchases
Future restorePurchases() async {
  try {
    customerInfo = await Purchases.restorePurchases();
  } on PlatformException catch (e) {
    print("Unable to restore purchases in RevenueCat: $e");
  }
}
