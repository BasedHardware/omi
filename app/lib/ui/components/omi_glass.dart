import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import 'package:omi/ui/components/omi_surface.dart';
import 'package:omi/ui/omi_tokens.dart';

/// The v2 floating material (tab bar, Ask button, header circles): a translucent fill (graphite,
/// or frosted white in daylight) over a saturated blur of whatever scrolls beneath it, lit on its top edge and casting a soft
/// shadow.
///
/// Blur is costly on low-end Android and unreadable for people who ask for more contrast, so it is
/// used only on Apple platforms without the high-contrast setting; everywhere else the surface is
/// solid [OmiColors.surface1]. Both look the same at rest.
class OmiGlass extends StatelessWidget {
  const OmiGlass({super.key, required this.borderRadius, required this.child});

  final BorderRadius borderRadius;
  final Widget child;

  static bool _blurs(BuildContext context) {
    final platform = Theme.of(context).platform;
    final apple = platform == TargetPlatform.iOS || platform == TargetPlatform.macOS;
    return apple && !MediaQuery.highContrastOf(context);
  }

  // The design's `.glass`: rgba(30,34,43,.58) over blur 26 + saturate 170%, a soft top sheen, a
  // 0.5 pt top highlight and hairline ring, and a drop shadow outside the shape.
  static const List<OmiShadow> _shadows = [
    OmiShadow(color: Color(0x73000000), offset: Offset(0, 10), blur: 30),
    OmiShadow(color: Color(0x59000000), offset: Offset(0, 1), blur: 2),
  ];

  // Daylight (Liquid Dock light `--shadow`): a wide, faint ink shadow.
  static const List<OmiShadow> _shadowsLight = [
    OmiShadow(color: Color(0x2414171E), offset: Offset(0, 18), blur: 44),
    OmiShadow(color: Color(0x1414171E), offset: Offset(0, 1), blur: 3),
  ];

  /// CSS `saturate(1.7)` as a colour matrix.
  static const double _s = 1.7;
  static const ColorFilter _saturate = ColorFilter.matrix(<double>[
    0.213 + 0.787 * _s, 0.715 - 0.715 * _s, 0.072 - 0.072 * _s, 0, 0, //
    0.213 - 0.213 * _s, 0.715 + 0.285 * _s, 0.072 - 0.072 * _s, 0, 0, //
    0.213 - 0.213 * _s, 0.715 - 0.715 * _s, 0.072 + 0.928 * _s, 0, 0, //
    0, 0, 0, 1, 0,
  ]);

  @override
  Widget build(BuildContext context) {
    final blur = _blurs(context);
    final palette = OmiColors.palette;
    // A gradient replaces a decoration's colour, so the sheen is its own layer over the fill.
    final surface = DecoratedBox(
      decoration: BoxDecoration(color: blur ? palette.glass : palette.surface1, borderRadius: borderRadius),
      child: DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: borderRadius,
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [palette.glassSheen, palette.glassSheen.withValues(alpha: 0)],
            stops: const [0, 0.58],
          ),
        ),
        child: child,
      ),
    );
    return OmiSurfaceLight(
      borderRadius: borderRadius,
      shadows: palette.isLight ? _shadowsLight : _shadows,
      topLight: palette.glassRim,
      ring: palette.glassRing,
      child: ClipRRect(
        borderRadius: borderRadius,
        child: blur
            ? BackdropFilter(
                filter: ui.ImageFilter.compose(outer: _saturate, inner: ui.ImageFilter.blur(sigmaX: 26, sigmaY: 26)),
                child: surface,
              )
            : surface,
      ),
    );
  }
}
