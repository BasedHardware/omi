import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart' show SyncJobStatusResponse;
import 'package:omi/gen/phone_mic_pigeon.g.dart';
import 'package:omi/services/capture/scenarios/capture_scenario.dart';
import 'package:omi/services/capture/scenarios/native_event_vector.dart';
import 'package:omi/services/mic/native_mic_recorder_service.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/enums.dart';

import '../support/capture/capture_replay_world.dart';

/// Deterministic capture -> frame processing -> file-backed WAL ->
/// recovery/upload replay schedules (SCA-489 / C3).
///
/// Every schedule runs the REAL production objects (CaptureController,
/// NativeMicRecorderService, TranscriptSegmentSocketService, WalService,
/// LocalWalSyncImpl, RecordingTransferCoordinator) against controlled
/// external I/O only: virtual clock, manual scheduler, scripted transport,
/// scripted upload boundary, fake native host. No wall-clock waits, no
/// network, no devices, synthetic audio only. Restart evidence reconstructs
/// production objects from real temp files, never reusing memory state.
///
/// Scenario ids mirror [CaptureScenarioCatalog.recordingRecovery].
void main() {
  late Directory tempDir;
  late CaptureReplayWorld world;

  setUp(() async {
    tempDir = await Directory.systemTemp.createTemp('capture_replay_');
    world = await CaptureReplayWorld.boot(tempDir: tempDir);
  });

  tearDown(() async {
    await world.dispose();
    if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
  });

  /// Keeps a live session healthy while advancing virtual time: 100 frames
  /// (10ms each = 1s of audio) per virtual second, matching the stall
  /// watchdog's expectations.
  Future<void> captureSeconds(int seconds, {required int sessionId, required int frameCursor}) async {
    for (var s = 0; s < seconds; s++) {
      world.injectAudioFrames(100, sessionId: sessionId, firstFrameIndex: frameCursor + s * 100);
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
    await world.startLiveCapture();
    final sessionId = world.hostApi.lastStartSessionId!;
    world.emitNativeState(PhoneMicCaptureState.running);
    await captureSeconds(2, sessionId: sessionId, frameCursor: frameCursor);
    world.setConnected(false);
    world.socket!.emitClose();
    await world.settle();
    await captureSeconds(seconds, sessionId: sessionId, frameCursor: frameCursor + 200);
    await world.stopLiveCapture();
    if (!leaveOffline) {
      world.setConnected(true);
      await world.settle();
    }
  }

  Future<List<List<int>>> readStoredWalFrames(Wal wal) async {
    final path = await Wal.getFilePath(wal.filePath);
    expect(path, isNotNull, reason: 'WAL must reference a real file on disk');
    final bytes = File(path!).readAsBytesSync();
    final frames = <List<int>>[];
    var offset = 0;
    while (offset + 4 <= bytes.length) {
      final length = ByteData.sublistView(bytes, offset, offset + 4).getUint32(0, Endian.little);
      offset += 4;
      frames.add(bytes.sublist(offset, offset + length));
      offset += length;
    }
    return frames;
  }

  List<List<int>> expectedFrames(int from, int to) =>
      List.generate(to - from, (i) => NativeEventVector.synthesizePcmFrame(from + i));

  // ---------------------------------------------------------------------------
  // 1. network-loss-reconnect-during-capture
  // ---------------------------------------------------------------------------

  test('network loss mid-capture retains unsynced frames in the WAL; recovery uploads them exactly once', () async {
    await world.startLiveCapture();
    final session1 = world.hostApi.lastStartSessionId!;
    world.emitNativeState(PhoneMicCaptureState.running);
    // 10s online: every frame is sent and marked synced.
    await captureSeconds(10, sessionId: session1, frameCursor: 0);
    final onlineSocket = world.socket!;
    expect(onlineSocket.sentBinary.length, 1000);

    // Network dies: transport drops, connectivity flips, capture continues.
    world.setConnected(false);
    onlineSocket.emitClose();
    await world.settle();
    // 15s offline: frames keep flowing into the WAL buffer; nothing is sent.
    await captureSeconds(15, sessionId: session1, frameCursor: 1000);
    expect(onlineSocket.sentBinary.length, 1000, reason: 'dead transport must not receive frames');

    // Connectivity returns mid-capture: the recovery coordinator wakes, but
    // live in-memory audio is still owned by the running session — nothing
    // can be uploaded yet.
    world.setConnected(true);
    await world.settle();
    expect(world.uploads.attempts, isEmpty, reason: 'in-memory frames belong to the live session, not the drain');

    // The keepalive reconnects at its 15s cadence: one failed attempt while
    // offline (rate-limited), then a successful one once the network is back.
    // Frames keep flowing throughout — a real mic does not pause for recovery.
    final createsAfterRestore = world.socketCreates;
    for (var s = 0; s < 16; s++) {
      world.injectAudioFrames(100, sessionId: world.hostApi.lastStartSessionId!, firstFrameIndex: 2500 + s * 100);
      await world.elapse(const Duration(seconds: 1));
    }
    expect(world.socketCreates - createsAfterRestore, lessThanOrEqualTo(2),
        reason: 'reconnect attempts are rate-limited to the 15s keepalive cadence');
    world.emitNativeState(PhoneMicCaptureState.running); // native engine is up on the fresh session
    await world.settle();
    expect(world.controller.recordingState, RecordingState.record,
        reason: 'the reconnected session returns to recording');
    final session2 = world.hostApi.lastStartSessionId!;
    expect(session2, session1 + 1);
    expect(world.hostApi.startSessionIds, [session1, session2], reason: 'one authoritative active session');

    // Streaming resumed on the reconnected transport.
    await captureSeconds(5, sessionId: session2, frameCursor: 4100);
    final reconnectedSocket = world.socket!;
    expect(reconnectedSocket, isNot(same(onlineSocket)));
    expect(reconnectedSocket.sentBinary.length, 600,
        reason:
            'post-reconnect frames stream on the new socket (the final restore-window second plus the recovered 5s)');

    // Session ends: the whole capture (online + offline + recovered windows) lands on disk.
    await world.stopLiveCapture();
    final createsAtStop = world.socketCreates;
    await world.elapse(const Duration(seconds: 20));
    expect(world.socketCreates, createsAtStop, reason: 'the keepalive dies with the session');

    final missing = await world.wal.syncs.phone.getMissingWals();
    expect(missing, hasLength(1));
    final wal = missing.single;
    expect(wal.status, WalStatus.miss);
    final storedFrames = await readStoredWalFrames(wal);
    expect(storedFrames, expectedFrames(0, 4600),
        reason: 'recoverable audio identity: stored bytes must equal the exact injected frame sequence');

    // Recovery drain uploads the WAL exactly once; a second wake is a no-op.
    await world.coordinator.wake(WakeTrigger.userRetry);
    await world.settle();
    expect(world.uploads.attempts, hasLength(1));
    final walPath = (await Wal.getFilePath(wal.filePath))!;
    expect(world.uploads.attempts.single.totalBytes, File(walPath).lengthSync());
    expect((await world.walCounts())[WalStatus.synced], 1);

    await world.coordinator.wake(WakeTrigger.userRetry);
    await world.settle();
    expect(world.uploads.attempts, hasLength(1), reason: 'synced WAL must never be re-uploaded locally');
  });

  test('stale native events carrying a retired session id are dropped, not applied', () async {
    await world.startLiveCapture();
    final session1 = world.hostApi.lastStartSessionId!;
    world.emitNativeState(PhoneMicCaptureState.running);
    world.injectAudioFrames(100, sessionId: session1);
    await world.stopLiveCapture();
    expect(world.hostApi.stopCalls, 1);

    // Fresh session on the same world.
    await world.startLiveCapture();
    final session2 = world.hostApi.lastStartSessionId!;
    world.emitNativeState(PhoneMicCaptureState.running);
    await world.settle();
    expect(world.controller.recordingState, RecordingState.record);

    // Stale terminal idle from session 1 must not stop the fresh session.
    world.emitNativeState(PhoneMicCaptureState.idle, sessionId: session1);
    await world.settle();
    expect(world.controller.recordingState, RecordingState.record,
        reason: 'a stale terminal idle must never clobber the current session');
    expect(world.hostApi.stopCalls, 1, reason: 'stale idle must not trigger a second native stop');

    // Stale audio frames are dropped: WAL sees only fresh-session frames.
    final framesBefore = world.wal.syncs.phone.testFrames.length;
    world.injectAudioFrames(10, sessionId: session1);
    expect(world.wal.syncs.phone.testFrames.length, framesBefore, reason: 'stale frames must not enter the WAL');
    world.injectAudioFrames(10, sessionId: session2);
    expect(world.wal.syncs.phone.testFrames.length, framesBefore + 10);

    // Foreign session ids are rejected entirely.
    world.emitNativeState(PhoneMicCaptureState.interrupted, sessionId: 999);
    world.emitNativeError('converter_failed', 'x', sessionId: 999);
    await world.settle();
    expect(world.controller.recordingState, RecordingState.record);
  });

  test('native terminal idle followed by Dart stop runs local teardown exactly once', () async {
    final host = FakePhoneMicHostApi();
    final service = NativeMicRecorderService(hostApi: host, registerFlutterApi: false);
    var stops = 0;
    await service.start(
      onByteReceived: (_) {},
      onRecording: () {},
      onStop: () => stops++,
      onInitializing: () {},
      onStalled: () {},
    );
    final sessionId = host.lastStartSessionId!;

    service.onStateChanged(PhoneMicCaptureState.idle, sessionId); // native-side terminal stop
    expect(stops, 1);
    service.stop(); // Dart-side redundancy must not double-fire teardown
    expect(stops, 1);
    expect(host.stopCalls, 1, reason: 'stop always forwards to native so an orphaned session dies');
  });

  // ---------------------------------------------------------------------------
  // 3. interruption-resumption
  // ---------------------------------------------------------------------------

  test('audio interruption mirrors state without teardown and resumes the same session', () async {
    await world.startLiveCapture();
    final sessionId = world.hostApi.lastStartSessionId!;
    world.emitNativeState(PhoneMicCaptureState.running);
    await captureSeconds(2, sessionId: sessionId, frameCursor: 0);

    world.emitNativeState(PhoneMicCaptureState.interrupted);
    await world.settle();
    expect(world.controller.recordingState, RecordingState.interrupted);
    expect(world.controller.isCallActive, isTrue);

    // Long silence during the interruption must NOT escalate to a stop/start
    // (native owns recovery; the stall watchdog stays silent).
    await world.elapse(const Duration(seconds: 8));
    expect(world.controller.recordingState, RecordingState.interrupted);
    expect(world.hostApi.startCalls, 1, reason: 'interruption is not a stall; no restart may occur');

    // Native resumes: state returns to record on the SAME session.
    world.emitNativeState(PhoneMicCaptureState.running);
    await world.settle();
    expect(world.controller.recordingState, RecordingState.record);
    expect(world.hostApi.lastStartSessionId, sessionId);
    await captureSeconds(2, sessionId: sessionId, frameCursor: 200);
    expect(world.socket!.sentBinary.length, 400);

    await world.stopLiveCapture();
    expect(world.hostApi.startCalls, 1);
    expect(world.hostApi.stopCalls, 1);
  });

  test('batch session survives interruption on progress liveness and escalates only on silence', () async {
    await world.startBatchCapture();
    final session1 = world.hostApi.lastStartSessionId!;
    expect(world.hostApi.lastStartMode, PhoneMicCaptureMode.batch);
    world.emitNativeState(PhoneMicCaptureState.running);

    world.emitNativeState(PhoneMicCaptureState.interrupted);
    await world.settle();
    expect(world.controller.recordingState, RecordingState.interrupted);

    // Progress keeps arriving through the interruption: liveness holds.
    for (var s = 0; s < 3; s++) {
      world.emitBatchProgress(1.0 * (s + 1));
      await world.elapse(const Duration(seconds: 1));
    }
    expect(world.controller.recordingState, RecordingState.interrupted);
    expect(world.hostApi.startCalls, 1);

    world.emitNativeState(PhoneMicCaptureState.running);
    await world.settle();
    expect(world.controller.recordingState, RecordingState.record);

    // Silence beyond the batch stall threshold (10s): bounded escalation —
    // tear down the dead session, start exactly one fresh one.
    await world.elapse(const Duration(seconds: 11));
    expect(world.hostApi.startCalls, 2, reason: 'stalled batch must escalate to a single fresh session');
    expect(world.hostApi.startSessionIds, [session1, session1 + 1]);
    world.emitNativeState(PhoneMicCaptureState.running);
    await world.settle();
    expect(world.controller.recordingState, RecordingState.record);
  });

  // ---------------------------------------------------------------------------
  // 4. partial-torn-persistence-reconstruction
  // ---------------------------------------------------------------------------

  test('process kill mid-capture: reconstruction reloads WAL state from real temp files', () async {
    await world.startLiveCapture();
    final sessionId = world.hostApi.lastStartSessionId!;
    world.emitNativeState(PhoneMicCaptureState.running);

    // 5s online, then the network dies but capture keeps running; the chunk
    // (75s) and flush (105s) timers materialize the unsynced audio on disk
    // before the process is killed.
    await captureSeconds(5, sessionId: sessionId, frameCursor: 0);
    world.setConnected(false);
    world.socket!.emitClose();
    await world.settle();
    await captureSeconds(105, sessionId: sessionId, frameCursor: 500);

    expect(File('${tempDir.path}/wals.json').existsSync(), isTrue, reason: 'WAL index must be on disk');
    final walIndexFiles = tempDir.listSync().whereType<File>().map((f) => f.path.split('/').last).toList();
    expect(walIndexFiles.any((n) => n.startsWith('audio_')), isTrue, reason: 'audio .bin must be on disk');

    world.killProcess();
    await world.reconstructProcess();

    final wals = await world.wal.syncs.phone.getAllWals();
    expect(wals, hasLength(1));
    final restored = wals.single;
    expect(restored.status, WalStatus.miss, reason: 'flushed-but-unuploaded WAL reloads as retryable');
    expect(restored.storage, WalStorage.disk);
    expect((await readStoredWalFrames(restored)).length, 6000,
        reason:
            'the 75s chunk stored a 60s WAL (6000 frames) and the 105s flush wrote it to disk; the in-memory tail dies with the process');
    // Recovery after restart uploads the reconstructed artifact once.
    await world.coordinator.wake(WakeTrigger.userRetry);
    await world.settle();
    expect(world.uploads.attempts, hasLength(1));
    expect((await world.walCounts())[WalStatus.synced], 1);
  });

  test('torn wals.json falls back to the backup file and keeps recoverable work', () async {
    // Batch-less world: a capture started while offline stays on the live WAL
    // path, so both saved generations below are deterministic.
    await world.dispose();
    world = await CaptureReplayWorld.boot(tempDir: tempDir, supportsBatch: false);
    // Two saved generations => wals.json has 2 WALs, wals_backup.json has 1.
    await produceWalOnDisk(12, frameCursor: 0);
    await produceWalOnDisk(12, frameCursor: 2000);
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
    await produceWalOnDisk(12);
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
    await produceWalOnDisk(12);

    // First drain: server refuses (non-transient) -> WAL stays miss.
    world.uploads.enqueueOutcome(() => throw StateError('server refused upload'));
    await world.coordinator.wake(WakeTrigger.userRetry);
    await world.settle();
    expect(world.uploads.attempts, hasLength(1));
    expect((await world.walCounts())[WalStatus.miss], 1, reason: 'failed upload must remain retryable');
    expect(world.coordinator.nextCooldownAt, world.clock.now().add(const Duration(seconds: 5)),
        reason: 'first failure schedules the first backoff step (5s)');

    // Retry at +5s fails again -> next backoff step is 10s.
    world.uploads.enqueueOutcome(() => throw StateError('server refused upload'));
    await world.elapse(const Duration(seconds: 5));
    expect(world.uploads.attempts, hasLength(2));
    expect((await world.walCounts())[WalStatus.miss], 1);
    expect(world.coordinator.nextCooldownAt, world.clock.now().add(const Duration(seconds: 10)),
        reason: 'backoff escalates 5s -> 10s');

    // Second retry succeeds -> terminal synced, retries stop.
    await world.elapse(const Duration(seconds: 10));
    expect(world.uploads.attempts, hasLength(3));
    expect((await world.walCounts())[WalStatus.synced], 1);
    expect(world.coordinator.nextCooldownAt, isNull, reason: 'success clears the retry schedule');

    await world.elapse(const Duration(seconds: 30));
    expect(world.uploads.attempts, hasLength(3), reason: 'no retries after acknowledgement');
  });

  test('queued upload: persisted -> enqueued(jobId) -> server-acknowledged(synced) stay distinct', () async {
    await produceWalOnDisk(12);
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

    // Non-terminal status again on a later pass: still not acknowledged.
    await world.coordinator.wake(WakeTrigger.userRetry);
    await world.settle();
    wal = (await world.wal.syncs.phone.getAllWals()).single;
    expect(wal.status, WalStatus.uploaded, reason: 'non-terminal job status must not flip the WAL');

    // Server completes the job -> acknowledged -> synced; no re-upload.
    world.jobStatuses['job-42'] = SyncJobFetch(
      SyncJobFetchOutcome.ok,
      SyncJobStatusResponse(jobId: 'job-42', status: 'completed'),
    );
    final uploadsBefore = world.uploads.attempts.length;
    await world.coordinator.wake(WakeTrigger.userRetry);
    await world.settle();
    wal = (await world.wal.syncs.phone.getAllWals()).single;
    expect(wal.status, WalStatus.synced);
    expect(world.uploads.attempts.length, uploadsBefore,
        reason: 'acknowledgement resolves by polling, never by re-uploading bytes');
  });

  // ---------------------------------------------------------------------------
  // 6. ownership-transition-outstanding-work
  // ---------------------------------------------------------------------------

  test('sign-out during outstanding WAL work stops reconnects and uploads; re-sign-in completes them', () async {
    await produceWalOnDisk(12); // leaves the network down and the WAL retryable

    final walBefore = (await world.wal.syncs.phone.getMissingWals()).single;
    final bytesBefore = File((await Wal.getFilePath(walBefore.filePath))!).lengthSync();

    // Account leaves (signed out) with retryable work outstanding; every
    // server interaction is refused while no account owns the device.
    world.signedIn = false;
    world.uploads.failAll = true;

    // Connectivity returning wakes recovery, but the server refuses the
    // upload: work stays local and retryable, the file untouched.
    world.setConnected(true);
    await world.settle();
    expect(world.uploads.attempts, isNotEmpty, reason: 'the refused attempt is visible');
    expect((await world.walCounts())[WalStatus.miss], 1, reason: 'refused upload keeps work local and retryable');
    expect(File((await Wal.getFilePath(walBefore.filePath))!).lengthSync(), bytesBefore,
        reason: 'refused attempts must not mutate the local artifact');

    // Socket reconnects are cancelled while signed out: after a transport
    // drop, the keepalive must not create new connections.
    await world.startLiveCapture();
    world.emitNativeState(PhoneMicCaptureState.running);
    final createsBefore = world.socketCreates;
    world.socket!.emitClose();
    await world.settle();
    await world.elapse(const Duration(seconds: 31));
    expect(world.socketCreates, createsBefore, reason: 'signed-out keepalive must cancel reconnects, not retry them');
    await world.stopLiveCapture();

    // A new account signs in on the same device: outstanding work completes.
    world.signedIn = true;
    world.uploads.failAll = false;
    await world.coordinator.wake(WakeTrigger.userRetry);
    await world.settle();
    expect((await world.walCounts())[WalStatus.synced], 1);
    expect(world.uploads.attempts.last.totalBytes, bytesBefore,
        reason: 'the acknowledged upload carries exactly the persisted bytes');
  });

  test('websocket close 4001 refreshes the rejected token at most once per 30s window', () async {
    Future<void> flowFor(int seconds, int fromFrame) async {
      for (var s = 0; s < seconds; s++) {
        world.injectAudioFrames(100,
            sessionId: world.hostApi.lastStartSessionId!, firstFrameIndex: fromFrame + s * 100);
        await world.elapse(const Duration(seconds: 1));
      }
    }

    await world.startLiveCapture();
    world.emitNativeState(PhoneMicCaptureState.running);
    await flowFor(1, 0);

    world.socket!.emitClose(4001);
    await world.settle();
    expect(world.tokenRefreshCalls, 1);

    // The keepalive reconnects within ~15s and the session resumes; a second
    // rejection inside the 30s window must not refresh again.
    await flowFor(16, 100);
    world.emitNativeState(PhoneMicCaptureState.running);
    await world.settle();
    expect(world.controller.recordingState, RecordingState.record);
    world.socket!.emitClose(4001);
    await world.settle();
    expect(world.tokenRefreshCalls, 1, reason: 'refresh is bounded within the 30s window');

    // Outside the window a further rejection refreshes again.
    await flowFor(31, 1700);
    world.emitNativeState(PhoneMicCaptureState.running);
    await world.settle();
    expect(world.controller.recordingState, RecordingState.record);
    world.socket!.emitClose(4001);
    await world.settle();
    expect(world.tokenRefreshCalls, 2);

    await world.stopLiveCapture();
  });

  // ---------------------------------------------------------------------------
  // Cleanup, clock advancement, session ownership
  // ---------------------------------------------------------------------------

  test('stop and dispose leave no pending capture timers and stop the recorder', () async {
    await world.startLiveCapture();
    final sessionId = world.hostApi.lastStartSessionId!;
    world.emitNativeState(PhoneMicCaptureState.running);
    await captureSeconds(2, sessionId: sessionId, frameCursor: 0);
    world.socket!.emitClose(); // arms the keepalive
    await world.settle();

    await world.stopLiveCapture();
    world.disposeController();
    await world.settle();

    // Only the WAL chunk/flush timers may remain; they die with wal.stop().
    final labels = world.scheduler.pendingTimerLabels;
    expect(labels, everyElement(matches('periodic')), reason: 'controller-owned one-shot timers must be gone: $labels');

    await world.wal.stop();
    expect(world.scheduler.hasPendingTimers, isFalse, reason: 'a stopped world must leave zero pending timers');
    expect(world.hostApi.stopCalls, greaterThanOrEqualTo(1));
  });

  test('sequential sessions mint strictly increasing session ids and distinct recording identities', () async {
    // Session 1: capture the identity while the session is live —
    // RecordingLifecycleTelemetry clears it when the session completes.
    await world.startLiveCapture();
    final first = world.hostApi.lastStartSessionId!;
    final firstRecordingId = world.controller.activeRecordingId;
    expect(firstRecordingId, isNotNull);
    world.emitNativeState(PhoneMicCaptureState.running);
    await captureSeconds(1, sessionId: first, frameCursor: 0);
    world.setConnected(false);
    world.socket!.emitClose();
    await world.settle();
    await captureSeconds(12, sessionId: first, frameCursor: 100);
    await world.stopLiveCapture();
    world.setConnected(true);
    await world.settle();

    // Session 2 on the same device.
    await world.startLiveCapture();
    final second = world.hostApi.lastStartSessionId!;
    final secondRecordingId = world.controller.activeRecordingId;
    expect(secondRecordingId, isNotNull);
    world.emitNativeState(PhoneMicCaptureState.running);
    await captureSeconds(1, sessionId: second, frameCursor: 1400);
    world.setConnected(false);
    world.socket!.emitClose();
    await world.settle();
    await captureSeconds(12, sessionId: second, frameCursor: 1500);
    await world.stopLiveCapture();

    expect(second, greaterThan(first));
    expect(world.hostApi.startSessionIds, [first, second],
        reason: 'exactly one authoritative native session at a time');
    expect(secondRecordingId, isNot(firstRecordingId), reason: 'each capture session mints a fresh recording identity');
  });

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

  test('native event vectors are deterministic and replay identically through the Dart seam', () async {
    // Identical seeds produce identical audio; adjacent frames differ.
    expect(NativeEventVector.synthesizePcmFrame(7), NativeEventVector.synthesizePcmFrame(7));
    expect(NativeEventVector.synthesizePcmFrame(7), isNot(equals(NativeEventVector.synthesizePcmFrame(8))));

    // A vector built with stale/fresh session ids replays with the exact
    // accept/drop decisions the session-identity gate mandates.
    final vector = NativeEventVector(
      id: 'stale-idle-after-restart',
      revision: 1,
      startSessionId: 1,
      events: [
        NativeCaptureEvent.state('running', 1),
        NativeCaptureEvent.frame([], 1),
        NativeCaptureEvent.state('idle', 1),
        NativeCaptureEvent.state('idle', 2),
      ],
    );

    final host = FakePhoneMicHostApi();
    final service = NativeMicRecorderService(hostApi: host, registerFlutterApi: false);
    var stops = 0;
    await service.start(onByteReceived: (_) {}, onStop: () => stops++);
    await service.start(onByteReceived: (_) {}, onStop: () => stops++); // session 2 now current

    for (final event in vector.events) {
      switch (event.kind) {
        case NativeCaptureEventKind.audioFrame:
          service.onAudioFrame(Uint8List.fromList(event.pcmFrame ?? const []), event.sessionId);
        case NativeCaptureEventKind.stateChanged:
          service.onStateChanged(
            PhoneMicCaptureState.values.byName(event.state ?? 'idle'),
            event.sessionId,
          );
        case NativeCaptureEventKind.captureError:
          service.onCaptureError(event.errorCode ?? '', event.errorMessage ?? '', event.sessionId);
        case NativeCaptureEventKind.batchProgress:
          service.onBatchProgress(event.capturedSeconds ?? 0, event.sessionId);
      }
    }
    // Session-1 idle is dropped; session-2 idle (current) stops once.
    expect(stops, 1);
    expect(host.startSessionIds, [1, 2]);

    // JSON round-trip preserves the replay inputs exactly.
    final decoded = NativeEventVector.fromJson(vector.toJson());
    expect(decoded.id, vector.id);
    expect(decoded.revision, vector.revision);
    expect(decoded.events.length, vector.events.length);
    expect(decoded.schemaVersion, nativeEventVectorSchemaVersion);
  });
}
