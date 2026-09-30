import 'package:flutter/material.dart';

import 'package:omi/ui/omi_tokens.dart';

/// One choice in a row of list filters ("All 12", "Needs Voice 3"). Exactly one chip in the row is
/// [selected]; it is filled with the neutral accent (INV-UI-1), the others sit on
/// [OmiColors.chipSurface].
///
/// [count], when given, is drawn after the label; [semanticsLabel] must then say what it counts
/// ("Needs Voice, 3 people"). The visual chip is 32pt; the touch target is 44pt.
class OmiFilterChip extends StatelessWidget {
  const OmiFilterChip({
    super.key,
    required this.label,
    required this.selected,
    required this.onSelected,
    this.count,
    this.semanticsLabel,
  });

  final String label;
  final bool selected;
  final VoidCallback onSelected;
  final int? count;
  final String? semanticsLabel;

  @override
  Widget build(BuildContext context) {
    final foreground = selected ? OmiColors.onAccent : OmiColors.textPrimary;
    return Semantics(
      button: true,
      selected: selected,
      label: semanticsLabel ?? label,
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () {
          if (selected) return;
          OmiHaptics.selection();
          onSelected();
        },
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 44),
          child: Center(
            widthFactor: 1,
            child: AnimatedContainer(
              duration: OmiMotion.of(context).quick,
              curve: OmiMotion.standardCurve,
              constraints: const BoxConstraints(minHeight: 32),
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: 6),
              decoration: BoxDecoration(
                color: selected ? OmiColors.accent : OmiColors.chipSurface,
                borderRadius: OmiRadius.pillAll,
              ),
              child: Text.rich(
                TextSpan(children: [
                  TextSpan(text: label),
                  if (count != null)
                    TextSpan(
                      text: '  $count',
                      style: TextStyle(color: foreground.withValues(alpha: 0.6)),
                    ),
                ]),
                style: OmiType.subhead.copyWith(color: foreground, fontWeight: FontWeight.w500),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
