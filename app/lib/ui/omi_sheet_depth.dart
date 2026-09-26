import 'package:flutter/material.dart';

import 'package:omi/ui/omi_tokens.dart';

/// How far a bottom sheet has risen over the page: 0 with no sheet, 1 with one fully open (the
/// highest when sheets stack). [OmiSheetObserver] feeds it; [OmiSheetRecede] follows it.
abstract final class OmiSheetDepth {
  static final ValueNotifier<double> value = ValueNotifier<double>(0);

  static final Map<Route<dynamic>, Animation<double>> _sheets = {};
  static final Map<Route<dynamic>, AnimationStatusListener> _statusListeners = {};

  static void _update() {
    var depth = 0.0;
    for (final animation in _sheets.values) {
      if (animation.value > depth) depth = animation.value;
    }
    value.value = depth;
  }

  /// Follows [route]'s [animation] until the sheet has closed.
  static void track(Route<dynamic> route, Animation<double> animation) {
    if (_sheets.containsKey(route)) return;
    void onStatus(AnimationStatus status) {
      if (status == AnimationStatus.dismissed) untrack(route);
    }

    _sheets[route] = animation;
    _statusListeners[route] = onStatus;
    animation
      ..addListener(_update)
      ..addStatusListener(onStatus);
    _update();
  }

  static void untrack(Route<dynamic> route) {
    final animation = _sheets.remove(route);
    final onStatus = _statusListeners.remove(route);
    if (animation != null) {
      animation.removeListener(_update);
      if (onStatus != null) animation.removeStatusListener(onStatus);
    }
    _update();
  }
}

/// Tells [OmiSheetDepth] about every bottom sheet on the navigator it observes.
class OmiSheetObserver extends NavigatorObserver {
  static bool _isSheet(Route<dynamic>? route) => route is ModalBottomSheetRoute;

  @override
  void didPush(Route<dynamic> route, Route<dynamic>? previousRoute) {
    if (_isSheet(route) && route is ModalRoute && route.animation != null) {
      OmiSheetDepth.track(route, route.animation!);
    }
  }

  @override
  void didRemove(Route<dynamic> route, Route<dynamic>? previousRoute) {
    if (_isSheet(route)) OmiSheetDepth.untrack(route);
  }

  @override
  void didReplace({Route<dynamic>? newRoute, Route<dynamic>? oldRoute}) {
    if (oldRoute != null && _isSheet(oldRoute)) OmiSheetDepth.untrack(oldRoute);
  }
}

/// The page behind an open bottom sheet (Motion N2): as the sheet rises the page shrinks to 92%
/// and rounds its corners, so it reads as still there, one step back. Under Reduce Motion it stays
/// put (the sheet's scrim still dims it).
///
/// The tree is the same at rest and while receded, so the page never loses its state.
class OmiSheetRecede extends StatelessWidget {
  const OmiSheetRecede({super.key, required this.child});

  final Widget child;

  static const double _scale = 0.92;

  @override
  Widget build(BuildContext context) {
    final still = MediaQuery.maybeDisableAnimationsOf(context) ?? false;
    return ValueListenableBuilder<double>(
      valueListenable: OmiSheetDepth.value,
      child: child,
      builder: (context, depth, child) {
        final t = still ? 0.0 : Curves.easeOut.transform(depth.clamp(0.0, 1.0));
        return Transform.scale(
          scale: 1 - (1 - _scale) * t,
          child: ClipRRect(
            borderRadius: BorderRadius.circular(OmiRadius.sheet * t),
            clipBehavior: t > 0 ? Clip.antiAlias : Clip.none,
            child: child,
          ),
        );
      },
    );
  }
}
