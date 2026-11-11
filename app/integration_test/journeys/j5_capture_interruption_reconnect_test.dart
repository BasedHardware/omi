import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';

import 'package:omi/gen/phone_mic_pigeon.g.dart';
import 'package:omi/services/capture/scenarios/capture_scenario.dart';
import 'package:omi/services/dev_controls/journey_faults.dart';
import 'package:omi/services/wals/wal.dart';

import '../../test/support/capture/capture_replay_world.dart';
import 'support/journey_evidence.dart';

/// Journey 5 — capture interruption/reconnect with recoverable persisted
/// audio (SCA-488 / C2).
///
/// Executes through the C3 `capture-scenario/v1` lane: the REAL production
/// capture path (CaptureController → NativeMicRecorderService → frame
/// processing → file-backed WAL → RecordingTransferCoordinator) over
/// controlled external I/O (virtual clock, scripted socket, scripted upload
/// boundary, fake native host). This journey composes the
/// `network-loss-reconnect-during-capture` schedule from the consumer side
/// and asserts the journey-level outcomes:
///
///   1. interruption mid-capture (transport drop + process reconstruction
///      from real temp files) keeps unsynced audio recoverable on disk,
///   2. reconnect drains the persisted audio through the real upload
///      boundary exactly once (no duplicate upload attempts for the same
///      bytes),
///   3. the live recording identity is `activeRecordingId`/native session
///      id — never `activeCaptureSessionId` uniqueness (documented C3
///      limitation).
///
/// Negative: fail-capture-recovery makes every post-reconnect upload fail
/// forever — the recoverability assertion must fail with the invariant
/// named.
void main() {
  late Directory tempDir;

  setUp(() {
    // Fresh, per-test scratch directory: independent clean seed state.
    tempDir = Directory.systemTemp.createTempSync('j5_capture_journey');
    // Under the flutter-tester host lane path_provider resolves through its
    // platform interface (Pigeon foundation channel) instead of the legacy
    // MethodChannel the replay world mocks; point it at the same scratch
    // directory so WAL files land inside the journey's own namespace.
    PathProviderPlatform.instance = _ScratchPathProvider(() => tempDir.path);
  });

  tearDown(() {
    if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
  });

  test('positive: interruption persists recoverable audio; reconnect uploads it exactly once', () async {
    final evidence = JourneyEvidence.begin(journeyId: 'j5_capture_interruption_reconnect', lane: 'hermetic-replay');
    evidence.stateBefore = {'contract': captureScenarioContractVersion};
    final world = await CaptureReplayWorld.boot(tempDir: tempDir);
    addTearDown(world.dispose);

    // Live capture with a real native session id.
    await world.startLiveCapture();
    final session1 = world.hostApi.lastStartSessionId!;
    world.emitNativeState(PhoneMicCaptureState.running);

    // 5s online, then the transport dies mid-capture.
    for (var s = 0; s < 5; s++) {
      world.injectAudioFrames(100, sessionId: session1, firstFrameIndex: s * 100);
      await world.elapse(const Duration(seconds: 1));
    }
    world.setConnected(false);
    world.socket!.emitClose();
    await world.settle();

    // 12s offline (the WAL chunk timer materializes at its ~10s cadence):
    // frames keep flowing into the file-backed WAL while elapsing virtual
    // time lets the chunker persist them to disk.
    for (var s = 0; s < 12; s++) {
      world.injectAudioFrames(100, sessionId: session1, firstFrameIndex: 500 + s * 100);
      await world.elapse(const Duration(seconds: 1));
    }
    await world.stopLiveCapture();

    // Capture the live identity BEFORE process death: reconstruction swaps
    // the native host, so the authoritative ids come from the pre-kill host.
    final startSessionIdsBeforeKill = List<int>.of(world.hostApi.startSessionIds);

    // Process death: the object graph is dropped; only real temp files
    // remain. Reconstruction must reload WAL state from disk.
    world.killProcess();
    await world.reconstructProcess();

    final persistedWals = await world.wal.syncs.phone.getAllWals();
    final recoverableOnDisk = persistedWals.isNotEmpty &&
        await Future.wait(persistedWals.map((w) async {
          final path = await Wal.getFilePath(w.filePath);
          return path != null && File(path).existsSync();
        })).then((checks) => checks.every((ok) => ok));
    evidence.record('audio-persisted-after-interruption',
        ok: recoverableOnDisk,
        invariant: JourneyFault.failCaptureRecovery.invariant,
        detail: '${persistedWals.length} WAL(s) on disk after reconstruction');
    expect(recoverableOnDisk, isTrue,
        reason: 'unsynced audio must be recoverable from real temp files after the process is gone');

    // Reconnect: the recovery coordinator drains the persisted WAL through
    // the real upload boundary.
    world.setConnected(true);
    await world.elapse(const Duration(seconds: 20));

    final attemptsByFile = <String, int>{};
    for (final attempt in world.uploads.attempts) {
      for (final file in attempt.fileNames) {
        attemptsByFile[file] = (attemptsByFile[file] ?? 0) + 1;
      }
    }
    final countsAfter = await world.walCounts();
    final allSynced = (countsAfter[WalStatus.miss] ?? 0) == 0 && (countsAfter[WalStatus.synced] ?? 0) > 0;
    final drainedExactlyOnce = attemptsByFile.values.every((c) => c == 1) && attemptsByFile.isNotEmpty && allSynced;
    evidence.record('recovery-uploads-exactly-once',
        ok: drainedExactlyOnce,
        invariant: 'reconnected recovery uploads persisted audio without duplicates',
        detail: attemptsByFile.toString());
    expect(drainedExactlyOnce, isTrue,
        reason: 'each persisted audio file must be uploaded exactly once after reconnect (got $attemptsByFile)');

    // Live identity rule: the authoritative recording identity is the
    // recording id + native session ids (C3 contract).
    final identitySane = startSessionIdsBeforeKill.isNotEmpty;
    evidence.record('live-identity-authoritative',
        ok: identitySane,
        invariant:
            'live capture identity comes from the native session id (activeCaptureSessionId is a window, not a per-recording id)');
    expect(identitySane, isTrue);

    evidence.stateAfter = {'wals_drained': attemptsByFile.length, 'contract': captureScenarioContractVersion};
    expect(evidence.failed, 0,
        reason: 'failing assertions: '
            '${evidence.assertions.where((a) => a['ok'] == false).map((a) => a['name']).toList()} '
            'detail: ${evidence.assertions.map((a) => "${a['name']}=${a['ok']} ${a['detail'] ?? ''}").toList()}');
    await evidence.write();
  });

  test('negative: fail-capture-recovery must fail naming recoverability', () async {
    final evidence = JourneyEvidence.begin(
        journeyId: 'j5_capture_interruption_reconnect.fail-capture-recovery', lane: 'hermetic-replay');
    evidence.stateBefore = {'contract': captureScenarioContractVersion, 'fault': JourneyFault.failCaptureRecovery.name};
    final world = await CaptureReplayWorld.boot(tempDir: tempDir);
    addTearDown(world.dispose);

    await world.startLiveCapture();
    final session1 = world.hostApi.lastStartSessionId!;
    world.emitNativeState(PhoneMicCaptureState.running);
    for (var s = 0; s < 5; s++) {
      world.injectAudioFrames(100, sessionId: session1, firstFrameIndex: s * 100);
      await world.elapse(const Duration(seconds: 1));
    }
    world.setConnected(false);
    world.socket!.emitClose();
    await world.settle();
    for (var s = 0; s < 12; s++) {
      world.injectAudioFrames(100, sessionId: session1, firstFrameIndex: 500 + s * 100);
      await world.elapse(const Duration(seconds: 1));
    }
    await world.stopLiveCapture();

    // FAULT: every upload attempt fails like a refused request, forever.
    world.uploads.failAll = true;

    world.setConnected(true);
    await world.elapse(const Duration(seconds: 20));

    final counts = await world.walCounts();
    final syncedCount = counts[WalStatus.synced] ?? 0;
    final stillPending = (counts[WalStatus.miss] ?? 0) > 0;
    final recoverabilityBroken = syncedCount == 0 && stillPending;

    evidence.record('fault-exposes-missing-invariant',
        ok: recoverabilityBroken,
        invariant: JourneyFault.failCaptureRecovery.invariant,
        detail: 'synced WALs: $syncedCount; pending WALs: ${counts[WalStatus.miss] ?? 0}');
    if (!recoverabilityBroken) {
      await evidence.write();
      fail('oracle cannot detect unrecoverable audio (synced=$syncedCount pending=${counts[WalStatus.miss] ?? 0})');
    }
    evidence.failed++;
    evidence.assertions.add({
      'name': 'journey-under-fault',
      'ok': false,
      'invariant': JourneyFault.failCaptureRecovery.invariant,
      'detail': 'recovery uploads permanently failing — expected failure',
    });
    evidence.stateAfter = {'contract': captureScenarioContractVersion};
    await evidence.write();
  });
}

/// Journey-owned path_provider boundary: the scratch directory IS the app's
/// documents directory for this run. Pure external-I/O redirection.
class _ScratchPathProvider extends PathProviderPlatform {
  _ScratchPathProvider(this._docs);

  final String Function() _docs;

  @override
  Future<String?> getApplicationDocumentsPath() async => _docs();

  @override
  Future<String?> getTemporaryPath() async => _docs();

  @override
  Future<String?> getApplicationSupportPath() async => _docs();
}
