import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart' show AppLifecycleState;
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
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

/// A phone-mic live session streams frames over the socket, which marks them
/// synced at transport send. Those frames must still become durable safety
/// copies: a send is not server confirmation, and until the session transcript
/// (or an upload) confirms coverage the audio must survive a kill on disk.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory tempDir;
  late ManualScheduler scheduler;
  late LocalWalSyncImpl sync;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    tempDir = await Directory.systemTemp.createTemp('phone_mic_safety_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (MethodCall call) async {
        if (call.method == 'getApplicationDocumentsDirectory') return tempDir.path;
        return null;
      },
    );
    await WalFileManager.init();
    scheduler = ManualScheduler(clock: VirtualClock(DateTime.utc(2026, 10, 29)));
    sync = LocalWalSyncImpl(
      _Listener(),
      periodic: scheduler.periodic,
      freeDiskBytes: () async => 1 << 40,
      persistWals: WalFileManager.saveWals,
    );
    sync.setDeviceInfo('phone-mic', 'Phone Microphone');
    sync.start();
    await sync.walReady;
  });

  tearDown(() async {
    await sync.stop();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
  });

  FrameSyncKey key(int counter) => FrameSyncKey([counter & 0xFF, (counter >> 8) & 0xFF]);

  Future<void> captureTransportSynced(int frames) async {
    for (var i = 0; i < frames; i++) {
      final frame = WalFrame(payload: [0xAA, i & 0xFF], syncKey: key(i));
      sync.onFrameCaptured(frame);
      // The socket-send path marks the frame synced without any server receipt.
      sync.markFrameSynced(frame.syncKey);
    }
    await Future<void>.delayed(const Duration(milliseconds: 150));
  }

  test('fully transport-synced phone-mic chunks are stored as safety copies, not dropped', () async {
    // 60s of audio at the default 100 fps. The 10-second live-tail drain
    // stores a safety copy long before the 75s chunk timer would.
    await captureTransportSynced(6000);
    expect(sync.testWals, isEmpty, reason: 'nothing stored before a drain runs');

    scheduler.elapse(const Duration(seconds: 10));
    await Future<void>.delayed(const Duration(milliseconds: 150));

    expect(sync.testWals, isNotEmpty);
    final wal = sync.testWals.first;
    expect(wal.status, WalStatus.synced, reason: 'all frames were transport-marked synced');
    expect(wal.syncedAt, 0, reason: 'a transport send must not start the retention clock');
    expect(wal.syncedFrameOffset, wal.totalFrames);
    expect(wal.device, 'phone-mic');
    expect(wal.storage, WalStorage.disk, reason: 'the drain flushes before it returns');
  });

  test('lifecycle pause seals the phone-mic tail before the app can be killed', () async {
    // 5s of audio: below every batch boundary, so only a pause seal can reach it.
    await captureTransportSynced(500);
    expect(sync.testWals, isEmpty);

    sync.didChangeAppLifecycleState(AppLifecycleState.paused);
    await Future<void>.delayed(const Duration(milliseconds: 60));

    expect(sync.testWals, hasLength(1));
    final wal = sync.testWals.single;
    expect(wal.totalFrames, 500);
    expect(wal.status, WalStatus.synced);
    expect(wal.syncedAt, 0);
    expect(wal.storage, WalStorage.disk, reason: 'the seal must flush the copy to disk before suspension');
  });

  test('transport-only synced safety copies bind to the conversation and confirm or repair', () async {
    await captureTransportSynced(6000);
    // One 10-second drain produces exactly one durable safety copy.
    scheduler.elapse(const Duration(seconds: 10));
    await Future<void>.delayed(const Duration(milliseconds: 150));
    final wal = sync.testWals.single;
    expect(wal.syncedAt, 0);
    expect(wal.storage, WalStorage.disk);

    // Conversation linkage is what lets the end-of-session confirmation judge
    // the copy; before the fix this stamp skipped transport-only synced rows.
    final sessionStart = wal.timerStart - 60;
    await sync.stampConversationId(sessionStart, 'conv-1');
    expect(sync.testWals.single.conversationId, 'conv-1');

    // Covered by the saved transcript: released into server-confirmed retention.
    final covered = await sync.confirmSessionTranscription(
      sessionStart,
      'conv-1',
      transcriptSpans: [(wal.timerStart, wal.timerStart + wal.seconds)],
      conversationStartSeconds: sessionStart,
    );
    expect(sync.testWals.single.status, WalStatus.synced);
    expect(sync.testWals.single.syncedAt, greaterThan(0));
    expect(covered.kept, 0);

    // Not covered (the transcript missed the tail): fail closed into repair so
    // the drain uploads what the server lost.
    final wal2 = sync.testWals.single
      ..status = WalStatus.synced
      ..syncedAt = 0;
    final kept = await sync.confirmSessionTranscription(
      sessionStart,
      'conv-1',
      transcriptSpans: [(wal2.timerStart + 3600, wal2.timerStart + 3600 + wal2.seconds)],
      conversationStartSeconds: sessionStart,
    );
    expect(sync.testWals.single.status, WalStatus.miss, reason: 'uncovered copies reclassify for repair upload');
    expect(sync.testWals.single.keptForTranscriptRecovery, isTrue);
    expect(kept.kept, 1);
    expect(isAutoUploadEligible(sync.testWals.single), isTrue, reason: 'the repair copy must be upload-eligible');
  });
}
