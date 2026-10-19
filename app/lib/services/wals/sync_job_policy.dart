import 'package:omi/backend/schema/conversation.dart';

const _kBackendBusyErrorHint = 'background worker likely died';

enum SyncJobTerminalPolicy { wait, acknowledge, retry }

/// The shared WAL acknowledgement boundary for async sync jobs.
///
/// Only the backend's truthful `completed` state permits local audio to become
/// terminally synced. Partial and full failures deliberately take the retry
/// path so the retained WAL remains recoverable.
SyncJobTerminalPolicy syncJobTerminalPolicy({required String status, required bool isTerminal}) {
  if (!isTerminal) return SyncJobTerminalPolicy.wait;
  return status == 'completed' ? SyncJobTerminalPolicy.acknowledge : SyncJobTerminalPolicy.retry;
}

/// Terminal `reason_code`s the backend only reaches because of the uploaded
/// audio itself. `sync_invalid_audio` is raised by `decode_files_to_wav` once
/// *nothing* in the batch decoded, and `stt_invalid_input` is the provider
/// refusing the decoded audio as invalid — re-sending identical bytes produces
/// the identical verdict. Keep in sync with `_SYNC_FAILURE_REASON_CODES` in
/// backend/utils/sync/pipeline.py.
const _kPermanentInputFailureReasonCodes = {'sync_invalid_audio', 'stt_invalid_input'};

/// Whether a terminal job failed for a reason no re-upload can change.
///
/// Only a whole-job `failed` qualifies: `partial_failure` proves some segments
/// landed, so the batch is not shown to be bad. A permanent verdict therefore
/// never strands a good sibling — the decoder drops unreadable files
/// individually and only fails the job when the batch has nothing left.
bool syncJobFailureIsPermanent(SyncJobStatusResponse status) =>
    status.status == 'failed' && _kPermanentInputFailureReasonCodes.contains(status.reasonCode);

bool syncJobIsBackendBusy(SyncJobStatusResponse status) {
  if ((status.error ?? '').contains(_kBackendBusyErrorHint)) return true;
  // Legacy stale-worker failures predate reason_code. New typed failures with
  // totalSegments=0 carry a reason and must consume retry budget normally.
  final reasonCode = status.reasonCode;
  return status.status == 'failed' && status.totalSegments == 0 && (reasonCode == null || reasonCode.isEmpty);
}
