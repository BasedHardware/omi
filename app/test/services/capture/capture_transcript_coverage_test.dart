// The phone keeps a local copy of live pendant audio (the WAL) until the server's saved transcript
// confirms it (#20364). These scenarios drive the real CaptureController and LocalWalSyncImpl over the
// replay world and check the split policy: copies the saved transcript provably covers move into
// synced retention and are never uploaded again, while any copy with an uncovered portion — a missing
// opening, an interior gap, a lost tail, or coverage that cannot be judged at all — stays miss, is
// marked for recovery, and uploads. No confirmation path ever deletes a copy.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/preferences.dart';
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
  /// [id], each two seconds after it ends, as transcription does. When [anchorEstimates] is given it
  /// records each delivery's `arrival - end` in epoch seconds — the exact anchor inputs the
  /// confirmation median sees (fixture provenance, not production measurement).
  Future<void> streamWithLiveSegments(
    ScriptedDeviceConnection link,
    int seconds,
    String id,
    List<(double, double)> spans, {
    List<int>? anchorEstimates,
  }) async {
    for (var s = 1; s <= seconds; s++) {
      await streamPendant(link, 1);
      for (final (i, span) in spans.indexed) {
        if (span.$2.ceil() + 2 == s) {
          anchorEstimates?.add(world.clock.now().millisecondsSinceEpoch ~/ 1000 - span.$2.ceil());
          world.controller.onSegmentReceived([segment(id, i, span)]);
        }
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

  /// Names of the audio files physically on disk.
  Set<String> audioFilesOnDisk() => {
        for (final entity in directory.listSync())
          if (entity is File && entity.path.endsWith('.bin')) entity.uri.pathSegments.last,
      };

  /// WAL statuses persisted in the durable index, by WAL id.
  Future<Map<String, WalStatus>> persistedStatuses() async =>
      {for (final wal in await WalFileManager.loadWals()) wal.id: wal.status};

  /// Waits until every stamped WAL is judged, then splits them: covered copies
  /// retained-synced vs uncovered copies still miss and marked for repair.
  Future<(List<Wal> covered, List<Wal> hole)> judgedWals() async {
    final wals = await walsReach(
      'every stamped copy judged: covered retained-synced, holes miss and marked',
      (wals) =>
          wals.isNotEmpty &&
          wals.every((wal) =>
              (wal.status == WalStatus.synced && wal.syncedAt > 0 && !wal.keptForTranscriptRecovery) ||
              (wal.status == WalStatus.miss && wal.keptForTranscriptRecovery)),
    );
    return (
      wals.where((wal) => wal.status == WalStatus.synced).toList(),
      wals.where((wal) => wal.status == WalStatus.miss).toList(),
    );
  }

  /// Runs one recovery pass and asserts exactly [expected]'s files were uploaded once each, that the
  /// uploads cleared their markers in the durable index, that a second pass finds nothing, and that
  /// every file present before the pass — covered or repaired — is still on disk.
  Future<void> expectRecoveryUploads(String convId, Iterable<Wal> expected) async {
    final expectedNames = expected.map((wal) => wal.getFileName()).toList();
    final filesBefore = audioFilesOnDisk();
    await recoveryPass();
    expect(world.uploads.attempts.expand((attempt) => attempt.fileNames), unorderedEquals(expectedNames),
        reason: 'recovery uploads exactly the uncovered copies, once each');
    if (expectedNames.isNotEmpty) {
      expect(world.uploads.attempts.map((attempt) => attempt.conversationId).toSet(), {convId},
          reason: 'the recovery upload keeps the conversation linkage of the stamped copies');
    }
    final expectedIds = expected.map((wal) => wal.id).toSet();
    await walsReach(
      'uploaded copies synced and markers cleared in the saved index',
      (wals) => wals
          .where((wal) => expectedIds.contains(wal.id))
          .every((wal) => wal.status == WalStatus.synced && !wal.keptForTranscriptRecovery),
    );
    final attempts = world.uploads.attempts.length;
    await recoveryPass();
    expect(world.uploads.attempts, hasLength(attempts), reason: 'a second recovery pass finds nothing left to repair');
    expect(audioFilesOnDisk(), containsAll(filesBefore),
        reason: 'every copy — covered or repaired — stays on disk in synced retention');
  }

  /// Fail-closed expectation: coverage could not be judged, so every stamped copy stays miss and
  /// marked, then a recovery pass uploads all of them once.
  Future<List<Wal>> expectAllKeptThenUploaded(String convId, {String? failClosedReason}) async {
    final (covered, hole) = await judgedWals();
    expect(covered, isEmpty, reason: 'fail-closed confirmation retains nothing as covered');
    final holeSeconds = hole.fold<double>(0, (sum, wal) => sum + walAudioSeconds(wal));
    await telemetryReaches(() => world.coverageEvents.any((event) => event['phase'] == 'confirmation'));
    final confirmation = world.coverageEvents.lastWhere((event) => event['phase'] == 'confirmation');
    expect(confirmation['policy'], 'retain_covered_upload_gaps');
    expect(confirmation['retained_covered_count'], 0);
    expect(confirmation['kept_count'], hole.length);
    expect(confirmation['kept_seconds'], holeSeconds);
    expect(confirmation['kept_uploaded_count'], 0);
    if (failClosedReason != null) expect(confirmation['fail_closed_reason'], failClosedReason);

    await expectRecoveryUploads(convId, hole);
    await telemetryReaches(() => world.coverageEvents.any((event) => event['phase'] == 'upload'));
    final uploadedCount = world.coverageEvents
        .where((event) => event['phase'] == 'upload')
        .fold<int>(0, (sum, event) => sum + (event['kept_uploaded_count'] as int));
    expect(uploadedCount, hole.length, reason: 'accepted repair uploads equal the marked uncovered subset');
    return hole;
  }

  /// The contiguous 200-second transcript that, anchored by the fixture's live arrivals, covers
  /// every WAL the session chunks — [0,60), [60,135) and [135,202) on this world's clock.
  const fullSpans = [(0.0, 60.0), (60.0, 120.0), (120.0, 180.0), (180.0, 200.0)];

  /// Seconds since [origin] each WAL started, sorted — the exact split the coverage judgement made.
  List<int> offsetsOf(Iterable<Wal> wals, DateTime origin) {
    final originSeconds = origin.millisecondsSinceEpoch ~/ 1000;
    return [for (final wal in wals) wal.timerStart - originSeconds]..sort();
  }

  /// Replays the fully covered session once — 202 s streamed, [fullSpans] delivered end+2s each —
  /// and returns the covered copies once every stamped WAL is judged synced. [serverSkew] offsets
  /// the conversation's own clock and [hasStart] drops `startedAt`, both ignored by the live anchor.
  Future<(DateTime, List<Wal>)> fullyCoveredReplay({
    Duration serverSkew = Duration.zero,
    bool hasStart = true,
    List<int>? anchorEstimates,
  }) async {
    final origin = world.clock.now();
    final link = await connectPendant();
    await streamWithLiveSegments(link, 202, 'c1', fullSpans, anchorEstimates: anchorEstimates);
    await serverCloses(conversation(
      'c1',
      origin.add(serverSkew),
      fullSpans,
      hasStart: hasStart,
      createdAt: hasStart ? null : origin.subtract(const Duration(minutes: 10)),
    ));
    final covered = await walsReach(
      'every stamped copy covered and retained-synced',
      (wals) =>
          wals.isNotEmpty &&
          wals.every((wal) => wal.status == WalStatus.synced && wal.syncedAt > 0 && !wal.keptForTranscriptRecovery),
    );
    return (origin, covered);
  }

  /// Streams [seconds] of pendant audio while [spans] arrive live (end+2s each), closes with the
  /// same saved transcript, and returns (origin, covered, hole) once every stamped WAL is judged.
  Future<(DateTime, List<Wal>, List<Wal>)> judgedReplay(int seconds, List<(double, double)> spans) async {
    final origin = world.clock.now();
    final link = await connectPendant();
    await streamWithLiveSegments(link, seconds, 'c1', spans);
    await serverCloses(conversation('c1', origin, spans));
    final (covered, hole) = await judgedWals();
    return (origin, covered, hole);
  }

  /// Streams [seconds] of pendant audio with no live arrivals, closes with a saved transcript of
  /// [spans], and asserts every stamped copy fails closed and uploads for repair once.
  Future<List<Wal>> plainTranscriptKeepsAll(
    int seconds,
    List<(double, double)> spans, {
    Duration serverSkew = Duration.zero,
    bool hasStart = true,
    String? failClosedReason,
  }) async {
    final origin = world.clock.now();
    final link = await connectPendant();
    await streamPendant(link, seconds);
    await serverCloses(conversation(
      'c1',
      origin.add(serverSkew),
      spans,
      hasStart: hasStart,
      createdAt: hasStart ? null : origin.subtract(const Duration(minutes: 10)),
    ));
    return expectAllKeptThenUploaded('c1', failClosedReason: failClosedReason);
  }

  test('pendant: a fully covered transcript moves every copy into synced retention and uploads nothing', () async {
    final anchorEstimates = <int>[];
    final (origin, covered) = await fullyCoveredReplay(anchorEstimates: anchorEstimates);
    final originSeconds = origin.millisecondsSinceEpoch ~/ 1000;
    // The fixture delivers each saved segment exactly end+2s after it ends, so every anchor estimate
    // is origin+2 and the median anchor lands there; the spans then cover every WAL within the 3s
    // boundary slack.
    expect(anchorEstimates.toSet(), {originSeconds + 2},
        reason: 'each live segment arrives exactly 2s after it ends, so the median anchor is origin+2');
    expect(offsetsOf(covered, origin), [0, 60, 135]);
    expect(world.uploads.attempts, isEmpty,
        reason: 'coverage the saved transcript proves suppresses the repair upload entirely');
    final retainedNames = audioFilesOnDisk();
    expect(retainedNames, unorderedEquals([for (final wal in covered) wal.getFileName()]),
        reason: 'every covered copy is retained in synced retention under its own name, not deleted');
    await recoveryPass();
    expect(world.uploads.attempts, isEmpty, reason: 'even a forced recovery pass finds nothing to repair');
    expect(audioFilesOnDisk(), retainedNames);
    expect(await persistedStatuses(), {for (final wal in covered) wal.id: WalStatus.synced},
        reason: 'the durable index agrees every covered copy is synced');
    await telemetryReaches(() => world.coverageEvents.any((event) => event['phase'] == 'confirmation'));
    final confirmation = world.coverageEvents.lastWhere((event) => event['phase'] == 'confirmation');
    expect(confirmation['retained_covered_count'], covered.length);
    expect(confirmation['kept_count'], 0);
    expect(confirmation['fail_closed_reason'], isNull);
  });

  test('pendant: an interior transcript gap keeps only the uncovered copies for repair', () async {
    // The saved transcript never mentions seconds 60..120, so the 75-second WAL covering that hole
    // stays miss-marked and recovers; the covered copies move into synced retention.
    final (origin, covered, hole) = await judgedReplay(202, const [(0.0, 60.0), (120.0, 180.0), (180.0, 200.0)]);
    expect(offsetsOf(hole, origin), [60], reason: 'only the WAL crossing the 60..120 hole remains miss');
    expect(offsetsOf(covered, origin), [0, 135]);
    expect(audioFilesOnDisk(), hasLength(covered.length + hole.length),
        reason: 'covered copies are retained, not deleted; hole copies stay for repair');
    await expectRecoveryUploads('c1', hole);
    expect(
        await persistedStatuses(),
        {
          for (final wal in [...covered, ...hole]) wal.id: WalStatus.synced
        },
        reason: 'the durable index agrees');
  });

  test('pendant: a transcript missing the opening keeps the opening and uploads it', () async {
    // The saved transcript never mentions the first minute; live arrivals anchor the rest.
    final (origin, covered, hole) = await judgedReplay(202, const [(60.0, 120.0), (120.0, 180.0), (180.0, 200.0)]);
    expect(offsetsOf(hole, origin), [0], reason: 'the opening minute the transcript never mentions is kept for repair');
    expect(offsetsOf(covered, origin), [60, 135]);
    await expectRecoveryUploads('c1', hole);
  });

  test('pendant: a transcript that loses the tail keeps the tail and uploads it', () async {
    // The saved transcript stops at second 120; everything after stays uncovered.
    final (origin, covered, hole) = await judgedReplay(202, const [(0.0, 60.0), (60.0, 120.0)]);
    expect(offsetsOf(hole, origin), [60, 135], reason: 'only the WALs crossing the lost tail remain miss');
    expect(offsetsOf(covered, origin), [0]);
    await expectRecoveryUploads('c1', hole);
  });

  test('pendant: a connect-burst chunk backdated before the window stays uncovered and uploads', () async {
    final origin = world.clock.now();
    final link = await connectPendant();
    // The pendant flushes 30 s of buffered audio the moment it connects, so the first chunk's start is
    // backdated before the session window — the transcript cannot cover its head.
    for (var i = 0; i < 3000; i++) {
      link.emitAudio();
    }
    await streamWithLiveSegments(link, 202, 'c1', fullSpans);

    await serverCloses(conversation('c1', origin, fullSpans));

    final (covered, hole) = await judgedWals();
    expect(hole, hasLength(1), reason: 'only the backdated first copy is uncovered');
    expect(hole.single.timerStart, lessThan(origin.millisecondsSinceEpoch ~/ 1000));
    expect(covered, isNotEmpty);
    await expectRecoveryUploads('c1', hole);
  });

  test('pendant: audio from before the conversation started is kept, not released', () async {
    final origin = world.clock.now();
    final link = await connectPendant();
    // Five quiet minutes, then a conversation the transcript covers contiguously.
    await streamPendant(link, 300);
    final talkStart = origin.add(const Duration(seconds: 300));
    await streamPendant(link, 140);

    await serverCloses(conversation('c1', talkStart, const [(0, 140)]));

    final (covered, hole) = await judgedWals();
    final talkStartSeconds = talkStart.millisecondsSinceEpoch ~/ 1000;
    expect(hole.every((wal) => wal.timerStart < talkStartSeconds || wal.timerStart + wal.seconds > talkStartSeconds),
        isTrue,
        reason: 'the pre-start copies and the boundary-straddling copy fail closed — no silence is inferred');
    expect(hole.any((wal) => wal.timerStart < talkStartSeconds), isTrue);
    expect(covered, isNotEmpty, reason: 'the covered talk copy is retained-synced');
    expect(audioFilesOnDisk(), hasLength(covered.length + hole.length));
    await expectRecoveryUploads('c1', hole);
  });

  test('pendant: a transcript that stops early keeps ALL the audio for repair', () async {
    // The server saved text for the first 20 s only; nothing else is covered.
    final kept = await plainTranscriptKeepsAll(200, const [(1, 20)]);
    expect(kept.length, greaterThanOrEqualTo(3), reason: 'every stamped copy fails closed');
  });

  test('pendant: a gapped timestamp transcript keeps every copy for repair', () async {
    // Fifteen saved seconds in every twenty leave a five-second interior hole in
    // every WAL, so even a transcript that mentions the whole session covers none of it.
    await plainTranscriptKeepsAll(200, [for (var t = 1.0; t < 190; t += 20) (t, t + 15)]);
  });

  test('pendant: a server clock ahead of the phone still covers via the live anchor', () async {
    final (_, covered) = await fullyCoveredReplay(serverSkew: const Duration(minutes: 5));
    expect(world.uploads.attempts, isEmpty);
    expect(audioFilesOnDisk(), hasLength(covered.length));
  });

  test('pendant: a server clock behind the phone still covers via the live anchor', () async {
    final (_, covered) = await fullyCoveredReplay(serverSkew: const Duration(minutes: -5));
    expect(world.uploads.attempts, isEmpty);
    expect(audioFilesOnDisk(), hasLength(covered.length));
  });

  test('pendant: no started_at uses the live anchor and ignores a stale created_at', () async {
    final (_, covered) = await fullyCoveredReplay(hasStart: false);
    expect(world.uploads.attempts, isEmpty);
    expect(audioFilesOnDisk(), hasLength(covered.length));
  });

  test('pendant: a conversation with no live arrivals and no start time keeps every copy', () async {
    // An old row without started_at and no live anchor; the session-start fallback still
    // leaves interior holes, so every copy fails closed.
    await plainTranscriptKeepsAll(140, [for (var t = 1.0; t < 130; t += 20) (t, t + 15)], hasStart: false);
  });

  test('pendant: no live arrivals falls back to the server start and keeps what it cannot cover', () async {
    // The server's clock runs five minutes ahead and no segment arrived live, so the
    // started_at fallback anchors every span outside the audio: all kept for repair.
    await plainTranscriptKeepsAll(200, const [(1, 20)], serverSkew: const Duration(minutes: 5));
  });

  test('pendant: an empty transcript keeps every copy and uploads it for repair', () async {
    await plainTranscriptKeepsAll(140, const [], failClosedReason: 'empty_transcript');
  });

  test('pendant: a socket interruption mid-session keeps every copy and uploads it', () async {
    final origin = world.clock.now();
    final link = await connectPendant();
    await streamPendant(link, 140);

    world.sockets.last.transport.emitClose();
    await world.settle();

    await serverCloses(conversation('c1', origin, [(1, 100)]));
    await expectAllKeptThenUploaded('c1', failClosedReason: 'needs_repair');
  });

  test('pendant: a missing ConversationEvent marks and recovers through the fallback', () async {
    final origin = world.clock.now();
    final link = await connectPendant();
    await streamPendant(link, 140);

    world.controller
        .onMessageEventReceived(ConversationProcessingStartedEvent(memory: conversation('c1', origin, [(1, 100)])));
    await settleFiles();
    await world.elapse(const Duration(seconds: 31));
    await settleFiles();

    await expectAllKeptThenUploaded('c1', failClosedReason: 'missing_conversation_event');
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

    expect(phone.testWals.map((wal) => wal.conversationId), everyElement(isNull),
        reason: 'a stale finalize must not stamp the successor account data');
    expect(phone.testWals.every((wal) => identical(wal, successorWals.single)), isTrue,
        reason: 'a stale confirmation must not mutate the successor inventory');
    expect(
      world.coverageEvents.any((event) => event['phase'] == 'confirmation' && event['kept_count'] != 0),
      isFalse,
    );
  });

  test('pendant: retained-covered copies age out under auto-remove', () async {
    SharedPreferencesUtil().autoRemoveSyncedCopies = true;
    final (_, covered) = await fullyCoveredReplay();
    expect(audioFilesOnDisk(), hasLength(covered.length));

    // Nothing is old yet, then jump straight past the 30-day retention window — no timers needed.
    expect(await world.wal.syncs.phone.applySyncedCopyRetention(), 0);
    expect(audioFilesOnDisk(), hasLength(covered.length));
    world.clock.advanceTo(world.clock.now().add(const Duration(days: 31)));
    final removed = await world.wal.syncs.phone.applySyncedCopyRetention();
    await settleFiles();

    expect(removed, covered.length);
    expect(audioFilesOnDisk(), isEmpty);
    expect(await world.wal.syncs.phone.getAllWals(), isEmpty);
    expect(await WalFileManager.loadWals(), isEmpty, reason: 'the durable index is swept too');
  });

  test('pendant: retained-covered copies stay when auto-remove is off', () async {
    SharedPreferencesUtil().autoRemoveSyncedCopies = false;
    final (_, covered) = await fullyCoveredReplay();
    expect(audioFilesOnDisk(), hasLength(covered.length));

    world.clock.advanceTo(world.clock.now().add(const Duration(days: 31)));
    final removed = await world.wal.syncs.phone.applySyncedCopyRetention();
    await settleFiles();

    expect(removed, 0);
    expect(audioFilesOnDisk(), hasLength(covered.length));
    expect(await WalFileManager.loadWals(), hasLength(covered.length),
        reason: 'the durable index keeps the retained copies too');
  });
}
