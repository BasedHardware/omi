import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/sync_upload_refusal.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/wals/recording_wait_deferrals.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _Env implements EnvFields {
  @override
  String get apiBaseUrl => 'https://api.omi.me/';
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('exact retry can defer only through a typed wait, then retained bytes can be accepted', () async {
    SharedPreferences.setMockInitialValues({'uid': 'owner'});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    Env.init(_Env());
    final previous = HttpOverrides.current;
    HttpOverrides.global = null;
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    final dir = await Directory.systemTemp.createTemp('wal-probe');
    final file = File('${dir.path}/audio_fixture_1790000000.bin');
    final wal = List<int>.filled(256 * 1024, 7);
    await file.writeAsBytes(wal);
    Env.overrideApiBaseUrl('http://127.0.0.1:${server.port}/');

    final expiry = DateTime.now().millisecondsSinceEpoch ~/ 1000 + 120;
    final handle = '$expiry.${'a' * 64}';
    const pending = '{"code":"record_capture_pending","retry_after_seconds":1800}';
    var invite = true;
    var issueHandle = true;
    var probeStatus = 503;
    var probeBody = pending;
    var uploadStatus = 503;
    final calls = <String>[];
    final probeMicros = <int>[];
    final uploadMicros = <int>[];
    final probeBytes = <int>[];
    final uploadBytes = <int>[];
    server.listen((request) async {
      final timer = Stopwatch()..start();
      final size = await request.fold<int>(0, (total, bytes) => total + bytes.length);
      final r = request.response;
      r.headers.contentType = ContentType.json;
      if (request.uri.path.endsWith('/sync-capture-manifest')) {
        calls.add('manifest');
        if (invite && request.headers.value('X-Omi-Wal-Retry') == handle) {
          r.headers.set('X-Omi-Wal-Retry', 'check');
        }
        r.write('{"manifest":"synthetic-manifest"}');
      } else if (request.method == 'PUT') {
        calls.add('probe');
        probeBytes.add(size);
        r.statusCode = probeStatus;
        if (probeStatus != 204) {
          r.write(probeBody);
        }
        probeMicros.add(timer.elapsedMicroseconds);
      } else {
        calls.add('multipart');
        uploadBytes.add(size);
        // Deterministic 2 MiB/s ingress service time for the synthetic replay.
        await Future<void>.delayed(Duration(microseconds: size * 1000000 ~/ (2 * 1024 * 1024)));
        r.statusCode = uploadStatus;
        if (issueHandle) {
          r.headers.set('X-Omi-Wal-Retry', handle);
        }
        r.write(switch (uploadStatus) {
          200 => '{"new_memories":[],"updated_memories":[]}',
          202 => '{"job_id":"queued-job","status":"queued","total_files":1,"total_segments":1,"poll_after_ms":20000}',
          _ => pending,
        });
        uploadMicros.add(timer.elapsedMicroseconds);
      }
      await r.close();
    });

    Future<UploadFilesResult> send() => uploadLocalFilesV2([file], conversationId: 'target', claimLiveCapture: true);
    final waiting = throwsA(isA<SyncUploadHttpException>().having((e) => e.reasonCode, 'reason', recordCapturePending));
    Future<void> refused(List<String> expected) async {
      calls.clear();
      await expectLater(send(), waiting);
      expect(calls, expected);
    }

    try {
      await refused(['manifest', 'multipart']);
      await refused(['manifest', 'probe']);
      expect(await file.readAsBytes(), wal);
      expect(probeBytes.single, lessThan(512));
      // ignore: avoid_print
      print('retry replay: ordinary ${uploadBytes.single} B / ${uploadMicros.single} us; '
          'probe ${probeBytes.single} B / ${probeMicros.single} us (server receive + synthetic service)');
      // The used hint is disposable. A cold process takes this same path.
      await refused(['manifest', 'multipart']);
      // Same name and size, different content: no probe.
      await file.writeAsBytes(wal.reversed.toList()..[0] = 8);
      await refused(['manifest', 'multipart']);
      invite = false; // Isolated WAL after the original memo expires.
      await refused(['manifest', 'multipart']);
      invite = true;
      probeStatus = 204; // Cleared at probe, pending again at ordinary admission.
      await refused(['manifest', 'probe', 'multipart']);
      probeStatus = 404; // Rolling back backend-sync after the manifest invitation.
      await refused(['manifest', 'probe', 'multipart']);
      probeStatus = 503;
      probeBody = '{"code":"record_capture_pending","retry_after_seconds":"invalid"}';
      await refused(['manifest', 'probe', 'multipart']);
      issueHandle = false;
      probeBody = 'unavailable';
      await refused(['manifest', 'probe', 'multipart']);
      await refused(['manifest', 'multipart']); // Older server has no handle.
      var now = DateTime.now();
      SyncUploadGate openGate() => SyncUploadGate(
          limiter: SyncRateLimiter.instance,
          uploader: uploadLocalFilesV2,
          fairUseStatusLoader: () async => null,
          recordingWaits: RecordingWaitDeferrals(() => now, persist: true));
      Future<UploadFilesResult> throughGate(SyncUploadGate gate) =>
          gate.upload([file], conversationId: 'target', claimLiveCapture: true);
      await expectLater(throughGate(openGate()), waiting);
      now = now.add(const Duration(minutes: 6));
      final afterRestart = openGate();
      calls.clear();
      await expectLater(throughGate(afterRestart), throwsA(isA<SyncRecordingWaitException>()));
      expect(calls, isEmpty);
      expect(await file.length(), wal.length);
      now = now.add(const Duration(minutes: 24));
      uploadStatus = 202;
      expect((await throughGate(afterRestart)).jobId, 'queued-job');
      expect(calls, ['manifest', 'multipart']);
      uploadStatus = 200;
      expect((await send()).completed, isNotNull);
    } finally {
      Env.clearApiBaseUrlOverrideForTesting();
      HttpOverrides.global = previous;
      await server.close(force: true);
      await dir.delete(recursive: true);
    }
  });
}
