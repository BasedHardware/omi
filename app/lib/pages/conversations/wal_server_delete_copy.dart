import 'package:flutter/widgets.dart';
import 'package:omi/backend/http/api/sync_job_cancel.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/ui/feedback/omi_feedback.dart';

void showWalServerDeleteNotice(BuildContext context, SyncJobCancelResult? result, AppLocalizations l10n) {
  final message = switch (result?.outcome) {
    SyncJobCancelOutcome.alreadyProcessed => l10n.deletedRecordingAlreadyTranscribed,
    SyncJobCancelOutcome.notCancellable => l10n.deletedRecordingWillBeProcessed,
    _ => null,
  };
  if (message != null && context.mounted) OmiFeedback.info(context, message);
}
