import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'package:omi/ui/omi_tokens.dart';

/// How an [OmiRingLogo] moves.
enum OmiRingMode {
  /// Static: lists, headers, anywhere the mark is a label.
  still,

  /// A slow scale and opacity pulse: the Ask Omi button at rest.
  breathe,

  /// The dots light in sequence: listening, or Omi thinking.
  chase,

  /// A slow turn with alternating glow: Welcome, the plans header.
  orbit,
}

/// The Omi mark as the app ships it (`assets/images/herologo.png`): eight dots on a ring, drawn in
/// code so it is sharp at any size and can animate.
///
/// Geometry is measured from the shipped asset: ring radius 0.344 × [size], dot radius 0.066 ×
/// [size] (0.079 below 40 pt, so small marks stay legible). Under Reduce Motion (iOS) or Remove
/// animations (Android) every mode draws as [OmiRingMode.still].
///
/// Decorative by default; pass [semanticLabel] where the mark is the only thing naming Omi.
class OmiRingLogo extends StatefulWidget {
  const OmiRingLogo({
    super.key,
    this.size = 24,
    this.color,
    this.mode = OmiRingMode.still,
    this.semanticLabel,
    this.loops,
  });

  /// Width and height, in logical pixels.
  final double size;

  /// Dot colour. Defaults to the ambient text colour, else [OmiColors.textPrimary].
  final Color? color;

  final OmiRingMode mode;

  /// The screen-reader name. Null keeps the mark out of the semantics tree.
  final String? semanticLabel;

  /// How many times an animated [mode] plays before the mark comes to rest. Null loops while the
  /// mark is shown: right for a state that ends on its own (Omi thinking), wrong for an idle
  /// control, which would animate (and draw power) for as long as the screen is open.
  final int? loops;

  @override
  State<OmiRingLogo> createState() => _OmiRingLogoState();
}

class _OmiRingLogoState extends State<OmiRingLogo> with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(vsync: this, duration: _periodFor(widget.mode));

  static Duration _periodFor(OmiRingMode mode) => switch (mode) {
        OmiRingMode.chase => const Duration(milliseconds: 1600),
        OmiRingMode.breathe => const Duration(milliseconds: 3000),
        OmiRingMode.orbit => const Duration(seconds: 14),
        OmiRingMode.still => const Duration(seconds: 1),
      };

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _sync();
  }

  @override
  void didUpdateWidget(covariant OmiRingLogo oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.mode != widget.mode) {
      _controller.duration = _periodFor(widget.mode);
      _sync();
    }
  }

  void _sync() {
    final reduceMotion = MediaQuery.maybeDisableAnimationsOf(context) ?? false;
    if (widget.mode == OmiRingMode.still || reduceMotion) {
      _controller.stop();
      _controller.value = 0;
    } else if (!_controller.isAnimating) {
      _controller.repeat(count: widget.loops);
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final color = widget.color ?? DefaultTextStyle.of(context).style.color ?? OmiColors.textPrimary;
    final ring = RepaintBoundary(
      child: AnimatedBuilder(
        animation: _controller,
        builder: (_, __) => CustomPaint(
          size: Size.square(widget.size),
          painter: _RingPainter(
            color: color,
            t: _controller.value,
            mode: widget.mode,
            animating: _controller.isAnimating,
          ),
        ),
      ),
    );
    return widget.semanticLabel == null
        ? ExcludeSemantics(child: ring)
        : Semantics(label: widget.semanticLabel, image: true, child: ring);
  }
}

class _RingPainter extends CustomPainter {
  _RingPainter({required this.color, required this.t, required this.mode, required this.animating});

  final Color color;

  /// Position in the current loop, 0..1.
  final double t;
  final OmiRingMode mode;
  final bool animating;

  @override
  void paint(Canvas canvas, Size size) {
    final side = size.shortestSide;
    final center = Offset(size.width / 2, size.height / 2);
    final ringRadius = side * 0.344;
    final dotRadius = side * (side >= 40 ? 0.066 : 0.079);

    var scale = 1.0;
    var rotation = 0.0;
    if (animating && mode == OmiRingMode.breathe) {
      final k = (1 - math.cos(t * 2 * math.pi)) / 2; // 0..1..0
      scale = 0.92 + 0.08 * k;
    }
    if (animating && mode == OmiRingMode.orbit) rotation = t * 2 * math.pi;

    final paint = Paint();
    canvas.save();
    canvas.translate(center.dx, center.dy);
    canvas.rotate(rotation);
    canvas.scale(scale);
    for (var i = 0; i < 8; i++) {
      final angle = -math.pi / 2 + i * math.pi / 4;
      var opacity = 1.0;
      if (animating) {
        switch (mode) {
          case OmiRingMode.chase:
            // Each dot peaks 0.2 s after the previous one (1.6 s loop).
            final phase = (t - i / 8) % 1.0;
            opacity = 0.28 + 0.72 * math.max(0, 1 - (phase - 0.35).abs() / 0.35);
          case OmiRingMode.breathe:
            opacity = 0.8 + 0.2 * scale;
          case OmiRingMode.orbit:
            final phase = (t * 14 / 2.4 + (i.isEven ? 0 : 0.5)) % 1.0;
            opacity = 0.28 + 0.72 * (1 - (phase - 0.35).abs() / 0.65).clamp(0.0, 1.0);
          case OmiRingMode.still:
            break;
        }
      }
      paint.color = color.withValues(alpha: color.a * opacity);
      canvas.drawCircle(Offset(ringRadius * math.cos(angle), ringRadius * math.sin(angle)), dotRadius, paint);
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(_RingPainter old) =>
      old.t != t || old.color != color || old.mode != mode || old.animating != animating;
}
