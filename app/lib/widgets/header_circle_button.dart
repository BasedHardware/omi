import 'package:flutter/material.dart';

import 'package:omi/ui/components/omi_icon_button.dart';
import 'package:omi/ui/omi_tokens.dart';

/// Smallest comfortable touch target. Same value as [kOmiMinTapTarget]; kept for existing callers.
const double kMinTapTarget = kOmiMinTapTarget;

/// Diameter of the circle a [HeaderCircleButton] paints. Same value as [kOmiIconCircleDiameter].
const double kHeaderCircleDiameter = kOmiIconCircleDiameter;

/// A small circular header control whose touch target is larger than the circle it paints.
///
/// This is now a thin wrapper over [OmiIconButton.filled], which new code should use directly:
/// the same 36pt circle centred in a 44pt target, plus a tooltip on long-press.
class HeaderCircleButton extends StatelessWidget {
  const HeaderCircleButton({
    super.key,
    required this.icon,
    required this.onTap,
    required this.semanticLabel,
    this.color,
    this.diameter = kHeaderCircleDiameter,
  });

  final Widget icon;
  final VoidCallback onTap;
  final String semanticLabel;
  final Color? color;

  /// Diameter of the painted circle. The touch target stays [kMinTapTarget].
  final double diameter;

  @override
  Widget build(BuildContext context) {
    // Daylight: liquid glass, like the device chip beside it (a flat white disc on the pale page read
    // as a sticker). Dark keeps the graphite circle.
    if (color == null && OmiColors.isLight) {
      return OmiIconButton.glass(icon: icon, label: semanticLabel, onPressed: onTap, diameter: diameter);
    }
    return OmiIconButton.filled(
      icon: icon,
      label: semanticLabel,
      onPressed: onTap,
      fillColor: color ?? OmiColors.surface1,
      diameter: diameter,
    );
  }
}
