import 'dart:async';
import 'dart:io';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/services/account_cutover/account_cutover_runtime.dart';
import 'package:omi/services/wals/sync_rate_limit_reconciliation.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/mutex.dart';
import 'package:uuid/uuid.dart';

typedef SyncFilesUploader = Future<UploadFilesResult> Function(
  List<File> files, {
  UploadProgressCallback? onUploadProgress,
  String? conversationId,
  bool claimLiveCapture,
  Geolocation? geolocation,
});
typedef FairUseStatusLoader = Future<Map<String, dynamic>?> Function();
typedef UploadTelemetryEmitter = void Function(String eventName, Map<String, dynamic> properties);
typedef UploadAttemptIdFactory = String Function();
typedef UploadClock = DateTime Function();

/// Account-global admission gate for every `/v2/sync-local-files` upload.
///
/// Uploads are serialized so independent WAL, live-capture, and Transcribe
/// Later loops cannot race past a newly established cooldown. Persisted fair-
/// use state is reconciled through a single in-flight status request before an
/// upload is admitted.
class SyncUploadGate {
  SyncUploadGate({
    required SyncRateLimiter limiter,
    required SyncFilesUploader uploader,
    required FairUseStatusLoader fairUseStatusLoader,
    UploadTelemetryEmitter? telemetryEmitter,
    UploadAttemptIdFactory? attemptIdFactory,
    UploadClock? clock,
  })  : _limiter = limiter,
        _uploader = uploader,
        _fairUseStatusLoader = fairUseStatusLoader,
        _telemetryEmitter = telemetryEmitter,
        _attemptIdFactory = attemptIdFactory ?? _defaultAttemptId,
        _clock = clock ?? DateTime.now;

  static final SyncUploadGate instance = SyncUploadGate(
    limiter: SyncRateLimiter.instance,
    uploader: uploadLocalFilesV2,
    fairUseStatusLoader: getFairUseStatus,
    telemetryEmitter: _emitProductionTelemetry,
  );

  static const int _statusRetryCooldownSeconds = 60;

  final SyncRateLimiter _limiter;
  final SyncFilesUploader _uploader;
  final FairUseStatusLoader _fairUseStatusLoader;
  final UploadTelemetryEmitter? _telemetryEmitter;
  final UploadAttemptIdFactory _attemptIdFactory;
  final UploadClock _clock;
  final Mutex _uploadMutex = Mutex();
  Future<bool>? _reconciliation;

  static String _defaultAttemptId() => const Uuid().v4();

  static void _emitProductionTelemetry(String eventName, Map<String, dynamic> properties) {
    final analytics = AnalyticsManager();
    switch (eventName) {
      case RecordingUploadTelemetry.startedEvent:
        analytics.recordingUploadStarted(
          attemptId: properties['upload_attempt_id'] as String,
          recordingId: properties['recording_id'] as String?,
          fileCount: properties['file_count'] as int,
          totalBytes: properties['total_bytes'] as int,
          claimsLiveCapture: properties['claims_live_capture'] as bool,
        );
        return;
      case RecordingUploadTelemetry.completedEvent:
        analytics.recordingUploadCompleted(
          attemptId: properties['upload_attempt_id'] as String,
          recordingId: properties['recording_id'] as String?,
          fileCount: properties['file_count'] as int,
          totalBytes: properties['total_bytes'] as int,
          claimsLiveCapture: properties['claims_live_capture'] as bool,
          durationSeconds: properties['duration_seconds'] as double,
          result: properties['result'] as String,
        );
        return;
      case RecordingUploadTelemetry.failedEvent:
        analytics.recordingUploadFailed(
          attemptId: properties['upload_attempt_id'] as String,
          recordingId: properties['recording_id'] as String?,
          fileCount: properties['file_count'] as int,
          totalBytes: properties['total_bytes'] as int,
          claimsLiveCapture: properties['claims_live_capture'] as bool,
          durationSeconds: properties['duration_seconds'] as double,
          failureClass: properties['failure_class'] as String,
        );
        return;
    }
  }

  /// Reconciles a previously confirmed fair-use restriction with the server.
  /// Returns whether uploads are currently allowed after all cooldowns.
  Future<bool> prepareToUpload() async {
    if (_limiter.hasPersistedFairUseState) {
      await reconcileFairUseStatus();
    }
    return !_limiter.isLimited;
  }

  /// Single-flight authoritative fair-use reconciliation.
  Future<bool> reconcileFairUseStatus() {
    if (!_limiter.hasPersistedFairUseState) {
      return Future.value(!_limiter.isLimited);
    }
    final active = _reconciliation;
    if (active != null) return active;

    final future = _reconcileFairUseStatus();
    _reconciliation = future;
    return future.whenComplete(() {
      if (identical(_reconciliation, future)) _reconciliation = null;
    });
  }

  Future<bool> _reconcileFairUseStatus() async {
    Map<String, dynamic>? status;
    try {
      status = await _fairUseStatusLoader();
    } catch (_) {
      status = null;
    }

    if (shouldClearSyncRateLimitForFairUseStatus(status)) {
      _limiter.clearRateLimit();
    } else if (!_limiter.isFairUseLimited) {
      // A hard restriction or failed status fetch remains authoritative. Retry
      // reconciliation soon without hitting upload after the local deadline.
      _limiter.markLimited(retryAfterSeconds: _statusRetryCooldownSeconds, reason: RateLimitReason.fairUse);
    }
    return !_limiter.isLimited;
  }

  Future<UploadFilesResult> upload(
    List<File> files, {
    UploadProgressCallback? onUploadProgress,
    String? conversationId,
    bool claimLiveCapture = false,
    Geolocation? geolocation,
  }) async {
    await _uploadMutex.acquire();
    try {
      if (!AccountCutoverRuntime.instance.allowsOfflineQueueUpload) {
        throw const SyncOfflineQueueQuarantinedException();
      }
      // Honor an active Retry-After without immediately probing fair-use
      // status. Lifecycle/manual entry points may reconcile active state, but
      // queued parallel uploads must stop at the established cooldown.
      var allowed = !_limiter.isLimited;
      if (allowed && _limiter.hasPersistedFairUseState) {
        allowed = await reconcileFairUseStatus();
      }
      if (!allowed) {
        throw SyncRateLimitedException(
          kind: _limiter.reason == RateLimitReason.backendBusy
              ? SyncRateLimitKind.backendCapacity
              : SyncRateLimitKind.fairUse,
          retryAfterSeconds: _limiter.activeRetryAfterSeconds,
        );
      }

      final attemptId = _attemptIdFactory();
      final startedAt = _clock();
      final totalBytes = await RecordingUploadTelemetry.totalBytes(files);
      _emitTelemetry(
        RecordingUploadTelemetry.startedEvent,
        RecordingUploadTelemetry.startedPayload(
          attemptId: attemptId,
          recordingId: conversationId,
          fileCount: files.length,
          totalBytes: totalBytes,
          claimsLiveCapture: claimLiveCapture,
        ),
      );

      try {
        final result = await _uploader(
          files,
          onUploadProgress: onUploadProgress,
          conversationId: conversationId,
          claimLiveCapture: claimLiveCapture,
          geolocation: geolocation,
        );
        _limiter.clear();
        _emitTelemetry(
          RecordingUploadTelemetry.completedEvent,
          RecordingUploadTelemetry.completedPayload(
            attemptId: attemptId,
            recordingId: conversationId,
            fileCount: files.length,
            totalBytes: totalBytes,
            claimsLiveCapture: claimLiveCapture,
            durationSeconds: _durationSeconds(startedAt),
            result: result.isQueued ? 'accepted' : 'completed',
          ),
        );
        return result;
      } on SyncRateLimitedException catch (error) {
        _limiter.markLimited(
          retryAfterSeconds: error.retryAfterSeconds,
          reason: error.kind == SyncRateLimitKind.fairUse ? RateLimitReason.fairUse : RateLimitReason.backendBusy,
        );
        _recordUploadFailure(
          error,
          attemptId: attemptId,
          recordingId: conversationId,
          fileCount: files.length,
          totalBytes: totalBytes,
          claimsLiveCapture: claimLiveCapture,
          startedAt: startedAt,
        );
        rethrow;
      } catch (error) {
        _recordUploadFailure(
          error,
          attemptId: attemptId,
          recordingId: conversationId,
          fileCount: files.length,
          totalBytes: totalBytes,
          claimsLiveCapture: claimLiveCapture,
          startedAt: startedAt,
        );
        rethrow;
      }
    } finally {
      _uploadMutex.release();
    }
  }

  double _durationSeconds(DateTime startedAt) {
    final milliseconds = _clock().difference(startedAt).inMilliseconds;
    return (milliseconds < 0 ? 0 : milliseconds) / 1000.0;
  }

  void _recordUploadFailure(
    Object error, {
    required String attemptId,
    required String? recordingId,
    required int fileCount,
    required int totalBytes,
    required bool claimsLiveCapture,
    required DateTime startedAt,
  }) {
    _emitTelemetry(
      RecordingUploadTelemetry.failedEvent,
      RecordingUploadTelemetry.failedPayload(
        attemptId: attemptId,
        recordingId: recordingId,
        fileCount: fileCount,
        totalBytes: totalBytes,
        claimsLiveCapture: claimsLiveCapture,
        durationSeconds: _durationSeconds(startedAt),
        failureClass: RecordingUploadTelemetry.failureClass(error),
      ),
    );
  }

  void _emitTelemetry(String eventName, Map<String, dynamic> properties) {
    try {
      _telemetryEmitter?.call(eventName, properties);
    } catch (_) {
      // Analytics must never change upload success, failure, or retry behavior.
    }
  }
}

class RecordingUploadTelemetry {
  static const String startedEvent = 'Recording Upload Started';
  static const String completedEvent = 'Recording Upload Completed';
  static const String failedEvent = 'Recording Upload Failed';

  static Future<int> totalBytes(List<File> files) async {
    var bytes = 0;
    for (final file in files) {
      try {
        bytes += await file.length();
      } catch (_) {
        // A missing/unreadable file will be classified by the authoritative
        // uploader. Telemetry remains best-effort and content-free.
      }
    }
    return bytes;
  }

  static Map<String, dynamic> startedPayload({
    required String attemptId,
    required String? recordingId,
    required int fileCount,
    required int totalBytes,
    required bool claimsLiveCapture,
  }) =>
      _basePayload(
        attemptId: attemptId,
        recordingId: recordingId,
        fileCount: fileCount,
        totalBytes: totalBytes,
        claimsLiveCapture: claimsLiveCapture,
      );

  static Map<String, dynamic> completedPayload({
    required String attemptId,
    required String? recordingId,
    required int fileCount,
    required int totalBytes,
    required bool claimsLiveCapture,
    required double durationSeconds,
    required String result,
  }) =>
      {
        ..._basePayload(
          attemptId: attemptId,
          recordingId: recordingId,
          fileCount: fileCount,
          totalBytes: totalBytes,
          claimsLiveCapture: claimsLiveCapture,
        ),
        'duration_seconds': durationSeconds < 0 ? 0.0 : durationSeconds,
        'result': result == 'completed' ? 'completed' : 'accepted',
      };

  static Map<String, dynamic> failedPayload({
    required String attemptId,
    required String? recordingId,
    required int fileCount,
    required int totalBytes,
    required bool claimsLiveCapture,
    required double durationSeconds,
    required String failureClass,
  }) =>
      {
        ..._basePayload(
          attemptId: attemptId,
          recordingId: recordingId,
          fileCount: fileCount,
          totalBytes: totalBytes,
          claimsLiveCapture: claimsLiveCapture,
        ),
        'duration_seconds': durationSeconds < 0 ? 0.0 : durationSeconds,
        'failure_class': _failureClasses.contains(failureClass) ? failureClass : 'unknown',
      };

  static const Set<String> _failureClasses = {
    'rate_limited',
    'timeout',
    'network',
    'authentication',
    'server',
    'unknown',
  };

  static String failureClass(Object error) {
    if (error is SyncRateLimitedException) return 'rate_limited';
    if (error is TimeoutException) return 'timeout';
    if (error is SocketException) return 'network';
    if (error is SyncUploadHttpException) {
      if (error.statusCode == 401 || error.statusCode == 403) return 'authentication';
      if (error.statusCode >= 500) return 'server';
    }
    final normalized = error.toString().toLowerCase();
    if (normalized.contains('401') || normalized.contains('403') || normalized.contains('unauthorized')) {
      return 'authentication';
    }
    if (normalized.contains('500') ||
        normalized.contains('502') ||
        normalized.contains('503') ||
        normalized.contains('504')) {
      return 'server';
    }
    return 'unknown';
  }

  static Map<String, dynamic> _basePayload({
    required String attemptId,
    required String? recordingId,
    required int fileCount,
    required int totalBytes,
    required bool claimsLiveCapture,
  }) =>
      {
        'upload_attempt_id': attemptId,
        if (recordingId != null && recordingId.isNotEmpty) 'recording_id': recordingId,
        'file_count': fileCount < 0 ? 0 : fileCount,
        'total_bytes': totalBytes < 0 ? 0 : totalBytes,
        'claims_live_capture': claimsLiveCapture,
        'upload_source': 'offline_audio_queue',
      };
}

/// Raised when the server cutover control quarantines legacy offline uploads.
class SyncOfflineQueueQuarantinedException implements Exception {
  const SyncOfflineQueueQuarantinedException();

  @override
  String toString() => 'SyncOfflineQueueQuarantinedException';
}
