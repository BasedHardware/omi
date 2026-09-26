import 'package:flutter/material.dart';

import 'package:omi/ui/components/omi_surface.dart';
import 'package:omi/ui/omi_tokens.dart';

/// The selected tab's lens: a faint white glass pill with a lit top edge (a frosted white pill in
/// daylight). Landing on a new tab it
/// squashes wide and settles (Liquid Dock "jelly", 0.5 s).
class OmiDockLens extends StatelessWidget {
  const OmiDockLens({super.key, required this.animate});

  final bool animate;

  static (double, double) _jelly(double t) {
    // 30 %: 1.12 × 0.94 → 60 %: 0.97 × 1.03 → 100 %: 1 × 1.
    double lerp(double a, double b, double f) => a + (b - a) * f;
    if (t < 0.3) {
      final f = t / 0.3;
      return (lerp(1, 1.12, f), lerp(1, 0.94, f));
    }
    if (t < 0.6) {
      final f = (t - 0.3) / 0.3;
      return (lerp(1.12, 0.97, f), lerp(0.94, 1.03, f));
    }
    final f = (t - 0.6) / 0.4;
    return (lerp(0.97, 1, f), lerp(1.03, 1, f));
  }

  @override
  Widget build(BuildContext context) {
    final palette = OmiColors.palette;
    // Daylight (Liquid Dock light `--lens`): a frosted white pill lifted by a soft ink glow.
    final lens = OmiSurfaceLight(
      borderRadius: OmiRadius.pillAll,
      shadows: [
        OmiShadow(
          color: palette.lensShadow,
          offset: palette.isLight ? const Offset(0, 6) : const Offset(0, 2),
          blur: palette.isLight ? 16 : 6,
        ),
      ],
      topLight: palette.lensRim,
      ring: palette.lensRing,
      child: DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: OmiRadius.pillAll,
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [palette.lensTop, palette.lensBottom],
            stops: palette.isLight ? const [0, 0.6] : const [0, 1],
          ),
        ),
      ),
    );
    if (!animate) return lens;
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: 1),
      duration: const Duration(milliseconds: 500),
      curve: OmiMotion.springCurve,
      builder: (context, t, child) {
        final (sx, sy) = _jelly(t);
        return Transform(
          alignment: Alignment.center,
          transform: Matrix4.diagonal3Values(sx, sy, 1),
          child: child,
        );
      },
      child: lens,
    );
  }
}
