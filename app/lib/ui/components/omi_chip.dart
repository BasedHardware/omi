import 'package:flutter/material.dart';

import 'package:omi/ui/omi_tokens.dart';

/// The v2 filter chip: a 34pt capsule inside a 44pt target. Selected is the neutral accent fill
/// with dark text; unselected sits on [OmiColors.surface2]. Announced as a selected or unselected
/// button.
class OmiChip extends StatelessWidget {
  const OmiChip({
    super.key,
    required this.label,
    required this.selected,
    required this.onTap,
    this.leading,
    this.large = false,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  /// An optional small icon before the label.
  final Widget? leading;

  /// A 40pt answer chip in regular weight (onboarding questions) instead of the 34pt filter chip.
  final bool large;

  @override
  Widget build(BuildContext context) {
    final foreground = selected ? OmiColors.onAccent : OmiColors.textPrimary;
    return Semantics(
      button: true,
      selected: selected,
      label: label,
      excludeSemantics: true,
      onTap: onTap,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () {
          OmiHaptics.selection();
          onTap();
        },
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: OmiSize.minTap),
          child: Center(
            widthFactor: 1,
            child: AnimatedContainer(
              duration: OmiMotion.of(context).quick,
              curve: OmiMotion.springCurve,
              height: large ? 40 : 34,
              padding: EdgeInsets.symmetric(horizontal: large ? OmiSpacing.md : OmiSpacing.sm),
              decoration: BoxDecoration(
                color: selected ? OmiColors.accent : OmiColors.surface2,
                borderRadius: OmiRadius.pillAll,
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (leading != null) ...[
                    IconTheme.merge(data: IconThemeData(size: 14, color: foreground), child: leading!),
                    const SizedBox(width: 6),
                  ],
                  Text(
                    label,
                    style: (large ? OmiType.callout : OmiType.subhead).copyWith(
                      color: foreground,
                      fontWeight: large ? FontWeight.w500 : FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
