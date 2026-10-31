import 'dart:ui' show lerpDouble;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';

/// Opens [page] by growing it out of the control that asked for it: the page's shape starts as
/// that control (its rect and pill corners, in [fromColor]) and widens to the full screen while
/// the page fades in over it. A back tap runs it back into the control; the iOS edge swipe still
/// slides it away like any page. Under Reduce Motion it is a plain fade.
///
/// The page is laid out at full size the whole time and only clipped, so nothing inside it
/// reflows while it grows.
Future<T?> pushGrowingFrom<T>(BuildContext context, {required GlobalKey from, required Widget page, Color? fromColor}) {
  final box = from.currentContext?.findRenderObject() as RenderBox?;
  final origin = box != null && box.hasSize ? box.localToGlobal(Offset.zero) & box.size : null;
  return Navigator.of(context).push<T>(
    _GrowRoute<T>(
      page: page,
      origin: origin,
      fromColor: fromColor ?? OmiColors.surface1,
      reduceMotion: OmiMotion.of(context).standard == Duration.zero,
    ),
  );
}

class _GrowRoute<T> extends PageRoute<T> with CupertinoRouteTransitionMixin<T> {
  _GrowRoute({required this.page, required this.origin, required this.fromColor, required this.reduceMotion});

  final Widget page;
  final Rect? origin;
  final Color fromColor;
  final bool reduceMotion;

  /// Set once an edge swipe starts, so the rest of that dismissal stays a slide instead of
  /// switching to the shrink halfway through.
  bool _swiping = false;

  @override
  Widget buildContent(BuildContext context) => page;

  @override
  String? get title => null;

  @override
  bool get maintainState => true;

  @override
  Duration get transitionDuration => reduceMotion ? OmiMotion.quickDuration : const Duration(milliseconds: 460);

  @override
  Duration get reverseTransitionDuration => reduceMotion ? OmiMotion.quickDuration : const Duration(milliseconds: 380);

  @override
  Widget buildTransitions(
    BuildContext context,
    Animation<double> animation,
    Animation<double> secondaryAnimation,
    Widget child,
  ) {
    if (popGestureInProgress) _swiping = true;
    if (animation.status == AnimationStatus.completed) _swiping = false;
    // One widget structure in every mode, so the page keeps its state when a swipe takes over:
    // the Cupertino layer (back swipe, parallax under later pages) holds still until a swipe
    // starts, and the grow layer steps aside while one runs.
    return _Grow(
      animation: animation,
      origin: origin,
      fromColor: fromColor,
      mode: _swiping
          ? _GrowMode.off
          : reduceMotion || origin == null
              ? _GrowMode.fade
              : _GrowMode.grow,
      child: super.buildTransitions(
        context,
        _swiping ? animation : kAlwaysCompleteAnimation,
        secondaryAnimation,
        child,
      ),
    );
  }
}

enum _GrowMode { grow, fade, off }

class _Grow extends StatelessWidget {
  const _Grow({
    required this.animation,
    required this.origin,
    required this.fromColor,
    required this.mode,
    required this.child,
  });

  final Animation<double> animation;
  final Rect? origin;
  final Color fromColor;
  final _GrowMode mode;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final screen = Offset.zero & MediaQuery.sizeOf(context);
    // The shape moves on an emphasized curve that leaves and lands softly (mirrored on the way
    // back); the page fades in only once there is room to read it.
    final shape = CurvedAnimation(
      parent: animation,
      curve: Curves.easeInOutCubicEmphasized,
      reverseCurve: Curves.easeInOutCubicEmphasized.flipped,
    );
    final content = mode == _GrowMode.grow
        ? CurvedAnimation(parent: animation, curve: const Interval(0.3, 0.85, curve: Curves.easeOut))
        : mode == _GrowMode.fade
            ? animation
            : kAlwaysCompleteAnimation;
    final pageColor = Theme.of(context).scaffoldBackgroundColor;
    final faded = FadeTransition(opacity: content, child: child);
    // The shape itself fades in over the first stretch (out over the last, on close), so the real
    // pill underneath shows through where the two overlap instead of a blank copy of it.
    final handoff = mode == _GrowMode.grow
        ? CurvedAnimation(parent: animation, curve: const Interval(0, 0.18, curve: Curves.easeOut))
        : kAlwaysCompleteAnimation;
    final shaped = AnimatedBuilder(
      animation: animation,
      child: faded,
      builder: (context, faded) {
        final growing = mode == _GrowMode.grow;
        final t = growing ? shape.value : 1.0;
        final from = origin ?? screen;
        final rect = Rect.lerp(from, screen, t)!;
        final radius = lerpDouble(from.shortestSide / 2, 0, t)!;
        return ClipRRect(
          clipper: _RectClipper(RRect.fromRectAndRadius(rect, Radius.circular(radius))),
          child: ColoredBox(
            color: growing ? Color.lerp(fromColor, pageColor, content.value)! : Colors.transparent,
            child: faded,
          ),
        );
      },
    );
    return FadeTransition(opacity: handoff, child: shaped);
  }
}

class _RectClipper extends CustomClipper<RRect> {
  const _RectClipper(this.rrect);

  final RRect rrect;

  @override
  RRect getClip(Size size) => rrect;

  @override
  bool shouldReclip(_RectClipper oldClipper) => oldClipper.rrect != rrect;
}
