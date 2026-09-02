import 'dart:math' as math;

import 'package:flutter/material.dart';

/// A continuously spinning ring of 8 white dots, echoing the Omi device's
/// center LED — used as a persistent decorative backdrop behind onboarding
/// steps that don't have their own artwork. Pass a new [burstTrigger] value
/// (e.g. the current page index) to make the ring briefly speed up, as a
/// little acknowledgement when the person answers a question or hits
/// Continue. [visible] drives an entrance where the dots start collapsed at
/// the center and expand outward into the ring while still spinning.
class OmiLogoSpinner extends StatefulWidget {
  const OmiLogoSpinner({super.key, this.burstTrigger, this.visible = true});

  final Object? burstTrigger;
  final bool visible;

  @override
  State<OmiLogoSpinner> createState() => _OmiLogoSpinnerState();
}

class _OmiLogoSpinnerState extends State<OmiLogoSpinner> with TickerProviderStateMixin {
  late final AnimationController _baseController;
  late final AnimationController _burstController;
  late final Animation<double> _burstCurve;
  late final AnimationController _revealController;
  late final Animation<double> _revealCurve;

  // Extra turns added on top of the steady rotation during a burst. Plain
  // ease-in-out also has zero velocity at both ends of the burst, so it
  // still blends seamlessly into the steady rotation on either side.
  static const double _burstExtraTurns = 0.55;
  double _bankedBurstOffset = 0;

  @override
  void initState() {
    super.initState();
    _baseController = AnimationController(duration: const Duration(milliseconds: 14000), vsync: this)..repeat();
    _burstController = AnimationController(duration: const Duration(milliseconds: 2600), vsync: this);
    _burstCurve = CurvedAnimation(parent: _burstController, curve: Curves.easeInOut);
    _revealController = AnimationController(
      duration: const Duration(milliseconds: 1800),
      reverseDuration: const Duration(milliseconds: 3200),
      vsync: this,
    );
    _revealCurve = CurvedAnimation(
      parent: _revealController,
      curve: Curves.easeOutCubic,
      reverseCurve: Curves.easeInCubic,
    );
    if (widget.visible) {
      _revealController.value = 1;
    }
  }

  @override
  void didUpdateWidget(covariant OmiLogoSpinner oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.visible && widget.burstTrigger != oldWidget.burstTrigger) {
      _startBurst();
    }
    if (widget.visible != oldWidget.visible) {
      if (widget.visible) {
        _revealController.forward(from: 0);
      } else {
        // Animate back down to the center instead of snapping away, so
        // hiding mirrors the reveal.
        _revealController.reverse();
      }
    }
  }

  void _startBurst() {
    // Bank whatever the current burst has already contributed (0 if the
    // previous one finished, partial if retriggered mid-burst) so resetting
    // the controller to 0 never causes a visible snap.
    _bankedBurstOffset += _burstCurve.value * 2 * math.pi * _burstExtraTurns;
    _burstController.value = 0;
    _burstController.forward();
  }

  @override
  void dispose() {
    _baseController.dispose();
    _burstController.dispose();
    _revealController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: Colors.black,
      child: Align(
        alignment: const Alignment(0, -0.32),
        child: AnimatedBuilder(
          animation: Listenable.merge([_baseController, _burstCurve, _revealCurve]),
          builder: (context, child) {
            final angle = _baseController.value * 2 * math.pi +
                _bankedBurstOffset +
                _burstCurve.value * 2 * math.pi * _burstExtraTurns;
            return Transform.scale(
              scale: _revealCurve.value,
              child: Transform.rotate(angle: angle, child: child),
            );
          },
          child: const _DotRing(),
        ),
      ),
    );
  }
}

class _DotRing extends StatelessWidget {
  const _DotRing();

  static const int dotCount = 8;
  static const double radius = 88;
  static const double dotSize = 26;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: radius * 2 + dotSize,
      height: radius * 2 + dotSize,
      child: Stack(
        alignment: Alignment.center,
        children: List.generate(dotCount, (i) {
          final angle = i * 2 * math.pi / dotCount;
          final offset = Offset(math.cos(angle), math.sin(angle)) * radius;
          return Transform.translate(
            offset: offset,
            child: Container(
              width: dotSize,
              height: dotSize,
              decoration: const BoxDecoration(shape: BoxShape.circle, color: Colors.white),
            ),
          );
        }),
      ),
    );
  }
}
