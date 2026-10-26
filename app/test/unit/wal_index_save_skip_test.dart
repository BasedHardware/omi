import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/wal_file_manager.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

/// Shared instances for the replaced-never-mutated object fields, so two
/// separately built WALs differ only in the field a mutation touches.
final _conversation = {'id': 'conversation'};
final _preparedUpload = {'phase': 1};
final _geolocation = Geolocation(latitude: 1, longitude: 2, accuracy: 3);

Wal _fullyPopulated() => Wal(
      timerStart: 1700000000,
      codec: BleAudioCodec.opus,
      seconds: 30,
      sampleRate: 16000,
      channel: 1,
      status: WalStatus.miss,
      storage: WalStorage.disk,
      onDeviceOnly: true,
      holdForUser: true,
      deviceType: DeviceType.omi,
      onDeviceConversation: _conversation,
      onDevicePreparedUpload: _preparedUpload,
      onDeviceUploadFailure: 'boom',
      capturedOnDeviceOnly: true,
      filePath: 'audio_one.bin',
      device: 'phone',
      deviceModel: 'Omi',
      storageOffset: 1,
      storageTotalBytes: 2,
      fileNum: 3,
      totalFrames: 100,
      syncedFrameOffset: 90,
      originalStorage: WalStorage.flashPage,
      conversationId: 'conv',
      recordingSessionId: 'rec',
      ownerUid: 'owner',
      captureRoot: 'root',
      sourceFrameStart: 5,
      sourceClockEpoch: 6,
      liveRingId: 7,
      liveOrdinalStart: 8,
      liveOrdinalEnd: 9,
      geolocation: _geolocation,
      retryCount: 1,
      lastRetryAt: 2,
      jobId: 'job',
      uploadedAt: 3,
      syncedAt: 4,
      keptForTranscriptRecovery: true,
      clockRun: 'run',
    );

/// One mutation per key [Wal.toJson] writes. The key set is asserted against
/// toJson itself, so a new persisted field fails here until its fingerprint
/// coverage is added.
final _mutations = <String, void Function(Wal)>{
  'timer_start': (w) => w.timerStart++,
  'codec': (w) => w.codec = BleAudioCodec.pcm16,
  'channel': (w) => w.channel = 2,
  'sample_rate': (w) => w.sampleRate = 8000,
  'status': (w) => w.status = WalStatus.synced,
  'storage': (w) => w.storage = WalStorage.mem,
  'on_device_only': (w) => w.onDeviceOnly = false,
  'hold_for_user': (w) => w.holdForUser = false,
  'device_type': (w) => w.deviceType = DeviceType.appleWatch,
  'on_device_conversation': (w) => w.onDeviceConversation = {'id': 'other'},
  'on_device_prepared_upload': (w) => w.onDevicePreparedUpload = {'phase': 2},
  'on_device_upload_failure': (w) => w.onDeviceUploadFailure = 'other',
  'captured_on_device_only': (w) => w.capturedOnDeviceOnly = false,
  'file_path': (w) => w.filePath = 'audio_two.bin',
  'seconds': (w) => w.seconds = 31,
  'device': (w) => w.device = 'watch',
  'device_model': (w) => w.deviceModel = 'Watch',
  'storage_offset': (w) => w.storageOffset = 11,
  'storage_total_bytes': (w) => w.storageTotalBytes = 12,
  'file_num': (w) => w.fileNum = 13,
  'total_frames': (w) => w.totalFrames = 101,
  'frame_size': (w) => w.frameSize = 161,
  'synced_frame_offset': (w) => w.syncedFrameOffset = 91,
  'original_storage': (w) => w.originalStorage = WalStorage.sdcard,
  'conversation_id': (w) => w.conversationId = 'conv-2',
  'recording_session_id': (w) => w.recordingSessionId = 'rec-2',
  'owner_uid': (w) => w.ownerUid = 'owner-2',
  'capture_root': (w) => w.captureRoot = 'root-2',
  'source_frame_start': (w) => w.sourceFrameStart = 15,
  'source_clock_epoch': (w) => w.sourceClockEpoch = 16,
  'live_ring_id': (w) => w.liveRingId = 17,
  'live_ordinal_start': (w) => w.liveOrdinalStart = 18,
  'live_ordinal_end': (w) => w.liveOrdinalEnd = 19,
  'geolocation': (w) => w.geolocation = Geolocation(latitude: 9, longitude: 8, accuracy: 7),
  'retry_count': (w) => w.retryCount = 5,
  'last_retry_at': (w) => w.lastRetryAt = 6,
  'job_id': (w) => w.jobId = 'job-2',
  'uploaded_at': (w) => w.uploadedAt = 7,
  'synced_at': (w) => w.syncedAt = 8,
  'kept_for_transcript_recovery': (w) => w.keptForTranscriptRecovery = false,
  'clock_run': (w) => w.clockRun = 'run-2',
};

Wal _diskWal(int timerStart) => Wal(
    timerStart: timerStart,
    codec: BleAudioCodec.opus,
    seconds: 30,
    status: WalStatus.miss,
    storage: WalStorage.disk,
    device: 'phone',
    filePath: 'audio_$timerStart.bin');

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory dir;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    dir = await Directory.systemTemp.createTemp('wal_index_save_skip_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (_) async => dir.path,
    );
    await WalFileManager.init();
  });

  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/path_provider'), null);
    await dir.delete(recursive: true);
  });

  test('every persisted field changes the index fingerprint', () {
    final base = _fullyPopulated();
    expect(base.toJson().keys.toSet(), _mutations.keys.toSet(),
        reason: 'Wal.toJson gained or lost a persisted key; keep persistentFingerprint and this map in lockstep');
    final basePrint = base.persistentFingerprint;
    final baseIndex = Wal.persistedIndexFingerprint([base]);
    for (final entry in _mutations.entries) {
      final mutated = _fullyPopulated();
      entry.value(mutated);
      expect(mutated.persistentFingerprint, isNot(basePrint),
          reason: 'a change to ${entry.key} must not read as an unchanged index');
    }
    // Order and membership are part of the signal.
    final other = _diskWal(1);
    expect(Wal.persistedIndexFingerprint([base, other]), isNot(baseIndex));
    expect(Wal.persistedIndexFingerprint([other, base]), isNot(Wal.persistedIndexFingerprint([base, other])));
    // Runtime-only fields never gate a save.
    base
      ..isSyncing = true
      ..syncStartedAt = DateTime.now()
      ..syncEtaSeconds = 10
      ..syncSpeedKBps = 12.5
      ..deviceDownloadFraction = 0.5;
    expect(base.persistentFingerprint, basePrint);
  });

  test('an unchanged snapshot skips the periodic re-encode; a change or a failure writes', () async {
    var persists = 0;
    var failNext = false;
    final sync = LocalWalSyncImpl(_Listener(), persistWals: (items) async {
      if (failNext) {
        failNext = false;
        throw const SocketException('disk full');
      }
      persists++;
    });
    final wal = _diskWal(1);
    sync.testWals = [wal];

    await sync.persistRetryMetadata(wal);
    expect(persists, 1, reason: 'the first save of a session always writes');

    await sync.persistRetryMetadata(wal);
    expect(persists, 1, reason: 'an unchanged snapshot is not re-encoded');

    wal.retryCount = 3; // in-place mutation, same list and identities
    await sync.persistRetryMetadata(wal);
    expect(persists, 2, reason: 'an in-place status change must still persist');

    wal.lastRetryAt = 42;
    failNext = true;
    await expectLater(sync.persistRetryMetadata(wal), throwsA(isA<SocketException>()));
    expect(persists, 2, reason: 'a failed write does not count as persisted');
    await sync.persistRetryMetadata(wal);
    expect(persists, 3, reason: 'a failed write is retried even though the snapshot is unchanged');

    // The idle flush timer re-saves unconditionally today; with the guard it
    // must not pay the encode again.
    await sync.stop();
    expect(persists, 3, reason: 'a flush with no durable change skips the index write');

    sync.clearUserData();
    await sync.persistRetryMetadata(wal);
    expect(persists, 4, reason: 'a session boundary always writes (retired records become durable)');
  });
  test('a skipped save waits for the matching in-flight write and writes itself if that write fails', () async {
    var persists = 0;
    Completer<void>? gate;
    final sync = LocalWalSyncImpl(_Listener(), persistWals: (items) async {
      persists++;
      final g = gate;
      gate = null;
      if (g != null) await g.future;
    });
    final wal = _diskWal(1);
    sync.testWals = [wal];

    final firstGate = gate = Completer<void>();
    final first = sync.persistRetryMetadata(wal);
    var secondDone = false;
    final second = sync.persistRetryMetadata(wal).then((_) => secondDone = true);
    await Future<void>.delayed(Duration.zero);
    expect(persists, 1);
    expect(secondDone, isFalse, reason: 'an identical snapshot is not durable until the in-flight write lands');

    firstGate.completeError(const SocketException('disk full'));
    await expectLater(first, throwsA(isA<SocketException>()));
    await second;
    expect(persists, 2, reason: 'the waiting save writes its own snapshot after the matching write failed');
    expect(secondDone, isTrue);
  });
}
