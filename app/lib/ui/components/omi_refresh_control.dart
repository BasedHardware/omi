import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/cupertino.dart';

import 'package:omi/ui/components/omi_spinner.dart';
import 'package:omi/ui/omi_tokens.dart';

/// Pull-to-refresh for a [CustomScrollView] on iOS: a thin ring draws itself as the list is pulled,
/// ticks once when letting go would refresh, then becomes the [OmiSpinner] while it loads.
///
/// Put it first in the slivers and keep the stock `RefreshIndicator` for Android with
/// [OmiRefreshControl.materialPredicate], which turns the Material one off where this one shows:
///
/// ```dart
/// RefreshIndicator(
///   notificationPredicate: OmiRefreshControl.materialPredicate,
///   onRefresh: refresh,
///   child: CustomScrollView(slivers: [if (OmiRefreshControl.supported) OmiRefreshControl(onRefresh: refresh), ...]),
/// )
/// ```
class OmiRefreshControl extends StatelessWidget {
  const OmiRefreshControl({super.key, required this.onRefresh});

  final Future<void> Function() onRefresh;

  /// iOS only: the control needs the bouncing overscroll iOS lists have.
  static bool get supported => !_forceMaterial && Platform.isIOS;

  /// Tests pin the Material path.
  static bool _forceMaterial = false;
  @visibleForTesting
  static set debugForceMaterial(bool value) => _forceMaterial = value;

  /// For the Material `RefreshIndicator` that wraps the same list: off wherever this control shows.
  static bool materialPredicate(ScrollNotification notification) => !supported && notification.depth == 0;

  static const double _trigger = 88;
  static const double _extent = 56;

  @override
  Widget build(BuildContext context) {
    return CupertinoSliverRefreshControl(
      refreshTriggerPullDistance: _trigger,
      refreshIndicatorExtent: _extent,
      onRefresh: onRefresh,
      builder: (context, mode, pulled, trigger, extent) =>
          _PullIndicator(mode: mode, progress: (pulled / trigger).clamp(0.0, 1.0)),
    );
  }
}

class _PullIndicator extends StatefulWidget {
  const _PullIndicator({required this.mode, required this.progress});

  final RefreshIndicatorMode mode;
  final double progress;

  @override
  State<_PullIndicator> createState() => _PullIndicatorState();
}

class _PullIndicatorState extends State<_PullIndicator> {
  @override
  void didUpdateWidget(covariant _PullIndicator old) {
    super.didUpdateWidget(old);
    // One tick at the moment letting go would refresh.
    if (widget.mode == RefreshIndicatorMode.armed && old.mode == RefreshIndicatorMode.drag) OmiHaptics.selection();
  }

  @override
  Widget build(BuildContext context) {
    final loading = widget.mode == RefreshIndicatorMode.armed || widget.mode == RefreshIndicatorMode.refresh;
    final done = widget.mode == RefreshIndicatorMode.done || widget.mode == RefreshIndicatorMode.inactive;
    final p = widget.progress;
    return Center(
      child: AnimatedOpacity(
        opacity: done ? 0 : (p * 1.8).clamp(0.0, 1.0),
        duration: const Duration(milliseconds: 160),
        child: AnimatedSwitcher(
          duration: const Duration(milliseconds: 180),
          child: loading
              ? const OmiSpinner(key: ValueKey('spin'), size: OmiSpinnerSize.small)
              : SizedBox(
                  key: const ValueKey('ring'),
                  width: 22,
                  height: 22,
                  child: CustomPaint(painter: _PullRing(progress: p, color: OmiColors.textPrimary)),
                ),
        ),
      ),
    );
  }
}

/// A ring that draws clockwise from the top as the list is pulled, and a dot that grows at its
/// centre: full ring + dot = let go to refresh.
class _PullRing extends CustomPainter {
  _PullRing({required this.progress, required this.color});

  final double progress;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final c = size.center(Offset.zero);
    final r = size.shortestSide / 2 - 1;
    final track = Paint()
      ..color = color.withValues(alpha: 0.12)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2;
    canvas.drawCircle(c, r, track);
    final arc = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeWidth = 2;
    canvas.drawArc(Rect.fromCircle(center: c, radius: r), -math.pi / 2, 2 * math.pi * progress, false, arc);
    canvas.drawCircle(c, 3.5 * Curves.easeOutBack.transform(progress), Paint()..color = color);
  }

  @override
  bool shouldRepaint(covariant _PullRing old) => old.progress != progress || old.color != color;
}
