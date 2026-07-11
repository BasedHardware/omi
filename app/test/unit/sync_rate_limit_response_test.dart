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
}
