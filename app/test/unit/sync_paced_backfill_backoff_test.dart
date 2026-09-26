import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Backend pacing (429 `backfill_paced` / `backfill_capacity`, and the 503
/// returned while a failed backfill job is still finalizing) is expected
/// backoff. The recording stays pending, Retry-After is honored, and the
/// client does not mint `Recording Upload Failed`.

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

SyncRateLimiter get limiter => SyncRateLimiter.instance;

void main() {
  late Directory tempDir;

  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    limiter.clear();
    tempDir = await Directory.systemTemp.createTemp('paced_backfill_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (MethodCall call) async {
        if (call.method == 'getApplicationDocumentsDirectory') return tempDir.path;
        return null;
      },
    );
  });

  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    limiter.clear();
    if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
  });

  group('paced backfill response classification', () {
    test('429 paced and capacity reasons are admission throttles, not silent for every 429', () {
      for (final reason in ['backfill_paced', 'backfill_capacity']) {
        final response = http.Response('', 429, headers: {'x-omi-rate-limit-reason': reason, 'retry-after': '60'});
        expect(isSyncUploadRateLimitResponse(response), isTrue);
        expect(isPacedBackfillReasonCode(syncRateLimitReasonCode(response)), isTrue);
        expect(syncRateLimitKindForResponse(response), SyncRateLimitKind.backendCapacity);
      }

      final fairUse = http.Response('', 429, headers: {'x-omi-rate-limit-reason': 'fair_use', 'retry-after': '3600'});
      expect(isSyncUploadRateLimitResponse(fairUse), isTrue);
      expect(isPacedBackfillReasonCode(syncRateLimitReasonCode(fairUse)), isFalse);

      final unscoped = http.Response('{"code":"burst_limit"}', 429, headers: {'retry-after': '30'});
      expect(isSyncUploadRateLimitResponse(unscoped), isTrue);
      expect(syncRateLimitReasonCode(unscoped), isNull);
      expect(isPacedBackfillReasonCode(syncRateLimitReasonCode(unscoped)), isFalse);
    });

    test('only a header-scoped 503 is an upload throttle; finalization retry is a transient poll', () {
      final capacity = http.Response(
        '{"code":"backfill_capacity"}',
        503,
        headers: {'x-omi-rate-limit-reason': 'backfill_capacity', 'retry-after': '30'},
      );
      expect(isSyncUploadRateLimitResponse(capacity), isTrue);
      expect(isPacedBackfillReasonCode(syncRateLimitReasonCode(capacity)), isTrue);

      final finalizationRetry = http.Response(
        '{"detail":"Sync recovery finalization is retrying; local audio remains available."}',
        503,
        headers: {'retry-after': '10'},
      );
      expect(isSyncUploadRateLimitResponse(finalizationRetry), isFalse);
      expect(syncJobFetchOutcomeForStatusCode(finalizationRetry.statusCode), SyncJobFetchOutcome.transient);

      final dispatchUnavailable = http.Response(
        '{"code":"sync_dispatch_unavailable"}',
        503,
        headers: {'retry-after': '30'},
      );
      expect(isSyncUploadRateLimitResponse(dispatchUnavailable), isFalse);
      expect(syncJobFetchOutcomeForStatusCode(500), SyncJobFetchOutcome.transient);
      expect(syncJobFetchOutcomeForStatusCode(404), SyncJobFetchOutcome.notFound);
    });
  });

  group('upload gate telemetry', () {
    SyncUploadGate gate({
      required List<({String name, Map<String, dynamic> properties})> events,
      required SyncFilesUploader uploader,
    }) {
      return SyncUploadGate(
        limiter: limiter,
        fairUseStatusLoader: () async => null,
        uploader: uploader,
        attemptIdFactory: () => 'attempt-paced',
        telemetryEmitter: (name, properties) => events.add((name: name, properties: properties)),
      );
    }

    test('paced 429 and header-scoped 503 stay a cooldown and do not emit Recording Upload Failed', () async {
      for (final reason in ['backfill_paced', 'backfill_capacity']) {
        limiter.clear();
        final events = <({String name, Map<String, dynamic> properties})>[];
        var uploads = 0;
        final uploadGate = gate(
          events: events,
          uploader: (files, {onUploadProgress, conversationId, claimLiveCapture = false, geolocation}) async {
            uploads++;
            throw SyncRateLimitedException(
              kind: SyncRateLimitKind.backendCapacity,
              retryAfterSeconds: 60,
              reasonCode: reason,
            );
          },
        );

        await expectLater(uploadGate.upload([]), throwsA(isA<SyncRateLimitedException>()));
        await expectLater(uploadGate.upload([]), throwsA(isA<SyncRateLimitedException>()));

        expect(uploads, 1, reason: 'Retry-After must close admission; the client must not loop faster');
        expect(limiter.reason, RateLimitReason.backendBusy);
        expect(limiter.activeRetryAfterSeconds, inInclusiveRange(59, 60));
        expect(events.map((event) => event.name), [RecordingUploadTelemetry.startedEvent]);
        expect(events.map((event) => event.name), isNot(contains(RecordingUploadTelemetry.failedEvent)));
      }
    });

    test('fair-use and unscoped 429 still emit rate_limited', () async {
      for (final reasonCode in <String?>['fair_use', null]) {
        limiter.clear();
        final events = <({String name, Map<String, dynamic> properties})>[];
        final uploadGate = gate(
          events: events,
          uploader: (files, {onUploadProgress, conversationId, claimLiveCapture = false, geolocation}) async {
            throw SyncRateLimitedException(
              kind: reasonCode == 'fair_use' ? SyncRateLimitKind.fairUse : SyncRateLimitKind.backendCapacity,
              retryAfterSeconds: 120,
              reasonCode: reasonCode,
            );
          },
        );

        await expectLater(uploadGate.upload([]), throwsA(isA<SyncRateLimitedException>()));

        expect(events.map((event) => event.name), [
          RecordingUploadTelemetry.startedEvent,
          RecordingUploadTelemetry.failedEvent,
        ]);
        expect(events.last.properties['failure_class'], 'rate_limited');
      }
    });

    test('unscoped 5xx still emits a server failure', () async {
      final events = <({String name, Map<String, dynamic> properties})>[];
      final uploadGate = gate(
        events: events,
        uploader: (files, {onUploadProgress, conversationId, claimLiveCapture = false, geolocation}) async {
          throw const SyncUploadHttpException(503, 'server');
        },
      );

      await expectLater(uploadGate.upload([]), throwsA(isA<SyncUploadHttpException>()));

      expect(events.map((event) => event.name), [
        RecordingUploadTelemetry.startedEvent,
        RecordingUploadTelemetry.failedEvent,
      ]);
      expect(events.last.properties['failure_class'], 'server');
      expect(RecordingUploadTelemetry.failureClass(const SyncUploadHttpException(500, 'server')), 'server');
    });
  });

  group('WAL stays pending', () {
    Future<File> pendingFile(Wal wal) async {
      final path = await Wal.getFilePath(wal.filePath);
      final file = File(path!);
      await file.writeAsBytes([1, 2, 3, 4]);
      return file;
    }

    LocalWalSyncImpl syncWith({
      SyncUploadGate? uploadGate,
      Future<SyncJobFetch> Function(String jobId)? jobStatusFetcher,
    }) {
      return LocalWalSyncImpl(
        _Listener(),
        uploadGate: uploadGate,
        persistWals: (_) async {},
        jobStatusFetcher: jobStatusFetcher,
      );
    }

    test('a paced 429 leaves the recording pending and keeps the file', () async {
      final events = <({String name, Map<String, dynamic> properties})>[];
      final wal = Wal(
        timerStart: 1700000000,
        codec: BleAudioCodec.opus,
        seconds: 31,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        device: 'omi',
        filePath: 'audio_paced.bin',
      );
      final file = await pendingFile(wal);
      final sync = syncWith(
        uploadGate: SyncUploadGate(
          limiter: limiter,
          fairUseStatusLoader: () async => null,
          uploader: (files, {onUploadProgress, conversationId, claimLiveCapture = false, geolocation}) async {
            throw SyncRateLimitedException(
              kind: SyncRateLimitKind.backendCapacity,
              retryAfterSeconds: 60,
              reasonCode: 'backfill_paced',
            );
          },
          telemetryEmitter: (name, properties) => events.add((name: name, properties: properties)),
        ),
      );
      sync.testWals = [wal];

      await sync.syncWal(wal: wal);

      expect(wal.status, WalStatus.miss);
      expect(wal.retryCount, 0);
      expect(wal.jobId, isNull);
      expect(wal.isSyncing, isFalse);
      expect(wal.syncDisplayState, WalSyncDisplayState.waiting);
      expect(wal.syncDisplayState, isNot(WalSyncDisplayState.failed));
      expect(isAutoUploadEligible(wal), isTrue);
      expect(file.existsSync(), isTrue);
      expect(events.map((event) => event.name), isNot(contains(RecordingUploadTelemetry.failedEvent)));
      expect(limiter.activeRetryAfterSeconds, inInclusiveRange(59, 60));
    });

    test('a 503 while backfill finalization is retrying leaves the upload pending', () async {
      final events = <({String name, Map<String, dynamic> properties})>[];
      final wal = Wal(
        timerStart: 1700000001,
        codec: BleAudioCodec.opus,
        seconds: 31,
        status: WalStatus.uploaded,
        storage: WalStorage.disk,
        device: 'omi',
        filePath: 'audio_retrying.bin',
        retryCount: 1,
      )..jobId = 'job-finalizing';
      final sync = syncWith(
        uploadGate: SyncUploadGate(
          limiter: limiter,
          fairUseStatusLoader: () async => null,
          uploader: (files, {onUploadProgress, conversationId, claimLiveCapture = false, geolocation}) async {
            throw StateError('a finalization 503 must not re-upload');
          },
          telemetryEmitter: (name, properties) => events.add((name: name, properties: properties)),
        ),
        jobStatusFetcher: (jobId) async {
          expect(jobId, 'job-finalizing');
          expect(syncJobFetchOutcomeForStatusCode(503), SyncJobFetchOutcome.transient);
          return const SyncJobFetch(SyncJobFetchOutcome.transient);
        },
      );
      sync.testWals = [wal];

      await sync.reconcileUploadedWals();

      expect(wal.status, WalStatus.uploaded);
      expect(wal.jobId, 'job-finalizing');
      expect(wal.retryCount, 1, reason: 'a retrying finalization is not a failed attempt');
      expect(wal.syncDisplayState, WalSyncDisplayState.uploaded);
      expect(wal.syncDisplayState, isNot(WalSyncDisplayState.failed));
      expect(events, isEmpty);
    });

    test('an unscoped 5xx still fails the upload attempt and keeps the file', () async {
      final events = <({String name, Map<String, dynamic> properties})>[];
      final wal = Wal(
        timerStart: 1700000002,
        codec: BleAudioCodec.opus,
        seconds: 31,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        device: 'omi',
        filePath: 'audio_server.bin',
      );
      final file = await pendingFile(wal);
      final sync = syncWith(
        uploadGate: SyncUploadGate(
          limiter: limiter,
          fairUseStatusLoader: () async => null,
          uploader: (files, {onUploadProgress, conversationId, claimLiveCapture = false, geolocation}) async {
            throw const SyncUploadHttpException(500, 'server');
          },
          telemetryEmitter: (name, properties) => events.add((name: name, properties: properties)),
        ),
      );
      sync.testWals = [wal];

      await expectLater(sync.syncWal(wal: wal), throwsA(isA<SyncUploadHttpException>()));

      expect(wal.status, WalStatus.miss);
      expect(wal.syncDisplayState, isNot(WalSyncDisplayState.synced));
      expect(file.existsSync(), isTrue, reason: 'a server failure must not discard the local recording');
      expect(events.map((event) => event.name), contains(RecordingUploadTelemetry.failedEvent));
      expect(events.last.properties['failure_class'], 'server');
    });
  });
}
