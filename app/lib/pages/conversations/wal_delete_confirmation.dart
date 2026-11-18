import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/services/wals/wal.dart';

/// Deleting a recording on Offline Sync removes only the phone's file and its list entry
/// (`LocalWalSyncImpl.deleteWal`); it never asks the server to stop. An uploaded file's job keeps
/// running, but if it fails or expires, job reconciliation re-uploads from the local file, which a
/// delete has removed. The uploaded copy says both halves: the server is processing, and a failure
/// can't be retried from this phone.
///
/// That copy shows only when every file is on the server (uploaded or already processed) and at
/// least one is still processing. Any file not yet uploaded, or refused by the server, means the
/// delete loses audio outright, so the row keeps [notUploadedMessage].
({String title, String message}) walDeleteConfirmation(
  AppLocalizations l10n,
  Iterable<Wal> wals, {
  required String notUploadedMessage,
}) {
  final states = wals.map((w) => w.syncDisplayState).toList();
  final processing = states.contains(WalSyncDisplayState.uploaded);
  final allOnServer = states.every((s) => s == WalSyncDisplayState.uploaded || s == WalSyncDisplayState.synced);
  if (processing && allOnServer) {
    return (title: l10n.deleteWhileProcessingTitle, message: l10n.deleteWhileProcessingMessage);
  }
  return (title: l10n.deleteRecording, message: notUploadedMessage);
}
