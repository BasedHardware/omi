import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
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
/// - [retryLater]: offline, throttled, being processed right now, paused or a server error.
enum SyncJobCancelOutcome { cancelled, erasurePending, alreadyProcessed, notFound, notCancellable, retryLater }

class SyncJobCancelResult {
  final SyncJobCancelOutcome outcome;
  final List<String> conversationIds;

  const SyncJobCancelResult(this.outcome, {this.conversationIds = const []});

  /// The server will never transcribe the recording.
  bool get fenced => outcome == SyncJobCancelOutcome.cancelled || outcome == SyncJobCancelOutcome.erasurePending;

  /// Nothing more to ask the server; the tombstone can go.
  bool get settled => outcome != SyncJobCancelOutcome.retryLater && outcome != SyncJobCancelOutcome.erasurePending;
}

SyncJobCancelResult syncJobCancelResultFor(int? statusCode, String body) {
  if (statusCode == 409) {
    final code = _code(body);
    return SyncJobCancelResult(
      code == 'sync_job_not_cancellable' ? SyncJobCancelOutcome.notCancellable : SyncJobCancelOutcome.retryLater,
    );
  }
  if (statusCode == 404 || statusCode == 403) return const SyncJobCancelResult(SyncJobCancelOutcome.notFound);
  if (statusCode != 200) return const SyncJobCancelResult(SyncJobCancelOutcome.retryLater);
  try {
    final json = jsonDecode(body) as Map<String, dynamic>;
    final ids = (json['conversation_ids'] as List?)?.whereType<String>().toList() ?? const <String>[];
    switch (json['outcome']) {
      case 'cancelled':
        return SyncJobCancelResult(
          json['erasure'] == 'complete' ? SyncJobCancelOutcome.cancelled : SyncJobCancelOutcome.erasurePending,
        );
      case 'already_processed':
        return SyncJobCancelResult(SyncJobCancelOutcome.alreadyProcessed, conversationIds: ids);
      case 'not_found':
        return const SyncJobCancelResult(SyncJobCancelOutcome.notFound);
    }
  } catch (_) {
    // An unreadable success is retried; never treated as erased.
  }
  return const SyncJobCancelResult(SyncJobCancelOutcome.retryLater);
}

String? _code(String body) {
  try {
    final value = (jsonDecode(body) as Map<String, dynamic>)['code'];
    return value is String ? value : null;
  } catch (_) {
    return null;
  }
}

/// One bounded attempt; the caller's durable tombstone owns retries.
Future<SyncJobCancelResult> cancelSyncJob(String jobId) async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v2/sync-local-files/${Uri.encodeComponent(jobId)}',
    headers: {},
    method: 'DELETE',
    body: '',
    timeout: const Duration(seconds: 10),
    retries: 0,
  );
  final result = syncJobCancelResultFor(response?.statusCode, response?.body ?? '');
  DebugLogManager.logEvent('sync_job_cancel', {
    'jobId': jobId,
    'httpStatus': response?.statusCode,
    'outcome': result.outcome.name,
  });
  return result;
}
