// Offers Too old recording export before either Offline Sync Clear All action.
// Only an explicit destructive selection returns confirmation.
import 'package:flutter/material.dart';

import 'package:omi/models/clear_all_recording_export.dart';
import 'package:omi/pages/conversations/recording_blocks.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';

enum _ClearAllAction { download, delete }

/// The same export offer protects Clear all in both Offline Sync screens.
Future<bool> confirmClearAllRecordings(
  BuildContext context, {
  required List<Wal> tooOld,
  required Future<void> Function(List<Wal>) share,
  required ClearAllRecordingExport recordingExport,
}) async {
  final l = context.l10n;
  if (tooOld.isEmpty) {
    return showOmiConfirm(
      context,
      title: l.deleteAllFiles,
      message: l.deleteAllFilesWarning,
      confirmLabel: l.clearAll,
      destructive: true,
    );
  }

  final action = await showDialog<_ClearAllAction>(
    context: context,
    builder: (dialogContext) => OmiAlertDialog(
      title: l.deleteAllFiles,
      message: l.deleteAllFilesWarning,
      content: Text(l.syncTooOldExplanation),
      actions: [
        OmiDialogAction(label: l.cancel, isDefault: true, onPressed: () => Navigator.of(dialogContext).pop()),
        OmiDialogAction(
          label: l.downloadAudio,
          onPressed: () => Navigator.of(dialogContext).pop(_ClearAllAction.download),
        ),
        OmiDialogAction(
          label: l.clearAll,
          isDestructive: true,
          onPressed: () => Navigator.of(dialogContext).pop(_ClearAllAction.delete),
        ),
      ],
    ),
  );
  if (action != _ClearAllAction.download || !context.mounted) return action == _ClearAllAction.delete;

  final sorted = [...tooOld]..sort((a, b) => b.timerStart.compareTo(a.timerStart));
  final recordings = groupRecordingBlocks(sorted);
  await showOmiSheet<void>(
    context: context,
    title: l.downloadAudio,
    builder: (_) => ValueListenableBuilder(
      valueListenable: recordingExport,
      builder: (sheetContext, exportingWalIds, _) {
        final rowHeight = 60.0 + MediaQuery.textScalerOf(sheetContext).scale(24);
        final maxHeight = MediaQuery.sizeOf(sheetContext).height * 0.55;
        return SizedBox(
          height: (recordings.length * rowHeight).clamp(0.0, maxHeight).toDouble(),
          child: ListView.builder(
            itemCount: recordings.length,
            itemBuilder: (_, index) {
              final recording = recordings[index];
              final date = DateTime.fromMillisecondsSinceEpoch(recording.startSeconds * 1000);
              return OmiSettingsRow(
                leading: exportingWalIds != null && recording.wals.any((wal) => exportingWalIds.contains(wal.id))
                    ? Semantics(
                        label: l.preparingAudio,
                        liveRegion: true,
                        child: const SizedBox.square(
                          dimension: 20,
                          child: Center(child: OmiSpinner(size: OmiSpinnerSize.small)),
                        ),
                      )
                    : const Icon(Icons.ios_share_rounded),
                title: OmiDateFormat.of(sheetContext).dateTime(date),
                subtitle: OmiDuration.compact(recording.seconds, l),
                showChevron: false,
                onTap: exportingWalIds != null
                    ? null
                    : () async {
                        try {
                          await recordingExport.run(recording.wals, share);
                        } catch (error) {
                          Logger.debug('Offline Sync export failed: ${error.runtimeType}');
                          final feedbackContext = sheetContext.mounted ? sheetContext : context;
                          if (feedbackContext.mounted) OmiFeedback.error(feedbackContext, l.exportFailedTryAgain);
                        }
                      },
              );
            },
          ),
        );
      },
    ),
  );
  // Returning from the export list never invokes the destructive action.
  return false;
}
