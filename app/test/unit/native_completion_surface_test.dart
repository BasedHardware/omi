import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/services/wals/native_recording_intake.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import '../support/custody_test_helpers.dart';

void main() {
  late Directory dir;
  const name = 'audio_omibatchphone_opus_16000_1_fs320_1720000000.bin';
  setUp(() async {
    dir = await custodyDirectory();
    await File('${dir.path}/$name').writeAsBytes([1, 0, 0, 0, 5]);
    await SharedPreferencesUtil().saveString('localRecordingJobs', jsonEncode({name: 'legacy-job'}));
  });
  tearDown(() async => dir.delete(recursive: true));

  test('manual acceptance stays on Home, wakes reconciliation, and failed processing stays held', () async {
    await SharedPreferencesUtil().remove('localRecordingJobs');
    var clock = DateTime.now();
    final gate = SyncUploadGate(
        limiter: SyncRateLimiter.instance,
        fairUseStatusLoader: () async => {'stage': 'none'},
        uploader: (files,
                {onUploadProgress,
                conversationId,
                captureEvidence,
                recordingSessionId,
                audioStartSeconds,
                audioEndSeconds,
                claimLiveCapture = false,
                geolocation}) async =>
            UploadFilesResult.queued('manual-job'));
    final ledger = await custodyLedger(
        gate: gate,
        now: () => clock,
        fetch: (id) async => SyncJobFetch(SyncJobFetchOutcome.ok,
            SyncJobStatusResponse(jobId: id, status: 'failed', totalSegments: 1, failedSegments: 1)));
    final woke = Completer<void>();
    final coordinator = RecordingTransferCoordinator.instance;
    coordinator.configure(
        reconcile: () async {
          if (!woke.isCompleted) woke.complete();
        },
        discover: () async {},
        refreshPending: () async {},
        drain: () async => const RecordingTransferDrainResult.skipped(),
        autoUploadEnabled: () => false,
        connectivityChanges: const Stream<bool>.empty(),
        initiallyConnected: true);
    addTearDown(coordinator.dispose);
    final view = LocalRecordingsProvider(ledger: ledger, initialize: false, surfaceConversations: (_) async {});
    addTearDown(view.dispose);
    await view.refresh();
    expect(await view.upload(view.recordings.single), LocalUploadOutcome.started);
    expect(view.recordings.single.state.name, 'processing');
    expect((await ledger.getAllWals()).single.holdForUser, isTrue);
    // Without the acceptance wake the idle reconciler never starts this job.
    await woke.future.timeout(const Duration(seconds: 1));
    await coordinator.wake(WakeTrigger.userRetry);
    clock = clock.add(const Duration(minutes: 1));
    await ledger.reconcileUploadedWals();
    await view.refresh();
    expect(view.recordings.single.state.name, 'failed');
    expect((await ledger.getAllWals()).single.holdForUser, isTrue);
  });

  test('a migrated queued job surfaces its confirmed conversation through the ledger completion hook', () async {
    final ledger = await custodyLedger(
        fetch: (id) async => SyncJobFetch(
            SyncJobFetchOutcome.ok,
            SyncJobStatusResponse(
                jobId: id,
                status: 'completed',
                result: SyncLocalFilesResponse(newConversationIds: ['conversation'], updatedConversationIds: []))));
    await NativeRecordingIntake(ledger).scan();
    final surfaced = <String>[];
    final done = Completer<void>();
    final view = LocalRecordingsProvider(
        ledger: ledger,
        surfaceConversations: (result) async {
          surfaced.addAll(result.newConversationIds);
          done.complete();
        });
    addTearDown(view.dispose);
    await view.refresh();
    expect(await File('${dir.path}/$name').exists(), isTrue);
    expect(view.recordings.single.state.name, 'processing');
    await ledger.reconcileUploadedWals();
    await done.future;
    expect(surfaced, ['conversation']);
    expect((await ledger.getAllWals()).single.status, WalStatus.synced);
    expect((await ledger.getAllWals()).single.holdForUser, isFalse);
    await view.refresh();
    expect(view.recordings, isEmpty);
    await ledger.reconcileUploadedWals();
    expect(surfaced, ['conversation'], reason: 'a finished job surfaces once');
  });

  test('a failed job with partial result IDs does not publish a completed Home conversation', () async {
    final ledger = await custodyLedger(
        fetch: (id) async => SyncJobFetch(
            SyncJobFetchOutcome.ok,
            SyncJobStatusResponse(
                jobId: id,
                status: 'failed',
                totalSegments: 1,
                failedSegments: 1,
                result: SyncLocalFilesResponse(newConversationIds: ['partial'], updatedConversationIds: []))));
    await NativeRecordingIntake(ledger).scan();
    final surfaced = <String>[];
    final view = LocalRecordingsProvider(
        ledger: ledger,
        surfaceConversations: (result) async {
          surfaced.addAll(result.newConversationIds);
        });
    addTearDown(view.dispose);
    await view.refresh();
    await ledger.reconcileUploadedWals();
    await view.refresh();
    final wal = (await ledger.getAllWals()).single;
    expect(wal.holdForUser, isTrue);
    expect(wal.status, WalStatus.miss);
    expect(view.recordings.single.state.name, 'failed');
    expect(surfaced, isEmpty);
    expect(ledger.conversationCompletions.value, isNull);
    expect(await File('${dir.path}/$name').exists(), isTrue);
  });
}
