import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/debug_log_manager.dart';

/// Server answer to deleting an uploaded recording's job
/// (`DELETE /v2/sync-local-files/{job_id}`).
///
/// - [cancelled]: fenced and every server copy erased.
/// - [erasurePending]: fenced (it will never be transcribed); erasure finishes on a later call.
/// - [alreadyProcessed]: a transcript exists; nothing was deleted. The owner deletes the conversation.
/// - [notFound]: nothing on the server for this account and handle.
/// - [notCancellable]: this upload will be processed (coalesced or live handoff).
/// - [paused]: the server's owner-cancel kill switch is off; retried once it is back on.
/// - [retryLater]: offline, throttled, being processed right now or a server error.
enum SyncJobCancelOutcome { cancelled, erasurePending, alreadyProcessed, notFound, notCancellable, paused, retryLater }

class SyncJobCancelResult {
  final SyncJobCancelOutcome outcome;
  final List<String> conversationIds;

  const SyncJobCancelResult(this.outcome, {this.conversationIds = const []});

  /// The server will never transcribe the recording.
  bool get fenced => outcome == SyncJobCancelOutcome.cancelled || outcome == SyncJobCancelOutcome.erasurePending;

  /// Nothing more to ask the server; the tombstone can go.
  bool get settled =>
      outcome != SyncJobCancelOutcome.retryLater &&
      outcome != SyncJobCancelOutcome.paused &&
      outcome != SyncJobCancelOutcome.erasurePending;

  /// The cancel endpoint itself answered (not an outage); its kill switch is on unless [paused].
  bool get serverAnswered => outcome != SyncJobCancelOutcome.retryLater;
}

/// Success body of the cancel endpoint. Throws [FormatException] for any shape this phone does not
/// understand, which [executeApi] reports as a decode failure and the tombstone retries.
SyncJobCancelResult decodeSyncJobCancel(String body) {
  final json = jsonDecode(body);
  if (json is! Map<String, dynamic>) throw const FormatException('sync job cancel: not an object');
  final ids = json['conversation_ids'];
  return switch (json['outcome']) {
    'cancelled' => SyncJobCancelResult(
        json['erasure'] == 'complete' ? SyncJobCancelOutcome.cancelled : SyncJobCancelOutcome.erasurePending,
      ),
    'already_processed' => SyncJobCancelResult(
        SyncJobCancelOutcome.alreadyProcessed,
        conversationIds: ids is List ? ids.whereType<String>().toList() : const <String>[],
      ),
    'not_found' => const SyncJobCancelResult(SyncJobCancelOutcome.notFound),
    _ => throw const FormatException('sync job cancel: unknown outcome'),
  };
}

/// Every [ApiResult] maps to one phone action. Only an explicit server answer settles a tombstone;
/// an unreadable success, an outage or a 409 `sync_job_processing` keeps it for a later pass.
SyncJobCancelResult syncJobCancelResultFrom(ApiResult<SyncJobCancelResult> result) => switch (result) {
      ApiSuccess(:final data) => data,
      ApiFailure(:final problem) => switch (problem.kind) {
          ApiProblemKind.notFound ||
          ApiProblemKind.forbidden =>
            const SyncJobCancelResult(SyncJobCancelOutcome.notFound),
          ApiProblemKind.rejected when problem.statusCode == 409 && problem.detail == 'sync_job_not_cancellable' =>
            const SyncJobCancelResult(SyncJobCancelOutcome.notCancellable),
          ApiProblemKind.server when problem.statusCode == 503 && problem.detail == 'sync_job_cancel_disabled' =>
            const SyncJobCancelResult(SyncJobCancelOutcome.paused),
          ApiProblemKind.transport ||
          ApiProblemKind.authTerminal ||
          ApiProblemKind.authTransient ||
          ApiProblemKind.paymentRequired ||
          ApiProblemKind.unprocessable ||
          ApiProblemKind.rateLimited ||
          ApiProblemKind.server ||
          ApiProblemKind.decode ||
          ApiProblemKind.rejected =>
            const SyncJobCancelResult(SyncJobCancelOutcome.retryLater),
        },
    };

/// One attempt; the caller's durable tombstone owns retries. [send] is a test seam.
Future<SyncJobCancelResult> cancelSyncJob(String jobId, {ApiSend? send}) async {
  final api = await executeApi(
    request: ApiRequest(
      url: '${Env.apiBaseUrl}v2/sync-local-files/${Uri.encodeComponent(jobId)}',
      method: 'DELETE',
    ),
    decode: decodeSyncJobCancel,
    send: send,
  );
  final result = syncJobCancelResultFrom(api);
  DebugLogManager.logEvent('sync_job_cancel', {
    'jobId': jobId,
    'httpStatus': switch (api) {
      ApiSuccess() => 200,
      ApiFailure(:final problem) => problem.statusCode ?? problem.kind.name,
    },
    'outcome': result.outcome.name,
  });
  return result;
}
