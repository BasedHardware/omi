import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_upload_batch.dart';
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
          uploadedConversations.add(conversationId);
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

  Future<Wal> writeWal(int timerStart, {String? conversationId, int seconds = 60}) async {
    final name = 'audio_$timerStart.bin';
    await File('${tempDir.path}/$name').writeAsBytes(List<int>.filled(64, 1));
    return Wal(
      timerStart: timerStart,
      codec: BleAudioCodec.opus,
      seconds: seconds,
      status: WalStatus.miss,
      storage: WalStorage.disk,
      device: 'omi',
      filePath: name,
      conversationId: conversationId,
    );
  }

  Future<List<Wal>> writeRecording(String conversationId, int startSeconds, int walCount) async => [
        for (var index = 0; index < walCount; index++)
          await writeWal(startSeconds + index * 60, conversationId: conversationId),
      ];

  test('a recording past its share defers its remainder while smaller recordings sync in the same pass', () async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    // Every recording sits outside the 6h live-capture window, so the drain
    // orders them purely oldest-first.
    final poison = await writeRecording('c1', now - 7 * 3600 - 190 * 60, 190); // 38 batches
    final smallA = await writeRecording('c2', now - 6 * 3600 - 30 * 60, 5); // 1 batch
    final smallB = await writeRecording('c3', now - 6 * 3600 - 20 * 60, 5); // 1 batch
    sync.testWals = [...poison, ...smallA, ...smallB];

    await sync.syncAll();

    expect(uploadedConversations.length, 38);
    expect(uploadedConversations.where((c) => c == 'c1').length, maxBatchesPerRecordingPerDrain);
    expect(uploadedConversations.last, 'c3');
    expect(uploadedConversations[uploadedConversations.length - 2], 'c2');
    // The small recordings finished; the poison recording keeps only the
    // batches beyond its share pending.
    expect(smallA.every((w) => w.status == WalStatus.uploaded), isTrue);
    expect(smallB.every((w) => w.status == WalStatus.uploaded), isTrue);
    expect(poison.where((w) => w.status == WalStatus.miss).length, 190 - 5 * maxBatchesPerRecordingPerDrain);

    // A later pass resumes the poison recording and finishes it.
    await sync.syncAll();
    expect(uploadedConversations.where((c) => c == 'c1').length, 38);
    expect(poison.every((w) => w.status == WalStatus.uploaded), isTrue);
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
}
