// The phone keeps a local copy of live pendant audio (the WAL) until the server's saved transcript
// confirms it (#20364). These scenarios drive the real CaptureController and LocalWalSyncImpl over the
// replay world and check the conservative rule: segment arrival times and server clock estimates can
// never prove which audio the transcript covers, so every stamped copy is kept, marked for recovery,
// and uploaded — nothing is released on timestamp evidence alone.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/utils/wal_file_manager.dart';

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

  TranscriptSegment segment(String conversationId, int index, (double, double) span) => TranscriptSegment(
        id: '$conversationId-s$index',
        text: 'words',
        speaker: 'SPEAKER_00',
        isUser: false,
        personId: null,
        start: span.$1,
        end: span.$2,
        translations: [],
      );

  /// A conversation whose saved transcript has one segment per [spans] entry, in seconds from [startedAt].
  ServerConversation conversation(String id, DateTime startedAt, List<(double, double)> spans,
          {DateTime? createdAt, bool hasStart = true}) =>
      ServerConversation(
        id: id,
        createdAt: createdAt ?? startedAt,
        startedAt: hasStart ? startedAt : null,
        structured: Structured('fixture', 'fixture'),
        transcriptSegments: [for (final (i, span) in spans.indexed) segment(id, i, span)],
      );

  /// Streams the pendant for [seconds] while the server sends [spans] as live segments of conversation
  /// [id], each two seconds after it ends, as transcription does.
  Future<void> streamWithLiveSegments(
    ScriptedDeviceConnection link,
    int seconds,
    String id,
    List<(double, double)> spans,
  ) async {
    for (var s = 1; s <= seconds; s++) {
      await streamPendant(link, 1);
      for (final (i, span) in spans.indexed) {
        if (span.$2.ceil() + 2 == s) world.controller.onSegmentReceived([segment(id, i, span)]);
      }
    }
  }

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

  double walAudioSeconds(Wal wal) {
    if (wal.totalFrames > 0) {
      final fps = wal.codec.getFramesPerSecond();
      if (fps > 0) return wal.totalFrames / fps;
    }
    return wal.seconds < 0 ? 0 : wal.seconds.toDouble();
  }

  Future<void> telemetryReaches(bool Function() done) async {
    for (var i = 0; i < 200 && !done(); i++) {
      await world.settle();
      await Future<void>.delayed(const Duration(milliseconds: 50));
    }
    expect(done(), isTrue);
  }

  Future<List<Wal>> expectKeptMarkedThenUploaded(String convId) async {
    final kept = await walsReach(
      'every stamped copy kept and marked for recovery',
      (wals) => wals.isNotEmpty && wals.every((wal) => wal.keptForTranscriptRecovery),
    );
    final keptSeconds = kept.fold<double>(0, (sum, wal) => sum + walAudioSeconds(wal));
    await telemetryReaches(
      () => world.coverageEvents.any((event) => event['phase'] == 'confirmation'),
    );
    final confirmation = world.coverageEvents.lastWhere((event) => event['phase'] == 'confirmation');
    expect(confirmation['policy'], 'retain_uncertain_coverage');
    expect(confirmation['released_count'], 0);
    expect(confirmation['released_seconds'], 0.0);
    expect(confirmation['kept_count'], kept.length);
    expect(confirmation['kept_seconds'], keptSeconds);
    expect(confirmation['kept_uploaded_seconds'], 0);

    final pendingIds = {for (final wal in kept.where((wal) => wal.status == WalStatus.miss)) wal.id};
    final pendingSeconds =
        kept.where((wal) => pendingIds.contains(wal.id)).fold<double>(0, (sum, wal) => sum + walAudioSeconds(wal));
    await recoveryPass();
    if (pendingIds.isNotEmpty) {
      expect(world.uploads.attempts, isNotEmpty, reason: 'the kept audio goes to the server for repair');
      expect(world.uploads.attempts.map((attempt) => attempt.conversationId).toSet(), {convId},
          reason: 'the recovery upload keeps the conversation linkage of the stamped copies');
      await walsReach(
        'kept pending copies uploaded and markers cleared in the saved index',
        (wals) => wals
            .where((wal) => pendingIds.contains(wal.id))
            .every((wal) => wal.status != WalStatus.miss && !wal.keptForTranscriptRecovery),
      );
      await telemetryReaches(
        () => world.coverageEvents.any((event) => event['phase'] == 'upload'),
      );
      final uploadedSeconds = world.coverageEvents
          .where((event) => event['phase'] == 'upload')
          .fold<double>(0, (sum, event) => sum + (event['kept_uploaded_seconds'] as double));
      expect(uploadedSeconds, pendingSeconds,
          reason: 'accepted redundant seconds equal the marked pending subset duration');
    }
    return kept;
  }

  test('pendant: a transcript that stops early keeps ALL the audio for repair', () async {
    final origin = world.clock.now();
    final link = await connectPendant();
    await streamPendant(link, 200);

    // The server saved text for the first 20 s only; arrival estimates can no more
    // prove the first minute than the rest, so nothing is released.
    await serverCloses(conversation('c1', origin, [(1, 20)]));
    final originSeconds = origin.millisecondsSinceEpoch ~/ 1000;
    final kept = await expectKeptMarkedThenUploaded('c1');

    printOnFailure(await describeWals(origin));
    expect(kept.any((wal) => wal.timerStart - originSeconds < 60), isTrue,
        reason: 'the first-minute WAL is retained too — timestamps cannot prove coverage');
    expect(await recoverableSecondsAfter(origin, 0), greaterThanOrEqualTo(180));
  });

  test('pendant: a gap in the middle of the transcript keeps every copy for repair', () async {
    final origin = world.clock.now();
    final link = await connectPendant();
    await streamPendant(link, 200);

    // Text saved for the opening and the end; the server lost the middle.
    await serverCloses(conversation('c1', origin, [(1, 20), (180, 195)]));
    final kept = await expectKeptMarkedThenUploaded('c1');

    printOnFailure(await describeWals(origin));
    final originSeconds = origin.millisecondsSinceEpoch ~/ 1000;
    expect(kept.map((wal) => wal.timerStart - originSeconds), contains(60),
        reason: 'the uncovered middle minute is among the retained copies');
  });

  test('pendant: even a complete timestamp transcript keeps every copy and uploads it', () async {
    final origin = world.clock.now();
    final link = await connectPendant();
    await streamPendant(link, 200);
    expect(await world.wal.syncs.phone.getAllWals(), isNotEmpty, reason: 'there are copies to judge');

    // The saved text appears to cover the whole session — but coverage was only ever
    // estimated from timestamps, so the audio still cannot be deleted.
    await serverCloses(conversation('c1', origin, [for (var t = 1.0; t < 190; t += 20) (t, t + 15)]));
    await expectKeptMarkedThenUploaded('c1');
    printOnFailure(await describeWals(origin));
  });

  test('pendant: audio from before the conversation started is kept, not released', () async {
    final origin = world.clock.now();
    final link = await connectPendant();
    // Five quiet minutes, then a conversation that the transcript appears to cover.
    await streamPendant(link, 300);
    final talkStart = origin.add(const Duration(seconds: 300));
    await streamPendant(link, 140);
    expect(await world.wal.syncs.phone.getAllWals(), isNotEmpty, reason: 'there are copies to judge');

    await serverCloses(conversation('c1', talkStart, [for (var t = 1.0; t < 130; t += 20) (t, t + 15)]));
    await expectKeptMarkedThenUploaded('c1');
    printOnFailure(await describeWals(origin));
  });

  test('pendant: a chunk backdated before the session start is kept and uploaded', () async {
    final origin = world.clock.now();
    final link = await connectPendant();
    // The pendant flushes 30 s of buffered audio the moment it connects, so the first chunk's start is
    // backdated before the session window.
    for (var i = 0; i < 3000; i++) {
      link.emitAudio();
    }
    await streamPendant(link, 140);
    expect(await world.wal.syncs.phone.getAllWals(), isNotEmpty, reason: 'there are copies to judge');

    await serverCloses(conversation('c1', origin, [for (var t = 1.0; t < 130; t += 20) (t, t + 15)]));
    await expectKeptMarkedThenUploaded('c1');
    printOnFailure(await describeWals(origin));
  });

  test('pendant: a conversation with no start time keeps every copy', () async {
    final origin = world.clock.now();
    final link = await connectPendant();
    await streamPendant(link, 140);
    expect(await world.wal.syncs.phone.getAllWals(), isNotEmpty, reason: 'there are copies to judge');

    // An old row without started_at, created ten minutes before this audio.
    final memory = conversation('c1', origin, [for (var t = 1.0; t < 130; t += 20) (t, t + 15)],
        createdAt: origin.subtract(const Duration(minutes: 10)), hasStart: false);
    await serverCloses(memory);
    await expectKeptMarkedThenUploaded('c1');
    printOnFailure(await describeWals(origin));
  });

  test('pendant: a server clock ahead of the phone keeps every copy', () async {
    final origin = world.clock.now();
    final link = await connectPendant();
    await streamPendant(link, 200);

    // The server's clock runs five minutes ahead; no estimate is trustworthy enough
    // to release audio, so everything is retained and repaired.
    await serverCloses(conversation('c1', origin.add(const Duration(minutes: 5)), const [(1, 20)]));
    await expectKeptMarkedThenUploaded('c1');
    printOnFailure(await describeWals(origin));
  });

  test('pendant: a server clock behind the phone keeps every copy', () async {
    final origin = world.clock.now();
    final link = await connectPendant();
    final spans = [for (var t = 1.0; t < 190; t += 20) (t, t + 15)];
    await streamPendant(link, 200);
    expect(await world.wal.syncs.phone.getAllWals(), isNotEmpty, reason: 'there are copies to judge');

    // The server's clock runs five minutes behind.
    await serverCloses(conversation('c1', origin.subtract(const Duration(minutes: 5)), spans));
    await expectKeptMarkedThenUploaded('c1');
    printOnFailure(await describeWals(origin));
  });

  test('pendant: live arrivals a minute or more late still keep everything', () async {
    final origin = world.clock.now();
    final link = await connectPendant();
    final spans = [for (var t = 1.0; t < 190; t += 20) (t, t + 15)];
    await streamPendant(link, 200);
    await world.elapse(const Duration(seconds: 90));

    world.controller.onSegmentReceived([for (final (i, span) in spans.indexed) segment('c1', i, span)]);

    await serverCloses(conversation('c1', origin, spans));
    await expectKeptMarkedThenUploaded('c1');
    printOnFailure(await describeWals(origin));
  });

  test('pendant: a continuous saved span over the whole session still keeps everything', () async {
    final origin = world.clock.now();
    final link = await connectPendant();
    await streamWithLiveSegments(link, 200, 'c1', const [(0, 200)]);
    expect(await world.wal.syncs.phone.getAllWals(), isNotEmpty, reason: 'there are copies to judge');

    await serverCloses(conversation('c1', origin, const [(0, 200)]));
    await expectKeptMarkedThenUploaded('c1');
    printOnFailure(await describeWals(origin));
  });

  test('pendant: an account roll mid-close never stamps or mutates the successor inventory', () async {
    final origin = world.clock.now();
    final link = await connectPendant();
    await streamPendant(link, 140);
    final phone = world.wal.syncs.phone;
    expect(phone.testWals, isNotEmpty, reason: 'there are copies to judge');
    final successorWals = <Wal>[
      Wal(
        timerStart: origin.millisecondsSinceEpoch ~/ 1000 + 10000,
        codec: BleAudioCodec.opus,
        seconds: 30,
        storage: WalStorage.disk,
        status: WalStatus.miss,
      ),
    ];

    final memory = conversation('c1', origin, [(1, 100)]);
    world.controller.onMessageEventReceived(ConversationProcessingStartedEvent(memory: memory));
    world.wal.syncs.phone.clearUserData();
    phone.testWals = successorWals;
    await settleFiles();
    world.controller.onMessageEventReceived(ConversationEvent(memory: memory, messages: []));
    await settleFiles();

    expect(
      phone.testWals.map((wal) => wal.conversationId),
      everyElement(isNull),
      reason: 'a stale finalize must not stamp the successor account data',
    );
    expect(
      phone.testWals.every((wal) => identical(wal, successorWals.single)),
      isTrue,
      reason: 'a stale confirmation must not mutate the successor inventory',
    );
    expect(
      world.coverageEvents.any((event) => event['phase'] == 'confirmation' && event['kept_count'] != 0),
      isFalse,
    );
    printOnFailure(await describeWals(origin));
  });

  test('pendant: an empty transcript keeps every copy and uploads it for repair', () async {
    final origin = world.clock.now();
    final link = await connectPendant();
    await streamPendant(link, 140);

    await serverCloses(conversation('c1', origin, const []));
    await expectKeptMarkedThenUploaded('c1');
    printOnFailure(await describeWals(origin));
  });

  test('pendant: a socket interruption mid-session keeps every copy and uploads it', () async {
    final origin = world.clock.now();
    final link = await connectPendant();
    await streamPendant(link, 140);

    world.sockets.last.transport.emitClose();
    await world.settle();

    await serverCloses(conversation('c1', origin, [(1, 100)]));
    await expectKeptMarkedThenUploaded('c1');
    printOnFailure(await describeWals(origin));
  });

  test('pendant: a transcript missing the opening keeps the opening and uploads it', () async {
    final origin = world.clock.now();
    final link = await connectPendant();
    await streamPendant(link, 200);

    await serverCloses(conversation('c1', origin.add(const Duration(seconds: 60)), [(1, 100)]));
    final originSeconds = origin.millisecondsSinceEpoch ~/ 1000;
    final kept = await expectKeptMarkedThenUploaded('c1');

    printOnFailure(await describeWals(origin));
    expect(kept.any((wal) => wal.timerStart - originSeconds < 60), isTrue,
        reason: 'the pre-start opening the transcript never mentions is retained');
  });

  test('pendant: a missing ConversationEvent marks and recovers through the fallback', () async {
    final origin = world.clock.now();
    final link = await connectPendant();
    await streamPendant(link, 140);
    expect(await world.wal.syncs.phone.getAllWals(), isNotEmpty, reason: 'there are copies to judge');

    final memory = conversation('c1', origin, [(1, 100)]);
    world.controller.onMessageEventReceived(ConversationProcessingStartedEvent(memory: memory));
    await settleFiles();

    await world.elapse(const Duration(seconds: 31));
    await settleFiles();

    await expectKeptMarkedThenUploaded('c1');
    printOnFailure(await describeWals(origin));
  });
}
