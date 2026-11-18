import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/services/wals/wal.dart';

/// Deleting a recording on Offline Sync removes only the phone's file and its list entry
/// (`LocalWalSyncImpl.deleteWal`); it never asks the server to stop. Audio the server already
/// holds keeps processing, so a delete there must not read as "this loses it if processing fails".
///
/// The phone-copy message shows only when every file is already on the server and at least one
/// is still being processed. If any file has not been uploaded, deleting really loses that audio,
/// so the row keeps [notUploadedMessage].
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
