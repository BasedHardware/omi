import 'package:flutter/material.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Picks how long a silence ends a conversation. A setting applies when it changes
/// (docs/ux-contract.md §12): tapping an option saves it and closes the sheet.
class ConversationTimeoutDialog {
  static Future<void> show(BuildContext context) async {
    final l10n = context.l10n;
    final currentDuration = SharedPreferencesUtil().conversationSilenceDuration;

    // Timeout options: 2 mins, 5 mins, 10 mins, 30 mins, 4 hours (-1)
    final options = <({int value, String label, String description})>[
      (value: 120, label: l10n.timeout2Minutes, description: l10n.timeout2MinutesDesc),
      (value: 300, label: l10n.timeout5Minutes, description: l10n.timeout5MinutesDesc),
      (value: 600, label: l10n.timeout10Minutes, description: l10n.timeout10MinutesDesc),
      (value: 1800, label: l10n.timeout30Minutes, description: l10n.timeout30MinutesDesc),
      (value: -1, label: l10n.timeout4Hours, description: l10n.timeout4HoursDesc),
    ];

    final selected = await showOmiSheet<int>(
      context: context,
      title: l10n.conversationTimeout,
      builder: (sheetContext) => SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(OmiSpacing.xxs, 0, OmiSpacing.xxs, OmiSpacing.md),
              child: Text(
                l10n.conversationTimeoutDesc,
                style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
              ),
            ),
            OmiSettingsGroup(
              children: [
                for (final option in options)
                  Semantics(
                    selected: option.value == currentDuration,
                    child: OmiSettingsRow(
                      title: option.label,
                      subtitle: option.description,
                      showChevron: false,
                      trailing: option.value == currentDuration
                          ? const Icon(Icons.check_rounded, color: OmiColors.accent, size: 22)
                          : const SizedBox(width: 22),
                      onTap: () => Navigator.of(sheetContext).pop(option.value),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: OmiSpacing.md),
          ],
        ),
      ),
    );

    if (selected == null || selected == currentDuration) return;
    SharedPreferencesUtil().conversationSilenceDuration = selected;
    if (!context.mounted) return;
    final message = selected == -1
        ? context.l10n.conversationEndAfterHours
        : context.l10n.conversationEndAfterMinutes(selected ~/ 60);
    OmiFeedback.confirm(context, message);
  }
}
