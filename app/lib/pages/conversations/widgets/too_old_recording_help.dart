// Explain a retained recording outside automatic sync and open existing support.
// This presentation never retries, retires, or sends the recording.
import 'package:flutter/material.dart';

import 'package:omi/pages/settings/settings_destinations.dart';
import 'package:omi/pages/settings/settings_search_index.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Presentation only: support opens a draft, never sends audio or recording IDs.
class TooOldRecordingHelp extends StatelessWidget {
  const TooOldRecordingHelp({super.key, required this.onDelete});

  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(context.l10n.syncTooOldExplanation, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            children: [
              OmiButton.secondary(
                key: const Key('too_old_get_help'),
                label: context.l10n.syncGetHelp,
                size: OmiButtonSize.compact,
                onPressed: () async {
                  final support = IntercomManager.instance;
                  if (support.isIntercomEnabled) {
                    await support.intercom.displayMessageComposer(context.l10n.syncTooOldExplanation);
                  } else {
                    await openSettingsDestination(context, SettingsDestination.helpCenter);
                  }
                },
              ),
              OmiButton.tertiary(
                key: const Key('too_old_delete'),
                label: context.l10n.delete,
                size: OmiButtonSize.compact,
                onPressed: onDelete,
              ),
            ],
          ),
        ],
      );
}
