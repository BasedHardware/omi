import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/apps/widgets/omi_web_page.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// The Omi store, tagged with where the reader came from so orders can be attributed.
Uri omiShopUrl(String source) => Uri.https('www.omi.me', '/', {'_ref': source});

/// The store template that shows the device without Omi Pro prices, the plan table or the Pro FAQ.
const omiHardwareView = 'app-hardware';

/// The marker element only that template renders. If the theme ever drops the template, Shopify
/// silently serves the normal product page, which has no marker: the app then shows nothing.
const omiHardwareMarkerScript = "document.getElementById('omi-app-hardware') !== null";

/// The Omi device product page: the only store page a Google Play-billed Android reader is shown,
/// because the rest of the store also sells Omi Pro and gift cards outside Google Play.
Uri omiHardwareUrl(String source) =>
    Uri.https('www.omi.me', '/products/omi', {'view': omiHardwareView, '_ref': source});

/// The host in lower case without trailing root dots (`app.omi.me.` and `app.omi.me..` are `app.omi.me`).
String _hostOf(Uri uri) => uri.host.toLowerCase().replaceFirst(RegExp(r'\.+$'), '');

bool _isStoreHost(String host) => host == 'www.omi.me' || host == 'omi.me';

/// Any Omi host. Only the store hosts serve pages here; the rest (app.omi.me sells Omi Pro, h.omi.me)
/// are never off-site payment pages and stay blocked from everywhere.
bool _isOmiHost(String host) => host == 'omi.me' || host.endsWith('.omi.me');

bool _isProductPage(Uri uri) {
  final path = uri.path.toLowerCase();
  return _isStoreHost(_hostOf(uri)) && (path == '/products/omi' || path == '/products/omi/');
}

bool _isCheckoutPath(String path) => path.startsWith('/checkouts/') || RegExp(r'^/\d+/checkouts/').hasMatch(path);

/// A post-purchase page on the store's own checkout: on omi.me under a checkout path, or on
/// checkout.shopify.com. The same words anywhere else are not an order.
bool _isPostPurchase(String host, String path) {
  if (!path.contains('post_purchase') && !path.contains('post-purchase')) return false;
  return host == 'checkout.shopify.com' || (_isStoreHost(host) && _isCheckoutPath(path));
}

/// Main-frame navigation in the hardware-only store.
///
/// * omi.me: only the device page (always on the [omiHardwareView] template; any other `view` is
///   replaced), its cart (including `/cart/<variant>:<qty>` permalinks, which the page's own Get Omi
///   button uses), checkout and the store policies. Everything else is blocked with a message.
/// * Off-site https pages are allowed only when the hop starts from a checkout page or from an
///   off-site payment page already reached that way (Shop Pay, PayPal, Klarna, Afterpay, Amazon Pay,
///   bank redirects, top-level 3-D Secure), so a paying buyer is never stranded. From the product,
///   cart and policy pages off-site navigation stays blocked. A return to omi.me is checked again.
///   Every other Omi host (app.omi.me, h.omi.me, any *.omi.me) is blocked from everywhere.
/// * A post-purchase page on the store's checkout means the payment was already taken: the store
///   closes and the reader is told the order was placed (it never shows the upsell sold outside
///   Google Play).
/// Subframes (card fields, in-page 3-D Secure) are not filtered.
WebNavigation omiHardwareNavigation(Uri? current, Uri target) {
  if (target.scheme != 'https') return WebNavigation.block;
  final host = _hostOf(target);
  final path = target.path.toLowerCase();
  if (_isPostPurchase(host, path)) return WebNavigation.finish;
  if (_isOmiHost(host) && !_isStoreHost(host)) return WebNavigation.block;
  if (_isStoreHost(host)) {
    if (_isProductPage(target)) {
      if (target.queryParameters['view'] == omiHardwareView) return WebNavigation.allow;
      return WebNavigation.replace(
          target.replace(queryParameters: {...target.queryParameters, 'view': omiHardwareView}));
    }
    final allowed = path == '/cart' ||
        path.startsWith('/cart/') ||
        path == '/checkout' ||
        _isCheckoutPath(path) ||
        path.startsWith('/policies/');
    return allowed ? WebNavigation.allow : WebNavigation.block;
  }
  if (current == null || current.scheme != 'https') return WebNavigation.block;
  final fromHost = _hostOf(current);
  final fromCheckout = _isCheckoutPath(current.path.toLowerCase());
  final fromPaymentHop = !_isOmiHost(fromHost);
  return fromCheckout || fromPaymentHop ? WebNavigation.allow : WebNavigation.block;
}

/// Whether a finished store page may be shown in the hardware-only store: the device page must
/// carry the template's marker. [markerResult] is what [omiHardwareMarkerScript] returned.
bool omiHardwarePageVerified(Object? markerResult) => markerResult == true || markerResult?.toString() == 'true';

/// The check the hardware-only store runs on every device page before showing it.
const omiHardwarePageCheck = WebPageCheck(
  appliesTo: _isProductPage,
  script: omiHardwareMarkerScript,
  passes: omiHardwarePageVerified,
);

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
  final outcome = await Navigator.of(context).push<WebNavigationKind>(
    MaterialPageRoute<WebNavigationKind>(
      fullscreenDialog: true,
      builder: (_) => OmiWebPage(
        title: title,
        url: hardwareOnly ? omiHardwareUrl(source) : omiShopUrl(source),
        showClose: true,
        navigationPolicy: hardwareOnly ? omiHardwareNavigation : null,
        pageCheck: hardwareOnly ? omiHardwarePageCheck : null,
      ),
    ),
  );
  // The store closed itself on a post-purchase page: the payment went through.
  if (outcome == WebNavigationKind.finish && context.mounted) {
    OmiFeedback.info(context, context.l10n.shopOrderPlacedCheckEmail);
  }
}
