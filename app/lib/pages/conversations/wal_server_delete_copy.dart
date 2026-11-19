import 'package:flutter/widgets.dart';
import 'package:omi/backend/http/api/sync_job_cancel.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/ui/feedback/omi_feedback.dart';

/// The server had already transcribed the recording: the conversation stays until the owner deletes it.
void showWalServerDeleteNotice(BuildContext context, SyncJobCancelResult? result, AppLocalizations l10n) {
  final outcome = result?.outcome;
  if (outcome != SyncJobCancelOutcome.alreadyProcessed && outcome != SyncJobCancelOutcome.notCancellable) return;
  if (context.mounted) OmiFeedback.info(context, l10n.deletedRecordingAlreadyTranscribed);
}
