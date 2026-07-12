import 'dart:async';
import 'dart:io';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/services/wals/sync_rate_limit_reconciliation.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/utils/mutex.dart';

typedef SyncFilesUploader = Future<UploadFilesResult> Function(
  List<File> files, {
  UploadProgressCallback? onUploadProgress,
  String? conversationId,
  SyncUploadLane syncLane,
});
typedef FairUseStatusLoader = Future<Map<String, dynamic>?> Function();

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
  })  : _limiter = limiter,
        _uploader = uploader,
        _fairUseStatusLoader = fairUseStatusLoader;

  static final SyncUploadGate instance = SyncUploadGate(
    limiter: SyncRateLimiter.instance,
    uploader: uploadLocalFilesV2,
    fairUseStatusLoader: getFairUseStatus,
  );

  static const int _statusRetryCooldownSeconds = 60;

  final SyncRateLimiter _limiter;
  final SyncFilesUploader _uploader;
  final FairUseStatusLoader _fairUseStatusLoader;
  final Mutex _uploadMutex = Mutex();
  Future<bool>? _reconciliation;

  /// Reconciles a previously confirmed fair-use restriction with the server.
  /// Returns whether uploads are currently allowed after all cooldowns.
  Future<bool> prepareToUpload({SyncUploadLane lane = SyncUploadLane.fresh}) async {
    if (lane == SyncUploadLane.fresh && _limiter.hasPersistedFairUseState) {
      await reconcileFairUseStatus();
    }
    return !_limiter.isLimitedForLane(lane.name);
  }

  /// Single-flight authoritative fair-use reconciliation.
  Future<bool> reconcileFairUseStatus() {
    if (!_limiter.hasPersistedFairUseState) {
      return Future.value(!_limiter.isLimitedForLane(SyncUploadLane.fresh.name));
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
    return !_limiter.isLimitedForLane(SyncUploadLane.fresh.name);
  }

  Future<UploadFilesResult> upload(
    List<File> files, {
    UploadProgressCallback? onUploadProgress,
    String? conversationId,
    SyncUploadLane lane = SyncUploadLane.fresh,
  }) async {
    await _uploadMutex.acquire();
    try {
      // Honor an active Retry-After without immediately probing fair-use
      // status. Lifecycle/manual entry points may reconcile active state, but
      // queued parallel uploads must stop at the established cooldown.
      var allowed = !_limiter.isLimitedForLane(lane.name);
      if (allowed && lane == SyncUploadLane.fresh && _limiter.hasPersistedFairUseState) {
        allowed = await reconcileFairUseStatus();
      }
      if (!allowed) {
        throw SyncRateLimitedException(
          kind: _limiter.reason == RateLimitReason.backendBusy
              ? SyncRateLimitKind.backendCapacity
              : lane == SyncUploadLane.backfill
                  ? SyncRateLimitKind.backfillPaced
                  : SyncRateLimitKind.fairUse,
          retryAfterSeconds: _limiter.activeRetryAfterSeconds,
        );
      }

      try {
        final result = await _uploader(
          files,
          onUploadProgress: onUploadProgress,
          conversationId: conversationId,
          syncLane: lane,
        );
        _limiter.clearForLane(lane.name);
        return result;
      } on SyncRateLimitedException catch (error) {
        _limiter.markLimited(
          retryAfterSeconds: error.retryAfterSeconds,
          reason: switch (error.kind) {
            SyncRateLimitKind.fairUse => RateLimitReason.fairUse,
            SyncRateLimitKind.backfillPaced => RateLimitReason.backfillPaced,
            SyncRateLimitKind.backendCapacity => RateLimitReason.backendBusy,
          },
        );
        rethrow;
      }
    } finally {
      _uploadMutex.release();
    }
  }
}
