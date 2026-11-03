import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'theme.dart';

/// The Omi pendant, drawn in code so the prototype ships no image assets.
///
/// A stand-in until real product photography exists. With [glow] on Aurora it
/// gets the "listening" ring.
class DfPendant extends StatelessWidget {
  const DfPendant({super.key, this.size = 120, this.showCord = true, this.glow = false});

  /// Width of the drawing. With a cord the drawing is 1.5x as tall.
  final double size;
  final bool showCord;
  final bool glow;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return SizedBox(
      width: size,
      height: showCord ? size * 1.5 : size,
      child: CustomPaint(
        painter: _PendantPainter(showCord: showCord, glow: glow && t.hasGlow ? t.glow : null),
      ),
    );
  }
}

class _PendantPainter extends CustomPainter {
  _PendantPainter({required this.showCord, required this.glow});

  final bool showCord;
  final List<Color>? glow;

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final r = w / 2 * 0.62;
    final center = Offset(w / 2, size.height - w / 2);

    if (showCord) {
      final bail = Offset(center.dx, center.dy - r - w * 0.05);
      final cord = Paint()
        ..color = const Color(0xFF3A3A3C)
        ..strokeWidth = math.max(1.2, w / 90)
        ..style = PaintingStyle.stroke;
      canvas.drawLine(Offset(w * 0.18, 0), bail, cord);
      canvas.drawLine(Offset(w * 0.82, 0), bail, cord);
      canvas.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromCenter(center: bail.translate(0, w * 0.025), width: r * 0.28, height: w * 0.07),
          Radius.circular(w * 0.02),
        ),
        Paint()..color = const Color(0xFF2C2C2E),
      );
    }

    final colors = glow;
    if (colors != null) {
      final ringRect = Rect.fromCircle(center: center, radius: r * 1.15);
      final sweep = SweepGradient(colors: <Color>[...colors, colors.first]).createShader(ringRect);
      canvas.drawCircle(
        center,
        r * 1.08,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = r * 0.16
          ..shader = sweep
          ..maskFilter = MaskFilter.blur(BlurStyle.normal, r * 0.12),
      );
      canvas.drawCircle(
        center,
        r * 1.05,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = math.max(1.5, r * 0.05)
          ..shader = sweep,
      );
    }

    final disc = Rect.fromCircle(center: center, radius: r);
    canvas.drawCircle(
      center,
      r,
      Paint()
        ..shader = const RadialGradient(
          center: Alignment(-0.35, -0.45),
          radius: 1.1,
          colors: <Color>[Color(0xFF5A5A60), Color(0xFF1C1C1F), Color(0xFF0B0B0C)],
          stops: <double>[0, 0.55, 1],
        ).createShader(disc),
    );
    canvas.drawCircle(
      center,
      r,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1
        ..color = const Color(0x33FFFFFF),
    );
    // Status light: on while Omi is capturing.
    canvas.drawCircle(center.translate(0, r * 0.45), math.max(1.5, r * 0.035), Paint()..color = Colors.white);
  }

  @override
  bool shouldRepaint(_PendantPainter oldDelegate) => oldDelegate.showCord != showCord || oldDelegate.glow != glow;
}

/// Aurora's hero: an iridescent orb of light.
class DfOrb extends StatelessWidget {
  const DfOrb({super.key, this.size = 220});

  final double size;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return CustomPaint(size: Size.square(size), painter: _OrbPainter(t.glow ?? <Color>[t.accent, t.accent, t.accent]));
  }
}

class _OrbPainter extends CustomPainter {
  _OrbPainter(this.colors);

  final List<Color> colors;

  @override
  void paint(Canvas canvas, Size size) {
    final c = size.center(Offset.zero);
    final r = size.shortestSide / 2 * 0.78;
    final rect = Rect.fromCircle(center: c, radius: r);
    canvas.drawCircle(
      c,
      r * 1.18,
      Paint()
        ..shader = RadialGradient(
          colors: <Color>[colors.first.withValues(alpha: 0.45), colors.first.withValues(alpha: 0)],
        ).createShader(Rect.fromCircle(center: c, radius: r * 1.3))
        ..maskFilter = MaskFilter.blur(BlurStyle.normal, r * 0.15),
    );
    canvas.drawCircle(
      c,
      r,
      Paint()
        ..shader = SweepGradient(
          colors: <Color>[...colors, colors.first],
          transform: const GradientRotation(0.6),
        ).createShader(rect),
    );
    canvas.drawCircle(
      c,
      r,
      Paint()
        ..shader = RadialGradient(
          center: const Alignment(-0.3, -0.35),
          colors: <Color>[Colors.white.withValues(alpha: 0.85), Colors.white.withValues(alpha: 0)],
          stops: const <double>[0, 0.55],
        ).createShader(rect),
    );
    canvas.drawCircle(
      c,
      r,
      Paint()
        ..shader = RadialGradient(
          colors: <Color>[Colors.black.withValues(alpha: 0), Colors.black.withValues(alpha: 0.45)],
          stops: const <double>[0.7, 1],
        ).createShader(rect),
    );
  }

  @override
  bool shouldRepaint(_OrbPainter oldDelegate) => oldDelegate.colors != colors;
}

/// Full-bleed hero for the welcome screen: the orb on Aurora, the pendant on
/// Graphite, lit from above.
class DfHeroArt extends StatelessWidget {
  const DfHeroArt({super.key, required this.height, this.product = false});

  final double height;

  /// Always show the pendant (with its glow on Aurora), e.g. when selling it.
  final bool product;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final top = MediaQuery.paddingOf(context).top;
    final glow = t.glow;
    return SizedBox(
      height: height,
      child: DecoratedBox(
        decoration: BoxDecoration(
          gradient: RadialGradient(
            center: const Alignment(0, -0.3),
            radius: 0.9,
            colors: <Color>[glow != null ? glow.first.withValues(alpha: 0.18) : t.surface2, t.background],
          ),
        ),
        child: Padding(
          padding: EdgeInsets.only(top: top),
          child: Center(
            child: t.hasGlow && !product ? DfOrb(size: height * 0.55) : DfPendant(size: height * 0.4, glow: product),
          ),
        ),
      ),
    );
  }
}

/// The pendant on a lit stage, inside a rounded card.
class DfProductStage extends StatelessWidget {
  const DfProductStage({super.key, required this.height});

  final double height;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return Container(
      height: height,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(24),
        gradient: RadialGradient(
          center: const Alignment(0, -0.4),
          radius: 0.9,
          colors: <Color>[t.surface2, t.background],
        ),
      ),
      child: Center(child: DfPendant(size: height * 0.5, glow: true)),
    );
  }
}

/// Rings that pulse outwards from the pendant while the app searches for it.
class DfPulseRings extends StatefulWidget {
  const DfPulseRings({super.key, required this.size, required this.child});

  final double size;
  final Widget child;

  @override
  State<DfPulseRings> createState() => _DfPulseRingsState();
}

class _DfPulseRingsState extends State<DfPulseRings> with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(vsync: this, duration: const Duration(seconds: 2))
    ..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return SizedBox.square(
      dimension: widget.size,
      child: CustomPaint(
        painter: _PulsePainter(progress: _controller, color: t.accent, glow: t.glow),
        child: Center(child: widget.child),
      ),
    );
  }
}

class _PulsePainter extends CustomPainter {
  _PulsePainter({required this.progress, required this.color, required this.glow}) : super(repaint: progress);

  final Animation<double> progress;
  final Color color;
  final List<Color>? glow;

  @override
  void paint(Canvas canvas, Size size) {
    final c = size.center(Offset.zero);
    final maxR = size.shortestSide / 2;
    final minR = maxR * 0.42;
    for (var i = 0; i < 3; i++) {
      final p = (progress.value + i / 3) % 1;
      final r = minR + (maxR - minR) * p;
      final alpha = (1 - p) * 0.6;
      final paint = Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.5;
      final colors = glow;
      if (colors != null) {
        paint.shader = SweepGradient(
          colors: <Color>[
            for (final g in colors) g.withValues(alpha: alpha),
            colors.first.withValues(alpha: alpha),
          ],
        ).createShader(Rect.fromCircle(center: c, radius: r));
      } else {
        paint.color = color.withValues(alpha: alpha);
      }
      canvas.drawCircle(c, r, paint);
    }
  }

  @override
  bool shouldRepaint(_PulsePainter oldDelegate) => oldDelegate.color != color || oldDelegate.glow != glow;
}

/// Header art for the paywalls: a macro of the pendant on Graphite, ribbons of
/// light on Aurora.
class DfPaywallArt extends StatelessWidget {
  const DfPaywallArt({super.key});

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final glow = t.glow;
    if (glow != null) {
      return CustomPaint(painter: _RibbonsPainter(glow), child: const SizedBox.expand());
    }
    return Stack(
      clipBehavior: Clip.hardEdge,
      children: <Widget>[
        Positioned.fill(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: RadialGradient(
                center: const Alignment(0.6, -0.2),
                radius: 1,
                colors: <Color>[t.surface2, t.background],
              ),
            ),
          ),
        ),
        const Positioned(right: -40, top: -20, child: DfPendant(size: 230, showCord: false)),
      ],
    );
  }
}

class _RibbonsPainter extends CustomPainter {
  _RibbonsPainter(this.colors);

  final List<Color> colors;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    final shader = LinearGradient(colors: colors).createShader(rect);
    for (var i = 0; i < 3; i++) {
      final path = Path()
        ..moveTo(-20, size.height * (0.8 - i * 0.12))
        ..cubicTo(
          size.width * 0.3,
          size.height * (0.15 + i * 0.1),
          size.width * 0.6,
          size.height * (1.05 - i * 0.15),
          size.width + 20,
          size.height * (0.35 + i * 0.08),
        );
      canvas.drawPath(
        path,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 18.0 - i * 5
          ..shader = shader
          ..maskFilter = MaskFilter.blur(BlurStyle.normal, 10.0 - i * 3),
      );
      canvas.drawPath(
        path,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.5
          ..shader = shader,
      );
    }
  }

  @override
  bool shouldRepaint(_RibbonsPainter oldDelegate) => oldDelegate.colors != colors;
}

/// The setup screen's progress ring.
class DfProgressRing extends StatelessWidget {
  const DfProgressRing({super.key, required this.value, this.size = 120});

  final double value;
  final double size;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return CustomPaint(
      size: Size.square(size),
      painter: _RingPainter(value: value, track: t.surface2, colors: t.glow ?? <Color>[t.accent, t.accent]),
    );
  }
}

class _RingPainter extends CustomPainter {
  _RingPainter({required this.value, required this.track, required this.colors});

  final double value;
  final Color track;
  final List<Color> colors;

  @override
  void paint(Canvas canvas, Size size) {
    const stroke = 8.0;
    final rect = (Offset.zero & size).deflate(stroke / 2);
    canvas.drawArc(
      rect,
      0,
      math.pi * 2,
      false,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = stroke
        ..color = track,
    );
    canvas.drawArc(
      rect,
      -math.pi / 2,
      math.pi * 2 * value.clamp(0.0, 1.0),
      false,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = stroke
        ..strokeCap = StrokeCap.round
        ..shader = SweepGradient(colors: <Color>[...colors, colors.first]).createShader(rect),
    );
  }

  @override
  bool shouldRepaint(_RingPainter oldDelegate) => oldDelegate.value != value || oldDelegate.colors != colors;
}
