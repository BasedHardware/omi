import 'package:flutter/material.dart';

/// Smallest comfortable touch target: Apple's HIG asks for 44x44pt, Material
/// for 48dp. Header controls use the smaller of the two so a row of them still
/// fits a phone-width app bar.
const double kMinTapTarget = 44;

/// Diameter of the circle a [HeaderCircleButton] paints.
const double kHeaderCircleDiameter = 36;

/// A small circular header control whose touch target is larger than the
/// circle it paints.
///
/// The home header's buttons are 36pt circles, and they used to be 36pt touch
/// targets too, 8pt apart. This keeps the 36pt visual and centers it in a
/// [kMinTapTarget] square that owns the taps, so neighbouring buttons laid out
/// edge to edge keep the same 8pt visual gap with no dead strip between them.
class HeaderCircleButton extends StatelessWidget {
  const HeaderCircleButton({
    super.key,
    required this.icon,
    required this.onTap,
    required this.semanticLabel,
    this.color = const Color(0xFF1F1F25),
    this.diameter = kHeaderCircleDiameter,
  });

  final Widget icon;
  final VoidCallback onTap;
  final String semanticLabel;
  final Color color;

  /// Diameter of the painted circle. The touch target stays [kMinTapTarget].
  final double diameter;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: semanticLabel,
      child: InkResponse(
        onTap: onTap,
        radius: kMinTapTarget / 2,
        child: SizedBox(
          width: kMinTapTarget,
          height: kMinTapTarget,
          child: Center(
            child: Container(
              width: diameter,
              height: diameter,
              alignment: Alignment.center,
              decoration: BoxDecoration(color: color, shape: BoxShape.circle),
              child: icon,
            ),
          ),
        ),
      ),
    );
  }
}
