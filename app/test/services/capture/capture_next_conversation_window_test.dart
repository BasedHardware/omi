// A pendant socket stays open across the conversations the server closes on silence (#20365). These
// scenarios drive the real CaptureController and LocalWalSyncImpl over the replay world and check
// that every conversation's safety copy is stamped and released, not only the first one's.
import 'dart:async';
import 'dart:io';
import 'dart:math' show min;

import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';

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

  /// A conversation whose saved transcript covers all of it, in segments of up to 15 s.
  ServerConversation conversation(String id, DateTime startedAt, int seconds) => ServerConversation(
        id: id,
        createdAt: startedAt,
        startedAt: startedAt,
        structured: Structured('fixture', 'fixture'),
        transcriptSegments: [
          for (var t = 0; t < seconds; t += 15)
            TranscriptSegment(
              id: '$id-s$t',
              text: 'words',
              speaker: 'SPEAKER_00',
              isUser: false,
              personId: null,
              start: t.toDouble(),
              end: min(t + 15, seconds).toDouble(),
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

  /// Fails unless the streamed audio is in a copy, so a later release can't pass on no copies at all.
  Future<void> expectCopies(String reason, {int fromSeconds = 0}) async {
    final wals = await world.wal.syncs.phone.getAllWals();
    expect(wals.where((wal) => wal.timerStart >= fromSeconds), isNotEmpty, reason: reason);
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
      await expectCopies('$id streamed into a copy before it closed');
      await serverCloses(conversation(id, start, 140));
      await walsReach('$id released like the first conversation', (wals) => wals.isEmpty);
    }

    await recoveryPass();
    expect(world.socketCreates, sockets, reason: 'all three conversations share one live socket');
    expect(world.uploads.attempts, isEmpty, reason: 'audio the server already transcribed is not uploaded again');
  });

  test("pendant: the next conversation's copies keep the recording's location", () async {
    world.locationFix = Position(
      latitude: 37.77,
      longitude: -122.42,
      timestamp: world.clock.now(),
      accuracy: 8,
      altitude: 0,
      altitudeAccuracy: 0,
      heading: 0,
      headingAccuracy: 0,
      speed: 0,
      speedAccuracy: 0,
    );
    final link = await connectPendant();
    final firstStart = world.clock.now();
    await streamPendant(link, 140);
    final firstCopies = await world.wal.syncs.phone.getAllWals();
    expect(firstCopies, isNotEmpty, reason: 'c1 streamed into a copy before it closed');
    expect(firstCopies.map((wal) => wal.geolocation?.latitude), everyElement(37.77),
        reason: "c1's copies carry the location captured when the recording started");
    await serverCloses(conversation('c1', firstStart, 140));
    await walsReach('c1 released', (wals) => wals.isEmpty);

    await streamPendant(link, 140);
    final secondCopies = await world.wal.syncs.phone.getAllWals();
    expect(secondCopies, isNotEmpty, reason: 'c2 streamed into a copy');
    expect(secondCopies.map((wal) => wal.geolocation?.latitude), everyElement(37.77),
        reason: "the recording goes on into c2, so c2's copies keep its location");
  });

  test('pendant: each conversation after the first gets its own capture identity', () async {
    final link = await connectPendant();
    await streamPendant(link, 5);
    final first = world.controller.activeCaptureSessionId;
    expect(first, isNotNull);

    await streamPendant(link, 135);
    await expectCopies('c1 streamed into a copy before it closed');
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
    await expectCopies('c1 streamed into a copy before the mute');
    await world.controller.pauseDeviceRecording();
    await world.settle();
    await serverCloses(conversation('c1', origin, 140));
    await walsReach('the muted conversation released', (wals) => wals.isEmpty);

    await world.controller.resumeDeviceRecording();
    await world.settle();
    final start = world.clock.now();
    await streamPendant(link, 140);
    await expectCopies('audio after the unmute is in a copy before c2 closes');
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
    await expectCopies('the next conversation streamed into its own copy', fromSeconds: startSeconds);
    await serverCloses(conversation('c2', start, 140));
    await walsReach('the next conversation released', (wals) => wals.every((wal) => wal.timerStart < startSeconds));
  });

  test('pendant: a late conversation event leaves the next close to its own event', () async {
    final link = await connectPendant();
    final firstStart = world.clock.now();
    await streamPendant(link, 140);
    world.controller
        .onMessageEventReceived(ConversationProcessingStartedEvent(memory: conversation('c1', firstStart, 140)));
    await settleFiles();

    // The server is slow: c1's event misses its 30 s fallback, and the next conversation closes first.
    final secondStart = world.clock.now();
    final secondSeconds = secondStart.millisecondsSinceEpoch ~/ 1000;
    await streamPendant(link, 140);
    await expectCopies('c2 streamed into a copy before it closed', fromSeconds: secondSeconds);
    final c2 = conversation('c2', secondStart, 140);
    world.controller.onMessageEventReceived(ConversationProcessingStartedEvent(memory: c2));
    await settleFiles();
    world.controller
        .onMessageEventReceived(ConversationEvent(memory: conversation('c1', firstStart, 140), messages: []));
    await settleFiles();
    final afterLateEvent = await world.wal.syncs.phone.getAllWals();
    expect(afterLateEvent.where((wal) => wal.conversationId == 'c2'), isNotEmpty,
        reason: "c1's late event leaves c2's close, and its copies, alone");
    world.controller.onMessageEventReceived(ConversationEvent(memory: c2, messages: []));

    await walsReach('c2 released by its own event', (wals) => wals.every((wal) => wal.timerStart < secondSeconds));
  });

  test('pendant: closes that come back to back stamp in close order', () async {
    final link = await connectPendant();
    final firstStart = world.clock.now();
    await streamPendant(link, 140);
    await expectCopies('c1 streamed into a copy before it closed');

    // c2 closes before c1's stamp is on disk. c2's drain has nothing to write, so it finishes first, and
    // every copy of c1, under the same recording id, is also among the WALs at c2's close.
    world.controller
        .onMessageEventReceived(ConversationProcessingStartedEvent(memory: conversation('c1', firstStart, 140)));
    world.controller
        .onMessageEventReceived(ConversationProcessingStartedEvent(memory: conversation('c2', world.clock.now(), 0)));

    await walsReach(
      "c1's copies stamped with c1, not with the close after it",
      (wals) => wals.isNotEmpty && wals.every((wal) => wal.conversationId == 'c1'),
    );
  });

  test('pendant: windows that open in the same second name different conversations', () async {
    final link = await connectPendant();
    await streamPendant(link, 140);
    world.controller
        .onMessageEventReceived(ConversationProcessingStartedEvent(memory: conversation('c1', world.clock.now(), 140)));
    await settleFiles();
    final first = world.controller.activeCaptureSessionId;

    // The next conversation closes within the same second.
    world.controller
        .onMessageEventReceived(ConversationProcessingStartedEvent(memory: conversation('c2', world.clock.now(), 0)));
    await settleFiles();
    final second = world.controller.activeCaptureSessionId;

    expect(first, isNotNull);
    expect(second, isNotNull);
    expect(second, isNot(first));
  });

  test('pendant: audio from a Process now that made no conversation goes with the conversation kept open', () async {
    // The replay world's processInProgressConversation returns null, as a failed request does.
    final origin = world.clock.now();
    final link = await connectPendant();
    await streamPendant(link, 140);
    await world.controller.forceProcessingCurrentConversation();
    await settleFiles();
    final beforeProcessNow = await world.wal.syncs.phone.getAllWals();
    expect(beforeProcessNow, isNotEmpty, reason: 'the audio before Process now is in a copy');
    expect(beforeProcessNow.every((wal) => wal.conversationId == null), isTrue,
        reason: 'no conversation id came back to stamp it with');

    // The server kept the conversation open, so the close it sends holds both parts.
    await streamPendant(link, 140);
    world.controller
        .onMessageEventReceived(ConversationProcessingStartedEvent(memory: conversation('c1', origin, 280)));
    await walsReach(
      'the audio before Process now stamped with the conversation the server kept open',
      (wals) => wals.length > beforeProcessNow.length && wals.every((wal) => wal.conversationId == 'c1'),
    );
  });

  test('pendant: a close during Process now stamps after the conversation Process now made', () async {
    final processed = Completer<CreateConversationResponse?>();
    world.processResponse = () => processed.future;
    final origin = world.clock.now();
    final link = await connectPendant();
    await streamPendant(link, 140);
    await world.controller.forceProcessingCurrentConversation();
    await settleFiles();
    final beforeProcessNow = await world.wal.syncs.phone.getAllWals();
    expect(beforeProcessNow, isNotEmpty, reason: 'the audio before Process now is in a copy');

    // The server is slow to answer, and the next conversation closes first. Every copy from before
    // Process now, under the same recording id, is also among the WALs at that close.
    final secondStart = world.clock.now();
    final secondSeconds = secondStart.millisecondsSinceEpoch ~/ 1000;
    await streamPendant(link, 140);
    await expectCopies('c2 streamed into a copy before it closed', fromSeconds: secondSeconds);
    await serverCloses(conversation('c2', secondStart, 140));
    processed.complete(CreateConversationResponse(messages: [], conversation: conversation('p1', origin, 140)));

    await walsReach(
        "c2's copies released by its own event", (wals) => wals.every((wal) => wal.timerStart < secondSeconds));
    expect(beforeProcessNow.map((wal) => wal.conversationId), everyElement('p1'),
        reason: 'the audio before Process now goes with the conversation it made, not the close after it');
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
    final sockets = world.sockets.length;
    final transport = world.sockets.last.transport;
    final sentBeforeResume = transport.sentBinary.length + transport.sentText.length;
    for (var s = 30; s < 60; s++) {
      world.injectAudioFrames(100, sessionId: session, firstFrameIndex: s * 100);
      await world.elapse(const Duration(seconds: 1));
    }

    expect(world.sockets, hasLength(sockets), reason: 'the resumed audio needs no new socket');
    expect(transport.sentBinary.length + transport.sentText.length, greaterThan(sentBeforeResume),
        reason: 'the resumed audio streams on the socket that outlived c1');
    expect(world.controller.activeCaptureSessionId, next, reason: "it streams into the window opened at c1's close");
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
