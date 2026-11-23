import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/apps/widgets/omi_web_page.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// The Omi store, tagged with where the reader came from so orders can be attributed.
Uri omiShopUrl(String source) => Uri.https('www.omi.me', '/', {'_ref': source});

/// The Omi device product page: the only store page a Google Play-billed Android reader is shown,
/// because the rest of the store also sells Omi Pro and gift cards outside Google Play.
Uri omiHardwareUrl(String source) => Uri.https('www.omi.me', '/products/omi', {'_ref': source});

/// Hosts that serve checkout for the store's cart, and the wallets checkout hands off to.
const _checkoutHosts = {'checkout.shopify.com', 'shop.app', 'pay.shopify.com'};
const _walletHostSuffixes = {'paypal.com', 'klarna.com', 'affirm.com'};

/// Main-frame pages a Play-billed reader may reach from the device page: that product, its cart and
/// checkout (minus post-purchase upsells), and the store policies checkout links to. Everything else
/// (other products, collections, search, the home page, gift cards) is blocked. Subframes (card fields,
/// 3-D Secure) are not filtered.
bool omiHardwareNavigationAllowed(Uri uri) {
  if (uri.scheme != 'https') return false;
  final host = uri.host.toLowerCase();
  final path = uri.path.toLowerCase();
  if (path.contains('post_purchase') || path.contains('post-purchase')) return false;
  if (host == 'www.omi.me' || host == 'omi.me') {
    return path == '/products/omi' ||
        path == '/products/omi/' ||
        path == '/cart' ||
        path.startsWith('/cart/') ||
        path == '/checkout' ||
        path.startsWith('/checkouts/') ||
        RegExp(r'^/\d+/checkouts/').hasMatch(path) ||
        path.startsWith('/policies/');
  }
  if (_checkoutHosts.contains(host)) return true;
  return _walletHostSuffixes.any((suffix) => host == suffix || host.endsWith('.$suffix'));
}

/// Android readers on a Google Play billing build (or whose billing provider is not known yet).
bool omiShopRestrictedToHardware(BuildContext context) {
  if (kIsWeb || defaultTargetPlatform != TargetPlatform.android) return false;
  try {
    final usage = context.read<UsageProvider>();
    return usage.playBilling != null || usage.billingProviderUnknown;
  } on ProviderNotFoundException {
    return false;
  }
}

/// Opens the Omi store inside the app (a clean in-app web page, not the browser), so buying the
/// device does not take the reader out of Omi. [source] names the entry point, e.g.
/// `onboarding_not_ordered`, and is sent as `_ref` and on the `Omi Shop Opened` event. Completes
/// when the reader closes the store.
Future<void> openOmiShop(BuildContext context, {required String source}) async {
  PlatformManager.instance.analytics.getOmiDeviceClicked();
  PlatformManager.instance.analytics.track('Omi Shop Opened', properties: {'source': source});
  final title = context.l10n.getOmiDevice;
  final hardwareOnly = omiShopRestrictedToHardware(context);
  // Presented as a sheet that slides up, with Close rather than Back: it is a detour, not a step.
  await Navigator.of(context).push(
    MaterialPageRoute<void>(
      fullscreenDialog: true,
      builder: (_) => OmiWebPage(
        title: title,
        url: hardwareOnly ? omiHardwareUrl(source) : omiShopUrl(source),
        showClose: true,
        allowNavigation: hardwareOnly ? omiHardwareNavigationAllowed : null,
      ),
    ),
  );
}
