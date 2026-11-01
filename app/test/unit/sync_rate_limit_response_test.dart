import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/gen/conversation_wire.g.dart' as wire;

void main() {
  group('sync capture manifest admission', () {
    test('requests proof only when the caller claims a live capture for a conversation', () {
      expect(shouldRequestSyncCaptureManifest('conversation', true), isTrue);
      expect(shouldRequestSyncCaptureManifest('conversation', false), isFalse);
      expect(shouldRequestSyncCaptureManifest(null, true), isFalse);
    });
  });

  group('syncRateLimitKindForResponse', () {
    test('recognizes the explicit fair-use header', () {
      final response = http.Response('', 429, headers: {'x-omi-rate-limit-reason': 'fair_use'});

      expect(syncRateLimitKindForResponse(response), SyncRateLimitKind.fairUse);
    });

    test('historical pacing and capacity are transient capacity, never a persisted fair-use cooldown', () {
      // #10948: these mapped to their own persisted cooldown that re-armed every
      // 30s and rendered as benign "ready to sync" copy.
      for (final reason in ['backfill_paced', 'backfill_capacity']) {
        final response = http.Response('', 503, headers: {'x-omi-rate-limit-reason': reason});
        expect(syncRateLimitKindForResponse(response), SyncRateLimitKind.backendCapacity);
      }
    });

    test('dispatch holds use the transient account cooldown', () {
      final response = http.Response(
        '{"code":"dispatch_hold"}',
        503,
        headers: {
          'x-omi-rate-limit-reason': 'dispatch_hold',
          'retry-after': '3600',
        },
      );

      expect(syncRateLimitKindForResponse(response), SyncRateLimitKind.backendCapacity);
      expect(isSyncUploadRateLimitResponse(response), isTrue);
      expect(isPacedSyncAdmissionReasonCode(syncRateLimitReasonCode(response)), isTrue);
    });

    test('unknown scoped 503 reasons remain unpaced', () {
      final response = http.Response(
        '{"code":"future_reason"}',
        503,
        headers: {
          'x-omi-rate-limit-reason': 'future_reason',
          'retry-after': '3600',
        },
      );

      expect(syncRateLimitKindForResponse(response), SyncRateLimitKind.edgeThrottle);
      expect(isSyncUploadRateLimitResponse(response), isFalse);
      expect(isPacedSyncAdmissionReasonCode(syncRateLimitReasonCode(response)), isFalse);
    });

    test('keeps unknown JSON, text, and misleading detail generic', () {
      final unknown = http.Response('{"code":"burst_limit"}', 429);
      final text = http.Response('Account temporarily restricted due to fair-use policy', 429);
      final html = http.Response('<html>Too many requests</html>', 429);

      expect(syncRateLimitKindForResponse(unknown), SyncRateLimitKind.edgeThrottle);
      expect(syncRateLimitKindForResponse(text), SyncRateLimitKind.edgeThrottle);
      expect(syncRateLimitKindForResponse(html), SyncRateLimitKind.edgeThrottle);
    });
  });

  group('generated sync response contracts', () {
    test('409 owner and poll hint decode through the generated response', () {
      final response = http.Response(
          '{"code":"sync_content_in_progress","detail":"The same audio is already processing",'
          '"job_id":"live-owner","poll_after_ms":90000}',
          409,
          headers: {'retry-after': '20'});
      expect(isSyncContentInProgressResponse(response), isTrue);
      final result = syncContentInProgressResult(response)!;
      expect(result.jobId, 'live-owner');
      expect(result.pollAfterMs, 90000);
      expect(result.completed, isNull);
    });

    test('shipped 409s without optional owner/hints remain a paced conflict', () {
      final legacy = http.Response('{"code":"sync_content_in_progress"}', 409);
      expect(isSyncContentInProgressResponse(legacy), isTrue);
      expect(syncContentInProgressResult(legacy), isNull);
      final ownerOnly = http.Response('{"code":"sync_content_in_progress","job_id":"live-owner"}', 409);
      expect(syncContentInProgressResult(ownerOnly)!.pollAfterMs, 20000);
      expect(isSyncContentInProgressResponse(http.Response('{}', 409)), isFalse);
      expect(isSyncContentInProgressResponse(http.Response('{"code":"different_conflict"}', 409)), isFalse);
      expect(isSyncContentInProgressResponse(http.Response('<html/>', 409)), isFalse);
    });

    test('status projection preserves generated poll hint and throttle metadata', () {
      final json = <String, dynamic>{
        'job_id': 'owner',
        'status': 'processing',
        'poll_after_ms': 90000,
        'lane': 'backfill',
        'reason_code': 'backfill_paced',
        'retry_after': 60
      };
      final fromJson = SyncJobStatusResponse.fromJson(json);
      final fromWire = SyncJobStatusResponse.fromGenerated(wire.GeneratedSyncJobStatusResponse.fromJson(json));
      for (final status in [fromJson, fromWire]) {
        expect(status.pollAfterMs, 90000);
        expect(status.lane, 'backfill');
        expect(status.reasonCode, 'backfill_paced');
        expect(status.retryAfter, 60);
      }
      expect(SyncJobStatusResponse.fromJson({'job_id': 'old', 'status': 'processing'}).pollAfterMs, isNull);
    });
  });

  group('isSyncRecoveryWindowExceededResponse', () {
    test('recognizes the backend lookback rejection on both sync routes', () {
      final v2 = http.Response(
        '{"code":"backfill_lookback_exceeded","detail":"Recording is older than the automatic recovery window; '
        'local audio was not consumed","lane":"backfill"}',
        422,
      );
      final v1 = http.Response(
        '{"code":"backfill_lookback_exceeded","detail":"Recording is older than the automatic recovery window; '
        'local audio was not consumed"}',
        422,
      );

      expect(isSyncRecoveryWindowExceededResponse(v2), isTrue);
      expect(isSyncRecoveryWindowExceededResponse(v1), isTrue);
    });

    test('does not widen to other 422s, other statuses, or unparseable bodies', () {
      expect(isSyncRecoveryWindowExceededResponse(http.Response('{"code":"validation_error"}', 422)), isFalse);
      expect(
        isSyncRecoveryWindowExceededResponse(
          http.Response('{"detail":"Recording is older than the automatic recovery window"}', 422),
        ),
        isFalse,
        reason: 'the bounded terminal discriminator must be present',
      );
      expect(isSyncRecoveryWindowExceededResponse(http.Response('<html>Unprocessable</html>', 422)), isFalse);
      expect(isSyncRecoveryWindowExceededResponse(http.Response('', 422)), isFalse);
      expect(
        isSyncRecoveryWindowExceededResponse(http.Response('{"code":"backfill_lookback_exceeded"}', 400)),
        isFalse,
        reason: 'only the 422 contract is terminal; a 400 stays the generic unprocessable-audio path',
      );
    });
  });
}
