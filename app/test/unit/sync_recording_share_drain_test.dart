import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/wal_file_manager.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

// One pathological recording (38 batches of the same conversation) queued
// ahead of two small ones. Oldest-first ordering would spend the whole pass
// on the poison recording before the small ones get a batch; the per-recording
// share cap defers its remainder so everything behind it syncs in the same
// pass (#14688).
void main() {
  late Directory tempDir;
  late List<String?> uploadedConversations;
  late List<String> uploadedBatchFirstFiles;
  late int rateLimitAtBatch;
  late LocalWalSyncImpl sync;

  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();

    tempDir = await Directory.systemTemp.createTemp('sync_recording_share_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (MethodCall call) async {
        if (call.method == 'getApplicationDocumentsDirectory') return tempDir.path;
        return null;
      },
    );
    await WalFileManager.init();

    uploadedConversations = [];
    uploadedBatchFirstFiles = [];
    rateLimitAtBatch = 0;
    SyncRateLimiter.instance.clear();
    sync = LocalWalSyncImpl(
      _Listener(),
      uploadGate: SyncUploadGate(
        limiter: SyncRateLimiter.instance,
        uploader: (files,
            {onUploadProgress,
            conversationId,
            captureEvidence,
            recordingSessionId,
            audioStartSeconds,
            audioEndSeconds,
            claimLiveCapture = false,
            geolocation}) async {
          if (rateLimitAtBatch > 0 && uploadedConversations.length >= rateLimitAtBatch) {
            throw SyncRateLimitedException(kind: SyncRateLimitKind.backendCapacity, retryAfterSeconds: 60);
          }
          uploadedConversations.add(conversationId);
          uploadedBatchFirstFiles.add(files.first.uri.pathSegments.last);
          return UploadFilesResult.queued('job-${uploadedConversations.length}');
        },
        fairUseStatusLoader: () async => {'stage': 'none'},
      ),
    );
  });

  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    SyncRateLimiter.instance.clear();
    if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
  });

  Future<Wal> writeWal(int timerStart, {String? conversationId, int seconds = 60, String device = 'omi'}) async {
    final name = 'audio_$timerStart.bin';
    await File('${tempDir.path}/$name').writeAsBytes(List<int>.filled(64, 1));
    return Wal(
      timerStart: timerStart,
      codec: BleAudioCodec.opus,
      seconds: seconds,
      status: WalStatus.miss,
      storage: WalStorage.disk,
      device: device,
      filePath: name,
      conversationId: conversationId,
    );
  }

  Future<List<Wal>> writeRecording(String conversationId, int startSeconds, int walCount) async => [
        for (var index = 0; index < walCount; index++)
          await writeWal(startSeconds + index * 60, conversationId: conversationId),
      ];

  // Device-imported WALs (StorageSync → persistDeviceChunk) carry no
  // conversation or recording-session id; one contiguous run of 60s chunks
  // is one pendant recording.
  Future<List<Wal>> writeDeviceRun(int startSeconds, int walCount) async => [
        for (var index = 0; index < walCount; index++) await writeWal(startSeconds + index * 60, device: 'pendant'),
      ];

  test('a recording past its share yields to smaller recordings and still finishes in the same pass', () async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    // Every recording sits outside the 6h live-capture window, so the drain
    // orders them purely oldest-first.
    final poison = await writeRecording('c1', now - 7 * 3600 - 190 * 60, 190); // 38 batches
    final smallA = await writeRecording('c2', now - 6 * 3600 - 30 * 60, 5); // 1 batch
    final smallB = await writeRecording('c3', now - 6 * 3600 - 20 * 60, 5); // 1 batch
    sync.testWals = [...poison, ...smallA, ...smallB];

    await sync.syncAll();

    // The cap yields after 36 poison batches so both small recordings land,
    // then the poison remainder resumes: one uninterrupted pass drains
    // everything. Leaving the tail pending would strand it until another
    // confirmed sync (#14688).
    expect(uploadedConversations.length, 40);
    expect(uploadedConversations.where((c) => c == 'c1').length, 38);
    expect(uploadedConversations[36], 'c2');
    expect(uploadedConversations[37], 'c3');
    expect(uploadedConversations.last, 'c1');
    expect(poison.every((w) => w.status == WalStatus.uploaded), isTrue);
    expect(smallA.every((w) => w.status == WalStatus.uploaded), isTrue);
    expect(smallB.every((w) => w.status == WalStatus.uploaded), isTrue);

    // A later pass has nothing left to upload.
    await sync.syncAll();
    expect(uploadedConversations.length, 40);
  });

  test('a recording near the 30-day backfill deadline is never stranded by the cap', () async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    // The recording's oldest audio is three hours inside the server's 30-day
    // backfill cutoff: any batch left pending after this pass faces
    // `backfill_lookback_exceeded` unless the user confirms another sync in
    // time. Custom-STT drains are manual-confirm only, so this pass must
    // finish what the cap interrupts (#14688).
    final poison = await writeRecording('c1', now - 30 * 86400 + 3 * 3600, 190); // 38 batches
    final small = await writeRecording('c2', now - 6 * 3600 - 30 * 60, 5);
    sync.testWals = [...poison, ...small];

    await sync.syncAll();

    // The cap still yielded first — the small recording landed right after
    // the 36th poison batch, so the deadline-near group really was deferred,
    // not exempted — and the resumed pass still uploaded every batch.
    expect(uploadedConversations.length, 39);
    expect(uploadedConversations[36], 'c2');
    expect(uploadedConversations.where((c) => c == 'c1').length, 38);
    expect(poison.where((w) => w.status == WalStatus.miss), isEmpty);
    expect(small.every((w) => w.status == WalStatus.uploaded), isTrue);
  });

  test('a lone backlog is never throttled by the share cap', () async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final backlog = await writeRecording('c1', now - 7 * 3600 - 190 * 60, 190);
    sync.testWals = backlog;

    await sync.syncAll();

    expect(uploadedConversations.length, 38);
    expect(backlog.every((w) => w.status == WalStatus.uploaded), isTrue);
  });

  test('recordings under the share cap drain unchanged', () async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final first = await writeRecording('c1', now - 7 * 3600 - 25 * 60, 25); // 5 batches
    final second = await writeRecording('c2', now - 6 * 3600 - 30 * 60, 5);
    sync.testWals = [...first, ...second];

    await sync.syncAll();

    expect(uploadedConversations, ['c1', 'c1', 'c1', 'c1', 'c1', 'c2']);
    expect(first.every((w) => w.status == WalStatus.uploaded), isTrue);
    expect(second.every((w) => w.status == WalStatus.uploaded), isTrue);
  });

  test('id-less device recordings cap per contiguous run, not one shared bucket', () async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final smallStart = now - 7 * 3600;
    final hugeStart = smallStart - 3600 - 190 * 60; // ends 1h before the small run
    final huge = await writeDeviceRun(hugeStart, 190); // one contiguous run, 38 batches
    final small = await writeDeviceRun(smallStart, 5); // separate recording, 1 batch
    sync.testWals = [...huge, ...small];

    await sync.syncAll();

    // The huge run defers at its 36-batch share with the small run waiting;
    // the small run's batch lands before the pass ends, then the huge run
    // resumes and finishes in the same pass. With the old null|null|false|
    // key every device recording shared one group, so the cap never fired
    // between them (#14688).
    expect(uploadedBatchFirstFiles.length, 39);
    expect(uploadedBatchFirstFiles[36], 'audio_$smallStart.bin');
    expect(huge.where((w) => w.status == WalStatus.miss), isEmpty);
    expect(small.every((w) => w.status == WalStatus.uploaded), isTrue);

    await sync.syncAll();
    expect(uploadedBatchFirstFiles.length, 39);
  });

  test('a rate-limit break before the cap carries the spent share into the next pass', () async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final poison = await writeRecording('c1', now - 7 * 3600 - 190 * 60, 190);
    final small = await writeRecording('c2', now - 6 * 3600 - 30 * 60, 5);
    sync.testWals = [...poison, ...small];

    // Pass 1 dies on the rate limiter one batch short of the cap. The
    // failed 36th batch still spent the rate-limit budget, so its share
    // counts; a pass-local counter would restart at zero and re-monopolize
    // every interrupted pass (#14688).
    rateLimitAtBatch = 35;
    await sync.syncAll();
    expect(uploadedConversations.where((c) => c == 'c1').length, 35);
    expect(small.every((w) => w.status == WalStatus.uploaded), isFalse);

    SyncRateLimiter.instance.clear();
    rateLimitAtBatch = 0;
    await sync.syncAll();

    // The carried share defers the poison remainder immediately; the small
    // recording gets its turn in pass 2 instead of waiting for 36 more
    // poison batches. Once nothing else waits, the poison remainder resumes
    // and pass 2 finishes it too.
    expect(uploadedConversations.where((c) => c == 'c1').length, 38);
    expect(uploadedConversations[35], 'c2');
    expect(uploadedConversations.last, 'c1');
    expect(small.every((w) => w.status == WalStatus.uploaded), isTrue);
    expect(poison.every((w) => w.status == WalStatus.uploaded), isTrue);

    await sync.syncAll();
    expect(uploadedConversations.length, 39);
  });
}
