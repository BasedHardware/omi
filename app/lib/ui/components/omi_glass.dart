import 'dart:ui' show ImageFilter;

import 'package:flutter/material.dart';

import '../omi_tokens.dart';

/// A little liquid glass for a control on the page: a fill and a rim. A control floating over
/// content that scrolls beneath it ([blur]) blurs what passes under and takes the float glass, which
/// on a light page adds a faint outline and a soft shadow.
///
/// [shape] is the outline: a [CircleBorder], [StadiumBorder] or [RoundedRectangleBorder]. [tint]
/// replaces the glass fill for a control that is on or busy. The child is not clipped; one that
/// paints to its edges (a map) clips itself.
///
/// A [Container] that needs no blur can take the glass as decorations instead of a wrapper:
/// `decoration: OmiGlass.fill(shape)` and `foregroundDecoration: OmiGlass.rim(shape)`.
class OmiGlass extends StatelessWidget {
  const OmiGlass({super.key, required this.shape, required this.child, this.tint, this.blur = false});

  final ShapeBorder shape;
  final Widget child;
  final Color? tint;

  /// Blur what scrolls beneath. It costs a compositing layer, so only controls that float over a
  /// list use it.
  final bool blur;

  static const double blurSigma = 16;

  /// The glass fill in [shape], or [tint] for a control that is on or busy.
  static ShapeDecoration fill(ShapeBorder shape, {Color? tint}) =>
      ShapeDecoration(shape: shape, color: tint ?? OmiColors.glass);

  /// Around a floating control: a hairline outline and a soft shadow; none in dark.
  static List<BoxShadow> get floatShadows {
    if (OmiColors.floatOutline.a == 0 && OmiColors.floatShadow.a == 0) return const [];
    return [
      BoxShadow(color: OmiColors.floatOutline, spreadRadius: 0.5),
      BoxShadow(color: OmiColors.floatShadow, blurRadius: 30, offset: const Offset(0, 10)),
    ];
  }

  /// The lit rim around [shape]. A foreground decoration, so it draws over a child that paints to
  /// the edges.
  static OmiGlassRim rim(ShapeBorder shape) =>
      OmiGlassRim(shape: shape, edge: OmiColors.glassEdge, rim: OmiColors.glassRim);

  @override
  Widget build(BuildContext context) {
    if (!blur) {
      return DecoratedBox(
        decoration: fill(shape, tint: tint),
        child: DecoratedBox(decoration: rim(shape), position: DecorationPosition.foreground, child: child),
      );
    }
    final floatRim = OmiGlassRim(shape: shape, edge: OmiColors.floatEdge, rim: OmiColors.floatRim);
    // The outline and shadow sit outside the blur's clip, so they are painted around it.
    return DecoratedBox(
      decoration: ShapeDecoration(shape: shape, shadows: floatShadows),
      child: ClipPath(
        clipper: ShapeBorderClipper(shape: shape),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: blurSigma, sigmaY: blurSigma),
          child: DecoratedBox(
            decoration: ShapeDecoration(shape: shape, color: tint ?? OmiColors.floatGlass),
            child: DecoratedBox(decoration: floatRim, position: DecorationPosition.foreground, child: child),
          ),
        ),
      ),
    );
  }
}

/// The glass rim: a hairline in [edge] along the top, fading to [rim] by the middle and below.
class OmiGlassRim extends Decoration {
  const OmiGlassRim({required this.shape, required this.edge, required this.rim});

  final ShapeBorder shape;
  final Color edge;
  final Color rim;

  @override
  BoxPainter createBoxPainter([VoidCallback? onChanged]) => _OmiGlassRimPainter(this);

  @override
  bool operator ==(Object other) =>
      other is OmiGlassRim && other.shape == shape && other.edge == edge && other.rim == rim;

  @override
  int get hashCode => Object.hash(shape, edge, rim);
}

class _OmiGlassRimPainter extends BoxPainter {
  _OmiGlassRimPainter(this.decoration);

  final OmiGlassRim decoration;

  @override
  void paint(Canvas canvas, Offset offset, ImageConfiguration configuration) {
    final rect = offset & configuration.size!;
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1
      ..shader = LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [decoration.edge, decoration.rim],
        stops: const [0, 0.5],
      ).createShader(rect);
    canvas.drawPath(
        decoration.shape.getOuterPath(rect.deflate(0.5), textDirection: configuration.textDirection), paint);
  }
}
