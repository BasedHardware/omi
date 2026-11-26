import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/audio_sources/audio_source.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/wal_file_manager.dart';

import '../support/capture/virtual_capture_time.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
  @override
  void onWalUpdated() {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory tempDir;
  late ManualScheduler scheduler;
  late LocalWalSyncImpl sync;
  Completer<void>? persistBarrier;
  Completer<void>? persistStarted;

  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'owner-a'});
    await SharedPreferencesUtil.init();
    tempDir = await Directory.systemTemp.createTemp('conversation_wal_snapshot_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (call) async => call.method == 'getApplicationDocumentsDirectory' ? tempDir.path : null,
    );
    await WalFileManager.init();
    scheduler = ManualScheduler(clock: VirtualClock(DateTime.utc(2026, 11, 22)));
    persistBarrier = null;
    persistStarted = null;
    sync = LocalWalSyncImpl(
      _Listener(),
      now: scheduler.clock.now,
      periodic: scheduler.periodic,
      freeDiskBytes: () async => 1 << 40,
      persistWals: (wals) async {
        final barrier = persistBarrier;
        if (barrier != null) {
          if (!persistStarted!.isCompleted) persistStarted!.complete();
          await barrier.future;
        }
        if (!await WalFileManager.saveWals(wals)) throw const FileSystemException('test index save failed');
      },
    );
    sync.setDeviceInfo('phone-mic', 'Phone Microphone');
    sync.setActiveRecordingSessionId('recording-1');
    sync.start();
    await sync.walReady;
  });

  tearDown(() async {
    if (persistBarrier != null && !persistBarrier!.isCompleted) persistBarrier!.complete();
    await scheduler.waitForCallbackIo();
    await sync.stop();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
  });

  int getStart() => scheduler.clock.now().millisecondsSinceEpoch ~/ 1000 - 60;

  void capture(int first, int count, {bool transportSynced = false, String? root = 'capture-root'}) {
    for (var i = first; i < first + count; i++) {
      final key = FrameSyncKey([i & 0xFF, i >> 8]);
      sync.onFrameCaptured(WalFrame(payload: [0xAA, i & 0xFF], syncKey: key), captureRoot: root);
      if (transportSynced) sync.markFrameSynced(key);
    }
  }

  Future<ConversationWalSnapshot> cut({String? recording = 'recording-1'}) async =>
      (await sync.finalizeAndSnapshotSession(sessionStartSeconds: getStart(), recordingSessionId: recording))!;

  test('queued close seals at admission and excludes frames received behind its barrier', () async {
    final barrier = Completer<void>();
    final queued = sync.testQueueWalIo(barrier.future);
    capture(0, 3);

    final snapshot = cut();
    expect(sync.testFrames, isEmpty, reason: 'the cut must seal before waiting for queued I/O');
    expect(sync.testWals.single.totalFrames, 3);
    capture(3, 2);
    expect(sync.testFrames, hasLength(2));

    barrier.complete();
    await queued;
    await sync.stampConversationSnapshot(await snapshot, 'conversation-1');
    expect(sync.testWals.single.conversationId, 'conversation-1');
    expect(sync.testWals.single.totalFrames, 3);
    expect(sync.testFrames, hasLength(2), reason: 'the old close cannot drain later ingress');

    await sync.stampConversationSnapshot(await cut(), 'conversation-2');
    expect(sync.testWals.map((wal) => wal.totalFrames), [3, 2]);
    expect(sync.testWals.map((wal) => wal.conversationId), ['conversation-1', 'conversation-2']);
    expect(sync.testWals.map((wal) => wal.sourceFrameStart), [0, 3]);
  });

  test('a cut stays exclusive while persistence awaits and responses finish out of order', () async {
    capture(0, 4);
    persistBarrier = Completer<void>();
    persistStarted = Completer<void>();
    final first = cut();
    await persistStarted!.future;

    capture(4, 5);
    final second = cut();
    expect(sync.testWals.map((wal) => wal.totalFrames), [4, 5]);
    persistBarrier!.complete();

    await sync.stampConversationSnapshot(await second, 'conversation-2');
    expect(sync.testWals.map((wal) => wal.conversationId), [null, 'conversation-2']);
    await sync.stampConversationSnapshot(await first, 'conversation-1');
    expect(sync.testWals.map((wal) => wal.conversationId), ['conversation-1', 'conversation-2']);
    expect(sync.testWals.every((wal) => wal.storage == WalStorage.disk), isTrue);
  });

  test('an unknown earlier close is not absorbed by a later cut in the same second and recording', () async {
    capture(0, 6);
    final unknownResult = await cut();
    capture(6, 7);
    final later = await cut();
    await sync.stampConversationSnapshot(later, 'conversation-2');

    expect(sync.testWals.map((wal) => wal.totalFrames), [6, 7]);
    expect(sync.testWals.map((wal) => wal.conversationId), [null, 'conversation-2']);
    await sync.stampConversationSnapshot(unknownResult, 'conversation-1');
    await sync.stampConversationSnapshot(later, 'wrong-second-id');
    expect(sync.testWals.map((wal) => wal.conversationId), ['conversation-1', 'conversation-2']);
  });

  for (final evidence in [false, true]) {
    test('a queued chunk cannot extend a reserved ${evidence ? 'evidence' : 'legacy'} memory WAL', () async {
      // The chunk and close share a second-rounded start. A chunk already
      // queued before close must make a distinct row for post-cut ingress.
      sync.setDeviceInfo('external-audio', 'External Audio');
      final old = Wal(
        codec: BleAudioCodec.opus,
        timerStart: scheduler.clock.now().millisecondsSinceEpoch ~/ 1000 + 59,
        data: [
          [1],
          [2],
          [3],
        ],
        storage: WalStorage.mem,
        status: WalStatus.miss,
        device: 'external-audio',
        totalFrames: 3,
        seconds: 0,
        ownerUid: 'owner-a',
        recordingSessionId: 'recording-1',
        captureRoot: evidence ? 'capture-root' : null,
        sourceFrameStart: evidence ? 0 : null,
        sourceClockEpoch: evidence ? 0 : null,
      );
      sync.testWals = [old];
      final barrier = Completer<void>();
      final queued = sync.testQueueWalIo(barrier.future);
      scheduler.elapse(const Duration(seconds: 75));
      final snapshot = cut();
      capture(3, 1600, root: evidence ? 'capture-root' : null);
      barrier.complete();
      await queued;
      await scheduler.waitForCallbackIo();
      await sync.stampConversationSnapshot(await snapshot, 'conversation-1');

      expect(old.totalFrames, 3, reason: 'closed row identities must also freeze their admitted payload extent');
      expect(old.conversationId, 'conversation-1');
      expect(sync.testWals, hasLength(2));
      expect(sync.testWals.last.totalFrames, 100);
      expect(sync.testWals.last.conversationId, isNull);
      expect(sync.testFrames, hasLength(1500));
    });
  }

  test('an account reset invalidates a queued cut without draining successor frames', () async {
    final barrier = Completer<void>();
    final queued = sync.testQueueWalIo(barrier.future);
    capture(0, 3);
    final stale = sync.finalizeAndSnapshotSession(sessionStartSeconds: getStart(), recordingSessionId: 'recording-1');
    sync.clearUserData();
    SharedPreferencesUtil().uid = 'owner-b';
    sync.setActiveRecordingSessionId('recording-2');
    capture(3, 2);

    barrier.complete();
    await queued;
    expect(await stale, isNull);
    expect(sync.testFrames, hasLength(2));
    expect(sync.testWals, isEmpty);
    expect(sync.testRetiredWals.single.conversationId, isNull);
    await sync.stampConversationSnapshot(await cut(recording: 'recording-2'), 'owner-b-conversation');
    expect(sync.testWals.single.ownerUid, 'owner-b');
    expect(sync.testWals.single.conversationId, 'owner-b-conversation');
    expect(sync.testRetiredWals.single.conversationId, isNull);
  });

  test('a snapshot cannot stamp another ledger or an identity reconstructed from its metadata', () async {
    capture(0, 3);
    final snapshot = await cut();
    final original = sync.testWals.single;
    final replacement = Wal.fromJson(original.toJson());
    final other = LocalWalSyncImpl(_Listener());
    other.testWals = [replacement];
    await other.stampConversationSnapshot(snapshot, 'wrong-ledger');
    expect(replacement.conversationId, isNull);

    sync.testWals = [replacement];
    await sync.stampConversationSnapshot(snapshot, 'reconstructed-row');
    expect(replacement.conversationId, isNull);
    expect(original.conversationId, isNull);
  });

  test('a snapshot does not cross an owner change or overwrite an existing conversation', () async {
    capture(0, 3);
    final snapshot = await cut();
    SharedPreferencesUtil().uid = 'owner-b';
    await sync.stampConversationSnapshot(snapshot, 'wrong-owner');
    expect(sync.testWals.single.conversationId, isNull);
    SharedPreferencesUtil().uid = 'owner-a';
    sync.testWals.single.conversationId = 'existing-conversation';
    await sync.stampConversationSnapshot(snapshot, 'replacement-conversation');
    expect(sync.testWals.single.conversationId, 'existing-conversation');
  });

  test('a recording match covers backdated chunks while unrelated and confirmed rows stay intact', () async {
    Wal row(String? recording, int start, {String owner = 'owner-a', String? conversation}) => Wal(
          codec: BleAudioCodec.opus,
          timerStart: start,
          seconds: 1,
          totalFrames: 100,
          storage: WalStorage.disk,
          status: WalStatus.miss,
          ownerUid: owner,
          recordingSessionId: recording,
          conversationId: conversation,
        );
    final through = scheduler.clock.now().millisecondsSinceEpoch ~/ 1000;
    final backdated = row('recording-1', through - 600);
    final unlinked = row(null, through - 1);
    final unrelated = row('other-recording', through - 1);
    final foreign = row('recording-1', through - 1, owner: 'other-owner');
    final linked = row('recording-1', through - 1, conversation: 'existing-conversation');
    sync.testWals = [backdated, unlinked, unrelated, foreign, linked];

    await sync.stampConversationSnapshot(await cut(), 'conversation-1');
    expect(backdated.conversationId, 'conversation-1');
    expect(unlinked.conversationId, 'conversation-1');
    expect(unrelated.conversationId, isNull);
    expect(foreign.conversationId, isNull);
    expect(linked.conversationId, 'existing-conversation');
    expect(
      [...sync.testWals, ...sync.testForeignWals, ...sync.testRetiredWals],
      containsAll([backdated, unlinked, unrelated, foreign, linked]),
      reason: 'foreign-account rows may be parked by native intake, but no source row is removed',
    );
  });

  test('transport-only safety copies retain coverage metadata and wait for transcript confirmation', () async {
    capture(0, 100, transportSynced: true);
    final snapshot = await cut();
    final wal = sync.testWals.single;
    await sync.stampConversationSnapshot(snapshot, 'conversation-1');

    expect(wal.status, WalStatus.synced);
    expect(wal.syncedAt, 0, reason: 'linkage alone is not durable transcript coverage');
    expect(wal.syncedFrameOffset, 100);
    expect(wal.captureRoot, 'capture-root');
    expect(wal.sourceFrameStart, 0);
    expect(wal.sourceClockEpoch, 0);
    expect(wal.recordingSessionId, 'recording-1');
    expect(wal.ownerUid, 'owner-a');
    expect(wal.conversationId, 'conversation-1');
    expect(wal.storage, WalStorage.disk);
    expect(await File((await Wal.getFilePath(wal.filePath!))!).exists(), isTrue);
    expect((await WalFileManager.loadWals()).single.conversationId, 'conversation-1');
  });
}
