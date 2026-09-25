import 'dart:async';

import 'package:flutter/widgets.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/ui/omi_routes.dart';
import 'package:omi/utils/logger.dart';

/// Opens a deep-link route (`/conversation/abc`, `/apps/xyz`, `/settings/data-privacy`) inside the
/// Home that is already on screen.
typedef HomeRouteOpener = Future<void> Function(String route);

/// Navigation that must land in the one Home shell instead of stacking a second one
/// (docs/ux-contract.md §1, nav #3).
///
/// The Home page registers itself while mounted. Notification taps and "done" buttons at the end of
/// a flow (firmware updated, device connected) come through here: they pop back to Home and, for a
/// deep link, let Home push the destination on top of itself — parent before child.
abstract final class HomeNavigation {
  static HomeRouteOpener? _opener;

  /// Whether a Home shell is mounted (it is the first route of the root navigator).
  static bool get isHomeMounted => _opener != null;

  /// Called by the Home page in `initState` / `dispose`.
  static void register(HomeRouteOpener opener) => _opener = opener;

  static void unregister(HomeRouteOpener opener) {
    // `==`, not identical: two tear-offs of the same method are equal but not identical.
    if (_opener == opener) _opener = null;
  }

  /// Leaves the current flow and shows Home: pops to the existing Home when there is one, otherwise
  /// replaces the whole stack with a fresh Home (a flow that started outside Home, e.g. onboarding).
  static void returnHome(BuildContext context) {
    final navigator = Navigator.of(context, rootNavigator: true);
    if (isHomeMounted) {
      navigator.popUntil((route) => route.isFirst);
      return;
    }
    navigator.pushAndRemoveUntil(omiPageRoute(builder: (_) => const HomePageWrapper()), (_) => false);
  }

  /// Opens [route] inside the existing Home: everything above Home is popped, then Home pushes the
  /// destination. Waits (up to [timeout]) for Home to mount on a cold start. Returns false when no
  /// Home appears — the reader is signed out or still onboarding — and the link is dropped rather
  /// than skipping those screens.
  static Future<bool> openRoute(
    String route, {
    NavigatorState? navigator,
    Duration timeout = const Duration(seconds: 15),
    Duration pollInterval = const Duration(milliseconds: 50),
  }) async {
    final deadline = DateTime.now().add(timeout);
    while (_opener == null && DateTime.now().isBefore(deadline)) {
      await Future<void>.delayed(pollInterval);
    }
    final opener = _opener;
    if (opener == null) {
      Logger.debug('HomeNavigation: no Home mounted; dropping $route');
      return false;
    }
    (navigator ?? globalNavigatorKey.currentState)?.popUntil((r) => r.isFirst);
    await opener(route);
    return true;
  }
}
