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
    this.badgeCount = 0,
  });

  final Widget icon;
  final VoidCallback onTap;
  final String semanticLabel;
  final Color? color;

  /// Diameter of the painted circle. The touch target stays [kMinTapTarget].
  final double diameter;

  /// A count shown in a small pill on the circle's top-right edge; hidden at zero. Visual only:
  /// put the count in [semanticLabel] too, since the pill is excluded from semantics.
  final int badgeCount;

  @override
  Widget build(BuildContext context) {
    final button = OmiIconButton.filled(
      icon: icon,
      label: semanticLabel,
      onPressed: onTap,
      fillColor: color ?? OmiColors.surface1,
      diameter: diameter,
    );
    if (badgeCount <= 0) return button;
    return Stack(
      clipBehavior: Clip.none,
      children: [
        button,
        Positioned(
          top: 0,
          right: 0,
          child: IgnorePointer(
            child: ExcludeSemantics(
              child: HeaderCountBadge(count: badgeCount),
            ),
          ),
        ),
      ],
    );
  }
}

/// The count pill on a [HeaderCircleButton]: capped at "9+", ringed in the page
/// surface so it reads as sitting on top of the circle.
class HeaderCountBadge extends StatelessWidget {
  const HeaderCountBadge({super.key, required this.count});

  final int count;

  @override
  Widget build(BuildContext context) {
    final label = count > 9 ? '9+' : '$count';
    return Container(
      key: const ValueKey('header_count_badge'),
      constraints: const BoxConstraints(minWidth: 20, minHeight: 20),
      padding: const EdgeInsets.symmetric(horizontal: 6),
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: OmiColors.accent,
        borderRadius: const BorderRadius.all(Radius.circular(10)),
        border: Border.all(color: OmiColors.surface0, width: 2),
      ),
      child: Text(
        label,
        textScaler: TextScaler.noScaling,
        style: OmiType.caption.copyWith(
          color: OmiColors.onAccent,
          fontWeight: FontWeight.w700,
          height: 1.0,
        ),
      ),
    );
  }
}
