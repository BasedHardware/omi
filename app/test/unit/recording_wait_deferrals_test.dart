import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/sync_upload_refusal.dart';
import 'package:omi/services/wals/recording_wait_deferrals.dart';

void main() {
  test('a recording wait holds only its own conversation until it expires', () {
    var now = DateTime.utc(2026, 11, 7, 12);
    final waits = RecordingWaitDeferrals(() => now);

    waits.defer('stuck-conversation', 30);

    expect(waits.isWaiting('stuck-conversation'), isTrue);
    expect(waits.isWaiting('other-conversation'), isFalse);
    expect(waits.isWaiting(null), isFalse);
    now = now.add(const Duration(seconds: 30));
    expect(waits.isWaiting('stuck-conversation'), isFalse);
  });

  test('a server wait is bounded so a bad value cannot strand a recording', () {
    var now = DateTime.utc(2026, 11, 7, 12);
    final waits = RecordingWaitDeferrals(() => now);

    waits.defer('stuck-conversation', 999999);
    now = now.add(const Duration(seconds: RecordingWaitDeferrals.maxWaitSeconds));

    expect(waits.isWaiting('stuck-conversation'), isFalse);
  });

  test('a recognized wait without server pacing still holds for the default', () {
    var now = DateTime.utc(2026, 11, 7, 12);
    final waits = RecordingWaitDeferrals(() => now);

    expect(waits.defer('a', null), isTrue);
    expect(waits.defer('b', 0), isTrue);
    expect(waits.defer(null, 30), isFalse);

    expect(waits.isWaiting('a'), isTrue);
    expect(waits.isWaiting('b'), isTrue);
    now = now.add(const Duration(seconds: RecordingWaitDeferrals.defaultWaitSeconds));
    expect(waits.isWaiting('a'), isFalse);
    expect(waits.isWaiting('b'), isFalse);
  });

  test('only a record_capture_pending body carries recording pacing', () {
    expect(
      syncUploadServerWaitSeconds(
          http.Response('{"code":"record_capture_pending","detail":"x","retry_after_seconds":30}', 503)),
      30,
    );
    expect(syncUploadServerWaitSeconds(http.Response('{"code":"record_capture_pending"}', 503)), isNull);
    expect(
        syncUploadServerWaitSeconds(
            http.Response('{"code":"sync_dispatch_unavailable","retry_after_seconds":30}', 503)),
        isNull);
    expect(syncUploadServerWaitSeconds(http.Response('Service Unavailable', 503)), isNull);
  });
}
