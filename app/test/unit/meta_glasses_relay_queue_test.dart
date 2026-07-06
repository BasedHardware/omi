import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/services/meta_wearables/meta_capture_diagnostics.dart';
import 'package:omi/services/meta_wearables/meta_capture_queue.dart';

import '../support/meta_wearables_mock_harness.dart';

void main() {
  late Directory dir;
  late MetaCaptureQueue queue;

  setUp(() async {
    dir = await Directory.systemTemp.createTemp('meta_capture_queue_test_');
    queue = MetaCaptureQueue(rootDirectory: dir);
  });

  tearDown(() async {
    if (await dir.exists()) {
      await dir.delete(recursive: true);
    }
  });

  test('persists pending frames across queue recreation', () async {
    final first = await queue.enqueue(
      bytes: Uint8List.fromList(utf8.encode('frame-a')),
      capturedAt: DateTime.utc(2026, 7, 5, 1, 2, 3),
      deviceUuid: 'glasses-1',
      deviceName: 'Meta Glasses',
    );

    final reopened = MetaCaptureQueue(rootDirectory: dir);
    final pending = await reopened.pending(limit: 10);

    expect(pending, hasLength(1));
    expect(pending.single.id, first.id);
    expect(pending.single.deviceUuid, 'glasses-1');
    expect(pending.single.sha256, isNotEmpty);
  });

  test('markUploaded removes only matching frame', () async {
    final a = await queue.enqueue(
      bytes: Uint8List.fromList([1]),
      capturedAt: DateTime.utc(2026, 7, 5, 1),
      deviceUuid: 'glasses-1',
    );
    final b = await queue.enqueue(
      bytes: Uint8List.fromList([2]),
      capturedAt: DateTime.utc(2026, 7, 5, 2),
      deviceUuid: 'glasses-1',
    );

    await queue.markUploaded(a.id);
    final pending = await queue.pending(limit: 10);

    expect(pending.map((item) => item.id), [b.id]);
  });

  test('enqueue does not leak the frame JPEG when the ledger append fails', () async {
    // Review thread: the frame file was written before the queue-file append;
    // an append failure (disk full, IO error) orphaned the JPEG forever.
    // Force the failure by occupying the ledger path with a directory.
    await Directory('${dir.path}/meta_capture_queue.jsonl').create(recursive: true);

    await expectLater(
      queue.enqueue(
        bytes: Uint8List.fromList([9, 9, 9]),
        capturedAt: DateTime.utc(2026, 7, 5, 4),
        deviceUuid: 'glasses-1',
      ),
      throwsA(isA<FileSystemException>()),
    );

    final frames = Directory('${dir.path}/meta_capture_frames');
    final leaked = frames.existsSync() ? frames.listSync().where((e) => e.path.endsWith('.jpg')).toList() : const [];
    expect(leaked, isEmpty, reason: 'a failed enqueue must delete the frame file it wrote');
  });

  test('uploaded ledger compacts instead of growing forever', () async {
    // Review thread: meta_capture_queue.jsonl and meta_capture_uploaded.txt
    // were append-only for the life of the install.
    final compacting = MetaCaptureQueue(rootDirectory: dir, compactionThreshold: 2);
    final a = await compacting.enqueue(
        bytes: Uint8List.fromList([1]), capturedAt: DateTime.utc(2026, 7, 5, 1), deviceUuid: 'g');
    final b = await compacting.enqueue(
        bytes: Uint8List.fromList([2]), capturedAt: DateTime.utc(2026, 7, 5, 2), deviceUuid: 'g');
    final c = await compacting.enqueue(
        bytes: Uint8List.fromList([3]), capturedAt: DateTime.utc(2026, 7, 5, 3), deviceUuid: 'g');

    await compacting.markUploaded(a.id);
    await compacting.markUploaded(b.id); // hits threshold -> compacts

    final ledger = await File('${dir.path}/meta_capture_queue.jsonl').readAsString();
    expect(ledger, isNot(contains(a.id)), reason: 'uploaded entries must be rewritten out of the ledger');
    expect(ledger, isNot(contains(b.id)));
    expect(ledger, contains(c.id), reason: 'pending entries must survive compaction');
    expect(File('${dir.path}/meta_capture_uploaded.txt').existsSync(), isFalse,
        reason: 'the uploaded ledger is redundant after compaction');

    final pending = await compacting.pending(limit: 10);
    expect(pending.map((i) => i.id), [c.id]);
  });

  test('diagnostics copyWith can clear nullable fields back to null', () {
    // Review thread: ??-based copyWith made an explicit null a no-op, so
    // stale lastUploadStatus/session state could never be cleared.
    final diag = const MetaCaptureDiagnostics().copyWith(
      lastUploadStatus: 'upload_failed',
      streamState: 'streaming',
      lastFrameAt: DateTime.utc(2026, 7, 5),
    );
    final cleared = diag.copyWith(lastUploadStatus: null, lastFrameAt: null);

    expect(cleared.lastUploadStatus, isNull);
    expect(cleared.lastFrameAt, isNull);
    expect(cleared.streamState, 'streaming', reason: 'omitted fields must still be preserved');
  });

  test('cache upload payload includes idempotency metadata', () async {
    final source = File('lib/backend/http/api/conversations.dart').readAsStringSync();

    expect(source, contains('device_uuid'));
    expect(source, contains('frame_sha256'));
    expect(source, contains('captured_at'));
    expect(source, contains('conversation_id'));
  });

  test('cache upload payload helper propagates queue metadata', () {
    final capturedAt = DateTime.utc(2026, 7, 5, 3, 4, 5);
    final payload = buildMetaWearablesPhotoCachePayload(
      Uint8List.fromList([1, 2, 3]),
      capturedAt: capturedAt,
      conversationId: 'conversation-1',
      deviceUuid: 'glasses-1',
      deviceName: 'Meta Glasses',
      frameSha256: 'abc123',
    );

    expect(payload['base64'], base64Encode([1, 2, 3]));
    expect(payload['captured_at'], capturedAt.toIso8601String());
    expect(payload['conversation_id'], 'conversation-1');
    expect(payload['device_uuid'], 'glasses-1');
    expect(payload['device_name'], 'Meta Glasses');
    expect(payload['frame_sha256'], 'abc123');
  });

  test('recording capture controller retains cache metadata', () async {
    final controller = RecordingCaptureController();

    await controller.cacheCapturedImage(
      Uint8List.fromList([4, 5, 6]),
      capturedAt: DateTime.utc(2026, 7, 5, 6),
      deviceUuid: 'glasses-2',
      deviceName: 'Meta Glasses 2',
      frameSha256: 'def456',
    );

    expect(controller.deviceUuidValues, ['glasses-2']);
    expect(controller.deviceNameValues, ['Meta Glasses 2']);
    expect(controller.frameSha256Values, ['def456']);
  });

  test('meta capture enqueue does not bypass the durable queue', () {
    final source = File('lib/providers/meta_wearables_provider.dart').readAsStringSync();

    expect(source, isNot(contains('unawaited(_cachePhotoBytes')));
  });

  test('local demo script starts proxy and cloudflared', () {
    final source = File('../scripts/run-meta-demo-relay.sh').readAsStringSync();
    final proxy = File('../scripts/meta_wearables_demo_proxy.js').readAsStringSync();

    expect(source, contains('meta_wearables_demo_proxy.js'));
    expect(source, contains('cloudflared tunnel --url'));
    expect(source, contains('API_BASE_URL='));
    expect(source, contains('trap cleanup EXIT INT TERM'));
    expect(source, contains('PID_DIR'));
    expect(source, contains('PROXY_META_FILE'));
    expect(source, contains(r'echo "port=$PORT state=$STATE"'));
    expect(source, contains(r'[[ "$meta" == "$expected_meta" ]]'));
    expect(source, contains(r'ps -p "$pid" -o command='));
    expect(source, contains(r'"cloudflared tunnel --url http://127.0.0.1:${PORT}"'));
    expect(source, isNot(contains('pkill -f')));
    expect(source, isNot(contains('| tee')));
    expect(proxy, contains('frame_sha256'));
    expect(proxy, contains('makeDeterministicPhotoId'));
    expect(proxy, contains('photos.some((photo) => photo.id === photoId)'));
  });

  test('local demo proxy dedupes retry by frame hash', () async {
    final socket = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
    final port = socket.port;
    await socket.close();
    final stateFile = File('${dir.path}/demo-state.json');
    final process = await Process.start(
      'node',
      ['../scripts/meta_wearables_demo_proxy.js'],
      workingDirectory: Directory.current.path,
      environment: {
        'PORT': '$port',
        'OMI_META_DEMO_STATE': stateFile.path,
      },
    );

    try {
      Future<Map<String, dynamic>> postFrame() async {
        final client = HttpClient();
        final request = await client.postUrl(Uri.parse('http://127.0.0.1:$port/v1/meta-wearables/photos/cache'));
        request.headers.contentType = ContentType.json;
        request.write(jsonEncode({
          'base64': base64Encode([1, 2, 3]),
          'conversation_id': 'conversation-1',
          'device_uuid': 'glasses-1',
          'captured_at': DateTime.utc(2026, 7, 5, 1, 2, 3).toIso8601String(),
          'frame_sha256': 'same-frame',
        }));
        final response = await request.close();
        final body = await utf8.decodeStream(response);
        client.close(force: true);
        expect(response.statusCode, 200);
        return jsonDecode(body) as Map<String, dynamic>;
      }

      var ready = false;
      for (var i = 0; i < 20; i++) {
        try {
          final client = HttpClient();
          final request = await client.getUrl(Uri.parse('http://127.0.0.1:$port/health'));
          final response = await request.close();
          await response.drain<void>();
          client.close(force: true);
          ready = response.statusCode == 200;
          if (ready) break;
        } catch (_) {}
        await Future<void>.delayed(const Duration(milliseconds: 100));
      }
      expect(ready, isTrue);

      final first = await postFrame();
      final second = await postFrame();
      final state = jsonDecode(await stateFile.readAsString()) as Map<String, dynamic>;
      final conversations = state['conversations'] as Map<String, dynamic>;
      final conversation = conversations['conversation-1'] as Map<String, dynamic>;
      final photos = conversation['photos'] as List<dynamic>;

      expect(second['photo_id'], first['photo_id']);
      expect(photos, hasLength(1));
    } finally {
      process.kill();
      await process.exitCode.timeout(const Duration(seconds: 2), onTimeout: () => -1);
    }
  });
}
