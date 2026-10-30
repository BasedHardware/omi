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
