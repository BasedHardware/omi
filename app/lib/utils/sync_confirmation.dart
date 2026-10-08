import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/ui/feedback/omi_dialogs.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Confirmation gate for manually syncing offline recordings.
///
/// Users on a third-party (custom) STT provider transcribe live on their own
/// provider, so their recordings normally never touch Omi's STT. Offline files,
/// however, can only be processed on Omi's servers — which means they DO use
/// Omi transcription and count toward the plan limit. Auto-sync is disabled for
/// these users (see capture/sync providers); when they manually press Sync we
/// surface this trade-off and let them opt in per their choice.
///
/// Returns `true` when the sync should proceed. For non-custom-STT users this is
/// a no-op that always returns `true` (no dialog). [showOmiConfirm] presents the
/// native system alert when the SwiftUI presentation is active and the adaptive
/// Flutter dialog otherwise.
Future<bool> confirmSyncForCustomStt(BuildContext context) async {
  if (!SharedPreferencesUtil().useCustomStt) return true;

  final l = context.l10n;
  return showOmiConfirm(
    context,
    title: l.syncCustomSttWarningTitle,
    message: l.syncCustomSttWarningMessage,
    confirmLabel: l.sync,
    cancelLabel: l.cancel,
  );
}

/// Asks before processing [sdCardCount] SD card recordings; `true` means process them.
Future<bool> confirmSdCardProcessing(BuildContext context, int sdCardCount) {
  final l = context.l10n;
  return showOmiConfirm(
    context,
    title: l.sdCardProcessing,
    message: l.sdCardProcessingMessage(sdCardCount),
    confirmLabel: l.process,
  );
}
