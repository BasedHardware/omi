import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/services/wals/server_cancel_pause.dart';
import 'package:omi/services/wals/wal.dart';

/// Which confirmation a delete on Offline Sync gets.
///
/// Deleting an uploaded recording that the server has not transcribed also cancels and erases its
/// server job (`LocalWalSyncImpl.deleteWal`, `cancelSyncJob`), so that
/// confirmation says the server copy goes too ([AppLocalizations.deleteFromServerMessage]).
///
/// While the server's owner-cancel kill switch is off ([ServerCancelPause]), the delete still
/// records its cancel for later, but the server keeps processing for now; the row then gets the
/// phone-copy wording ([AppLocalizations.deleteWhileProcessingMessage]).
///
/// If any file is only on this device, preserve its loss warning. For a fully uploaded
/// selection, promise server erasure only when every member has a job handle.
({String title, String message}) walDeleteConfirmation(
  AppLocalizations l10n,
  Iterable<Wal> wals, {
  required String notUploadedMessage,
  bool? serverCancelPaused,
}) {
  final selected = wals.toList();
  final states = selected.map((w) => w.syncDisplayState).toList();
  final allOnServer = states.every((s) => s == WalSyncDisplayState.uploaded || s == WalSyncDisplayState.synced);
  if (states.contains(WalSyncDisplayState.synced)) {
    final keepsConversation = l10n.deleteRecordingKeepsConversation;
    return (
      title: l10n.deleteRecording,
      message: allOnServer ? keepsConversation : '$notUploadedMessage\n\n$keepsConversation',
    );
  }
  if (selected.isEmpty || !allOnServer) {
    return (title: l10n.deleteRecording, message: notUploadedMessage);
  }
  if (selected.every((w) => (w.jobId ?? '').isNotEmpty) && !(serverCancelPaused ?? ServerCancelPause.instance.paused)) {
    return (title: l10n.deleteFromServerTitle, message: l10n.deleteFromServerMessage);
  }
  return (title: l10n.deleteWhileProcessingTitle, message: l10n.deleteWhileProcessingMessage);
}
