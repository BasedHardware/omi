// A pendant socket can outlive several server conversations. Each close must retain its own
// durable audio boundary and transcript evidence without adopting the next conversation's copies.
import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/services/capture/empty_recording_notice.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/wal_file_manager.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';
import '../../support/refactor_flag_adapter.dart';

void main() {
  late Directory directory;
  late CaptureReplayWorld world;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('capture_next_window_');
    world = await CaptureReplayWorld.boot(
      tempDir: directory,
      pendantCodec: BleAudioCodec.opus,
      initialPrefs: {'conversationSilenceDuration': -1, 'uid': 'owner-a'},
    );
    // This regression exercises the legacy saved-transcript coverage contract. Committed receipt
    // custody, and Custom STT's deliberate coverage fallback, have separate assertions below.
    await setRefactorFlags({'custody_capture_committed_release': false});
  });

  tearDown(() async {
    await world.dispose();
    AnalyticsManager.resetForTesting();
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

  TranscriptSegment segment(String id, double end) => TranscriptSegment(
        id: '$id-words',
        text: 'synthetic words',
        speaker: 'SPEAKER_00',
        isUser: false,
        personId: null,
        start: 0,
        end: end,
        translations: [],
      );

  ServerConversation conversation(String id, DateTime origin, {double end = 140}) => ServerConversation(
        id: id,
        createdAt: origin,
        startedAt: origin,
        structured: Structured('fixture', 'fixture'),
        transcriptSegments: [segment(id, end)],
      );

  Future<void> streamPendant(ScriptedDeviceConnection link, int seconds) async {
    for (var s = 0; s < seconds; s++) {
      for (var i = 0; i < 100; i++) {
        link.emitAudio();
      }
      await world.elapse(const Duration(seconds: 1));
    }
  }

  bool retained(Wal wal) => wal.status == WalStatus.synced && wal.syncedAt > 0 && !wal.keptForTranscriptRecovery;
  bool kept(Wal wal) => wal.status == WalStatus.miss && wal.keptForTranscriptRecovery;

  /// A quiet event queue does not prove that an unawaited stamp reached disk. Require the actual
  /// expected state in both inventories, with nonempty sets at each call site.
  Future<List<Wal>> walsReach(String expectation, bool Function(List<Wal>) done) async {
    for (var i = 0; i < 200; i++) {
      final wals = await world.wal.syncs.phone.getAllWals();
      if (done(wals) && done(await WalFileManager.loadWals())) return wals;
      await world.settle();
      await Future<void>.delayed(const Duration(milliseconds: 15));
    }
    final wals = await world.wal.syncs.phone.getAllWals();
    fail('WALs never reached "$expectation": ${[
      for (final wal in wals)
        '${wal.filePath}: ${wal.totalFrames} frames ${wal.status.name} syncedAt=${wal.syncedAt} '
            'recovery=${wal.keptForTranscriptRecovery} conversation=${wal.conversationId}',
    ].join('; ')}');
  }

  int framesOf(Iterable<Wal> wals) => wals.fold(0, (count, wal) => count + wal.totalFrames);

  Future<List<Wal>> stamped(String id, {int frames = 14000}) => walsReach('$id stamped durably', (wals) {
        final selected = wals.where((wal) => wal.conversationId == id);
        return selected.isNotEmpty && framesOf(selected) == frames;
      });

  Future<List<Wal>> confirmed(String id, {int frames = 14000}) =>
      walsReach('$id covered copies retained durably', (wals) {
        final selected = wals.where((wal) => wal.conversationId == id);
        return selected.isNotEmpty && framesOf(selected) == frames && selected.every(retained);
      });

  Future<void> serverCloses(ServerConversation saved, {int frames = 14000}) async {
    world.controller.onMessageEventReceived(ConversationProcessingStartedEvent(memory: saved));
    await stamped(saved.id, frames: frames);
    world.controller.onMessageEventReceived(ConversationEvent(memory: saved, messages: []));
    await confirmed(saved.id, frames: frames);
  }

  Future<void> recoveryPass() async {
    await world.coordinator.wake(WakeTrigger.dataStalled);
    await world.settle();
  }

  String fileName(Wal wal) => (wal.filePath ?? wal.getFileName() as String).split('/').last;

  Set<String> filesOf(Iterable<Wal> wals) => {for (final wal in wals) fileName(wal)};

  bool filesExist(Iterable<String> names) => names.every((name) => File('${directory.path}/$name').existsSync());

  Future<void> expectRecoveryUploads(String conversationId, List<Wal> holes) async {
    final expectedNames = holes.map(fileName).toList();
    await recoveryPass();
    expect(world.uploads.attempts.expand((attempt) => attempt.fileNames), unorderedEquals(expectedNames));
    expect(world.uploads.attempts.map((attempt) => attempt.conversationId).toSet(), {conversationId});
    await walsReach('only the repair copies become synced', (wals) {
      final repaired = wals.where((wal) => expectedNames.contains(fileName(wal)));
      return repaired.length == expectedNames.length && repaired.every(retained);
    });
    final attempts = world.uploads.attempts.length;
    await recoveryPass();
    expect(world.uploads.attempts, hasLength(attempts), reason: 'a second pass cannot upload the same repair twice');
    expect(filesExist(expectedNames), isTrue, reason: 'repair preserves the source audio under retention');
  }

  test('pendant: three conversations on one socket each retain their covered backup without upload', () async {
    final link = await connectPendant();
    final sockets = world.socketCreates;
    final expectedFiles = <String, Set<String>>{};

    for (final id in ['c1', 'c2', 'c3']) {
      final origin = world.clock.now();
      await streamPendant(link, 140);
      // Observe the live arrival independently of the saved server clock.
      world.controller.onSegmentReceived([segment(id, 140)]);
      expect((await world.wal.syncs.phone.getAllWals()).where((wal) => wal.conversationId == null), isNotEmpty,
          reason: '$id must have real audio copies before its close');
      await serverCloses(conversation(id, origin));
      final selected = (await world.wal.syncs.phone.getAllWals()).where((wal) => wal.conversationId == id);
      expectedFiles[id] = filesOf(selected);
      expect(expectedFiles[id], isNotEmpty);
    }

    expect(expectedFiles.values.expand((files) => files).toSet().length,
        expectedFiles.values.fold<int>(0, (count, files) => count + files.length),
        reason: 'each durable backup belongs to exactly one conversation');
    await recoveryPass();
    expect(world.socketCreates, sockets, reason: 'all conversations use the original pendant socket');
    expect(world.uploads.attempts, isEmpty, reason: 'covered saved audio must not be uploaded again');
    final persisted = await WalFileManager.loadWals();
    for (final entry in expectedFiles.entries) {
      expect(filesOf(persisted.where((wal) => wal.conversationId == entry.key)), entry.value);
      expect(filesExist(entry.value), isTrue,
          reason: 'coverage moves copies into retention rather than deleting audio');
    }

    world.killProcess();
    await world.reconstructProcess();
    await recoveryPass();
    expect(world.uploads.attempts, isEmpty,
        reason: 'the durable confirmation also suppresses duplicate upload after restart');
    for (final entry in expectedFiles.entries) {
      final restored = (await world.wal.syncs.phone.getAllWals()).where((wal) => wal.conversationId == entry.key);
      expect(filesOf(restored), entry.value);
      expect(restored.every(retained), isTrue);
    }
  });

  test('pendant: reversed confirmations retain c1 without releasing partial c2 audio', () async {
    final link = await connectPendant();
    final firstOrigin = world.clock.now();
    await streamPendant(link, 20);
    final c1 = conversation('c1', firstOrigin, end: 20);
    world.controller.onMessageEventReceived(ConversationProcessingStartedEvent(memory: c1));
    final firstFiles = filesOf((await stamped('c1', frames: 2000)).where((wal) => wal.conversationId == 'c1'));

    // Keep both confirmations inside the first close's 30-second fallback deadline.
    final secondOrigin = world.clock.now();
    await streamPendant(link, 20);
    final c2 = conversation('c2', secondOrigin, end: 10);
    world.controller.onMessageEventReceived(ConversationProcessingStartedEvent(memory: c2));
    await stamped('c2', frames: 2000);
    world.controller.onMessageEventReceived(ConversationEvent(memory: c2, messages: []));
    final secondJudged = await walsReach('c2 covered opening and uncovered tail judged independently', (wals) {
      final second = wals.where((wal) => wal.conversationId == 'c2').toList();
      return framesOf(second) == 2000 &&
          second.any(retained) &&
          second.any(kept) &&
          second.every((wal) => retained(wal) || kept(wal));
    });
    final holes = secondJudged.where((wal) => wal.conversationId == 'c2' && kept(wal)).toList();
    final holeFiles = filesOf(holes);
    expect(secondJudged.where((wal) => wal.conversationId == 'c1').every((wal) => !retained(wal)), isTrue,
        reason: 'c2 confirmation supplies no coverage for c1');

    world.controller.onMessageEventReceived(ConversationEvent(memory: c1, messages: []));
    final afterFirst = await confirmed('c1', frames: 2000);
    expect(filesOf(afterFirst.where((wal) => wal.conversationId == 'c1')), firstFiles);
    expect(filesOf(afterFirst.where((wal) => wal.conversationId == 'c2' && kept(wal))), holeFiles,
        reason: 'late c1 coverage cannot release the holes belonging to c2');
    await expectRecoveryUploads('c2', holes);
  });

  test('pendant: a duplicate processing event cannot consume the next conversation window', () async {
    final link = await connectPendant();
    final firstOrigin = world.clock.now();
    await streamPendant(link, 20);
    final c1 = conversation('c1', firstOrigin, end: 20);
    await serverCloses(c1, frames: 2000);

    final secondOrigin = world.clock.now();
    await streamPendant(link, 20);
    final secondWindow = world.controller.activeCaptureSessionId;
    expect(secondWindow, isNotNull);
    world.controller.onMessageEventReceived(ConversationProcessingStartedEvent(memory: c1));
    expect(world.controller.activeCaptureSessionId, secondWindow,
        reason: 'a repeated close for c1 cannot rotate the live c2 window');
    await serverCloses(conversation('c2', secondOrigin, end: 20), frames: 2000);
    final wals = await world.wal.syncs.phone.getAllWals();
    expect(framesOf(wals.where((wal) => wal.conversationId == 'c1')), 2000);
    expect(framesOf(wals.where((wal) => wal.conversationId == 'c2')), 2000);
    await recoveryPass();
    expect(world.uploads.attempts, isEmpty);
  });

  test('pendant: delayed typed Process Now result keeps its snapshot when c2 closes first', () async {
    final processed = Completer<InProgressProcessOutcome>();
    world.processOutcome = () => processed.future;
    addTearDown(() {
      if (!processed.isCompleted) processed.complete(const InProgressProcessOutcome(absence: ProcessAbsence.transport));
    });
    final link = await connectPendant();
    final firstOrigin = world.clock.now();
    await streamPendant(link, 20);
    await world.controller.forceProcessingCurrentConversation();
    final firstFiles = filesOf(
        await walsReach('Process Now snapshot persisted before its response', (wals) => framesOf(wals) == 2000));
    expect(firstFiles, isNotEmpty);

    final secondOrigin = world.clock.now();
    await streamPendant(link, 20);
    final c2 = conversation('c2', secondOrigin, end: 20);
    world.controller.onMessageEventReceived(ConversationProcessingStartedEvent(memory: c2));
    world.controller.onMessageEventReceived(ConversationEvent(memory: c2, messages: []));
    processed.complete(InProgressProcessOutcome(
        response: CreateConversationResponse(messages: [], conversation: conversation('p1', firstOrigin, end: 20))));

    await confirmed('p1', frames: 2000);
    final finalWals = await confirmed('c2', frames: 2000);
    expect(filesOf(finalWals.where((wal) => wal.conversationId == 'p1')), firstFiles);
    expect(filesOf(finalWals.where((wal) => wal.conversationId == 'c2')).intersection(firstFiles), isEmpty);
    await recoveryPass();
    expect(world.uploads.attempts, isEmpty);
  });

  test('pendant: a matching server event before Process Now response cannot adopt intervening audio', () async {
    world.autoUploadAllowed = false;
    final processed = Completer<InProgressProcessOutcome>();
    world.processOutcome = () => processed.future;
    addTearDown(() {
      if (!processed.isCompleted) processed.complete(const InProgressProcessOutcome(absence: ProcessAbsence.transport));
    });
    final link = await connectPendant();
    final firstOrigin = world.clock.now();
    await streamPendant(link, 20);
    await world.controller.forceProcessingCurrentConversation();
    final firstFiles =
        filesOf(await walsReach('original Process Now cut is durable', (wals) => framesOf(wals) == 2000));

    await streamPendant(link, 20);
    final p1 = conversation('p1', firstOrigin, end: 20);
    world.controller.onMessageEventReceived(ConversationProcessingStartedEvent(memory: p1));
    world.controller.onMessageEventReceived(ConversationEvent(memory: p1, messages: []));
    processed.complete(InProgressProcessOutcome(response: CreateConversationResponse(messages: [], conversation: p1)));
    await confirmed('p1', frames: 2000);
    final afterResponse = await walsReach('intervening cut stays unlinked after the matching response', (wals) {
      final original = wals.where((wal) => wal.conversationId == 'p1');
      final intervening = wals.where((wal) => wal.conversationId == null);
      return framesOf(wals) == 4000 &&
          filesOf(original).containsAll(firstFiles) &&
          framesOf(original) == 2000 &&
          framesOf(intervening) == 2000 &&
          intervening.every((wal) => !retained(wal));
    });
    final interveningFiles = filesOf(afterResponse.where((wal) => wal.conversationId == null));
    expect(interveningFiles.intersection(firstFiles), isEmpty);

    final secondOrigin = world.clock.now();
    await streamPendant(link, 20);
    await serverCloses(conversation('c2', secondOrigin, end: 20), frames: 2000);
    final finalWals = await world.wal.syncs.phone.getAllWals();
    expect(filesOf(finalWals.where((wal) => wal.conversationId == 'p1')), firstFiles);
    expect(filesOf(finalWals.where((wal) => wal.conversationId == null)), interveningFiles);
    expect(
        filesOf(finalWals.where((wal) => wal.conversationId == 'c2'))
            .intersection({...firstFiles, ...interveningFiles}),
        isEmpty,
        reason: 'the next confirmed close owns only audio admitted after the ambiguous event');
    expect(filesExist(filesOf(finalWals)), isTrue);
    await recoveryPass();
    expect(world.uploads.attempts, isEmpty);
  });

  test('pendant: concurrent Process Now responses preserve both original cuts and the intervening ambiguity', () async {
    world.autoUploadAllowed = false;
    final firstResponse = Completer<InProgressProcessOutcome>();
    final secondResponse = Completer<InProgressProcessOutcome>();
    var requests = 0;
    world.processOutcome = () {
      requests++;
      if (requests == 1) return firstResponse.future;
      if (requests == 2) return secondResponse.future;
      throw StateError('unexpected third Process Now request');
    };
    addTearDown(() {
      for (final pending in [firstResponse, secondResponse]) {
        if (!pending.isCompleted) pending.complete(const InProgressProcessOutcome(absence: ProcessAbsence.transport));
      }
    });
    final link = await connectPendant();
    final firstOrigin = world.clock.now();
    await streamPendant(link, 20);
    await world.controller.forceProcessingCurrentConversation();
    final firstFiles =
        filesOf(await walsReach('first reserved Process Now cut persisted', (wals) => framesOf(wals) == 2000));

    final secondOrigin = world.clock.now();
    await streamPendant(link, 20);
    await world.controller.forceProcessingCurrentConversation();
    final firstTwo =
        await walsReach('both Process Now cuts persisted before their responses', (wals) => framesOf(wals) == 4000);
    final secondFiles = filesOf(firstTwo).difference(firstFiles);
    expect(secondFiles, isNotEmpty);
    expect(requests, 2, reason: 'both HTTP requests must be pending when the server event arrives');

    await streamPendant(link, 20);
    final firstSaved = conversation('process-a', firstOrigin, end: 20);
    world.controller.onMessageEventReceived(ConversationProcessingStartedEvent(memory: firstSaved));
    world.controller.onMessageEventReceived(ConversationEvent(memory: firstSaved, messages: []));
    secondResponse.complete(InProgressProcessOutcome(
        response:
            CreateConversationResponse(messages: [], conversation: conversation('process-b', secondOrigin, end: 20))));
    // Let B's response handler run while A is unresolved. Durable outcomes below, rather than this
    // scheduling step, establish that the server event did not forget A or adopt the newer cut.
    await world.settle();
    firstResponse.complete(
        InProgressProcessOutcome(response: CreateConversationResponse(messages: [], conversation: firstSaved)));

    await confirmed('process-a', frames: 2000);
    await confirmed('process-b', frames: 2000);
    final resolved = await walsReach('matching older response leaves only the intervening cut unlinked', (wals) {
      final intervening = wals.where((wal) => wal.conversationId == null);
      return framesOf(wals) == 6000 && framesOf(intervening) == 2000 && intervening.every((wal) => !retained(wal));
    });
    final interveningFiles = filesOf(resolved.where((wal) => wal.conversationId == null));
    expect(filesOf(resolved.where((wal) => wal.conversationId == 'process-a')), firstFiles);
    expect(filesOf(resolved.where((wal) => wal.conversationId == 'process-b')), secondFiles);
    expect(interveningFiles.intersection({...firstFiles, ...secondFiles}), isEmpty);

    final nextOrigin = world.clock.now();
    await streamPendant(link, 20);
    await serverCloses(conversation('c', nextOrigin, end: 20), frames: 2000);
    final finalWals = await world.wal.syncs.phone.getAllWals();
    expect(framesOf(finalWals), 8000);
    expect(filesOf(finalWals.where((wal) => wal.conversationId == 'process-a')), firstFiles);
    expect(filesOf(finalWals.where((wal) => wal.conversationId == 'process-b')), secondFiles);
    expect(filesOf(finalWals.where((wal) => wal.conversationId == null)), interveningFiles);
    expect(
        filesOf(finalWals.where((wal) => wal.conversationId == 'c'))
            .intersection({...firstFiles, ...secondFiles, ...interveningFiles}),
        isEmpty);
    expect(filesExist(filesOf(finalWals)), isTrue);
    await recoveryPass();
    expect(world.uploads.attempts, isEmpty);
  });

  for (final throwsRequest in [false, true]) {
    test(
        'pendant: pending Process Now ${throwsRequest ? 'exception' : 'transport absence'} preserves ambiguous cuts and unblocks the next close',
        () async {
      world.autoUploadAllowed = false;
      final processed = Completer<InProgressProcessOutcome>();
      world.processOutcome = () => processed.future;
      addTearDown(() {
        if (!processed.isCompleted) {
          processed.complete(const InProgressProcessOutcome(absence: ProcessAbsence.transport));
        }
      });
      final link = await connectPendant();
      await streamPendant(link, 20);
      await world.controller.forceProcessingCurrentConversation();
      await walsReach('first ambiguous cut is durable', (wals) => framesOf(wals) == 2000);

      final ambiguousOrigin = world.clock.now();
      await streamPendant(link, 20);
      final ambiguous = conversation('ambiguous', ambiguousOrigin, end: 20);
      world.controller.onMessageEventReceived(ConversationProcessingStartedEvent(memory: ambiguous));
      world.controller.onMessageEventReceived(ConversationEvent(memory: ambiguous, messages: []));
      if (throwsRequest) {
        processed.completeError(StateError('synthetic Process Now transport failure'), StackTrace.current);
      } else {
        processed.complete(const InProgressProcessOutcome(absence: ProcessAbsence.transport));
      }
      final unresolved = await walsReach('neither ambiguous cut acquires a guessed conversation',
          (wals) => framesOf(wals) == 4000 && wals.every((wal) => wal.conversationId == null && !retained(wal)));
      final unresolvedFiles = filesOf(unresolved);

      final nextOrigin = world.clock.now();
      await streamPendant(link, 20);
      await serverCloses(conversation('next', nextOrigin, end: 20), frames: 2000);
      // A stale fallback must also leave the ambiguity intact after the new close has succeeded.
      await world.elapse(const Duration(seconds: 40));
      final finalWals = await world.wal.syncs.phone.getAllWals();
      final stillUnresolved = finalWals.where((wal) => unresolvedFiles.contains(fileName(wal))).toList();
      expect(framesOf(stillUnresolved), 4000);
      expect(stillUnresolved.every((wal) => wal.conversationId == null && !retained(wal)), isTrue);
      expect(filesOf(finalWals.where((wal) => wal.conversationId == 'next')).intersection(unresolvedFiles), isEmpty);
      expect(filesExist(filesOf(finalWals)), isTrue,
          reason: 'failed processing cannot consume the recoverable source audio');
      await recoveryPass();
      expect(world.uploads.attempts, isEmpty);
    });
  }

  test('pendant: server close during Process Now drain adopts the reserved audio boundary', () async {
    final writeEntered = Completer<void>();
    final releaseWrite = Completer<void>();
    var blockWrites = false;
    var heldWrite = false;
    Future<void>? process;
    addTearDown(() async {
      if (!releaseWrite.isCompleted) releaseWrite.complete();
      await process;
    });
    // Inject the existing persistence seam only for this deterministic race. Every admitted write
    // still goes through the real WalFileManager, so the assertions include the durable index.
    await world.dispose();
    world = await CaptureReplayWorld.boot(
      tempDir: directory,
      pendantCodec: BleAudioCodec.opus,
      initialPrefs: {'conversationSilenceDuration': -1, 'uid': 'owner-a'},
      phonePersistWals: (wals) async {
        if (blockWrites && !heldWrite) {
          heldWrite = true;
          writeEntered.complete();
          await releaseWrite.future;
        }
        if (!await WalFileManager.saveWals(wals)) throw StateError('test WAL index write failed');
      },
    );
    await setRefactorFlags({'custody_capture_committed_release': false});
    final link = await connectPendant();
    final origin = world.clock.now();
    await streamPendant(link, 20);
    for (var i = 0; i < 100; i++) {
      link.emitAudio();
    }
    blockWrites = true;
    process = world.controller.forceProcessingCurrentConversation();
    await writeEntered.future.timeout(const Duration(seconds: 2));

    // The processing event closes the same live window whose forced drain is still awaiting disk.
    // Its revision change must not strand that earlier reservation or let the next close steal it.
    final c1 = conversation('c1', origin, end: 21);
    world.controller.onMessageEventReceived(ConversationProcessingStartedEvent(memory: c1));
    final secondOrigin = world.clock.now();
    for (var i = 0; i < 100; i++) {
      link.emitAudio();
    }
    releaseWrite.complete();
    await process;
    world.controller.onMessageEventReceived(ConversationEvent(memory: c1, messages: []));
    await stamped('c1', frames: 2100);

    await streamPendant(link, 19);
    await serverCloses(conversation('c2', secondOrigin, end: 20), frames: 2000);
    final wals = await world.wal.syncs.phone.getAllWals();
    expect(framesOf(wals.where((wal) => wal.conversationId == 'c1')), 2100);
    expect(framesOf(wals.where((wal) => wal.conversationId == 'c2')), 2000);
    expect(wals.where((wal) => wal.conversationId == null), isEmpty);
    expect(filesExist(filesOf(wals)), isTrue);
  });

  test('pendant: older Process Now event during a second blocked drain cannot adopt the second reservation', () async {
    final firstResponse = Completer<InProgressProcessOutcome>();
    final writeEntered = Completer<void>();
    final releaseWrite = Completer<void>();
    var blockWrites = false;
    var heldWrite = false;
    Future<void>? secondProcess;
    addTearDown(() async {
      if (!releaseWrite.isCompleted) releaseWrite.complete();
      if (!firstResponse.isCompleted) {
        firstResponse.complete(const InProgressProcessOutcome(absence: ProcessAbsence.transport));
      }
      await secondProcess;
    });
    await world.dispose();
    world = await CaptureReplayWorld.boot(
      tempDir: directory,
      pendantCodec: BleAudioCodec.opus,
      initialPrefs: {'conversationSilenceDuration': -1, 'uid': 'owner-a'},
      phonePersistWals: (wals) async {
        if (blockWrites && !heldWrite) {
          heldWrite = true;
          writeEntered.complete();
          await releaseWrite.future;
        }
        if (!await WalFileManager.saveWals(wals)) throw StateError('test WAL index write failed');
      },
    );
    await setRefactorFlags({'custody_capture_committed_release': false});
    world.autoUploadAllowed = false;
    world.processOutcome = () => firstResponse.future;
    final link = await connectPendant();
    final firstOrigin = world.clock.now();
    await streamPendant(link, 20);
    await world.controller.forceProcessingCurrentConversation();
    final firstFiles = filesOf(await walsReach('first Process Now cut persisted', (wals) => framesOf(wals) == 2000));

    await streamPendant(link, 20);
    for (var i = 0; i < 100; i++) {
      link.emitAudio();
    }
    blockWrites = true;
    secondProcess = world.controller.forceProcessingCurrentConversation();
    await writeEntered.future.timeout(const Duration(seconds: 2));
    final firstSaved = conversation('process-a', firstOrigin, end: 20);
    world.controller.onMessageEventReceived(ConversationProcessingStartedEvent(memory: firstSaved));
    world.controller.onMessageEventReceived(ConversationEvent(memory: firstSaved, messages: []));
    releaseWrite.complete();
    await secondProcess;
    expect(world.processCalls, 1, reason: 'the server close supersedes the second request during its drain');
    firstResponse.complete(
        InProgressProcessOutcome(response: CreateConversationResponse(messages: [], conversation: firstSaved)));

    await confirmed('process-a', frames: 2000);
    final afterResponse =
        await walsReach('second reserved cut stays recoverable after the older matching response', (wals) {
      final unresolved = wals.where((wal) => wal.conversationId == null);
      return framesOf(wals) == 4100 && framesOf(unresolved) == 2100 && unresolved.every((wal) => !retained(wal));
    });
    final secondFiles = filesOf(afterResponse.where((wal) => wal.conversationId == null));
    expect(filesOf(afterResponse.where((wal) => wal.conversationId == 'process-a')), firstFiles);

    final nextOrigin = world.clock.now();
    await streamPendant(link, 20);
    await serverCloses(conversation('c', nextOrigin, end: 20), frames: 2000);
    final finalWals = await world.wal.syncs.phone.getAllWals();
    expect(framesOf(finalWals), 6100);
    expect(filesOf(finalWals.where((wal) => wal.conversationId == 'process-a')), firstFiles);
    expect(filesOf(finalWals.where((wal) => wal.conversationId == null)), secondFiles);
    expect(filesOf(finalWals.where((wal) => wal.conversationId == 'c')).intersection({...firstFiles, ...secondFiles}),
        isEmpty);
    expect(filesExist(filesOf(finalWals)), isTrue);
    await recoveryPass();
    expect(world.uploads.attempts, isEmpty);
  });

  test('pendant: an uncertain Process Now response cannot attach its audio to c2', () async {
    world.autoUploadAllowed = false;
    world.processOutcome = () async => const InProgressProcessOutcome(absence: ProcessAbsence.transport);
    final link = await connectPendant();
    await streamPendant(link, 20);
    await world.controller.forceProcessingCurrentConversation();
    final uncertainFiles =
        filesOf(await walsReach('uncertain Process Now audio stays durable', (wals) => framesOf(wals) == 2000));
    expect(uncertainFiles, isNotEmpty);

    final secondOrigin = world.clock.now();
    await streamPendant(link, 20);
    await serverCloses(conversation('c2', secondOrigin, end: 20), frames: 2000);
    final wals = await world.wal.syncs.phone.getAllWals();
    final uncertain = wals.where((wal) => uncertainFiles.contains(fileName(wal))).toList();
    expect(framesOf(uncertain), 2000);
    expect(uncertain.every((wal) => wal.conversationId == null && !retained(wal)), isTrue,
        reason: 'a transport failure does not prove which conversation the backend created');
    expect(filesExist(uncertainFiles), isTrue);
    await recoveryPass();
    expect(world.uploads.attempts, isEmpty);
  });

  for (final rawAudio in [false, true]) {
    test('Custom STT second window preserves partial coverage and upload choice rawAudio=$rawAudio', () async {
      await setRefactorFlags({'custody_capture_committed_release': true});
      await SharedPreferencesUtil().saveCustomSttConfig(
          CustomSttConfig(provider: SttProvider.geminiLive, apiKey: 'synthetic-key', sendRawAudioToOmi: rawAudio));
      world.autoUploadAllowed = false;
      final link = await connectPendant();
      final firstOrigin = world.clock.now();
      await streamPendant(link, 60);
      world.controller.onSegmentReceived([segment('custom1', 60)]);
      await serverCloses(conversation('custom1', firstOrigin, end: 60), frames: 6000);

      final secondOrigin = world.clock.now();
      await streamPendant(link, 20);
      world.controller.onSegmentReceived([segment('custom2', 20)]);
      await streamPendant(link, 40);
      final c2 = conversation('custom2', secondOrigin, end: 20);
      world.controller.onMessageEventReceived(ConversationProcessingStartedEvent(memory: c2));
      await stamped('custom2', frames: 6000);
      // Saved coverage belongs to the admitted Custom STT socket, even after a setting change.
      await SharedPreferencesUtil().saveCustomSttConfig(const CustomSttConfig(provider: SttProvider.omi));
      world.controller.onMessageEventReceived(ConversationEvent(memory: c2, messages: []));
      final finalWals = await walsReach('second Custom STT opening retained and uncovered tail recoverable', (wals) {
        final second = wals.where((wal) => wal.conversationId == 'custom2').toList();
        return framesOf(second) == 6000 &&
            second.any(retained) &&
            second.any(kept) &&
            second.every((wal) => retained(wal) || kept(wal));
      });
      expect(finalWals.where((wal) => wal.conversationId == 'custom1').every(retained), isTrue);
      expect(filesExist(filesOf(finalWals)), isTrue);
      await recoveryPass();
      expect(world.uploads.attempts, isEmpty,
          reason: 'partial transcription cannot override the Custom STT upload choice');
    });
  }

  test('pendant: a late server close after explicit stop opens no new capture window', () async {
    final link = await connectPendant();
    final origin = world.clock.now();
    await streamPendant(link, 20);
    await world.controller.stopStreamDeviceRecording();
    final files = filesOf(await walsReach('stopped recording audio is durable', (wals) => framesOf(wals) == 2000));
    final sockets = world.socketCreates;
    final saved = conversation('late', origin, end: 20);
    world.controller.onMessageEventReceived(ConversationProcessingStartedEvent(memory: saved));
    world.controller.onMessageEventReceived(ConversationEvent(memory: saved, messages: []));
    await world.elapse(const Duration(seconds: 40));

    expect(world.controller.activeCaptureSessionId, isNull);
    expect(world.socketCreates, sockets);
    expect(filesExist(files), isTrue, reason: 'late server events cannot discard the stopped recording');
  });

  test('pendant: callbacks after controller disposal cannot create a new close or timer', () async {
    final link = await connectPendant();
    final origin = world.clock.now();
    await streamPendant(link, 20);
    await world.wal.syncs.phone.finalizeCurrentSession();
    final files = filesOf(await walsReach('audio is durable before disposal', (wals) => framesOf(wals) == 2000));
    final disposed = world.controller;
    world.disposeController();
    final timers = world.scheduler.pendingTimerLabels.toList();
    final saved = conversation('late', origin, end: 20);
    disposed.onMessageEventReceived(ConversationProcessingStartedEvent(memory: saved));
    disposed.onMessageEventReceived(ConversationEvent(memory: saved, messages: []));
    expect(world.scheduler.pendingTimerLabels, timers,
        reason: 'an already disposed owner cannot admit a fallback timer');
    await world.elapse(const Duration(seconds: 40));
    expect(filesExist(files), isTrue);
    expect((await world.wal.syncs.phone.getAllWals()).every((wal) => wal.conversationId == null), isTrue);
  });

  test('pendant: account cutover during the second close cannot mutate successor inventory', () async {
    final link = await connectPendant();
    final firstOrigin = world.clock.now();
    await streamPendant(link, 20);
    await serverCloses(conversation('c1', firstOrigin, end: 20), frames: 2000);
    final secondOrigin = world.clock.now();
    await streamPendant(link, 20);
    final c2 = conversation('c2', secondOrigin, end: 20);
    world.controller.onMessageEventReceived(ConversationProcessingStartedEvent(memory: c2));

    final phone = world.wal.syncs.phone;
    phone.clearUserData();
    SharedPreferencesUtil().uid = 'owner-b';
    world.controller.clearUserData();
    final successor = Wal(
      timerStart: world.clock.now().millisecondsSinceEpoch ~/ 1000 + 1000,
      codec: BleAudioCodec.opus,
      seconds: 10,
      totalFrames: 1000,
      ownerUid: 'owner-b',
      recordingSessionId: 'successor-recording',
      storage: WalStorage.disk,
      status: WalStatus.miss,
    );
    phone.testWals = [successor];
    world.controller.onMessageEventReceived(ConversationEvent(memory: c2, messages: []));
    // Join the WAL buffer lane behind the admitted close, then deliver any old fallback deadline.
    await phone.finalizeCurrentSession();
    await world.elapse(const Duration(seconds: 40));
    final remaining = await phone.getAllWals();
    expect(remaining, hasLength(1));
    expect(identical(remaining.single, successor), isTrue);
    expect(successor.conversationId, isNull);
    expect(successor.status, WalStatus.miss);
    expect(successor.keptForTranscriptRecovery, isFalse);
    expect(world.uploads.attempts, isEmpty);
  });
}
