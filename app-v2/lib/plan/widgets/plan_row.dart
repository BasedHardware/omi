import 'package:flutter/material.dart';

import 'package:nooto_v2/providers/action_items_provider.dart';
import 'package:nooto_v2/theme/app_theme.dart';

/// One commitment row in the Plan screen. Tap the checkbox to mark complete
/// (optimistic, rolls back on server error). Description wraps to 2 lines;
/// due-date tag (or relative-age fallback) sits on the right.
class PlanRow extends StatelessWidget {
  const PlanRow({super.key, required this.item, required this.onToggle});

  final ActionItem item;
  final Future<void> Function() onToggle;

  @override
  Widget build(BuildContext context) {
    final trailing = _trailingLabel(item);
    return InkWell(
      onTap: onToggle,
      borderRadius: BorderRadius.circular(AppStyles.radiusMedium),
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppStyles.spacingS,
          vertical: AppStyles.spacingM,
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: _Checkbox(checked: item.completed),
            ),
            const SizedBox(width: AppStyles.spacingM),
            Expanded(
              child: Text(
                item.description,
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 15,
                  color: item.completed
                      ? AppColors.textTertiary
                      : AppColors.textPrimary,
                  height: 1.4,
                  decoration: item.completed
                      ? TextDecoration.lineThrough
                      : TextDecoration.none,
                  decorationColor: AppColors.textTertiary,
                ),
              ),
            ),
            if (trailing != null) ...[
              const SizedBox(width: AppStyles.spacingS),
              Padding(
                padding: const EdgeInsets.only(top: 2),
                child: Text(
                  trailing,
                  style: const TextStyle(
                    fontSize: 12,
                    color: AppColors.textTertiary,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  /// Due → relative ("today", "tomorrow", "3d", "overdue 2d"). Else age of
  /// createdAt ("2d"). Null if neither is set.
  static String? _trailingLabel(ActionItem item) {
    final now = DateTime.now();
    final due = item.dueAt;
    if (due != null) {
      final today = DateTime(now.year, now.month, now.day);
      final dueDay = DateTime(due.year, due.month, due.day);
      final diffDays = dueDay.difference(today).inDays;
      if (diffDays < 0) return 'overdue ${-diffDays}d';
      if (diffDays == 0) return 'today';
      if (diffDays == 1) return 'tomorrow';
      if (diffDays < 7) return '${diffDays}d';
      if (diffDays < 30) return '${(diffDays / 7).round()}w';
      return '${(diffDays / 30).round()}mo';
    }
    final created = item.createdAt;
    if (created != null) {
      final age = now.difference(created);
      if (age.inDays < 1) return '${age.inHours}h';
      if (age.inDays < 30) return '${age.inDays}d';
      if (age.inDays < 365) return '${(age.inDays / 30).round()}mo';
      return '${(age.inDays / 365).round()}y';
    }
    return null;
  }
}

class _Checkbox extends StatelessWidget {
  const _Checkbox({required this.checked});
  final bool checked;

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 150),
      width: 20,
      height: 20,
      decoration: BoxDecoration(
        color: checked ? AppColors.brandPrimary : Colors.transparent,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(
          color: checked
              ? AppColors.brandPrimary
              : AppColors.textTertiary.withValues(alpha: 0.5),
          width: 1.5,
        ),
      ),
      child: checked
          ? const Icon(
              Icons.check_rounded,
              size: 14,
              color: AppColors.textPrimary,
            )
          : null,
    );
  }
}
