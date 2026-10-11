import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/sync_job_poller.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/wal_file_manager.dart';
import 'package:omi/pages/conversations/sync_cooldown_copy.dart';
import 'package:omi/l10n/app_localizations_en.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

Wal pending(int i) => Wal(
    timerStart: 1700000000 + i,
    codec: BleAudioCodec.opus,
    seconds: 31,
    status: WalStatus.uploaded,
    storage: WalStorage.disk,
    device: 'omi',
    filePath: 'audio_$i.bin')
  ..jobId = 'job-$i';

void main() {
  late Directory dir;
  late DateTime now;
  late SyncRateLimiter limiter;
  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    limiter = SyncRateLimiter.instance;
    limiter.clear();
    now = DateTime(2026, 10, 11);
    dir = await Directory.systemTemp.createTemp('sync_poll_storm_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/path_provider'), (call) async => dir.path);
    await WalFileManager.init();
  });
  tearDown(() async {
    limiter.clear();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/path_provider'), null);
    await dir.delete(recursive: true);
  });

  test('50 pending jobs and five serial wakes cannot produce 250 polls', () async {
    var requests = 0;
    final sync = LocalWalSyncImpl(_Listener(),
        now: () => now,
        jobStatusFetcher: (id) async {
          requests++;
          return SyncJobFetch(SyncJobFetchOutcome.ok, SyncJobStatusResponse(jobId: id, status: 'processing'));
        },
        persistWals: (_) async {});
    sync.testWals = List.generate(50, pending);
    final coordinator = RecordingTransferCoordinator(
        reconcile: () async {
          await sync.reconcileUploadedWals();
        },
        drain: () async => const RecordingTransferDrainResult.skipped(),
        discover: () async {},
        refreshPending: () async {},
        autoUploadEnabled: () => false);
    addTearDown(coordinator.dispose);
    for (var i = 0; i < 5; i++) {
      await coordinator.wake(WakeTrigger.socketReconnected);
      now = now.add(const Duration(seconds: 10));
    }
    expect(requests, lessThanOrEqualTo(18), reason: 'baseline makes 50 x 5 = 250 requests in 50 seconds');
    expect(sync.testWals.every((wal) => wal.status == WalStatus.uploaded), isTrue);
  });

  test('shared budget, per-job cadence, server hint, fairness and sliding window', () async {
    final poller = SyncJobPoller(clock: () => now);
    final seen = <String>[];
    Future<SyncJobFetch> fetch(String id) async {
      seen.add(id);
      return SyncJobFetch(SyncJobFetchOutcome.ok,
          SyncJobStatusResponse(jobId: id, status: 'processing', pollAfterMs: id == '0' ? 90000 : null));
    }

    for (final id in poller.ordered(List.generate(50, (i) => '$i'))) {
      await poller.fetch(id, fetch);
    }
    expect(seen.length, 18);
    now = now.add(const Duration(seconds: 20));
    await poller.fetch('0', fetch);
    await poller.fetch('49', fetch);
    expect(seen.length, 18);
    now = now.add(const Duration(seconds: 40));
    final next = poller.ordered(List.generate(50, (i) => '$i'));
    expect(seen, isNot(contains(next.first)), reason: 'unpolled jobs precede jobs already polled');
    for (final id in next) {
      await poller.fetch(id, fetch);
    }
    expect(seen.length, 36);
    expect(seen.where((id) => id == '0').length, 1);
  });

  test('overlapping passes join; each job has one request in flight', () async {
    var requests = 0;
    final gate = Completer<SyncJobFetch>();
    final sync = LocalWalSyncImpl(_Listener(),
        now: () => now,
        persistWals: (_) async {},
        jobStatusFetcher: (_) {
          requests++;
          return gate.future;
        });
    sync.testWals = [pending(1)];
    final first = sync.reconcileUploadedWals();
    final second = sync.reconcileUploadedWals();
    gate.complete(const SyncJobFetch(SyncJobFetchOutcome.transient));
    await Future.wait([first, second]);
    expect(requests, 1);
  });

  test('poll 429 stops the pass and all subsequent wakes during cooldown', () async {
    var requests = 0;
    final sync = LocalWalSyncImpl(_Listener(),
        now: () => now,
        persistWals: (_) async {},
        jobStatusFetcher: (_) async {
          requests++;
          return SyncJobFetch.throttled(
              SyncRateLimitedException(kind: SyncRateLimitKind.edgeThrottle, retryAfterSeconds: 120));
        });
    sync.testWals = List.generate(50, pending);
    await sync.reconcileUploadedWals();
    now = now.add(const Duration(minutes: 1));
    await sync.reconcileUploadedWals();
    expect(requests, 1);
    expect(limiter.reason, RateLimitReason.edgeThrottle);
    expect(sync.testWals.every((wal) => wal.status == WalStatus.uploaded && wal.retryCount == 0), isTrue);
  });

  test('404 requires a second missing read after five minutes; no retry spent', () async {
    var requests = 0;
    final sync = LocalWalSyncImpl(_Listener(),
        now: () => now,
        persistWals: (_) async {},
        jobStatusFetcher: (_) async {
          requests++;
          return const SyncJobFetch(SyncJobFetchOutcome.notFound);
        });
    final wal = pending(1);
    await File('${dir.path}/audio_1.bin').writeAsBytes([1, 2]);
    sync.testWals = [wal];
    await sync.reconcileUploadedWals();
    expect(wal.status, WalStatus.uploaded);
    now = now.add(const Duration(minutes: 4));
    await sync.reconcileUploadedWals();
    expect(requests, 1);
    now = now.add(const Duration(minutes: 1));
    await sync.reconcileUploadedWals();
    expect(requests, 2);
    expect(wal.status, WalStatus.miss);
    expect(wal.retryCount, 0);
    expect(wal.jobId, isNull);
  });

  test('409 content in progress pauses batch and manual uploads without failures or retries', () async {
    var uploads = 0;
    final gate = SyncUploadGate(
        limiter: limiter,
        fairUseStatusLoader: () async => {'stage': 'none'},
        uploader: (files,
            {onUploadProgress,
            conversationId,
            captureEvidence,
            recordingSessionId,
            audioStartSeconds,
            audioEndSeconds,
            claimLiveCapture = false,
            geolocation}) async {
          uploads++;
          throw SyncRateLimitedException(
              kind: SyncRateLimitKind.edgeThrottle, retryAfterSeconds: 60, reasonCode: 'sync_content_in_progress');
        });
    final sync = LocalWalSyncImpl(_Listener(), uploadGate: gate, persistWals: (_) async {});
    final wal = pending(1)
      ..status = WalStatus.miss
      ..jobId = null;
    await File('${dir.path}/audio_1.bin').writeAsBytes([1, 2]);
    sync.testWals = [wal];
    final result = await sync.syncAll();
    await sync.syncWal(wal: wal);
    expect(uploads, 1);
    expect(result?.localUploadFailures, 0);
    expect(wal.retryCount, 0);
    expect(wal.status, WalStatus.miss);
    expect(wal.isSyncing, isFalse);
  });

  test('server hint bounds a single job independently of the request budget', () async {
    final poller = SyncJobPoller(clock: () => now);
    var requests = 0;
    Future<SyncJobFetch> fetch(String id) async {
      requests++;
      return SyncJobFetch(
          SyncJobFetchOutcome.ok, SyncJobStatusResponse(jobId: id, status: 'processing', pollAfterMs: 90000));
    }

    await poller.fetch('one', fetch);
    now = now.add(const Duration(seconds: 20));
    await poller.fetch('one', fetch);
    expect(requests, 1);
    now = now.add(const Duration(seconds: 69));
    await poller.fetch('one', fetch);
    expect(requests, 1);
    now = now.add(const Duration(seconds: 1));
    await poller.fetch('one', fetch);
    expect(requests, 2);
    expect(poller.beginPass(), isTrue);
    expect(poller.beginPass(), isFalse, reason: 'both polling owners share one pass admission');
    poller.endPass();
    expect(poller.beginPass(), isTrue);
    poller.endPass();
  });

  test('409 with owner id tracks processing job and never reoffers the same bytes', () async {
    var uploads = 0;
    var polls = 0;
    final gate = SyncUploadGate(
        limiter: limiter,
        fairUseStatusLoader: () async => {'stage': 'none'},
        uploader: (files,
            {onUploadProgress,
            conversationId,
            captureEvidence,
            recordingSessionId,
            audioStartSeconds,
            audioEndSeconds,
            claimLiveCapture = false,
            geolocation}) async {
          uploads++;
          return syncContentInProgressResult(http.Response(
              '{"code":"sync_content_in_progress","job_id":"active-owner","poll_after_ms":120000}', 409))!;
        });
    final sync = LocalWalSyncImpl(_Listener(),
        uploadGate: gate,
        now: () => now,
        persistWals: (_) async {},
        jobStatusFetcher: (id) async {
          polls++;
          expect(id, 'active-owner');
          return SyncJobFetch(SyncJobFetchOutcome.ok, SyncJobStatusResponse(jobId: id, status: 'processing'));
        });
    final wal = pending(1)
      ..status = WalStatus.miss
      ..jobId = null;
    await File('${dir.path}/audio_1.bin').writeAsBytes([1, 2]);
    sync.testWals = [wal];
    await sync.syncAll();
    expect(wal.status, WalStatus.uploaded);
    expect(wal.jobId, 'active-owner');
    await sync.syncAll();
    await sync.reconcileUploadedWals();
    expect(polls, 0);
    now = now.add(const Duration(minutes: 2));
    await sync.reconcileUploadedWals();
    await sync.syncAll();
    expect(polls, 1);
    expect(uploads, 1);
    expect(wal.retryCount, 0);
  });

  test('a shorter concurrent capacity response cannot shorten an edge throttle', () {
    limiter.markLimited(retryAfterSeconds: 120, reason: RateLimitReason.edgeThrottle);
    final edgeDeadline = limiter.until;
    limiter.markLimited(retryAfterSeconds: 60, reason: RateLimitReason.backendBusy);
    expect(limiter.until, edgeDeadline);
    expect(limiter.reason, RateLimitReason.edgeThrottle);
  });

  test('edge throttle is neutral; explicit capacity and fair-use keep distinct copy', () {
    final l = AppLocalizationsEn();
    expect(syncCooldownTitle(RateLimitReason.edgeThrottle, l), l.paused);
    expect(syncCooldownTitle(RateLimitReason.backendBusy, l), l.syncCardBackendBusy);
    expect(syncJobFetchOutcomeForStatusCode(429), SyncJobFetchOutcome.throttled);
    expect(isSyncContentInProgressResponse(http.Response('{"code":"sync_content_in_progress"}', 409)), isTrue);
    expect(isSyncContentInProgressResponse(http.Response('{"code":"other"}', 409)), isFalse);
    expect(isSyncContentInProgressResponse(http.Response('<html/>', 409)), isFalse);
    expect(
        syncContentInProgressResult(http.Response('{"code":"sync_content_in_progress","job_id":"owner-1"}', 409))
            ?.jobId,
        'owner-1');
    expect(syncContentInProgressResult(http.Response('{"code":"sync_content_in_progress"}', 409)), isNull);
  });
}
