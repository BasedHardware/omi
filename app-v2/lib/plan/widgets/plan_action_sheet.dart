import 'package:flutter/cupertino.dart';

import 'package:nooto_v2/theme/app_theme.dart';

/// Result of tapping a row in [PlanActionSheet]. Returned to the caller via
/// `Navigator.pop` so the swipe gesture and the long-press path share one
/// resolution surface.
sealed class PlanActionResult {
  const PlanActionResult();
}

/// User picked a transition target. The caller fires the actual API call.
class PlanActionTransition extends PlanActionResult {
  const PlanActionTransition(this.toStatus);
  final String toStatus;
}

/// User picked Snooze 1 day.
class PlanActionSnooze extends PlanActionResult {
  const PlanActionSnooze();
}

/// Action sheet fired from a Jira row's long-press (and reused for swipe
/// gestures). Renders one row per available transition + an optional Snooze
/// row, gated by the calling screen's two-way-sync state.
///
/// VoiceOver parity: swipe gestures aren't reachable to assistive-tech
/// users, so the long-press → sheet path is the canonical entry point and
/// the sheet bundles BOTH directions (transition + snooze) under one
/// surface. The swipe gestures remain as a power-user shortcut.
class PlanActionSheet {
  PlanActionSheet._();

  /// Show the sheet. Returns the picked action, or null on cancel.
  ///
  /// [transitions] is the list of available status names. Pass an empty
  /// list to hide the transition rows entirely (e.g. for an item already
  /// in "done" state).
  /// [snoozeAvailable] gates the Snooze 1d row. False → row hidden (e.g.
  /// when called from a swipe-only path that already targeted snooze, or
  /// when two-way-sync just got disabled mid-flight).
  static Future<PlanActionResult?> show(
    BuildContext context, {
    required List<String> transitions,
    required bool snoozeAvailable,
  }) {
    return showCupertinoModalPopup<PlanActionResult>(
      context: context,
      builder: (popupContext) => CupertinoActionSheet(
        title: const Text('Move or snooze'),
        actions: [
          for (final option in transitions)
            CupertinoActionSheetAction(
              key: ValueKey('plan-action-transition-$option'),
              onPressed: () => Navigator.of(popupContext).pop(PlanActionTransition(option)),
              child: Text('Move to $option'),
            ),
          if (snoozeAvailable)
            CupertinoActionSheetAction(
              key: const ValueKey('plan-action-snooze'),
              onPressed: () => Navigator.of(popupContext).pop(const PlanActionSnooze()),
              child: const Text('Snooze 1 day'),
            ),
        ],
        cancelButton: CupertinoActionSheetAction(
          isDefaultAction: true,
          onPressed: () => Navigator.of(popupContext).pop(),
          child: const Text('Cancel'),
        ),
      ),
    );
  }
}

/// Convenience: a labeled icon for the swipe-revealed background. Kept
/// separate from the sheet so `_SwipeBg` in plan_screen stays free of
/// sheet-specific knowledge.
class PlanSwipeLabel extends StatelessWidget {
  const PlanSwipeLabel({super.key, required this.label, required this.icon, required this.leading});

  final String label;
  final IconData icon;
  final bool leading;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (leading) ...[
          Icon(icon, color: AppColors.textPrimary, size: 20),
          const SizedBox(width: AppStyles.spacingS),
          Text(
            label,
            style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
          ),
        ] else ...[
          Text(
            label,
            style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
          ),
          const SizedBox(width: AppStyles.spacingS),
          Icon(icon, color: AppColors.textPrimary, size: 20),
        ],
      ],
    );
  }
}
