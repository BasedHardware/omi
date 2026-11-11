import 'package:flutter/material.dart';

import 'package:omi/ui/omi_tokens.dart';

enum OmiLevelMeterSize {
  small(8, 4, 2),
  medium(12, 5, 3),
  large(22, 7, 4);

  const OmiLevelMeterSize(this.stepWidth, this.stepHeight, this.gap);
  final double stepWidth;
  final double stepHeight;
  final double gap;
}

/// A three-step level meter, never a percentage: how sure Omi is about a person (confidence) or how
/// close a voice is to someone (voice match).
///
/// Neutral by design (INV-UI-1): filled steps use [OmiColors.textPrimary] and empty steps a faint
/// fill of the same colour; the level is carried by shape, not colour. A step that fills while on
/// screen animates in ([OmiMotion.standard], none under Reduce Motion), which is the "confidence
/// ticked up" moment after a label.
///
/// It is one accessibility node: [semanticsLabel] says what the level means ("Confidence: Likely").
class OmiLevelMeter extends StatelessWidget {
  const OmiLevelMeter({
    super.key,
    required this.level,
    required this.semanticsLabel,
    this.size = OmiLevelMeterSize.small,
  });

  /// 0 to 3 filled steps.
  final int level;
  final String semanticsLabel;
  final OmiLevelMeterSize size;

  @override
  Widget build(BuildContext context) {
    final motion = OmiMotion.of(context);
    final filled = level.clamp(0, 3);
    return Semantics(
      label: semanticsLabel,
      excludeSemantics: true,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (var step = 0; step < 3; step++) ...[
            if (step > 0) SizedBox(width: size.gap),
            AnimatedContainer(
              key: ValueKey('omi_level_meter_step_$step'),
              duration: motion.standard,
              curve: OmiMotion.emphasizedCurve,
              width: size.stepWidth,
              height: size.stepHeight,
              decoration: BoxDecoration(
                color: step < filled ? OmiColors.textPrimary : OmiColors.textPrimary.withValues(alpha: 0.18),
                borderRadius: BorderRadius.circular(size.stepHeight / 2),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
