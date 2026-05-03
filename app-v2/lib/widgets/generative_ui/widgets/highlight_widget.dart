import 'package:flutter/material.dart';

import 'package:nooto_v2/theme/app_theme.dart';
import '../models/highlight_data.dart';

/// Widget that displays highlighted text. The legacy `/app` renders a
/// hand-drawn marker effect via CustomPainter; in app-v2 we use a flat
/// background tint to stay consistent with DESIGN.md's "minimal, no
/// decoration" stance — and the legacy painter was actually disabled there
/// too via a TODO at build time, so this matches what shipped on iOS.
class HighlightWidget extends StatelessWidget {
  final HighlightData data;

  const HighlightWidget({super.key, required this.data});

  @override
  Widget build(BuildContext context) {
    return MarkerHighlight(
      color: data.color,
      child: Text(
        data.text,
        style: const TextStyle(color: AppColors.textPrimary, fontSize: 16, fontWeight: FontWeight.w500, height: 1.5),
      ),
    );
  }
}

/// Flat-tint highlight wrapper. Wraps text in a lightly tinted rounded
/// container. Multi-line is handled implicitly by Flutter — no per-line
/// custom painting.
class MarkerHighlight extends StatelessWidget {
  final Widget child;
  final Color color;
  final double opacity;
  final double verticalPadding;
  final double horizontalPadding;

  const MarkerHighlight({
    super.key,
    required this.child,
    required this.color,
    this.opacity = 0.25,
    this.verticalPadding = 2.0,
    this.horizontalPadding = 4.0,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(horizontal: horizontalPadding, vertical: verticalPadding),
      decoration: BoxDecoration(
        color: color.withValues(alpha: opacity),
        borderRadius: BorderRadius.circular(AppStyles.radiusSmall),
      ),
      child: child,
    );
  }
}
