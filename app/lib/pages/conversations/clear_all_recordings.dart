// Offers Too old recording export before either Offline Sync Clear All action.
// Only an explicit destructive selection returns confirmation.
import 'package:flutter/material.dart';

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
  int? exportingIndex;
  await showOmiSheet<void>(
    context: context,
    title: l.downloadAudio,
    builder: (_) => StatefulBuilder(builder: (sheetContext, setSheetState) {
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
              leading: exportingIndex == index
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
              onTap: exportingIndex != null
                  ? null
                  : () async {
                      // Another tap can still reach this callback before the sheet rebuilds.
                      if (exportingIndex != null) return;
                      setSheetState(() => exportingIndex = index);
                      try {
                        await share(recording.wals);
                      } catch (error) {
                        Logger.debug('Offline Sync export failed: ${error.runtimeType}');
                        if (sheetContext.mounted) OmiFeedback.error(sheetContext, l.exportFailedTryAgain);
                      } finally {
                        if (sheetContext.mounted) setSheetState(() => exportingIndex = null);
                      }
                    },
            );
          },
        ),
      );
    }),
  );
  // Returning from the export list never invokes the destructive action.
  return false;
}
