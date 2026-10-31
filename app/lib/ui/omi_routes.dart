import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

/// A page route that keeps the platform's own transition and back gesture: a
/// [CupertinoPageRoute] on iOS (edge-swipe back works) and a [MaterialPageRoute] elsewhere.
///
/// Pushing a page: call `routeToPage(context, page)` (utils/other/temp.dart), which picks the same
/// routes. Use [omiPageRoute] only where code needs a [Route] object — `pushReplacement`,
/// `pushAndRemoveUntil`, a route returned from a navigator callback.
///
/// Never build a `PageRouteBuilder` for a push: it has no iOS back-swipe. Custom transitions are
/// only for modals that carry an explicit `OmiCloseButton`. Set [fullscreenDialog] for a
/// full-screen modal (slides up, has no back swipe, and its header uses a close X, not a back
/// chevron).
Route<T> omiPageRoute<T>({
  required WidgetBuilder builder,
  RouteSettings? settings,
  bool fullscreenDialog = false,
  bool maintainState = true,
}) {
  switch (defaultTargetPlatform) {
    case TargetPlatform.iOS:
    case TargetPlatform.macOS:
      return CupertinoPageRoute<T>(
        builder: builder,
        settings: settings,
        fullscreenDialog: fullscreenDialog,
        maintainState: maintainState,
      );
    case TargetPlatform.android:
    case TargetPlatform.fuchsia:
    case TargetPlatform.linux:
    case TargetPlatform.windows:
      return MaterialPageRoute<T>(
        builder: builder,
        settings: settings,
        fullscreenDialog: fullscreenDialog,
        maintainState: maintainState,
      );
  }
}

/// Replaces the whole navigator stack with [builder]'s page by fading it in: for hand-offs that
/// leave nothing to go back to (onboarding done → Home). A slide there shows the incoming page
/// moving over whatever the old root is redrawing underneath (often the same page), which reads
/// as a double. Use with `pushAndRemoveUntil(..., (_) => false)`; never for an ordinary push.
Route<T> omiRootRoute<T>({required WidgetBuilder builder, RouteSettings? settings}) {
  return PageRouteBuilder<T>(
    settings: settings,
    transitionDuration: const Duration(milliseconds: 260),
    reverseTransitionDuration: const Duration(milliseconds: 200),
    pageBuilder: (context, animation, secondaryAnimation) => builder(context),
    transitionsBuilder: (context, animation, secondaryAnimation, child) =>
        FadeTransition(opacity: CurvedAnimation(parent: animation, curve: Curves.easeOut), child: child),
  );
}
