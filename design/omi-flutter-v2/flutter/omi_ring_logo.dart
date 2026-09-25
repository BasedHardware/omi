// The Omi mark as the app ships it (assets/images/herologo.png, app_launcher_icon.png):
// eight dots on a ring. Drawn in code so it is sharp at any size and can animate.
// Geometry measured from the shipped assets: ring radius = 0.344 × size, dot radius = 0.066 × size.
//
// Modes:
//   OmiRingMode.still    — static (lists, headers)
//   OmiRingMode.breathe  — slow scale/opacity pulse (Ask button at rest)
//   OmiRingMode.chase    — dots light in sequence (listening / "thinking")
//   OmiRingMode.orbit    — slow rotation + alternating glow (Welcome, Plans header)
// Respects "Reduce motion" / Android "Remove animations": falls back to still.
//
// Suggested home: app/lib/ui/components/omi_ring_logo.dart (export it from ui.dart).

import 'dart:math' as math;

import 'package:flutter/material.dart';

enum OmiRingMode { still, breathe, chase, orbit }

class OmiRingLogo extends StatefulWidget {
  const OmiRingLogo({super.key, this.size = 24, this.color, this.mode = OmiRingMode.still, this.semanticLabel});

  final double size;
  final Color? color;
  final OmiRingMode mode;
  final String? semanticLabel;

  @override
  State<OmiRingLogo> createState() => _OmiRingLogoState();
}

class _OmiRingLogoState extends State<OmiRingLogo> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: _durationFor(widget.mode));

  static Duration _durationFor(OmiRingMode m) => switch (m) {
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
  void didUpdateWidget(covariant OmiRingLogo old) {
    super.didUpdateWidget(old);
    if (old.mode != widget.mode) {
      _c.duration = _durationFor(widget.mode);
      _sync();
    }
  }

  void _sync() {
    final reduce = MediaQuery.maybeDisableAnimationsOf(context) ?? false;
    if (widget.mode == OmiRingMode.still || reduce) {
      _c.stop();
      _c.value = 0;
    } else if (!_c.isAnimating) {
      _c.repeat();
    }
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final color = widget.color ?? DefaultTextStyle.of(context).style.color ?? Colors.white;
    final ring = RepaintBoundary(
      child: AnimatedBuilder(
        animation: _c,
        builder: (_, __) => CustomPaint(
          size: Size.square(widget.size),
          painter: _RingPainter(color: color, t: _c.value, mode: widget.mode, animating: _c.isAnimating),
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
  final double t; // 0..1
  final OmiRingMode mode;
  final bool animating;

  @override
  void paint(Canvas canvas, Size size) {
    final s = size.shortestSide;
    final c = Offset(size.width / 2, size.height / 2);
    final r = s * 0.344;
    // Small marks get slightly larger dots so they stay legible (matches the design).
    final dr = s * (s >= 40 ? 0.066 : 0.079);

    double scale = 1, rotation = 0;
    if (animating && mode == OmiRingMode.breathe) {
      final k = (1 - math.cos(t * 2 * math.pi)) / 2; // 0..1..0
      scale = 0.92 + 0.08 * k;
    }
    if (animating && mode == OmiRingMode.orbit) rotation = t * 2 * math.pi;

    canvas.save();
    canvas.translate(c.dx, c.dy);
    canvas.rotate(rotation);
    canvas.scale(scale);
    for (var i = 0; i < 8; i++) {
      final a = -math.pi / 2 + i * math.pi / 4;
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
      canvas.drawCircle(Offset(r * math.cos(a), r * math.sin(a)), dr, Paint()..color = color.withValues(alpha: opacity));
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(_RingPainter old) => old.t != t || old.color != color || old.mode != mode || old.animating != animating;
}
