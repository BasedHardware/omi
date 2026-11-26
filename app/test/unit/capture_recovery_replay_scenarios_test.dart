import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart' show SyncJobStatusResponse;
import 'package:omi/services/capture/scenarios/capture_scenario.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

import '../support/capture/capture_replay_world.dart';
import '../support/capture/scripted_device_connection.dart';

/// Deterministic capture -> frame processing -> file-backed WAL ->
/// recovery/upload replay schedules (SCA-489 / C3).
///
/// Every schedule runs the REAL production objects (CaptureController,
/// BLE device source, TranscriptSegmentSocketService, WalService,
/// LocalWalSyncImpl, RecordingTransferCoordinator) against controlled
/// external I/O only: virtual clock, manual scheduler, scripted transport,
/// scripted upload boundary, scripted BLE connection. No wall-clock waits, no
/// network, no devices, synthetic audio only. Restart evidence reconstructs
/// production objects from real temp files, never reusing memory state.
///
/// Scenario ids mirror [CaptureScenarioCatalog.recordingRecovery].
void main() {
  late Directory tempDir;
  late CaptureReplayWorld world;

  setUp(() async {
    tempDir = await Directory.systemTemp.createTemp('capture_replay_');
    world = await CaptureReplayWorld.boot(tempDir: tempDir, pendantCodec: BleAudioCodec.opus);
  });

  tearDown(() async {
    await world.dispose();
    if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
  });

  /// Keeps a live session healthy while advancing virtual time: 100 frames
  /// (10ms each = 1s of audio) per virtual second, matching the stall
  /// watchdog's expectations.
  Future<void> captureSeconds(int seconds, {required int frameCursor}) async {
    for (var s = 0; s < seconds; s++) {
      world.deviceConnection!.emitFixtureFrames(100, firstFrameIndex: frameCursor + s * 100);
      await world.elapse(const Duration(seconds: 1));
    }
  }

  /// Captures [seconds] of unsynced audio (network down) then stops cleanly,
  /// leaving one retryable WAL on disk.
  ///
  /// [leaveOffline] keeps the network down afterwards so no connectivity
  /// restoration can auto-drain the WAL before the scenario scripts its
  /// outcome; pass false when a later live session must start online again
  /// (the restored connectivity will legitimately upload the finished WAL).
  Future<void> produceWalOnDisk(int seconds, {int frameCursor = 0, bool leaveOffline = true}) async {
    world.deviceConnection = ScriptedDeviceConnection();
    await world.controller.streamDeviceRecording(
      device: BtDevice(id: 'recovery-pendant', name: 'Omi', type: DeviceType.omi, rssi: -40),
    );
    await world.settle();
    await captureSeconds(2, frameCursor: frameCursor);
    world.setConnected(false);
    world.socket!.emitClose();
    await world.settle();
    await captureSeconds(seconds, frameCursor: frameCursor + 200);
    await world.controller.stopStreamDeviceRecording(cleanDevice: true);
    await world.settle();
    if (!leaveOffline) {
      world.setConnected(true);
      await world.settle();
    }
  }

  test('torn wals.json falls back to the backup file and keeps recoverable work', () async {
    // Batch-less world: a capture started while offline stays on the live WAL
    // path, so both saved generations below are deterministic.
    await world.dispose();
    world = await CaptureReplayWorld.boot(tempDir: tempDir, pendantCodec: BleAudioCodec.opus);
    // Two saved generations => wals.json has 2 WALs, wals_backup.json has 1.
    await produceWalOnDisk(2, frameCursor: 0);
    await produceWalOnDisk(2, frameCursor: 2000);
    expect((await world.wal.syncs.phone.getAllWals()), hasLength(2));

    world.killProcess();

    // Torn write: cut the index file mid-JSON.
    final walFile = File('${tempDir.path}/wals.json');
    final bytes = walFile.readAsBytesSync();
    walFile.writeAsBytesSync(bytes.sublist(0, bytes.length ~/ 3), flush: true);
    expect(File('${tempDir.path}/wals_backup.json').existsSync(), isTrue);

    await world.reconstructProcess();

    final wals = await world.wal.syncs.phone.getAllWals();
    expect(wals, hasLength(1), reason: 'backup recovery must restore the last durable generation');
    expect(wals.single.status, WalStatus.miss);
    expect(wals.single.filePath, isNotNull);

    await world.coordinator.wake(WakeTrigger.userRetry);
    await world.settle();
    expect(world.uploads.attempts, hasLength(1));
    expect((await world.walCounts())[WalStatus.synced], 1);
  });

  test('WAL whose audio file was deleted is classified corrupted on recovery, not silently retried', () async {
    await produceWalOnDisk(5);
    final wal = (await world.wal.syncs.phone.getMissingWals()).single;
    world.killProcess();

    // Storage loss between sessions: the index survives, the audio does not.
    File((await Wal.getFilePath(wal.filePath))!).deleteSync();

    await world.reconstructProcess();
    final reloaded = (await world.wal.syncs.phone.getAllWals()).single;
    expect(reloaded.status, WalStatus.miss);

    await world.coordinator.wake(WakeTrigger.userRetry);
    await world.settle();

    final after = (await world.wal.syncs.phone.getAllWals()).single;
    expect(after.status, WalStatus.corrupted,
        reason: 'missing audio must become terminal corruption, not an infinite retry');
    expect(world.uploads.attempts, isEmpty, reason: 'no upload can be attempted without bytes');
    expect(await world.wal.syncs.phone.getMissingWals(), isEmpty, reason: 'corrupted WAL leaves the retry queue');
  });

  // ---------------------------------------------------------------------------
  // 5. failed-upload-retry-recovery
  // ---------------------------------------------------------------------------

  test('failed upload stays retryable with bounded backoff and succeeds on the scheduled retry', () async {
    await produceWalOnDisk(5);

    void eventQueuePressure() {
      for (var i = 0; i < 32; i++) {
        scheduleMicrotask(() {});
        Timer.run(() {});
      }
    }

    // First drain: server refuses (non-transient) -> WAL stays miss.
    world.uploads.enqueueOutcome(() => throw StateError('server refused upload'));
    await world.coordinator.wake(WakeTrigger.userRetry);
    await world.settle();
    expect(world.uploads.attempts, hasLength(1));
    expect((await world.walCounts())[WalStatus.miss], 1, reason: 'failed upload must remain retryable');
    expect(world.coordinator.nextCooldownAt, world.clock.now().add(const Duration(seconds: 5)),
        reason: 'first failure schedules the first backoff step (5s)');

    // Retry at +5s fails again -> next backoff step is 10s. Event-queue
    // pressure must not hide the cooldown drain (CI load reproduced this).
    world.uploads.enqueueOutcome(() => throw StateError('server refused upload'));
    eventQueuePressure();
    await world.elapse(const Duration(seconds: 5));
    eventQueuePressure();
    await world.settle();
    expect(world.uploads.attempts, hasLength(2));
    expect((await world.walCounts())[WalStatus.miss], 1);
    expect(world.coordinator.nextCooldownAt, world.clock.now().add(const Duration(seconds: 10)),
        reason: 'backoff escalates 5s -> 10s');

    // Second retry succeeds -> terminal synced, retries stop.
    eventQueuePressure();
    await world.elapse(const Duration(seconds: 10));
    expect(world.uploads.attempts, hasLength(3));
    expect((await world.walCounts())[WalStatus.synced], 1);
    expect(world.coordinator.nextCooldownAt, isNull, reason: 'success clears the retry schedule');

    await world.elapse(const Duration(seconds: 30));
    expect(world.uploads.attempts, hasLength(3), reason: 'no retries after acknowledgement');
  });

  test('in-flight cooldown drain finishes before dispose so WAL index writes cannot race temp-dir teardown', () async {
    await produceWalOnDisk(5);
    world.uploads.enqueueOutcome(() => throw StateError('server refused upload'));
    await world.coordinator.wake(WakeTrigger.userRetry);
    await world.settle();
    expect(world.uploads.attempts, hasLength(1));

    world.uploads.enqueueOutcome(() => throw StateError('server refused upload'));
    // Fire the backoff timer without settling: the production cooldown wake is
    // unawaited. dispose() must still drain it before the caller may delete
    // the documents directory.
    world.scheduler.elapse(const Duration(seconds: 5));
    await world.dispose();
    expect(world.uploads.attempts, hasLength(2), reason: 'dispose waits for the in-flight retry drain');
    expect(tempDir.existsSync(), isTrue);
    tempDir.deleteSync(recursive: true);
    expect(tempDir.existsSync(), isFalse);
  });

  test('queued upload: persisted -> enqueued(jobId) -> server-acknowledged(synced) stay distinct', () async {
    await produceWalOnDisk(5);
    world.uploads.enqueueOutcome(() => UploadFilesResult.queued('job-42'));
    // The server accepts the job and is still processing it.
    world.jobStatuses['job-42'] = SyncJobFetch(
      SyncJobFetchOutcome.ok,
      SyncJobStatusResponse(jobId: 'job-42', status: 'processing'),
    );

    await world.coordinator.wake(WakeTrigger.userRetry);
    await world.settle();

    var wal = (await world.wal.syncs.phone.getAllWals()).single;
    expect(wal.status, WalStatus.uploaded, reason: 'queued job is enqueued, not yet acknowledged');
    expect(wal.jobId, 'job-42');
    final walPath = (await Wal.getFilePath(wal.filePath))!;
    expect(File(walPath).existsSync(), isTrue,
        reason: 'uploaded-but-unconfirmed audio is retained until server acknowledgement');

    // Upload hints intentionally delay the first poll; event wakes cannot bypass them.
    expect(world.jobPolls, isEmpty);
    await world.coordinator.wake(WakeTrigger.userRetry);
    await world.settle();
    expect(world.jobPolls, isEmpty);
    await world.elapse(const Duration(seconds: 20));
    // Non-terminal status on the first eligible pass: still not acknowledged.
    await world.coordinator.wake(WakeTrigger.userRetry);
    await world.settle();
    wal = (await world.wal.syncs.phone.getAllWals()).single;
    expect(wal.status, WalStatus.uploaded, reason: 'non-terminal job status must not flip the WAL');
    expect(world.jobPolls, hasLength(1));

    // Server completes the job -> acknowledged -> synced; no re-upload.
    world.jobStatuses['job-42'] = SyncJobFetch(
      SyncJobFetchOutcome.ok,
      SyncJobStatusResponse(jobId: 'job-42', status: 'completed'),
    );
    final uploadsBefore = world.uploads.attempts.length;
    await world.coordinator.wake(WakeTrigger.userRetry);
    await world.settle();
    expect(world.jobPolls, hasLength(1), reason: 'same-time wakes cannot repoll a processing job');
    await world.elapse(const Duration(seconds: 20));
    await world.coordinator.wake(WakeTrigger.userRetry);
    await world.settle();
    wal = (await world.wal.syncs.phone.getAllWals()).single;
    expect(wal.status, WalStatus.synced);
    expect(world.jobPolls, hasLength(2));
    expect(world.uploads.attempts.length, uploadsBefore,
        reason: 'acknowledgement resolves by polling, never by re-uploading bytes');
  });

  test('a job the server refuses for an input reason stops re-uploading the same bytes', () async {
    await produceWalOnDisk(5);
    // More queued outcomes than wakes: any re-upload is visible as an attempt
    // rather than being absorbed by the script running dry.
    for (var i = 0; i < 12; i++) {
      world.uploads.enqueueOutcome(() => UploadFilesResult.queued('job-undecodable'));
    }
    // The measured production verdict for an undecodable recording: the whole
    // job fails because nothing in the batch produced PCM.
    world.jobStatuses['job-undecodable'] = SyncJobFetch(
      SyncJobFetchOutcome.ok,
      SyncJobStatusResponse(
        jobId: 'job-undecodable',
        status: 'failed',
        totalSegments: 1,
        processedSegments: 1,
        failedSegments: 1,
        reasonCode: 'sync_invalid_audio',
        error: 'Audio decode failed',
      ),
    );

    await world.coordinator.wake(WakeTrigger.userRetry);
    await world.settle();
    expect(world.uploads.attempts, hasLength(1), reason: 'the first attempt is what earns the verdict');

    final walPath = (await Wal.getFilePath((await world.wal.syncs.phone.getAllWals()).single.filePath))!;
    final bytesAfterVerdict = File(walPath).lengthSync();

    // Advance the upload's poll deadline before earning the terminal input verdict.
    expect(world.jobPolls, isEmpty);
    await world.elapse(const Duration(seconds: 20));
    await world.coordinator.wake(WakeTrigger.userRetry);
    await world.settle();
    expect(world.jobPolls, hasLength(1));

    // Every later wake reason the app has: foreground, connectivity, device,
    // cooldown, startup — plus the most permissive one, an explicit retry.
    for (final trigger in WakeTrigger.values) {
      await world.coordinator.wake(trigger);
      await world.settle();
    }

    expect(world.uploads.attempts, hasLength(1),
        reason: 'a permanently refused recording must not buy another upload on every wake');

    final wal = (await world.wal.syncs.phone.getAllWals()).single;
    expect(wal.status, WalStatus.unsupportedAudio,
        reason: 'audio is never dropped — only the sync attempt is terminal');
    expect(wal.syncDisplayState, WalSyncDisplayState.unsupportedAudio);
    expect(File(walPath).lengthSync(), bytesAfterVerdict, reason: 'the local recording is retained untouched');

    // The row used to render as "Failed — tap Retry", which sent the same bytes
    // back for the same verdict on every tap and left the needs-attention banner
    // permanent. The verdict is now stated instead of re-armed.
    expect(wal.syncDisplayState, isNot(WalSyncDisplayState.failed));
    expect(isRetryableSyncState(wal.syncDisplayState), isFalse);

    // A deliberate call still reaches the server — audio is never orphaned — but
    // the sync pages no longer offer it for this state, they offer deletion.
    await world.wal.syncs.phone.syncWal(wal: wal);
    await world.settle();
    expect(world.uploads.attempts, hasLength(2), reason: 'a deliberate retry is honoured');

    // That retry earns the same verdict after its poll hint, and the loop stays closed.
    await world.elapse(const Duration(seconds: 20));
    await world.coordinator.wake(WakeTrigger.cooldownElapsed);
    await world.settle();
    expect(world.uploads.attempts, hasLength(2), reason: 'one deliberate tap buys exactly one upload');
    expect(
      (await world.wal.syncs.phone.getAllWals()).single.syncDisplayState,
      WalSyncDisplayState.unsupportedAudio,
    );
  });

  test('a transient job failure keeps its per-attempt retry budget', () async {
    await produceWalOnDisk(5);
    for (var i = 0; i < 12; i++) {
      world.uploads.enqueueOutcome(() => UploadFilesResult.queued('job-flaky'));
    }
    world.jobStatuses['job-flaky'] = SyncJobFetch(
      SyncJobFetchOutcome.ok,
      SyncJobStatusResponse(
        jobId: 'job-flaky',
        status: 'failed',
        totalSegments: 1,
        processedSegments: 1,
        failedSegments: 1,
        reasonCode: 'stt_upstream_error',
      ),
    );

    await world.coordinator.wake(WakeTrigger.userRetry);
    await world.settle();
    expect(world.jobPolls, isEmpty, reason: 'upload admission does not immediately poll');
    await world.elapse(const Duration(seconds: 20));
    // Observe the first verdict before the coordinator drains the newly retryable WAL.
    await world.wal.syncs.phone.reconcileUploadedWals();
    await world.settle();
    expect(world.jobPolls, hasLength(1));
    expect(world.uploads.attempts, hasLength(1));
    expect((await world.wal.syncs.phone.getAllWals()).single.retryCount, 1,
        reason: 'an upstream failure costs one attempt, not the whole budget');

    await world.coordinator.wake(WakeTrigger.userRetry);
    await world.settle();
    expect(world.jobPolls, hasLength(1), reason: 'the second upload also honors its first-poll delay');
    await world.elapse(const Duration(seconds: 20));
    await world.wal.syncs.phone.reconcileUploadedWals();
    await world.settle();
    expect(world.jobPolls, hasLength(2));
    final wal = (await world.wal.syncs.phone.getAllWals()).single;
    expect(world.uploads.attempts, hasLength(2), reason: 'transient failures keep retrying');
    expect(wal.retryCount, 2);
    expect(wal.syncDisplayState, WalSyncDisplayState.retrying);
  });

  // ---------------------------------------------------------------------------
  // Cleanup, clock advancement, session ownership
  // ---------------------------------------------------------------------------

  // ---------------------------------------------------------------------------
  // Contracts: catalog, results, native event vectors (C2/C4/C5 surfaces)
  // ---------------------------------------------------------------------------

  test('scenario catalog exposes the six recording-recovery schedules with stable ids', () {
    expect(CaptureScenarioCatalog.ids, hasLength(6));
    expect(
      CaptureScenarioCatalog.ids,
      containsAll([
        'network-loss-reconnect-during-capture',
        'stale-native-event-after-stop-new-session',
        'interruption-resumption',
        'partial-torn-persistence-reconstruction',
        'failed-upload-retry-recovery',
        'ownership-transition-outstanding-work',
      ]),
    );
    expect(CaptureScenarioCatalog.recordingRecovery.any((s) => s.negative), isTrue);
  });

  test('scenario result contract round-trips with timeline and observations', () {
    const result = CaptureScenarioResult(
      scenarioId: 'network-loss-reconnect-during-capture',
      outcome: CaptureScenarioOutcome.passed,
      timeline: [CaptureScenarioTimelineEntry(at: Duration(seconds: 10), event: 'connectivity=lost')],
      observations: {'wals_synced': 1},
    );
    final json = result.toJsonString();
    expect(json, contains('"contract_version": "capture-scenario/v1"'));
    expect(json, contains('"outcome": "passed"'));
  });
}
