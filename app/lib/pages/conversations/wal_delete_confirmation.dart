import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/services/wals/server_cancel_pause.dart';
import 'package:omi/services/wals/wal.dart';

/// Which confirmation a delete on Offline Sync gets.
///
/// Deleting an uploaded recording that the server has not transcribed also cancels and erases its
/// server job (`LocalWalSyncImpl.deleteWal`, `DELETE /v2/sync-local-files/{job_id}`), so that
/// confirmation says the server copy goes too ([AppLocalizations.deleteFromServerMessage]).
///
/// While the server's owner-cancel kill switch is off ([ServerCancelPause]), the delete still
/// records its cancel for later, but the server keeps processing for now; the row then gets the
/// phone-copy wording ([AppLocalizations.deleteWhileProcessingMessage]).
///
/// Either uploaded copy shows only when every file is on the server (uploaded or already processed)
/// and at least one is still processing. Any file not yet uploaded, or refused by the server, means
/// the delete loses audio outright, so the row keeps [notUploadedMessage].
({String title, String message}) walDeleteConfirmation(
  AppLocalizations l10n,
  Iterable<Wal> wals, {
  required String notUploadedMessage,
  bool? serverCancelPaused,
}) {
  final states = wals.map((w) => w.syncDisplayState).toList();
  final processing = states.contains(WalSyncDisplayState.uploaded);
  final allOnServer = states.every((s) => s == WalSyncDisplayState.uploaded || s == WalSyncDisplayState.synced);
  if (processing && allOnServer) {
    final cancels = wals.any((w) => w.syncDisplayState == WalSyncDisplayState.uploaded && (w.jobId ?? '').isNotEmpty);
    if (cancels && !(serverCancelPaused ?? ServerCancelPause.instance.paused)) {
      return (title: l10n.deleteFromServerTitle, message: l10n.deleteFromServerMessage);
    }
    return (title: l10n.deleteWhileProcessingTitle, message: l10n.deleteWhileProcessingMessage);
  }
  return (title: l10n.deleteRecording, message: notUploadedMessage);
}
