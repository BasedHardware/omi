import 'package:flutter/material.dart';

import 'package:omi/pages/apps/widgets/omi_web_page.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// The Omi store, tagged with where the reader came from so orders can be attributed.
Uri omiShopUrl(String source) => Uri.https('www.omi.me', '/', {'_ref': source});

/// Opens the Omi store inside the app (a clean in-app web page, not the browser), so buying the
/// device does not take the reader out of Omi. [source] names the entry point, e.g.
/// `onboarding_not_ordered`, and is sent as `_ref` and on the `Omi Shop Opened` event. Completes
/// when the reader closes the store.
Future<void> openOmiShop(BuildContext context, {required String source}) async {
  PlatformManager.instance.analytics.getOmiDeviceClicked();
  PlatformManager.instance.analytics.track('Omi Shop Opened', properties: {'source': source});
  await routeToPage(context, OmiWebPage(title: context.l10n.getOmiDevice, url: omiShopUrl(source)));
}
