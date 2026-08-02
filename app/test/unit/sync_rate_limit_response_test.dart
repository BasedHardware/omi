import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/conversations.dart';

void main() {
  group('sync capture manifest admission', () {
    test('requests proof only for conversation-targeted fresh uploads', () {
      expect(shouldRequestSyncCaptureManifest('conversation', SyncUploadLane.fresh), isTrue);
      expect(shouldRequestSyncCaptureManifest('conversation', SyncUploadLane.backfill), isFalse);
      expect(shouldRequestSyncCaptureManifest(null, SyncUploadLane.fresh), isFalse);
    });

    test('a batch with no issued manifest uploads on the backfill lane instead of stalling', () {
      expect(syncUploadLaneForCaptureManifest(SyncUploadLane.fresh, null), SyncUploadLane.backfill);
    });

    test('an issued manifest keeps the requested lane', () {
      expect(syncUploadLaneForCaptureManifest(SyncUploadLane.fresh, 'manifest-token'), SyncUploadLane.fresh);
      expect(syncUploadLaneForCaptureManifest(SyncUploadLane.backfill, 'manifest-token'), SyncUploadLane.backfill);
    });
  });

  group('syncRateLimitKindForResponse', () {
    test('recognizes the explicit fair-use header', () {
      final response = http.Response('', 429, headers: {'x-omi-rate-limit-reason': 'fair_use'});

      expect(syncRateLimitKindForResponse(response), SyncRateLimitKind.fairUse);
    });

    test('recognizes historical pacing and capacity headers', () {
      for (final reason in ['backfill_paced', 'backfill_capacity']) {
        final response = http.Response('', 503, headers: {'x-omi-rate-limit-reason': reason});
        expect(syncRateLimitKindForResponse(response), SyncRateLimitKind.backfillPaced);
      }
    });

    test('keeps unknown JSON, text, and misleading detail generic', () {
      final unknown = http.Response('{"code":"burst_limit"}', 429);
      final text = http.Response('Account temporarily restricted due to fair-use policy', 429);
      final html = http.Response('<html>Too many requests</html>', 429);

      expect(syncRateLimitKindForResponse(unknown), SyncRateLimitKind.backendCapacity);
      expect(syncRateLimitKindForResponse(text), SyncRateLimitKind.backendCapacity);
      expect(syncRateLimitKindForResponse(html), SyncRateLimitKind.backendCapacity);
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
