// The phone keeps a local copy of live pendant audio (the WAL) until the server's saved transcript
// confirms it (#20364). These scenarios drive the real CaptureController and LocalWalSyncImpl over the
// replay world and check that the copy is released only for audio the saved transcript covers.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';

void main() {
  late Directory directory;
  late CaptureReplayWorld world;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('capture_safety_copy_');
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

  /// A conversation whose saved transcript has one segment per [spans] entry, in seconds from [startedAt].
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
              isUser: false,
              personId: null,
              start: span.$1,
              end: span.$2,
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

  /// Seconds of audio, from [from] (inclusive) in seconds since [origin], that the phone still holds
  /// locally or has uploaded for repair.
  Future<int> recoverableSecondsAfter(DateTime origin, int from) async {
    final originSeconds = origin.millisecondsSinceEpoch ~/ 1000;
    var seconds = 0;
    for (final wal in await world.wal.syncs.phone.getAllWals()) {
      final start = wal.timerStart - originSeconds;
      final end = start + wal.seconds;
      if (end <= from) continue;
      seconds += end - (start < from ? from : start);
    }
    return seconds;
  }

  Future<String> describeWals(DateTime origin) async {
    final originSeconds = origin.millisecondsSinceEpoch ~/ 1000;
    final rows = [
      for (final wal in await world.wal.syncs.phone.getAllWals())
        '${wal.timerStart - originSeconds}+${wal.seconds}s ${wal.status.name} conv=${wal.conversationId}',
    ];
    return '${rows.join('; ')} | uploads=${world.uploads.attempts.length}';
  }

  test('pendant: a transcript that stops early keeps the audio after it for repair', () async {
    final origin = world.clock.now();
    final link = await connectPendant();
    await streamPendant(link, 200);

    // The server saved text for the first 20 s only; the rest of the speech never reached Firestore.
    await serverCloses(conversation('c1', origin, [(1, 20)]));
    await recoveryPass();

    final kept = await recoverableSecondsAfter(origin, 60);
    printOnFailure(await describeWals(origin));
    expect(kept, greaterThanOrEqualTo(120), reason: 'audio the transcript does not cover must not be deleted');
    expect(world.uploads.attempts, isNotEmpty, reason: 'the kept audio goes to the server for repair');
    expect(world.uploads.attempts.map((attempt) => attempt.conversationId).toSet(), {'c1'});
    expect(await recoverableSecondsAfter(origin, 0) - kept, lessThan(60),
        reason: 'the first minute, which the transcript covers, is released');
  });

  test('pendant: a gap in the middle of the transcript keeps that audio for repair', () async {
    final origin = world.clock.now();
    final link = await connectPendant();
    await streamPendant(link, 200);

    // Text saved for the opening and the end; the server lost the middle.
    await serverCloses(conversation('c1', origin, [(1, 20), (180, 195)]));
    await recoveryPass();

    final wals = await world.wal.syncs.phone.getAllWals();
    printOnFailure(await describeWals(origin));
    final originSeconds = origin.millisecondsSinceEpoch ~/ 1000;
    expect(wals.map((wal) => wal.timerStart - originSeconds), [60], reason: 'only the uncovered middle minute stays');
    expect(world.uploads.attempts, hasLength(1));
  });

  test('pendant: a transcript that covers the recording still releases every copy', () async {
    final origin = world.clock.now();
    final link = await connectPendant();
    await streamPendant(link, 200);

    await serverCloses(conversation('c1', origin, [for (var t = 1.0; t < 190; t += 20) (t, t + 15)]));
    await recoveryPass();

    printOnFailure(await describeWals(origin));
    expect(await world.wal.syncs.phone.getAllWals(), isEmpty);
    expect(world.uploads.attempts, isEmpty, reason: 'transcribed audio is not uploaded again');
  });

  test('pendant: audio from before the conversation started is released, not uploaded', () async {
    final origin = world.clock.now();
    final link = await connectPendant();
    // Five quiet minutes, then a conversation that the transcript fully covers.
    await streamPendant(link, 300);
    final talkStart = origin.add(const Duration(seconds: 300));
    await streamPendant(link, 140);

    await serverCloses(conversation('c1', talkStart, [for (var t = 1.0; t < 130; t += 20) (t, t + 15)]));
    await recoveryPass();

    printOnFailure(await describeWals(origin));
    expect(await world.wal.syncs.phone.getAllWals(), isEmpty);
    expect(world.uploads.attempts, isEmpty);
  });

  test('pendant: a chunk backdated before the session start is judged by the transcript too', () async {
    final origin = world.clock.now();
    final link = await connectPendant();
    // The pendant flushes 30 s of buffered audio the moment it connects, so the first chunk's start is
    // backdated before the session window.
    for (var i = 0; i < 3000; i++) {
      link.emitAudio();
    }
    await streamPendant(link, 140);

    await serverCloses(conversation('c1', origin, [for (var t = 1.0; t < 130; t += 20) (t, t + 15)]));
    await recoveryPass();

    printOnFailure(await describeWals(origin));
    expect(await world.wal.syncs.phone.getAllWals(), isEmpty);
    expect(world.uploads.attempts, isEmpty, reason: 'transcribed audio is not uploaded again');
  });
}
