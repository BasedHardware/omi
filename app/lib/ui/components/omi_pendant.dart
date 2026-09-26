import 'package:flutter/material.dart';

import 'package:omi/ui/omi_tokens.dart';

/// The Omi pendant as the v2 designs draw it (Welcome, Sign in, Complete): a glass shell, a
/// silver rim, the dark core and the blue LED, hanging from its bail. Drawn in code from the design
/// canvas's layers, so it is sharp at any size and needs no image asset.
///
/// [lit] shows the LED and its halo ([OmiColors.live]); an unlit pendant is the device at rest.
class OmiPendant extends StatelessWidget {
  const OmiPendant({super.key, this.size = 150, this.lit = true});

  /// Diameter of the shell.
  final double size;
  final bool lit;

  @override
  Widget build(BuildContext context) {
    final s = size;
    return ExcludeSemantics(
      child: SizedBox.square(
        dimension: s,
        child: Stack(
          clipBehavior: Clip.none,
          children: [
            if (lit)
              Positioned(
                left: -0.85 * s,
                top: -0.85 * s,
                width: 2.7 * s,
                height: 2.7 * s,
                child: const DecoratedBox(
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: RadialGradient(
                      colors: [Color(0x264C9BFF), Color(0x0E4C9BFF), Color(0x004C9BFF)],
                      stops: [0, 0.32, 0.62],
                    ),
                  ),
                ),
              ),
            // Bail: the loop the cord runs through.
            Positioned(
              left: 0.4427 * s,
              top: -0.192 * s,
              width: 0.1147 * s,
              height: 0.24 * s,
              child: DecoratedBox(
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(0.0573 * s),
                  gradient: const LinearGradient(
                    colors: [Color(0x1AFFFFFF), Color(0x47FFFFFF), Color(0x1FFFFFFF)],
                    stops: [0, 0.45, 1],
                  ),
                  border: Border.all(color: const Color(0x59FFFFFF), width: 0.5),
                ),
                child: Align(
                  alignment: const Alignment(0, -0.35),
                  child: Container(
                    width: 0.046 * s,
                    height: 0.087 * s,
                    decoration: BoxDecoration(
                      color: const Color(0xB3000000),
                      borderRadius: BorderRadius.circular(0.023 * s),
                    ),
                  ),
                ),
              ),
            ),
            // Glass shell.
            Positioned.fill(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: const RadialGradient(
                    center: Alignment(0, -0.16),
                    colors: [Color(0x0FFFFFFF), Color(0x0DFFFFFF), Color(0x2BDCE4F0), Color(0x12FFFFFF)],
                    stops: [0, 0.58, 0.8, 1],
                  ),
                  border: Border.all(color: const Color(0x33FFFFFF), width: 0.5),
                  boxShadow: const [
                    BoxShadow(color: Color(0x99000000), offset: Offset(0, 22), blurRadius: 44),
                    BoxShadow(color: Color(0x66000000), offset: Offset(0, 4), blurRadius: 10),
                  ],
                ),
              ),
            ),
            // Silver rim.
            Positioned(
              left: 0.07 * s,
              top: 0.07 * s,
              width: 0.86 * s,
              height: 0.86 * s,
              child: const DecoratedBox(
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: RadialGradient(
                    colors: [
                      Color(0x00000000),
                      Color(0x47CDD8E8),
                      Color(0x9EECF1F8),
                      Color(0x33CDD8E8),
                      Color(0x00CDD8E8),
                    ],
                    stops: [0.76, 0.84, 0.91, 0.97, 1],
                  ),
                ),
              ),
            ),
            // Dark core, lit from the upper right.
            Positioned(
              left: 0.15 * s,
              top: 0.15 * s,
              width: 0.7 * s,
              height: 0.7 * s,
              child: const DecoratedBox(
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: RadialGradient(
                    center: Alignment(0.36, -0.52),
                    radius: 1.02,
                    colors: [
                      Color(0xFF7A808A),
                      Color(0xFF40454E),
                      Color(0xFF1B1E24),
                      Color(0xFF0C0D10),
                      Color(0xFF08090B)
                    ],
                    stops: [0, 0.2, 0.52, 0.8, 1],
                  ),
                  boxShadow: [BoxShadow(color: Color(0x8C000000), spreadRadius: 1)],
                ),
              ),
            ),
            // LED.
            Center(
              child: Container(
                width: 0.052 * s,
                height: 0.052 * s,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: lit
                      ? RadialGradient(
                          radius: 0.707,
                          colors: [const Color(0xFFFFFFFF), const Color(0xFFD2E6FF), OmiColors.live],
                          stops: const [0, 0.3, 0.72],
                        )
                      : null,
                  color: lit ? null : OmiColors.surface3,
                  boxShadow: lit
                      ? const [
                          BoxShadow(color: Color(0xF24C9BFF), blurRadius: 3, spreadRadius: 1),
                          BoxShadow(color: Color(0x804C9BFF), blurRadius: 12, spreadRadius: 3),
                          BoxShadow(color: Color(0x334C9BFF), blurRadius: 30, spreadRadius: 8),
                        ]
                      : null,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// The pendant hanging from its cord across the top of the screen (v2 Welcome, Sign in,
/// Complete). The cord spans the full width; the pendant hangs at its lowest point.
class OmiPendantHero extends StatelessWidget {
  const OmiPendantHero({super.key, this.scale = 1, this.lit = true});

  /// 1 is the design's 393pt-wide phone: a 150pt pendant under a 225pt drop.
  final double scale;
  final bool lit;

  static const double _cordHeight = 227;
  static const double _pendantTop = 225;
  static const double _pendantSize = 150;

  /// Height the hero occupies at [scale].
  static double heightFor(double scale) => (_pendantTop + _pendantSize) * scale;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: heightFor(scale),
      width: double.infinity,
      child: Stack(
        clipBehavior: Clip.none,
        alignment: Alignment.topCenter,
        children: [
          Positioned(
            left: 0,
            right: 0,
            top: 0,
            height: _cordHeight * scale,
            child: ExcludeSemantics(child: CustomPaint(painter: _CordPainter.hero(OmiColors.palette.isLight))),
          ),
          Positioned(
            top: _pendantTop * scale,
            child: OmiPendant(size: _pendantSize * scale, lit: lit),
          ),
        ],
      ),
    );
  }
}

/// The pendant hanging inside a card from a short cord (the device page hero, `Device.dc`): a
/// 120pt pendant whose bail meets the cord's low point. Fills the card, which the design draws
/// 250pt tall; the cord spans the card's width.
class OmiPendantInCard extends StatelessWidget {
  const OmiPendantInCard({super.key, this.lit = true});

  final bool lit;

  static const double _cordHeight = 120;
  static const double _pendantTop = 104;
  static const double _pendantSize = 120;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) => Stack(
        children: [
          Positioned(
            left: 0,
            right: 0,
            top: 0,
            height: _cordHeight,
            child: ExcludeSemantics(child: CustomPaint(painter: _CordPainter.card(OmiColors.palette.isLight))),
          ),
          Positioned(
            top: _pendantTop,
            left: (constraints.maxWidth - _pendantSize) / 2,
            child: OmiPendant(size: _pendantSize, lit: lit),
          ),
        ],
      ),
    );
  }
}

/// The cord: two curves meeting under the pendant, drawn as the design's three strokes (a faint
/// highlight, the dark cord, and its shadow). The design gives the left half in a [box]; the right
/// half mirrors it about [low], the lowest point.
class _CordPainter extends CustomPainter {
  /// Across the top of the screen (Welcome, Sign in, Complete): a 393 x 227 box.
  const _CordPainter.hero(this.light)
      : box = const Size(393, 227),
        start = const Offset(20, -10),
        c1 = const Offset(41.2, 190.4),
        c2 = const Offset(122.4, 207.9),
        low = const Offset(196.5, 207.9);

  /// Inside the device hero card: a 361 x 120 box.
  const _CordPainter.card(this.light)
      : box = const Size(361, 120),
        start = const Offset(30, -10),
        c1 = const Offset(48.1, 76.5),
        c2 = const Offset(117.3, 84),
        low = const Offset(180.5, 84);

  final Size box;
  final Offset start;
  final Offset c1;
  final Offset c2;
  final Offset low;

  /// The light palette lifts the cord with a faint dark edge instead of a white one.
  final bool light;

  @override
  void paint(Canvas canvas, Size size) {
    // Stretch the design path across the real size.
    final sx = size.width / box.width;
    final sy = size.height / box.height;
    Offset mirror(Offset o) => Offset(2 * low.dx - o.dx, o.dy);
    Path cord(double dy) {
      Offset at(Offset o) => Offset(o.dx * sx, o.dy * sy + dy);
      final (a, b, m, b2, a2, end) = (at(c1), at(c2), at(low), at(mirror(c2)), at(mirror(c1)), at(mirror(start)));
      final from = at(start);
      return Path()
        ..moveTo(from.dx, from.dy)
        ..cubicTo(a.dx, a.dy, b.dx, b.dy, m.dx, m.dy)
        ..cubicTo(b2.dx, b2.dy, a2.dx, a2.dy, end.dx, end.dy);
    }

    Paint stroke(Color color, double width) => Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeWidth = width
      ..color = color;
    canvas.drawPath(cord(1.6), stroke(light ? const Color(0x0B14171E) : const Color(0x13FFFFFF), 6.2));
    canvas.drawPath(cord(0), stroke(const Color(0xFF040507), 5));
    canvas.drawPath(cord(-0.8), stroke(const Color(0x8C000000), 2.2));
  }

  @override
  bool shouldRepaint(_CordPainter oldDelegate) => oldDelegate.light != light || oldDelegate.box != box;
}
