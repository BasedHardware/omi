import 'package:flutter/widgets.dart';
import 'package:omi/backend/http/api/sync_job_cancel.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/ui/feedback/omi_feedback.dart';

/// Deleting a recording that is uploaded but not transcribed yet also cancels and erases its
/// server job (`LocalWalSyncImpl.deleteWal`). The confirmation says so whenever any row being
/// deleted is in that state; otherwise the caller's local-delete copy applies.
({String title, String message}) walDeleteConfirmationCopy(
  AppLocalizations l10n,
  Iterable<Wal> wals, {
  required String localTitle,
  required String localMessage,
}) {
  final onServer = wals.any((w) => w.syncDisplayState == WalSyncDisplayState.uploaded && (w.jobId ?? '').isNotEmpty);
  return onServer
      ? (title: l10n.deleteFromServerTitle, message: l10n.deleteFromServerMessage)
      : (title: localTitle, message: localMessage);
}

/// The server had already transcribed the recording: the conversation stays until the owner deletes it.
void showWalServerDeleteNotice(BuildContext context, SyncJobCancelResult? result, AppLocalizations l10n) {
  final outcome = result?.outcome;
  if (outcome != SyncJobCancelOutcome.alreadyProcessed && outcome != SyncJobCancelOutcome.notCancellable) return;
  if (context.mounted) OmiFeedback.info(context, l10n.deletedRecordingAlreadyTranscribed);
}
