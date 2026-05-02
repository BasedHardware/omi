import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import 'package:nooto_v2/plan/widgets/plan_pivot_picker.dart';
import 'package:nooto_v2/theme/app_theme.dart';

/// Quick filters on Plan. Mutually exclusive single-select; "All" is the
/// default zero-state.
///
/// Stuck reuses the JiraStuckIssuesCard threshold (≥3 days at the same
/// status). DueSoon is hard-coded to "next 24h" for now — calendar-aware
/// "due this week" is a follow-up. "Mine" was dropped per the design
/// review — every Plan row is the user's by definition (transcript items
/// belong to the user; Jira sync is assignee-filtered server-side), so a
/// dedicated chip just added visual weight without semantic value.
enum PlanFilter { all, stuck, dueSoon }

extension PlanFilterLabel on PlanFilter {
  String get label {
    switch (this) {
      case PlanFilter.all:
        return 'All';
      case PlanFilter.stuck:
        return 'Stuck';
      case PlanFilter.dueSoon:
        return 'Due Soon';
    }
  }
}

/// Horizontally scrolling chip rail. Sized to a 44pt content height (touch
/// target) plus padding. Designed to live inside a SliverPersistentHeader so
/// it pins under the AppBar while the list scrolls.
///
/// Layout: `[By Date ⌄] | [All] [Stuck] [Due Soon] [PROJ ×]?`
///   * Pivot pill at the left end — shows the active pivot, taps open a
///     Cupertino action sheet with three options (mirrors the same picker
///     UI we'd previously parked on the AppBar title).
///   * 1pt vertical hairline separator visually groups "pivot vs filter".
///   * Filter chips for All / Stuck / Due Soon (dropped Mine; every row is
///     the user's by definition).
///   * Optional active-project chip ("PROJ ×") at the trailing end when the
///     user has tapped a project pill on a Jira chip.
class PlanFilterRail extends StatelessWidget {
  const PlanFilterRail({
    super.key,
    required this.selected,
    required this.onChanged,
    required this.pivot,
    required this.onPivotChanged,
    this.activeProjectFilter,
    this.onClearProjectFilter,
  });

  final PlanFilter selected;
  final ValueChanged<PlanFilter> onChanged;

  /// Active pivot, rendered as the leading pill. Tapping opens the picker
  /// sheet; selecting a different value calls [onPivotChanged].
  final PlanPivot pivot;
  final ValueChanged<PlanPivot> onPivotChanged;

  /// When non-null, an extra "PROJ ×" chip renders at the end of the rail
  /// in selected state. Tapping it calls [onClearProjectFilter]. This is a
  /// transient layer on top of the [PlanFilter] selection — the user can
  /// have e.g. "Stuck" + "PROJ" applied at the same time.
  final String? activeProjectFilter;
  final VoidCallback? onClearProjectFilter;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: AppStyles.touchTargetMinimum + AppStyles.spacingS,
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingL, vertical: AppStyles.spacingXS),
        children: [
          _PivotPill(key: const ValueKey('plan-pivot-pill'), pivot: pivot, onChanged: onPivotChanged),
          const SizedBox(width: AppStyles.spacingM),
          const _RailDivider(),
          const SizedBox(width: AppStyles.spacingM),
          for (final filter in PlanFilter.values) ...[
            _FilterChip(
              key: ValueKey('plan-filter-${filter.name}'),
              label: filter.label,
              selected: selected == filter,
              onTap: () => onChanged(filter),
            ),
            const SizedBox(width: AppStyles.spacingS),
          ],
          if (activeProjectFilter != null && activeProjectFilter!.isNotEmpty)
            _FilterChip(
              key: const ValueKey('plan-filter-project'),
              label: '$activeProjectFilter ×',
              selected: true,
              onTap: onClearProjectFilter ?? () {},
            ),
        ],
      ),
    );
  }
}

/// Leading pill in the rail. Visually distinct from filter chips — uses
/// `brandPrimary` text on `backgroundSecondary` so users perceive it as a
/// "category selector" rather than a filter. Same touch target (≥44pt) as
/// the filter chips so taps stay equally hittable.
class _PivotPill extends StatelessWidget {
  const _PivotPill({super.key, required this.pivot, required this.onChanged});

  final PlanPivot pivot;
  final ValueChanged<PlanPivot> onChanged;

  Future<void> _open(BuildContext context) async {
    final picked = await showCupertinoModalPopup<PlanPivot>(
      context: context,
      builder: (popupContext) => CupertinoActionSheet(
        title: const Text('Group plan by'),
        actions: [
          for (final option in PlanPivot.values)
            CupertinoActionSheetAction(
              key: ValueKey('plan-pivot-action-${option.name}'),
              onPressed: () => Navigator.of(popupContext).pop(option),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(option.label, style: TextStyle(fontWeight: option == pivot ? FontWeight.w600 : FontWeight.w400)),
                  if (option == pivot) ...[
                    const SizedBox(width: AppStyles.spacingS),
                    const Icon(Icons.check_rounded, size: 18),
                  ],
                ],
              ),
            ),
        ],
        cancelButton: CupertinoActionSheetAction(
          isDefaultAction: true,
          onPressed: () => Navigator.of(popupContext).pop(),
          child: const Text('Cancel'),
        ),
      ),
    );
    if (picked != null && picked != pivot) onChanged(picked);
  }

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: 'Plan pivot: ${pivot.label}',
      hint: 'Tap to change grouping',
      child: InkWell(
        borderRadius: BorderRadius.circular(AppStyles.radiusPill),
        onTap: () => _open(context),
        child: Container(
          constraints: const BoxConstraints(minHeight: AppStyles.touchTargetMinimum),
          alignment: Alignment.center,
          padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingM, vertical: AppStyles.spacingS),
          decoration: BoxDecoration(
            color: AppColors.backgroundSecondary,
            borderRadius: BorderRadius.circular(AppStyles.radiusPill),
            border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                pivot.label,
                style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.brandPrimary),
              ),
              const SizedBox(width: AppStyles.spacingXS),
              const Icon(Icons.arrow_drop_down_rounded, size: 16, color: AppColors.brandPrimary),
            ],
          ),
        ),
      ),
    );
  }
}

/// 1pt vertical hairline between the pivot pill and the first filter chip.
/// Matches the chip height so it doesn't look like a stray line — visually
/// groups "pivot vs filter" without needing a label.
class _RailDivider extends StatelessWidget {
  const _RailDivider();
  @override
  Widget build(BuildContext context) {
    return Container(
      width: 1,
      height: AppStyles.touchTargetMinimum - AppStyles.spacingS,
      color: Colors.white.withValues(alpha: 0.06),
    );
  }
}

class _FilterChip extends StatelessWidget {
  const _FilterChip({super.key, required this.label, required this.selected, required this.onTap});

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final bg = selected ? AppColors.brandPrimary : AppColors.backgroundSecondary;
    final fg = selected ? AppColors.textPrimary : AppColors.textSecondary;
    return InkWell(
      borderRadius: BorderRadius.circular(AppStyles.radiusPill),
      onTap: onTap,
      child: Container(
        constraints: const BoxConstraints(
          minHeight: AppStyles.touchTargetMinimum,
          minWidth: AppStyles.touchTargetMinimum,
        ),
        alignment: Alignment.center,
        padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingL, vertical: AppStyles.spacingS),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(AppStyles.radiusPill),
          border: Border.all(color: selected ? AppColors.brandPrimary : Colors.white.withValues(alpha: 0.06)),
        ),
        child: Text(
          label,
          style: TextStyle(fontSize: 14, fontWeight: FontWeight.w500, color: fg),
        ),
      ),
    );
  }
}
