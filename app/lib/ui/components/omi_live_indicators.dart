import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'package:omi/ui/omi_tokens.dart';

/// A thin arc that circles [child] while background work runs (offline sync, processing). Quiet
/// by design: no text, no colour, just motion around a glyph that already has a label. Under
/// Reduce Motion it is a still, partial ring.
class OmiActivityRing extends StatefulWidget {
  const OmiActivityRing({super.key, required this.active, required this.child, this.diameter = 22, this.color});

  final bool active;
  final Widget child;

  /// Outer size of the ring; the child is centred inside it.
  final double diameter;

  /// Arc colour. Defaults to [OmiColors.textSecondary].
  final Color? color;

  @override
  State<OmiActivityRing> createState() => _OmiActivityRingState();
}

class _OmiActivityRingState extends State<OmiActivityRing> with SingleTickerProviderStateMixin {
  late final AnimationController _spin = AnimationController(vsync: this, duration: const Duration(milliseconds: 1400));

  void _sync(bool reduceMotion) {
    if (widget.active && !reduceMotion) {
      if (!_spin.isAnimating) _spin.repeat();
    } else if (_spin.isAnimating) {
      _spin.stop();
    }
  }

  @override
  void dispose() {
    _spin.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final reduceMotion = OmiMotion.of(context).standard == Duration.zero;
    _sync(reduceMotion);
    return SizedBox.square(
      dimension: widget.diameter,
      child: Stack(
        alignment: Alignment.center,
        children: [
          widget.child,
          if (widget.active)
            Positioned.fill(
              child: ExcludeSemantics(
                child: RotationTransition(
                  turns: _spin,
                  child: CustomPaint(painter: _ArcPainter(widget.color ?? OmiColors.textSecondary)),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _ArcPainter extends CustomPainter {
  _ArcPainter(this.color);

  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5
      ..strokeCap = StrokeCap.round;
    final rect = Offset.zero & size;
    canvas.drawArc(rect.deflate(1), -math.pi / 2, math.pi * 0.6, false, paint);
  }

  @override
  bool shouldRepaint(_ArcPainter oldDelegate) => oldDelegate.color != color;
}

/// The live dot: green, gently pulsing while [live]; grey and still otherwise (paused, waiting).
/// Green is reserved for live and listening. Still under Reduce Motion.
class OmiLiveDot extends StatefulWidget {
  const OmiLiveDot({super.key, this.live = true, this.size = 10});

  final bool live;
  final double size;

  @override
  State<OmiLiveDot> createState() => _OmiLiveDotState();
}

class _OmiLiveDotState extends State<OmiLiveDot> with SingleTickerProviderStateMixin {
  late final AnimationController _pulse =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 1600));

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final reduceMotion = OmiMotion.of(context).standard == Duration.zero;
    if (widget.live && !reduceMotion) {
      if (!_pulse.isAnimating) _pulse.repeat(reverse: true);
    } else if (_pulse.isAnimating) {
      _pulse.stop();
    }
    final dot = Container(
      width: widget.size,
      height: widget.size,
      decoration:
          BoxDecoration(color: widget.live ? OmiColors.success : OmiColors.textTertiary, shape: BoxShape.circle),
    );
    if (!widget.live || reduceMotion) return dot;
    return FadeTransition(opacity: Tween<double>(begin: 1, end: 0.35).animate(_pulse), child: dot);
  }
}
