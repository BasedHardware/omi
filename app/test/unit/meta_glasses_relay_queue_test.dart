import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/meta_wearables/meta_capture_diagnostics.dart';
import 'package:omi/services/meta_wearables/meta_capture_queue.dart';

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

  test('meta capture enqueue does not bypass the durable queue', () {
    final source = File('lib/providers/meta_wearables_provider.dart').readAsStringSync();

    expect(source, isNot(contains('unawaited(_cachePhotoBytes')));
  });
}
