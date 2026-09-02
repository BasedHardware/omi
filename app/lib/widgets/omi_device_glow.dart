import 'package:flutter/material.dart';

import 'package:omi/gen/assets.gen.dart';

/// The Omi device artwork with a white glow behind it, shared by the
/// onboarding splash and the sign-in screen so the device reads as the same
/// element carrying through from one page to the next.
///
/// [glowIntensity] is 0 for no glow (flat product shot) to 1 for full glow;
/// callers can animate it (the splash's glow-in transition) or just pass a
/// fixed value (sign-in's steady-state glow). The device is always rendered
/// at the same size so it reads as one continuous element across pages.
class OmiDeviceGlow extends StatelessWidget {
  final double imageSize;
  final double glowIntensity;

  const OmiDeviceGlow({super.key, this.imageSize = 200, this.glowIntensity = 1.0});

  @override
  Widget build(BuildContext context) {
    final pixelRatio = MediaQuery.of(context).devicePixelRatio;
    final t = glowIntensity.clamp(0.0, 1.0);

    return Stack(
      alignment: Alignment.center,
      children: [
        Container(
          width: 460,
          height: 460,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            gradient: RadialGradient(colors: [Colors.white.withValues(alpha: 0.22 * t), Colors.transparent]),
          ),
        ),
        Container(
          width: 300,
          height: 300,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            gradient: RadialGradient(colors: [Colors.white.withValues(alpha: 0.45 * t), Colors.transparent]),
          ),
        ),
        Container(
          width: 170,
          height: 170,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            boxShadow: [BoxShadow(color: Colors.white.withValues(alpha: 0.7 * t), blurRadius: 100 * t)],
          ),
        ),
        Image.asset(
          Assets.images.omiWithoutRope.path,
          height: imageSize,
          width: imageSize,
          cacheHeight: (imageSize * pixelRatio).round(),
          cacheWidth: (imageSize * pixelRatio).round(),
        ),
      ],
    );
  }
}
