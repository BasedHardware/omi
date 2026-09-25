import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';

/// One choice in a task-integration picker (Asana workspace/project, ClickUp team/space/list).
///
/// The whole card is a single ≥48pt button that screen readers announce as selected or not, so the
/// pickers read like a radio group rather than a column of unlabeled boxes.
class IntegrationSelectionCard extends StatelessWidget {
  const IntegrationSelectionCard({super.key, required this.label, required this.isSelected, required this.onTap});

  final String label;
  final bool isSelected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: OmiSpacing.sm),
      child: Semantics(
        button: true,
        selected: isSelected,
        inMutuallyExclusiveGroup: true,
        label: label,
        excludeSemantics: true,
        onTap: onTap,
        child: Material(
          color: OmiColors.surface1,
          shape: RoundedRectangleBorder(
            borderRadius: OmiRadius.mdAll,
            side: isSelected ? const BorderSide(color: OmiColors.accent, width: 2) : BorderSide.none,
          ),
          clipBehavior: Clip.antiAlias,
          child: InkWell(
            onTap: onTap,
            child: ConstrainedBox(
              constraints: const BoxConstraints(minHeight: 48),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
                child: Row(
                  children: [
                    Expanded(child: Text(label, style: OmiType.callout)),
                    if (isSelected) const Icon(Icons.check_circle, color: OmiColors.accent, size: 24),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// The note a task-integration picker shows when it has nothing to choose from.
class IntegrationSelectionEmpty extends StatelessWidget {
  const IntegrationSelectionEmpty(this.message, {super.key});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(OmiSpacing.lg),
      decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
      child: Text(
        message,
        textAlign: TextAlign.center,
        style: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
      ),
    );
  }
}

/// "Connected as …" banner above a task-integration picker.
class IntegrationConnectedBanner extends StatelessWidget {
  const IntegrationConnectedBanner(this.message, {super.key});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(OmiSpacing.sm),
      margin: const EdgeInsets.only(bottom: OmiSpacing.md),
      decoration: BoxDecoration(
        color: OmiColors.successSurface,
        borderRadius: OmiRadius.smAll,
        border: Border.all(color: OmiColors.success.withValues(alpha: 0.3)),
      ),
      child: Row(
        children: [
          const Icon(Icons.check_circle, color: OmiColors.success, size: 16),
          const SizedBox(width: OmiSpacing.xs),
          Expanded(child: Text(message, style: OmiType.footnote.copyWith(color: OmiColors.success))),
        ],
      ),
    );
  }
}

enum IntegrationChipTone { accent, muted, danger }

/// The small pill at the end of an integration row ("Connect", "Disconnect", "Coming Soon"). The row
/// is the tap target; the pill only labels what a tap does.
class IntegrationStatusChip extends StatelessWidget {
  const IntegrationStatusChip(this.label, {super.key, this.tone = IntegrationChipTone.accent});

  final String label;
  final IntegrationChipTone tone;

  @override
  Widget build(BuildContext context) {
    final (background, foreground) = switch (tone) {
      IntegrationChipTone.accent => (OmiColors.accent, OmiColors.onAccent),
      IntegrationChipTone.muted => (OmiColors.border, OmiColors.textSecondary),
      IntegrationChipTone.danger => (OmiColors.dangerSurface, OmiColors.textPrimary),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: 6),
      decoration: BoxDecoration(color: background, borderRadius: OmiRadius.pillAll),
      child: Text(label, style: OmiType.footnote.copyWith(color: foreground, fontWeight: FontWeight.w500)),
    );
  }
}
