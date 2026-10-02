// Live phone-mic audio stays in the phone's WAL until the server's transcript confirms it, as pendant
// audio does (#20366). A socket send is not a save. These scenarios drive the real CaptureController,
// native mic service and LocalWalSyncImpl over the replay world.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/gen/phone_mic_pigeon.g.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/utils/wal_file_manager.dart';

import '../../support/capture/capture_replay_world.dart';

void main() {
  late Directory directory;
  late CaptureReplayWorld world;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('capture_phone_backup_');
    world = await CaptureReplayWorld.boot(tempDir: directory);
  });

  tearDown(() async {
    await world.dispose();
    if (directory.existsSync()) directory.deleteSync(recursive: true);
  });

  /// Finalize, stamp and confirm write real files outside the virtual scheduler, so let real time
  /// pass until the WAL index stops changing.
  Future<void> settleFiles() async {
    var last = '';
    for (var i = 0; i < 40; i++) {
      await world.settle();
      await Future<void>.delayed(const Duration(milliseconds: 50));
      final wals = await world.wal.syncs.phone.getAllWals();
      final now = [
        for (final wal in wals) '${wal.id}:${wal.status.name}:${wal.conversationId}',
        'uploads=${world.uploads.attempts.length}',
      ].join(',');
      if (now == last && i >= 3) return;
      last = now;
    }
  }

  /// Waits, in real time, until the phone's WALs satisfy [done] in memory and in the saved index, and
  /// fails with their state if they never do. Writing, stamping and releasing copies touch real files
  /// outside the virtual scheduler, so a quiet moment does not prove they are done; and a change only
  /// counts once it is saved, because an app kill reloads the index.
  Future<List<Wal>> walsReach(String expectation, bool Function(List<Wal> wals) done) async {
    for (var i = 0; i < 200; i++) {
      final wals = await world.wal.syncs.phone.getAllWals();
      if (done(wals) && done(await WalFileManager.loadWals())) return wals;
      await world.settle();
      await Future<void>.delayed(const Duration(milliseconds: 50));
    }
    final wals = await world.wal.syncs.phone.getAllWals();
    final state = [
      for (final wal in wals) '${wal.timerStart}+${wal.seconds}s ${wal.status.name} conv=${wal.conversationId}'
    ];
    fail('WALs never reached "$expectation": ${state.join('; ')}');
  }

  int totalSeconds(List<Wal> wals) => wals.fold<int>(0, (total, wal) => total + wal.seconds);

  /// The controller asks for recovery through its session owner; the replay world has none, so wake
  /// the world's coordinator the way that request would.
  Future<void> recoveryPass() async {
    await world.coordinator.wake(WakeTrigger.dataStalled);
    await settleFiles();
  }

  /// Records [seconds] of phone-mic audio with the socket connected the whole time, then stops.
  Future<void> recordOnline(int seconds) async {
    await world.startLiveCapture();
    final session = world.hostApi.lastStartSessionId!;
    world.emitNativeState(PhoneMicCaptureState.running);
    for (var s = 0; s < seconds; s++) {
      world.injectAudioFrames(100, sessionId: session, firstFrameIndex: s * 100);
      await world.elapse(const Duration(seconds: 1));
    }
    expect(world.socket!.sentBinary, hasLength(seconds * 100), reason: 'every frame reached the server');
    await world.stopLiveCapture();
    await settleFiles();
  }

  ServerConversation conversation(String id, DateTime startedAt, List<(double, double)> spans) => ServerConversation(
        id: id,
        createdAt: startedAt,
        startedAt: startedAt,
        structured: Structured('fixture', 'fixture'),
        transcriptSegments: [
          for (final (i, span) in spans.indexed)
            TranscriptSegment(
              id: '$id-s$i',
              text: 'words',
              speaker: 'SPEAKER_00',
              isUser: true,
              personId: null,
              start: span.$1,
              end: span.$2,
              translations: [],
            ),
        ],
      );

  Future<void> serverCloses(ServerConversation memory) async {
    world.controller.onMessageEventReceived(ConversationProcessingStartedEvent(memory: memory));
    await settleFiles();
    world.controller.onMessageEventReceived(ConversationEvent(memory: memory, messages: []));
    await settleFiles();
  }

  test('phone mic: a recording the server never transcribed stays on the phone and is uploaded', () async {
    await recordOnline(130);

    // Sent audio is kept until a transcript confirms it.
    await walsReach('at least 120 s kept', (wals) => totalSeconds(wals) >= 120);
    await recoveryPass();
    expect(world.uploads.attempts, isNotEmpty, reason: 'the recovery pass sends the audio for repair');
    await walsReach(
        'nothing left waiting after the upload', (wals) => wals.every((wal) => wal.status != WalStatus.miss));
  });

  test('phone mic: a conversation with no saved text uploads the recording for repair', () async {
    final origin = world.clock.now();
    await recordOnline(130);

    await serverCloses(conversation('c1', origin, const []));
    await walsReach(
        'every copy stamped c1', (wals) => wals.isNotEmpty && wals.every((wal) => wal.conversationId == 'c1'));
    await recoveryPass();

    expect(world.uploads.attempts, isNotEmpty);
    expect(world.uploads.attempts.map((attempt) => attempt.conversationId).toSet(), {'c1'});
  });

  test('phone mic: a recording bound after the stop does not orphan the stopped one', () async {
    final origin = world.clock.now();
    await recordOnline(130);

    // A newer recording binds to the WAL store before the server closes c1.
    world.wal.syncs.phone.setActiveRecordingSessionId('a-newer-recording');
    await serverCloses(conversation('c1', origin, const []));

    await walsReach(
        'every copy stamped c1', (wals) => wals.isNotEmpty && wals.every((wal) => wal.conversationId == 'c1'));
  });

  test('phone mic: a transcript that covers the recording releases the copy without uploading', () async {
    final origin = world.clock.now();
    await recordOnline(130);

    await serverCloses(conversation('c1', origin, [for (var t = 1.0; t < 125; t += 20) (t, t + 15)]));
    await walsReach('every copy released', (wals) => wals.isEmpty);

    await recoveryPass();
    expect(world.uploads.attempts, isEmpty, reason: 'transcribed audio is not uploaded again');
  });

  test('phone mic: the capture screen counts only audio the socket did not take', () async {
    await world.startLiveCapture();
    final session = world.hostApi.lastStartSessionId!;
    world.emitNativeState(PhoneMicCaptureState.running);
    Future<void> record(int from, int to) async {
      for (var s = from; s < to; s++) {
        world.injectAudioFrames(100, sessionId: session, firstFrameIndex: s * 100);
        await world.elapse(const Duration(seconds: 1));
      }
    }

    // 110 s online: the first minute is chunked at 75 s and written to disk at 105 s.
    await record(0, 110);
    await walsReach('a streamed copy saved to disk', (wals) => wals.any((wal) => wal.storage == WalStorage.disk));
    expect(world.wal.syncs.phone.getSessionUnsyncedWals(0), isEmpty,
        reason: 'the copy is kept, but nothing is at risk');
    expect(world.controller.unsyncedSessionWals, isEmpty);
    expect(world.controller.inFlightAudioSeconds, 0, reason: 'every frame in memory reached the socket');

    world.setConnected(false);
    world.socket!.emitClose();
    await world.settle();
    await record(110, 130);
    expect(world.controller.inFlightAudioSeconds, 20, reason: 'the 20 s no socket took are at risk until saved');
  });
}
