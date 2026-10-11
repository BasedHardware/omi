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
    // These custody fixtures intentionally delay transcripts for several minutes.
    // Keep capture admitted using the existing four-hour setting; default silence
    // pause is exercised separately in tiered_capture_test.dart.
    world = await CaptureReplayWorld.boot(
      tempDir: directory,
      pendantCodec: BleAudioCodec.opus,
      initialPrefs: {'conversationSilenceDuration': -1},
    );
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
  ServerConversation conversation(
    String id,
    DateTime startedAt,
    List<(double, double)> spans, {
    DateTime? createdAt,
    bool hasStart = true,
  }) =>
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
      for (final wal in wals) '${wal.timerStart}+${wal.seconds}s ${wal.status.name} conv=${wal.conversationId}',
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
  Future<Map<String, WalStatus>> persistedStatuses() async => {
        for (final wal in await WalFileManager.loadWals()) wal.id: wal.status,
      };

  /// Waits until every stamped WAL is judged, then splits them: covered copies
  /// retained-synced vs uncovered copies still miss and marked for repair.
  Future<(List<Wal> covered, List<Wal> hole)> judgedWals() async {
    final wals = await walsReach(
      'every stamped copy judged: covered retained-synced, holes miss and marked',
      (wals) =>
          wals.isNotEmpty &&
          wals.every(
            (wal) =>
                (wal.status == WalStatus.synced && wal.syncedAt > 0 && !wal.keptForTranscriptRecovery) ||
                (wal.status == WalStatus.miss && wal.keptForTranscriptRecovery),
          ),
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
    expect(
      world.uploads.attempts.expand((attempt) => attempt.fileNames),
      unorderedEquals(expectedNames),
      reason: 'recovery uploads exactly the uncovered copies, once each',
    );
    if (expectedNames.isNotEmpty) {
      expect(
        world.uploads.attempts.map((attempt) => attempt.conversationId).toSet(),
        {convId},
        reason: 'the recovery upload keeps the conversation linkage of the stamped copies',
      );
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
    expect(
      audioFilesOnDisk(),
      containsAll(filesBefore),
      reason: 'every copy — covered or repaired — stays on disk in synced retention',
    );
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

  /// A 200-second conversation of 2–12 s utterances, 1–8 s pauses and 18/25 s silences, covering
  /// WALs [0,60), [60,135), [135,202) when anchored by live arrivals and judged with pause tolerance.
  const fullSpans = [
    (0.0, 8.0),
    (10.0, 14.0),
    (19.0, 31.0),
    (34.0, 40.0),
    (48.0, 52.0),
    (55.0, 60.0),
    (78.0, 83.0),
    (84.0, 86.0),
    (89.0, 101.0),
    (106.0, 112.0),
    (113.0, 120.0),
    (122.0, 128.0),
    (131.0, 139.0),
    (164.0, 172.0),
    (175.0, 177.0),
    (185.0, 195.0),
    (198.0, 200.0),
  ];

  /// Seconds since [origin] each WAL started, sorted — the exact split the coverage judgement made.
  List<int> offsetsOf(Iterable<Wal> wals, DateTime origin) {
    final originSeconds = origin.millisecondsSinceEpoch ~/ 1000;
    return [for (final wal in wals) wal.timerStart - originSeconds]..sort();
  }

  /// Replays the fully covered session once — 202 s streamed, [fullSpans] delivered end+2s each —
  /// and returns the covered copies once every stamped WAL is judged synced. [serverSkew] offsets
  /// the conversation's own clock and [hasStart] drops `startedAt`, both ignored by the live anchor.
  Future<(DateTime, List<Wal>, List<Wal>)> fullyCoveredReplay({
    Duration serverSkew = Duration.zero,
    bool hasStart = true,
    List<int>? anchorEstimates,
  }) async {
    final origin = world.clock.now();
    final link = await connectPendant();
    await streamWithLiveSegments(link, 202, 'c1', fullSpans, anchorEstimates: anchorEstimates);
    await serverCloses(
      conversation(
        'c1',
        origin.add(serverSkew),
        fullSpans,
        hasStart: hasStart,
        createdAt: hasStart ? null : origin.subtract(const Duration(minutes: 10)),
      ),
    );
    final (covered, hole) = await judgedWals();
    expect(
        offsetsOf(hole, origin),
        [
          70,
          150,
        ],
        reason: 'silence-only 10s chunks inside tolerated pauses stay miss on every anchor');
    return (origin, covered, hole);
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
  /// [spans], and returns (origin, covered, hole) once every stamped WAL is judged.
  Future<(DateTime, List<Wal>, List<Wal>)> plainJudgedReplay(
    int seconds,
    List<(double, double)> spans, {
    Duration serverSkew = Duration.zero,
    bool hasStart = true,
  }) async {
    final origin = world.clock.now();
    final link = await connectPendant();
    await streamPendant(link, seconds);
    await serverCloses(
      conversation(
        'c1',
        origin.add(serverSkew),
        spans,
        hasStart: hasStart,
        createdAt: hasStart ? null : origin.subtract(const Duration(minutes: 10)),
      ),
    );
    final (covered, hole) = await judgedWals();
    return (origin, covered, hole);
  }

  Future<List<Wal>> plainTranscriptKeepsAll(
    int seconds,
    List<(double, double)> spans, {
    Duration serverSkew = Duration.zero,
    bool hasStart = true,
    String? failClosedReason,
  }) async {
    await plainJudgedReplay(seconds, spans, serverSkew: serverSkew, hasStart: hasStart);
    return expectAllKeptThenUploaded('c1', failClosedReason: failClosedReason);
  }

  test('pendant: a conversation with natural pauses retains every covered copy and repairs silent gaps', () async {
    final anchorEstimates = <int>[];
    final origin = world.clock.now();
    final link = await connectPendant();
    await streamWithLiveSegments(link, 202, 'c1', fullSpans, anchorEstimates: anchorEstimates);
    await serverCloses(conversation('c1', origin, fullSpans));
    final (covered, hole) = await judgedWals();
    final originSeconds = origin.millisecondsSinceEpoch ~/ 1000;
    // The fixture delivers each saved segment exactly end+2s after it ends, so every anchor estimate
    // is origin+2 and the median anchor lands there; the utterance pauses then fall inside the 30s
    // pause tolerance and every WAL touching text is covered.
    expect(
      anchorEstimates.toSet(),
      {originSeconds + 2},
      reason: 'each live segment arrives exactly 2s after it ends, so the median anchor is origin+2',
    );
    // Pendant drains on the 10s custody cadence: chunks at 60 and 140/150 lie
    // wholly inside the 60..78 and 139..164 silences — no span overlap, so they
    // fail closed and repair-upload rather than inferring silence.
    expect(
        offsetsOf(hole, origin),
        [
          70,
          150,
        ],
        reason: 'chunks with zero transcript overlap stay miss — no overlap is not proven silence');
    expect(offsetsOf(covered, origin), [
      for (var t = 0; t <= 200; t += 10)
        if (t != 70 && t != 150) t,
    ]);
    final retainedNames = audioFilesOnDisk();
    expect(
      retainedNames,
      unorderedEquals([
        for (final wal in [...covered, ...hole]) wal.getFileName(),
      ]),
      reason: 'every covered copy is retained in synced retention under its own name, not deleted',
    );
    await expectRecoveryUploads('c1', hole);
    expect(audioFilesOnDisk(), retainedNames);
    expect(
        await persistedStatuses(),
        {
          for (final wal in [...covered, ...hole]) wal.id: WalStatus.synced,
        },
        reason: 'the durable index agrees every judged copy is synced');
    await telemetryReaches(() => world.coverageEvents.any((event) => event['phase'] == 'confirmation'));
    final confirmation = world.coverageEvents.lastWhere((event) => event['phase'] == 'confirmation');
    expect(confirmation['retained_covered_count'], covered.length);
    expect(confirmation['kept_count'], hole.length);
    expect(confirmation['fail_closed_reason'], isNull);
  });

  test('pendant: an interior transcript gap keeps only the uncovered copies for repair', () async {
    // The saved transcript loses the utterances between seconds 86 and 131 — a 45-second hole past
    // the pause tolerance — so the WAL covering that hole stays miss-marked and recovers.
    final (origin, covered, hole) = await judgedReplay(
      202,
      fullSpans.where((span) => span.$2 <= 86 || span.$1 >= 131).toList(),
    );
    // The 86..131 hole keeps chunks 90–120 miss; chunks fully inside the 60..78
    // and 139..164 silences also stay miss (no overlap), tolerated only at edges.
    expect(
        offsetsOf(hole, origin),
        [
          70,
          90,
          100,
          110,
          120,
          150,
        ],
        reason: 'the 10s chunks with no transcript overlap stay miss');
    expect(offsetsOf(covered, origin), [
      for (var t = 0; t <= 200; t += 10)
        if (t != 70 && (t < 90 || t > 120) && t != 150) t,
    ]);
    expect(
      audioFilesOnDisk(),
      hasLength(covered.length + hole.length),
      reason: 'covered copies are retained, not deleted; hole copies stay for repair',
    );
    await expectRecoveryUploads('c1', hole);
    expect(
        await persistedStatuses(),
        {
          for (final wal in [...covered, ...hole]) wal.id: WalStatus.synced,
        },
        reason: 'the durable index agrees');
  });

  test('pendant: a transcript missing the opening keeps the opening and uploads it', () async {
    // The saved transcript never mentions the opening; its first anchored utterance lands 36 s in — past the pause tolerance.
    final (origin, covered, hole) = await judgedReplay(202, fullSpans.where((span) => span.$1 >= 34).toList());
    expect(
        offsetsOf(hole, origin),
        [
          0,
          10,
          20,
          70,
          150,
        ],
        reason: 'the missing opening and every silence-only chunk are kept for repair');
    expect(offsetsOf(covered, origin), [
      for (var t = 30; t <= 200; t += 10)
        if (t != 70 && t != 150) t,
    ]);
    await expectRecoveryUploads('c1', hole);
  });

  test('pendant: a transcript that loses the tail keeps the tail and uploads it', () async {
    // The saved transcript stops after the last utterance at second 86 while 90 s of audio keep streaming.
    final (origin, covered, hole) = await judgedReplay(176, fullSpans.where((span) => span.$2 <= 86).toList());
    expect(
        offsetsOf(hole, origin),
        [
          70,
          90,
          100,
          110,
          120,
          130,
          140,
          150,
          160,
          170,
        ],
        reason: 'the tail chunks and the silence-only chunk at 60 stay miss');
    expect(offsetsOf(covered, origin), [
      for (var t = 0; t <= 80; t += 10)
        if (t != 70) t,
    ]);
    await expectRecoveryUploads('c1', hole);
  });

  test('pendant: a connect-burst chunk backdated before the window stays uncovered and uploads', () async {
    final origin = world.clock.now();
    final link = await connectPendant();
    // The pendant flushes 30 s of buffered audio the moment it connects, so the first chunk's start is
    // backdated before the session window — a 32 s opening hole the pause tolerance cannot absorb.
    for (var i = 0; i < 3000; i++) {
      link.emitAudio();
    }
    await streamWithLiveSegments(link, 202, 'c1', fullSpans);

    await serverCloses(conversation('c1', origin, fullSpans));

    final (covered, hole) = await judgedWals();
    final originSeconds = origin.millisecondsSinceEpoch ~/ 1000;
    // The backdated copies land before the window; silence-only chunks inside
    // the tolerated transcript pauses fail closed alongside them.
    expect(
      hole.where((wal) => wal.timerStart < originSeconds),
      hasLength(1),
      reason: 'the backdated copy before the window stays uncovered',
    );
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
    expect(
      hole.every((wal) => wal.timerStart < talkStartSeconds || wal.timerStart + wal.seconds > talkStartSeconds),
      isTrue,
      reason: 'the pre-start copies and the boundary-straddling copy fail closed — no silence is inferred',
    );
    expect(hole.any((wal) => wal.timerStart < talkStartSeconds), isTrue);
    expect(covered, isNotEmpty, reason: 'the covered talk copy is retained-synced');
    expect(audioFilesOnDisk(), hasLength(covered.length + hole.length));
    await expectRecoveryUploads('c1', hole);
  });

  test('pendant: a transcript that stops early keeps the uncovered audio for repair', () async {
    // The server saved text for the first 20 s only. On the 10s custody
    // cadence the chunks overlapping that text are proven covered; every
    // later chunk fails closed and uploads for repair.
    final (origin, covered, hole) = await judgedReplay(200, const [(1, 20)]);
    expect(
        offsetsOf(covered, origin),
        [
          0,
          10,
          20,
        ],
        reason: 'the chunks overlapping the saved 20s (anchored via server start) are covered');
    expect(
        offsetsOf(hole, origin),
        [
          for (var t = 30; t <= 190; t += 10) t,
        ],
        reason: 'everything after the saved text fails closed');
    await expectRecoveryUploads('c1', hole);
  });

  test('pendant: a gapped timestamp transcript retains every copy and uploads nothing', () async {
    // Fifteen saved seconds in every twenty leave five-second pauses inside the tolerance,
    // so a transcript that mentions the whole session covers all of it.
    final (_, covered, hole) = await plainJudgedReplay(200, [for (var t = 1.0; t < 190; t += 20) (t, t + 15)]);
    expect(hole, isEmpty, reason: 'five-second pauses are tolerated, not repair holes');
    expect(covered, isNotEmpty);
    await expectRecoveryUploads('c1', hole);
  });

  test('pendant: a server clock ahead of the phone still covers via the live anchor', () async {
    final (_, covered, hole) = await fullyCoveredReplay(serverSkew: const Duration(minutes: 5));
    expect(world.uploads.attempts, isEmpty);
    expect(audioFilesOnDisk(), hasLength(covered.length + hole.length));
  });

  test('pendant: a server clock behind the phone still covers via the live anchor', () async {
    final (_, covered, hole) = await fullyCoveredReplay(serverSkew: const Duration(minutes: -5));
    expect(world.uploads.attempts, isEmpty);
    expect(audioFilesOnDisk(), hasLength(covered.length + hole.length));
  });

  test('pendant: no started_at uses the live anchor and ignores a stale created_at', () async {
    final (_, covered, hole) = await fullyCoveredReplay(hasStart: false);
    expect(world.uploads.attempts, isEmpty);
    expect(audioFilesOnDisk(), hasLength(covered.length + hole.length));
  });

  test('pendant: a conversation with no live arrivals and no start time still covers via the session start', () async {
    // An old row without started_at and no live anchor; the session-start fallback anchors the
    // spans, and their five-second pauses fall inside the tolerance.
    final (_, covered, hole) = await plainJudgedReplay(
        140,
        [
          for (var t = 1.0; t < 130; t += 20) (t, t + 15),
        ],
        hasStart: false);
    expect(hole, isEmpty);
    expect(covered, isNotEmpty);
    await expectRecoveryUploads('c1', hole);
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

    world.controller.onMessageEventReceived(
      ConversationProcessingStartedEvent(memory: conversation('c1', origin, [(1, 100)])),
    );
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
    expect(world.coverageEvents.any((event) => event['phase'] == 'confirmation' && event['kept_count'] != 0), isFalse);
  });

  test('pendant: retained-covered copies age out under auto-remove', () async {
    SharedPreferencesUtil().autoRemoveSyncedCopies = true;
    final (_, covered, hole) = await fullyCoveredReplay();
    expect(audioFilesOnDisk(), hasLength(covered.length + hole.length));

    // Nothing is old yet, then jump straight past the 30-day retention window — no timers needed.
    expect(await world.wal.syncs.phone.applySyncedCopyRetention(), 0);
    expect(audioFilesOnDisk(), hasLength(covered.length + hole.length));
    world.clock.advanceTo(world.clock.now().add(const Duration(days: 31)));
    final removed = await world.wal.syncs.phone.applySyncedCopyRetention();
    await settleFiles();

    expect(removed, covered.length);
    // The fail-closed silence copies were never synced, so auto-remove leaves
    // them pending on disk and in the index.
    expect(audioFilesOnDisk(), hasLength(hole.length));
    expect(await world.wal.syncs.phone.getAllWals(), hasLength(hole.length));
    expect(
      await WalFileManager.loadWals(),
      hasLength(hole.length),
      reason: 'the durable index keeps the unrepaired copies',
    );
  });

  test('pendant: retained-covered copies stay when auto-remove is off', () async {
    SharedPreferencesUtil().autoRemoveSyncedCopies = false;
    final (_, covered, hole) = await fullyCoveredReplay();
    expect(audioFilesOnDisk(), hasLength(covered.length + hole.length));

    world.clock.advanceTo(world.clock.now().add(const Duration(days: 31)));
    final removed = await world.wal.syncs.phone.applySyncedCopyRetention();
    await settleFiles();

    expect(removed, 0);
    expect(audioFilesOnDisk(), hasLength(covered.length + hole.length));
    expect(
      await WalFileManager.loadWals(),
      hasLength(covered.length + hole.length),
      reason: 'the durable index keeps the retained copies too',
    );
  });
}
