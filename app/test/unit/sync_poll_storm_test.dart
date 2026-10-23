import 'dart:async';
import 'dart:io';
import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/wals/native_recording_intake.dart';
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
    limiter.clockForTesting = () => now;
    SyncJobPoller.instance.resetForTesting(clock: () => now);
    dir = await Directory.systemTemp.createTemp('sync_poll_storm_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/path_provider'), (call) async => dir.path);
    await WalFileManager.init();
  });
  tearDown(() async {
    limiter.clear();
    limiter.clockForTesting = null;
    SyncJobPoller.instance.resetForTesting();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/path_provider'), null);
    await dir.delete(recursive: true);
  });

  test('first polls are immediate unless an upload explicitly supplies a poll deadline', () async {
    final poller = SyncJobPoller(clock: () => now);
    final seen = <String>[];
    Future<SyncJobFetch> fetch(String id) async {
      seen.add(id);
      return SyncJobFetch(SyncJobFetchOutcome.ok, SyncJobStatusResponse(jobId: id, status: 'completed'));
    }

    await poller.fetch('restored-job', fetch);
    expect(seen, ['restored-job'], reason: 'persisted jobs have no artificial initial delay');
    poller.defer('new-upload', 90000);
    await poller.fetch('new-upload', fetch);
    now = now.add(const Duration(seconds: 89));
    await poller.fetch('new-upload', fetch);
    expect(seen, ['restored-job'], reason: 'wake triggers cannot bypass the server upload hint');
    now = now.add(const Duration(seconds: 1));
    await poller.fetch('new-upload', fetch);
    expect(seen, ['restored-job', 'new-upload'], reason: 'skipped polls do not extend the deadline');
  });

  test('singleton reset removes request budget, per-job deadlines and confirmed-missing owners', () async {
    final poller = SyncJobPoller.instance;
    Future<SyncJobFetch> missing(String _) async => const SyncJobFetch(SyncJobFetchOutcome.notFound);
    await poller.fetch('expired', missing);
    now = now.add(SyncJobPoller.missingConfirmationInterval);
    await poller.fetch('expired', missing);
    expect(() => poller.validateOwner(UploadFilesResult.queued('expired')), throwsA(isA<SyncRateLimitedException>()));
    var requests = 0;
    Future<SyncJobFetch> fetch(String id) async {
      requests++;
      return SyncJobFetch(SyncJobFetchOutcome.ok, SyncJobStatusResponse(jobId: id, status: 'processing'));
    }

    for (var i = 0; i < 18; i++) {
      await poller.fetch('job-$i', fetch);
    }
    expect(requests, 17, reason: 'the confirmed-missing request consumes one slot');
    limiter.markLimited(retryAfterSeconds: 120, reason: RateLimitReason.edgeThrottle);
    expect(poller.beginPass(), isFalse);
    limiter.clear();
    poller.resetForTesting(clock: () => now);
    expect(limiter.isLimited, isFalse);
    expect(poller.beginPass(), isTrue);
    poller.endPass();
    poller.validateOwner(UploadFilesResult.queued('expired'));
    await poller.fetch('job-0', fetch);
    expect(requests, 18, reason: 'a new test can poll the same job at the same time');
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

  test('127 restored uploads recover without deleting audio or letting a queued job starve siblings', () async {
    final requests = <DateTime>[];
    final persisted = <Map<String, dynamic>>[];
    var throttle = true;
    var transient = true;
    var uploads = 0;
    final originals = <String, List<int>>{};
    final wals = List.generate(127, pending);
    wals[0].jobId = null;
    wals[1].jobId = '   ';
    wals[2].jobId = '';
    // One orphan no longer has local audio. It must remain unavailable, not
    // be acknowledged as processed or silently removed to unblock the queue.
    for (var i = 0; i < wals.length; i++) {
      if (i == 2) continue;
      final bytes = <int>[i, 1, 2, 3];
      originals[wals[i].filePath!] = bytes;
      await File('${dir.path}/${wals[i].filePath}').writeAsBytes(bytes);
    }
    final sync = LocalWalSyncImpl(
      _Listener(),
      now: () => now,
      persistWals: (items) async {
        persisted
          ..clear()
          ..addAll(items.map((wal) => wal.toJson()));
      },
      uploadGate: SyncUploadGate(
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
          expect(files.length, 2, reason: 'only the retained orphan files need re-upload');
          for (final file in files) {
            expect(await file.readAsBytes(), originals[file.path.split('/').last]);
          }
          return UploadFilesResult.queued('recovered-orphans');
        },
      ),
      jobStatusFetcher: (id) async {
        requests.add(now);
        if (throttle) {
          throttle = false;
          return SyncJobFetch.throttled(
              SyncRateLimitedException(kind: SyncRateLimitKind.edgeThrottle, retryAfterSeconds: 120));
        }
        if (id == 'job-4' && transient) {
          transient = false;
          return const SyncJobFetch(SyncJobFetchOutcome.transient);
        }
        return SyncJobFetch(
            SyncJobFetchOutcome.ok, SyncJobStatusResponse(jobId: id, status: id == 'job-3' ? 'queued' : 'completed'));
      },
    );
    sync.testWals = wals;
    await sync.reconcileUploadedWals();
    expect(requests, hasLength(1), reason: 'the first 429 stops the entire pass');
    expect(wals.take(2).every((wal) => wal.status == WalStatus.miss), isTrue);
    expect(wals[2].status, WalStatus.corrupted);
    expect(wals.skip(3).every((wal) => wal.status == WalStatus.uploaded), isTrue);
    await sync.reconcileUploadedWals();
    expect(requests, hasLength(1), reason: 'repeated wakes respect the account cooldown');

    now = now.add(const Duration(minutes: 2));
    await sync.syncAll();
    expect(uploads, 1);
    for (var pass = 0; pass < 12; pass++) {
      now = now.add(const Duration(minutes: 1));
      await sync.reconcileUploadedWals();
    }
    expect(wals.where((wal) => wal.status == WalStatus.synced), hasLength(125));
    expect(wals[2].status, WalStatus.corrupted);
    expect(wals[3].status, WalStatus.uploaded, reason: 'queued is never fabricated as successful');
    expect(wals[3].jobId, 'job-3');
    expect(wals.where((wal) => wal.status != WalStatus.corrupted).every((wal) => wal.retryCount == 0), isTrue);
    expect(persisted.map(Wal.fromJson).where((wal) => wal.status == WalStatus.synced), hasLength(125));
    for (final request in requests) {
      expect(
          requests
              .where((other) => other.isAfter(request.subtract(const Duration(minutes: 1))) && !other.isAfter(request))
              .length,
          lessThanOrEqualTo(SyncJobPoller.maxRequestsPerMinute));
    }
    for (final entry in originals.entries) {
      expect(await File('${dir.path}/${entry.key}').readAsBytes(), entry.value);
    }
  });

  LocalWalSyncImpl orphanSync(List<Map<String, dynamic>> persisted, {void Function()? onPoll}) => LocalWalSyncImpl(
        _Listener(),
        now: () => now,
        persistWals: (items) async {
          persisted
            ..clear()
            ..addAll(items.map((wal) => wal.toJson()));
        },
        jobStatusFetcher: (id) async {
          onPoll?.call();
          return SyncJobFetch(SyncJobFetchOutcome.ok, SyncJobStatusResponse(jobId: id, status: 'processing'));
        },
      );

  Future<List<Wal>> orphanRows(int count) async {
    final rows = List.generate(count, pending)..forEach((wal) => wal.jobId = null);
    for (final wal in rows) {
      await File('${dir.path}/${wal.filePath}').writeAsBytes([1, 2, 3]);
    }
    return rows;
  }

  test('a recording admitted while orphan uploads are checked does not break recovery', () async {
    final persisted = <Map<String, dynamic>>[];
    final orphans = await orphanRows(3);
    final incoming = Wal(
        timerStart: 1700000100,
        codec: BleAudioCodec.opus,
        seconds: 31,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        device: 'omi',
        filePath: 'incoming.bin');
    await File('${dir.path}/incoming.bin').writeAsBytes([9, 9, 9]);
    final sync = orphanSync(persisted);
    final wals = [...orphans];
    sync.testWals = wals;

    // The pass suspends on the first orphan's file check; the new recording is
    // appended synchronously before addExternalWal's first await.
    final pass = sync.reconcileUploadedWals();
    final admitted = sync.addExternalWal(incoming, admittedGeneration: sync.sessionGeneration);
    await expectLater(pass, completes);
    await admitted;

    expect(orphans.every((wal) => wal.status == WalStatus.miss && wal.jobId == null), isTrue,
        reason: 'retained orphan audio re-enters the upload path');
    expect(orphans.every((wal) => wal.retryCount == 0), isTrue, reason: 'recovery spends no retry budget');
    expect(wals.where((wal) => identical(wal, incoming)), hasLength(1));
    expect(incoming.status, WalStatus.miss);
    final saved = persisted.map(Wal.fromJson).toList();
    expect(saved.where((wal) => wal.filePath == 'incoming.bin'), hasLength(1), reason: 'the new recording is durable');
    for (final orphan in orphans) {
      expect(saved.singleWhere((wal) => wal.filePath == orphan.filePath).status, WalStatus.miss,
          reason: 'recovery is persisted, not only in memory');
    }
    for (final wal in [...orphans, incoming]) {
      expect(await File('${dir.path}/${wal.filePath}').exists(), isTrue, reason: 'no retained audio is deleted');
    }
  });

  test('orphan rows that changed during a file check are re-read before they move', () async {
    final persisted = <Map<String, dynamic>>[];
    var polls = 0;
    final orphans = await orphanRows(4);
    final sync = orphanSync(persisted, onPoll: () => polls++);
    final wals = [...orphans];
    sync.testWals = wals;

    final pass = sync.reconcileUploadedWals();
    orphans[0].jobId = 'job-new'; // a newer upload claimed this row
    wals.remove(orphans[1]); // retention released this row
    orphans[2].status = WalStatus.synced; // another path already finished it
    await expectLater(pass, completes);

    expect(orphans[0].status, WalStatus.uploaded, reason: 'newer upload state is never overwritten');
    expect(orphans[0].jobId, 'job-new');
    expect(orphans[1].status, WalStatus.uploaded, reason: 'a row no longer owned by this sync is left alone');
    expect(orphans[2].status, WalStatus.synced);
    expect(orphans[3].status, WalStatus.miss);
    expect(orphans.every((wal) => wal.retryCount == 0), isTrue);
    expect(polls, 1, reason: 'existing job polling still runs for the newly claimed handle');
  });

  test('an account change during an orphan file check leaves every row untouched', () async {
    final persisted = <Map<String, dynamic>>[];
    final orphans = await orphanRows(2);
    final sync = orphanSync(persisted);
    sync.testWals = [...orphans];

    final pass = sync.reconcileUploadedWals();
    sync.clearUserData();
    await expectLater(pass, completes);

    expect(orphans.every((wal) => wal.status == WalStatus.uploaded && wal.jobId == null), isTrue,
        reason: 'the retired session moves nothing');
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
    expect(limiter.activeRetryAfterSeconds, 60);
    now = now.add(const Duration(seconds: 59));
    await sync.reconcileUploadedWals();
    expect(requests, 1);
    expect(limiter.activeRetryAfterSeconds, 1);
    now = now.add(const Duration(seconds: 1));
    expect(limiter.isLimited, isFalse);
    await sync.reconcileUploadedWals();
    expect(requests, 2, reason: 'the real limiter expires exactly at its injected deadline');
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

  test('a confirmed missing 409 owner cannot be adopted again', () async {
    final poller = SyncJobPoller.instance;
    final wal = pending(1);
    await File('${dir.path}/audio_1.bin').writeAsBytes([1, 2]);
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
                geolocation}) async =>
            syncContentInProgressResult(http.Response('{"code":"sync_content_in_progress","job_id":"job-1"}', 409))!);
    final sync = LocalWalSyncImpl(_Listener(),
        jobPoller: poller,
        uploadGate: gate,
        now: () => now,
        persistWals: (_) async {},
        jobStatusFetcher: (_) async => const SyncJobFetch(SyncJobFetchOutcome.notFound));
    sync.testWals = [wal];
    await sync.reconcileUploadedWals();
    now = now.add(const Duration(minutes: 5));
    await sync.reconcileUploadedWals();
    expect(wal.status, WalStatus.miss);
    await sync.syncAll();
    expect(wal.status, WalStatus.miss);
    expect(wal.jobId, isNull);
    expect(wal.retryCount, 0);
    expect(limiter.activeRetryAfterSeconds, 60);
  });

  test('Transcribe Later confirmed 404 keeps the file and auto-uploads again', () async {
    const name = 'audio_omibatchphoneauto_opus_fs320_16000_1_fs320_1720000001.bin';
    await File('${dir.path}/$name').writeAsBytes([4, 0, 0, 0, 1, 2, 3, 4]);
    SharedPreferencesUtil().uid = 'owner';
    await SharedPreferencesUtil().saveString('batchAudioDir', dir.path);
    await SharedPreferencesUtil().saveString('localRecordingJobs', jsonEncode({name: 'expired'}));
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
          expect(files.single.existsSync(), isTrue);
          return UploadFilesResult.queued('replacement');
        });
    final sync = LocalWalSyncImpl(_Listener(),
        uploadGate: gate,
        now: () => now,
        freeDiskBytes: () async => 4 * 1024 * 1024 * 1024,
        jobStatusFetcher: (_) async => const SyncJobFetch(SyncJobFetchOutcome.notFound));
    await sync.loadForOnDeviceWorker();
    await NativeRecordingIntake(sync).scan();
    await sync.reconcileUploadedWals();
    expect(uploads, 0);
    now = now.add(const Duration(minutes: 5));
    await sync.reconcileUploadedWals();
    await sync.syncAll();
    expect(File('${dir.path}/$name').existsSync(), isTrue);
    expect(uploads, 1);
    expect((await sync.getAllWals()).single.jobId, 'replacement');
    expect(SharedPreferencesUtil().getString('localRecordingJobs'), isEmpty);
  });

  test('migrated native jobs and device jobs share one reconciliation pass and budget', () async {
    const name = 'audio_omibatchphone_opus_16000_1_fs320_1720000001.bin';
    await File('${dir.path}/$name').writeAsBytes([1, 0, 0, 0, 5]);
    SharedPreferencesUtil().uid = 'owner';
    await SharedPreferencesUtil().saveString('batchAudioDir', dir.path);
    await SharedPreferencesUtil().saveString('localRecordingJobs', jsonEncode({name: 'phone-job'}));
    var requests = 0;
    final sync = LocalWalSyncImpl(_Listener(),
        now: () => now,
        freeDiskBytes: () => Future.value(4 * 1024 * 1024 * 1024),
        jobPoller: SyncJobPoller.instance,
        jobStatusFetcher: (id) async {
          requests++;
          return SyncJobFetch(SyncJobFetchOutcome.ok, SyncJobStatusResponse(jobId: id, status: 'processing'));
        });
    await sync.loadForOnDeviceWorker();
    sync.testWals = List.generate(50, pending);
    await NativeRecordingIntake(sync).scan();
    await Future.wait([sync.reconcileUploadedWals(), sync.reconcileUploadedWals()]);
    expect(requests, 18);
    await sync.reconcileUploadedWals();
    expect(requests, 18);
    now = now.add(const Duration(minutes: 1));
    await sync.reconcileUploadedWals();
    expect(requests, 36);
    expect((await sync.getAllWals()).where((w) => w.filePath == name).single.jobId, 'phone-job');
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
    var status = 'processing';
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
          return SyncJobFetch(SyncJobFetchOutcome.ok, SyncJobStatusResponse(jobId: id, status: status));
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
    expect(wal.status, WalStatus.uploaded);
    expect(File('${dir.path}/audio_1.bin').existsSync(), isTrue);
    status = 'completed';
    now = now.add(const Duration(seconds: 20));
    await sync.reconcileUploadedWals();
    expect(wal.status, WalStatus.synced);
    expect(wal.jobId, isNull);
    expect(polls, 2);
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
    expect(syncCooldownTitle(RateLimitReason.edgeThrottle, l), l.syncCardThrottlePaused);
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
