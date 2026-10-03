// A recording can run on into the next conversation, so the stamp for a closing conversation is fenced
// to the WALs that existed when it closed (#20365).
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

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

void main() {
  Wal wal(int timerStart) => Wal(
        timerStart: timerStart,
        codec: BleAudioCodec.opus,
        seconds: 60,
        storage: WalStorage.disk,
        status: WalStatus.miss,
        recordingSessionId: 'recording-1',
      );

  LocalWalSyncImpl syncWith(List<Wal> wals) => LocalWalSyncImpl(
        _Listener(),
        now: () => DateTime.fromMillisecondsSinceEpoch(10000 * 1000),
        persistWals: (_) async {},
      )..testWals = wals;

  test('the stamp leaves WALs created after the close to the next conversation', () async {
    final backdated = wal(940);
    final closing = wal(1000);
    final sync = syncWith([backdated, closing]);
    final walsAtClose = sync.walIdsNow();
    // Created after the close, so the next conversation's, even when the start is backdated before it.
    final nextBackdated = wal(990);
    final next = wal(1200);
    sync.testWals = [backdated, closing, nextBackdated, next];

    sync.prepareConversationStamp('recording-1', walsAtClose: walsAtClose);
    await sync.stampConversationId(1000, 'c1');

    expect(backdated.conversationId, 'c1', reason: 'a backdated WAL of the same recording still belongs to c1');
    expect(closing.conversationId, 'c1');
    expect(nextBackdated.conversationId, isNull, reason: 'it was created after the close');
    expect(next.conversationId, isNull, reason: 'the recording went on into the next conversation');
  });

  test('the fence holds for one stamp only', () async {
    final next = wal(1200);
    final sync = syncWith([next]);

    sync.prepareConversationStamp('recording-1', walsAtClose: const {});
    await sync.stampConversationId(1000, 'c1');
    expect(next.conversationId, isNull);

    sync.prepareConversationStamp('recording-1');
    await sync.stampConversationId(1000, 'c2');
    expect(next.conversationId, 'c2', reason: 'a stamp prepared without a fence keeps its old reach');
  });

  group('a drain at the close', () {
    const pathProvider = MethodChannel('plugins.flutter.io/path_provider');
    late Directory directory;

    setUp(() async {
      TestWidgetsFlutterBinding.ensureInitialized();
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
      directory = await Directory.systemTemp.createTemp('wal_stamp_fence_');
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        pathProvider,
        (call) async => call.method == 'getApplicationDocumentsDirectory' ? directory.path : null,
      );
    });

    tearDown(() {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(pathProvider, null);
      if (directory.existsSync()) directory.deleteSync(recursive: true);
    });

    test('leaves even a sub-second tail to the conversation closing', () async {
      final sync = LocalWalSyncImpl(_Listener(), now: () => DateTime.fromMillisecondsSinceEpoch(10000 * 1000));
      sync.setActiveRecordingSessionId('recording-1');
      // Half a second at 100 frames per second: a close that comes right after the previous drain.
      for (var i = 0; i < 50; i++) {
        sync.onFrameCaptured(WalFrame(payload: [i], syncKey: FrameSyncKey([i])));
      }
      final drained = sync.finalizeCurrentSession();
      final walsAtClose = sync.walIdsNow();
      await drained;
      final tail = sync.testWals.single;
      expect(tail.timerStart, 10000, reason: "half a second rounds to the close's own second, so time can't fence it");

      sync.prepareConversationStamp('recording-1', walsAtClose: walsAtClose);
      await sync.stampConversationId(9990, 'c1');
      expect(tail.conversationId, 'c1');
    });
  });
}
