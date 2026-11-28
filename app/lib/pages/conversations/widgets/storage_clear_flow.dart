import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/storage_clear.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';

/// Confirm, run and report one Manage Storage clear.
///
/// The confirm names the hours being removed. While the clear runs, a progress
/// sheet nothing can dismiss shows what it is doing (stopping sync, deleting
/// N of M, checking), and the result toast reports what the stores hold
/// afterwards, never an assumed success.
Future<void> runStorageClear({
  required BuildContext context,
  required SyncProvider provider,
  required StorageClearScope scope,
  required StorageAmounts amounts,
  String? firmwareVersion,
  Future<void> Function()? afterClear,
}) async {
  final l = context.l10n;
  String dur(int seconds) => OmiDuration.compact(seconds, l);
  final (title, message, confirmLabel) = switch (scope) {
    StorageClearScope.uploaded => (
        l.storageFreeUpTitle(dur(amounts.uploadedSeconds)),
        l.storageFreeUpMessage,
        l.storageFreeUpSpace,
      ),
    StorageClearScope.notUploaded => (
        l.storageDeletePendingTitle(dur(amounts.pendingSeconds)),
        l.storageDeletePendingMessage,
        l.delete,
      ),
    StorageClearScope.all => (
        l.storageDeleteAllTitle(dur(amounts.allSeconds)),
        amounts.unuploadedCount > 0
            ? l.storageDeleteAllMessage(dur(amounts.unuploadedSeconds))
            : l.storageDeleteAllUploadedMessage,
        l.storageDeleteEverything,
      ),
  };
  final confirmed = await showOmiConfirm(
    context,
    title: title,
    message: message,
    confirmLabel: confirmLabel,
    destructive: true,
  );
  if (!confirmed || !context.mounted) return;

  final progress = ValueNotifier(StorageClearProgress(
      scope == StorageClearScope.uploaded ? StorageClearPhase.deleting : StorageClearPhase.stopping));
  BuildContext? sheetContext;
  final sheet = showOmiSheet<void>(
    context: context,
    isDismissible: false,
    enableDrag: false,
    showCloseButton: false,
    builder: (ctx) {
      sheetContext = ctx;
      return PopScope(canPop: false, child: StorageClearProgressView(progress: progress));
    },
  );
  StorageClearOutcome? outcome;
  try {
    outcome = await provider.clearStorage(
      scope,
      firmwareVersion: firmwareVersion,
      // Thousands of files report one step each; repaint per percent.
      onProgress: (value) {
        final last = progress.value;
        int percent(StorageClearProgress p) => p.total > 0 ? p.done * 100 ~/ p.total : -1;
        if (value.phase != last.phase || value.total != last.total || percent(value) != percent(last)) {
          progress.value = value;
        }
      },
    );
    // Best effort: a failed storage-card re-read must not hide the clear's own
    // result toast below, so it is logged rather than surfaced.
    await afterClear?.call().then<void>((_) {}, onError: (Object e) {
      Logger.debug('Storage clear: refresh after clear failed: ${e.runtimeType}');
    });
  } finally {
    // The clear can finish before the sheet's first frame; pop it with its
    // own context once it exists. The clear is already done here.
    for (var i = 0; sheetContext == null && i < 10; i++) {
      await WidgetsBinding.instance.endOfFrame;
    }
    final own = sheetContext;
    if (own != null && own.mounted) Navigator.of(own).pop(); // omi-ux-allow: pop-before-await -- done
    await sheet;
    progress.dispose();
  }
  if (!context.mounted) return;
  showStorageClearOutcome(context, outcome);
}

/// The result toast for a clear, from the verified outcome.
void showStorageClearOutcome(BuildContext context, StorageClearOutcome outcome) {
  final l = context.l10n;
  String dur(int seconds) => OmiDuration.compact(seconds, l);
  if (outcome.targetCount == 0) {
    if (outcome.failed) OmiFeedback.error(context, l.storageClearFailed);
    return;
  }
  if (outcome.remainingCount == 0) {
    OmiFeedback.confirm(context, l.storageClearDone(dur(outcome.targetSeconds)));
  } else if (outcome.failed && outcome.deletedSeconds == 0) {
    // Sync would not stop, or a store refused: nothing was tried on the Omi,
    // so asking the user to reconnect it would send them the wrong way.
    OmiFeedback.error(context, l.storageClearFailed);
  } else if (!outcome.failed &&
      outcome.remainingOnDeviceSeconds > 0 &&
      outcome.remainingOnDeviceSeconds >= outcome.remainingSeconds) {
    OmiFeedback.error(context, l.storageClearOmiUnreachable(dur(outcome.remainingOnDeviceSeconds)));
  } else if (outcome.deletedSeconds > 0) {
    OmiFeedback.error(context, l.storageClearPartial(dur(outcome.deletedSeconds), dur(outcome.remainingSeconds)));
  } else {
    OmiFeedback.error(context, l.storageClearFailed);
  }
}

class StorageClearProgressView extends StatelessWidget {
  const StorageClearProgressView({super.key, required this.progress});

  final ValueListenable<StorageClearProgress> progress;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final count = NumberFormat.decimalPattern(Localizations.localeOf(context).toString());
    return ValueListenableBuilder<StorageClearProgress>(
      valueListenable: progress,
      builder: (context, value, _) {
        final label = switch (value.phase) {
          StorageClearPhase.stopping => l.storageClearStopping,
          StorageClearPhase.deleting => value.total > 0
              ? l.storageClearDeleting('${count.format(value.done)} / ${count.format(value.total)}')
              : l.storageClearStopping,
          StorageClearPhase.verifying => l.storageClearVerifying,
        };
        return Padding(
          padding: const EdgeInsets.symmetric(vertical: OmiSpacing.xl),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              OmiSpinner(size: OmiSpinnerSize.large, label: label),
              if (value.phase == StorageClearPhase.deleting && value.total > 0) ...[
                const SizedBox(height: OmiSpacing.md),
                ClipRRect(
                  borderRadius: OmiRadius.smAll,
                  child: LinearProgressIndicator(
                    value: value.done / value.total,
                    minHeight: 6,
                    backgroundColor: OmiColors.surface3,
                    valueColor: AlwaysStoppedAnimation<Color>(OmiColors.accent),
                  ),
                ),
              ],
            ],
          ),
        );
      },
    );
  }
}
