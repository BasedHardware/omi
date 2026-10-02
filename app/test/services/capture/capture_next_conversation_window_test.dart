// A pendant socket stays open across the conversations the server closes on silence (#20365). These
// scenarios drive the real CaptureController and LocalWalSyncImpl over the replay world and check
// that every conversation's safety copy is stamped and released, not only the first one's.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/gen/phone_mic_pigeon.g.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/utils/wal_file_manager.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';

void main() {
  late Directory directory;
  late CaptureReplayWorld world;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('capture_next_window_');
    world = await CaptureReplayWorld.boot(tempDir: directory, pendantCodec: BleAudioCodec.opus);
  });

  tearDown(() async {
    await world.dispose();
    if (directory.existsSync()) directory.deleteSync(recursive: true);
  });

  final pendant = BtDevice(id: 'pendant-1', name: 'Omi', type: DeviceType.omi, rssi: -40);

  Future<ScriptedDeviceConnection> connectPendant() async {
    final link = ScriptedDeviceConnection();
    world.deviceConnection = link;
    await world.controller.streamDeviceRecording(device: pendant);
    await world.settle();
    return link;
  }

  /// Opus pendant audio: 100 packets per virtual second.
  Future<void> streamPendant(ScriptedDeviceConnection link, int seconds) async {
    for (var s = 0; s < seconds; s++) {
      for (var i = 0; i < 100; i++) {
        link.emitAudio();
      }
      await world.elapse(const Duration(seconds: 1));
    }
  }

  /// A conversation whose saved transcript covers it in 15 s segments every 20 s.
  ServerConversation conversation(String id, DateTime startedAt, int seconds) => ServerConversation(
        id: id,
        createdAt: startedAt,
        startedAt: startedAt,
        structured: Structured('fixture', 'fixture'),
        transcriptSegments: [
          for (var t = 1; t + 15 < seconds; t += 20)
            TranscriptSegment(
              id: '$id-s$t',
              text: 'words',
              speaker: 'SPEAKER_00',
              isUser: false,
              personId: null,
              start: t.toDouble(),
              end: t + 15.0,
              translations: [],
            ),
        ],
      );

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
  /// fails with their state if they never do. Stamping and release touch real files outside the
  /// virtual scheduler, so a quiet moment does not prove they are done; and a release only counts once
  /// it is saved, because an app kill reloads the index.
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

  /// The server closes [memory]: processing starts, then the conversation arrives with its transcript.
  Future<void> serverCloses(ServerConversation memory) async {
    world.controller.onMessageEventReceived(ConversationProcessingStartedEvent(memory: memory));
    await settleFiles();
    world.controller.onMessageEventReceived(ConversationEvent(memory: memory, messages: []));
    await settleFiles();
  }

  /// The controller asks for recovery through its session owner; the replay world has none, so wake
  /// the world's coordinator the way that request would.
  Future<void> recoveryPass() async {
    await world.coordinator.wake(WakeTrigger.dataStalled);
    await settleFiles();
  }

  test('pendant: every conversation on one socket gets its copy stamped and released', () async {
    final link = await connectPendant();
    final sockets = world.socketCreates;

    for (final id in ['c1', 'c2', 'c3']) {
      final start = world.clock.now();
      await streamPendant(link, 140);
      await serverCloses(conversation(id, start, 140));
      await walsReach('$id released like the first conversation', (wals) => wals.isEmpty);
    }

    await recoveryPass();
    expect(world.socketCreates, sockets, reason: 'all three conversations share one live socket');
    expect(world.uploads.attempts, isEmpty, reason: 'audio the server already transcribed is not uploaded again');
  });

  test('pendant: each conversation after the first gets its own capture identity', () async {
    final link = await connectPendant();
    await streamPendant(link, 5);
    final first = world.controller.activeCaptureSessionId;
    expect(first, isNotNull);

    await streamPendant(link, 135);
    await serverCloses(conversation('c1', world.clock.now().subtract(const Duration(seconds: 140)), 140));
    await walsReach('c1 released', (wals) => wals.isEmpty);
    await streamPendant(link, 5);

    final second = world.controller.activeCaptureSessionId;
    expect(second, isNotNull, reason: 'the pendant is still streaming into the next conversation');
    expect(second, isNot(first));
  });

  test('pendant: a conversation closed while muted still has the audio after unmute released', () async {
    final origin = world.clock.now();
    final link = await connectPendant();

    await streamPendant(link, 140);
    await world.controller.pauseDeviceRecording();
    await world.settle();
    await serverCloses(conversation('c1', origin, 140));
    await walsReach('the muted conversation released', (wals) => wals.isEmpty);

    await world.controller.resumeDeviceRecording();
    await world.settle();
    final start = world.clock.now();
    await streamPendant(link, 140);
    await serverCloses(conversation('c2', start, 140));
    await walsReach('audio after the unmute released with the next conversation', (wals) => wals.isEmpty);

    await recoveryPass();
    expect(world.uploads.attempts, isEmpty, reason: 'audio the server already transcribed is not uploaded again');
  });

  test('pendant: Process now opens the window the next conversation needs', () async {
    final link = await connectPendant();
    await streamPendant(link, 140);
    await world.controller.forceProcessingCurrentConversation();
    await settleFiles();
    expect(world.controller.activeCaptureSessionId, isNotNull,
        reason: 'the pendant streams on into the next conversation');

    final start = world.clock.now();
    final startSeconds = start.millisecondsSinceEpoch ~/ 1000;
    await streamPendant(link, 140);
    await serverCloses(conversation('c2', start, 140));
    await walsReach('the next conversation released', (wals) => wals.every((wal) => wal.timerStart < startSeconds));
  });

  test('phone mic: a conversation closed during a call opens the window the resumed audio needs', () async {
    final origin = world.clock.now();
    await world.startLiveCapture();
    final session = world.hostApi.lastStartSessionId!;
    world.emitNativeState(PhoneMicCaptureState.running);
    for (var s = 0; s < 30; s++) {
      world.injectAudioFrames(100, sessionId: session, firstFrameIndex: s * 100);
      await world.elapse(const Duration(seconds: 1));
    }
    world.emitNativeState(PhoneMicCaptureState.interrupted);
    await world.settle();

    world.controller.onMessageEventReceived(ConversationProcessingStartedEvent(memory: conversation('c1', origin, 30)));
    await settleFiles();
    final next = world.controller.activeCaptureSessionId;
    expect(next, isNotNull, reason: 'the call ends and audio resumes on the same socket');

    world.emitNativeState(PhoneMicCaptureState.running);
    await world.settle();
    expect(world.controller.activeCaptureSessionId, next);
  });

  test('phone mic: a conversation closed after the user stopped opens no new window', () async {
    final origin = world.clock.now();
    await world.startLiveCapture();
    final session = world.hostApi.lastStartSessionId!;
    world.emitNativeState(PhoneMicCaptureState.running);
    for (var s = 0; s < 30; s++) {
      world.injectAudioFrames(100, sessionId: session, firstFrameIndex: s * 100);
      await world.elapse(const Duration(seconds: 1));
    }
    await world.stopLiveCapture();
    await world.settle();

    world.controller.onMessageEventReceived(ConversationProcessingStartedEvent(memory: conversation('c1', origin, 30)));
    await settleFiles();

    expect(world.controller.activeCaptureSessionId, isNull, reason: 'nothing is recording, so no next conversation');
  });
}
