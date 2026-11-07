import 'dart:async';

import 'package:flutter/widgets.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/ui/omi_routes.dart';
import 'package:omi/utils/logger.dart';

/// Opens a deep-link route (`/conversation/abc`, `/apps/xyz`, `/settings/data-privacy`) inside the
/// Home that is already on screen.
typedef HomeRouteOpener = Future<bool> Function(String route, {bool Function()? canOpen});

/// Navigation that must land in the one Home shell instead of stacking a second one
/// (docs/ux-contract.md §1, nav #3).
///
/// The Home page registers itself while mounted. Notification taps and "done" buttons at the end of
/// a flow (firmware updated, device connected) come through here: they pop back to Home and, for a
/// deep link, let Home push the destination on top of itself — parent before child.
abstract final class HomeNavigation {
  // Every mounted Home, newest last. Two can be mounted for a moment: finishing onboarding pushes a new Home while
  // the old root route, still on screen during the transition, can build one too. The newest opens links, and the
  // one that goes away never takes the other's registration with it.
  static final List<HomeRouteOpener> _openers = [];
  static HomeRouteOpener? get _opener => _openers.isEmpty ? null : _openers.last;
  static void Function()? onHomeMounted;

  /// Whether a Home shell is mounted (it is the first route of the root navigator).
  static bool get isHomeMounted => _openers.isNotEmpty;

  /// Called by the Home page in `initState` / `dispose`.
  static void register(HomeRouteOpener opener) {
    _openers
      ..remove(opener)
      ..add(opener);
    final callback = onHomeMounted;
    if (callback != null) scheduleMicrotask(callback);
  }

  static void unregister(HomeRouteOpener opener) {
    // `==`, not identical: two tear-offs of the same method are equal but not identical.
    _openers.remove(opener);
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
    bool Function()? canOpen,
    Duration timeout = const Duration(seconds: 15),
    Duration pollInterval = const Duration(milliseconds: 50),
  }) async {
    final deadline = DateTime.now().add(timeout);
    while ((_opener == null || (canOpen != null && !canOpen())) && DateTime.now().isBefore(deadline)) {
      await Future<void>.delayed(pollInterval);
    }
    final opener = _opener;
    if (opener == null || (canOpen != null && !canOpen())) {
      Logger.debug('HomeNavigation: no Home mounted; dropping $route');
      return false;
    }
    (navigator ?? globalNavigatorKey.currentState)?.popUntil((r) => r.isFirst);
    final opened = await opener(route, canOpen: canOpen);
    return opened && (canOpen == null || canOpen());
  }
}
