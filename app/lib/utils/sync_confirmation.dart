import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/ui/molecules/omi_confirm_dialog.dart';
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
/// a no-op that always returns `true` (no dialog).
Future<bool> confirmSyncForCustomStt(BuildContext context) async {
  if (!SharedPreferencesUtil().useCustomStt) return true;

  final l = context.l10n;
  final confirmed = await OmiConfirmDialog.show(
    context,
    title: l.syncCustomSttWarningTitle,
    message: l.syncCustomSttWarningMessage,
    confirmLabel: l.sync,
    cancelLabel: l.cancel,
    confirmColor: Colors.deepPurpleAccent,
  );
  return confirmed ?? false;
}
