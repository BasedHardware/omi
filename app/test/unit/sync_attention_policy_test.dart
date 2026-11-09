import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/api/sync_upload_refusal.dart';
import 'dart:io';
import 'package:http/http.dart' as http;

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/settings/device/device_catching_up_card.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/services/wals/wal_backlog_telemetry.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/sync_job_poller.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/wal_file_manager.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

Wal _wal(DateTime at, {WalStatus status = WalStatus.miss}) => Wal(
    timerStart: at.millisecondsSinceEpoch ~/ 1000,
    codec: BleAudioCodec.opus,
    seconds: 60,
    device: 'omi',
    storage: WalStorage.disk,
    status: status,
    filePath: 'audio.bin');

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory dir;
  late DateTime now;
  setUp(() async {
    now = DateTime(2026, 10, 28, 12);
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();
    dir = await Directory.systemTemp.createTemp('sync_attention_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/path_provider'), (call) async => dir.path);
    await WalFileManager.init();
  });
  tearDown(() async {
    SyncRateLimiter.instance.clear();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/path_provider'), null);
    await dir.delete(recursive: true);
  });

  test('daily refusal recovery survives restart, keeps bytes, stops at seven days', () async {
    final events = <RegisteredEvent>[];
    var calls = 0;
    var success = false;
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
            geolocation}) async {
          calls++;
          if (success) return UploadFilesResult.queued('fixed');
          throw const SyncUploadHttpException(400, 'arbitrary prose', reasonCode: 'invalid_file');
        });
    LocalWalSyncImpl instance() => LocalWalSyncImpl(_Listener(),
        now: () => now, uploadGate: gate, backlogTelemetry: WalBacklogTelemetry(emit: events.add));
    var sync = instance();
    final bytes = [1, 0, 0, 0, 42]; // A complete tiny frame is still retained audio.
    await File('${dir.path}/audio.bin').writeAsBytes(bytes);
    sync.testWals = [_wal(now)];
    await sync.syncAll();
    expect(calls, 1);
    expect(events.single.properties, {'reason': 'invalid_file', 'status_code': 400});
    var restored = (await WalFileManager.loadWals()).single;
    expect(restored.uploadRejectionReason, 'invalid_file');
    expect(restored.uploadRejectionStatusCode, 400);
    expect(walRetryCanHelp(restored), isFalse);
    expect(isAttentionSyncState(restored.syncDisplayState), isFalse);
    sync = instance()..testWals = [restored];
    await sync.syncAll();
    expect(calls, 1);
    for (var day = 1; day <= 7; day++) {
      now = now.add(const Duration(days: 1));
      await sync.syncAll();
      expect(calls, day < 7 ? day + 1 : 7);
      expect(await File('${dir.path}/audio.bin').readAsBytes(), bytes);
    }
    final summary = WalRefusalSummary.from(sync.testWals, nowSeconds: now.millisecondsSinceEpoch ~/ 1000);
    expect((summary.count, summary.seconds, summary.reportedCount, summary.userActionCanHelp), (1, 60, 1, false));

    // A fresh refusal whose next daily attempt reaches the corrected server succeeds.
    now = now.add(const Duration(days: 1));
    restored = _wal(now)..markUploadRejected(nowSeconds: now.millisecondsSinceEpoch ~/ 1000);
    sync.testWals = [restored];
    now = now.add(const Duration(days: 1));
    success = true;
    await sync.syncAll();
    expect(restored.status, WalStatus.uploaded);
  });

  test('empty/torn header clears on old server refusal; tiny frame stays retained', () async {
    for (final size in [0, 1, 4, 5]) {
      final wal = _wal(now);
      await File('${dir.path}/audio.bin').writeAsBytes(List.filled(size, 0));
      final sync = LocalWalSyncImpl(_Listener(),
          now: () => now,
          uploadGate: SyncUploadGate(
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
                  throw const SyncUploadHttpException(400, 'refused')));
      sync.testWals = [wal];
      await sync.syncAll();
      expect(wal.status, size <= 4 ? WalStatus.synced : WalStatus.uploadRejected);
    }
  });

  test('known legacy refusal reasons become closed tokens without retaining prose', () {
    expect(
        (decodeSyncUploadRefusal(http.Response('{"detail":"Missing boundary in multipart."}', 400))
                as ApiSuccess<SyncUploadRefusalBody>)
            .data
            .reasonCode,
        'malformed_multipart');
    expect(
        (decodeSyncUploadRefusal(http.Response('{"code":"private-unbounded-text"}', 400))
                as ApiSuccess<SyncUploadRefusalBody>)
            .data
            .reasonCode,
        'server_refused');
    expect(
        (decodeSyncUploadRefusal(http.Response('{"detail":{"code":"invalid_file"}}', 400))
                as ApiSuccess<SyncUploadRefusalBody>)
            .data
            .reasonCode,
        'invalid_file');
  });

  test('only closed tokens persist and refusal retry obeys custody', () {
    final wal = _wal(now)
      ..markUploadRejected(reasonCode: 'private server prose', nowSeconds: now.millisecondsSinceEpoch ~/ 1000);
    expect(wal.uploadRejectionReason, WalUploadRejection.serverRefused);
    expect(Wal.fromJson(wal.toJson()).uploadRejectionReason, WalUploadRejection.serverRefused);
    final tomorrow = now.add(const Duration(days: 1)).millisecondsSinceEpoch ~/ 1000;
    wal.retryCount = 99;
    expect(isAutoUploadEligible(wal, nowSeconds: tomorrow), isTrue);
    wal.onDeviceOnly = true;
    expect(isAutoUploadEligible(wal, nowSeconds: tomorrow), isFalse);
  });

  test('byte-determined refusals never auto-resend; one drain re-sends at most a capped batch', () async {
    final yesterday = now.subtract(const Duration(days: 1)).millisecondsSinceEpoch ~/ 1000;
    final today = now.millisecondsSinceEpoch ~/ 1000;
    for (final reason in [WalUploadRejection.tooLarge, WalUploadRejection.tooManyParts]) {
      final wal = _wal(now)..markUploadRejected(reasonCode: reason, nowSeconds: yesterday);
      expect(wal.refusalRetryDue(today), isFalse, reason: reason);
    }
    var calls = 0;
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
            geolocation}) async {
          calls++;
          throw const SyncUploadHttpException(400, 'still refused', reasonCode: 'invalid_file');
        });
    await File('${dir.path}/audio.bin').writeAsBytes([1, 0, 0, 0, 42]);
    final sync = LocalWalSyncImpl(_Listener(), now: () => now, uploadGate: gate);
    sync.testWals = [
      for (var i = 0; i < walMaxRefusalRetriesPerDrain + 5; i++)
        _wal(now.subtract(Duration(minutes: 2 * i)))
          ..markUploadRejected(reasonCode: WalUploadRejection.invalidFile, nowSeconds: yesterday),
    ];
    await sync.syncAll();
    expect(calls, walMaxRefusalRetriesPerDrain, reason: 'a server-wide refusal never fires every resend at once');
    await sync.syncAll();
    expect(calls, walMaxRefusalRetriesPerDrain + 5, reason: 'the rest wait for a later drain, not a later day');
  });

  test('old completed/gone jobs reconcile; confirmed pending alone renews old span', () async {
    final poller = SyncJobPoller(clock: () => now);
    final wals = [
      for (final id in ['done', 'gone', 'pending'])
        _wal(now.subtract(const Duration(days: 23)), status: WalStatus.uploaded)
          ..device = id
          ..jobId = id
          ..uploadedAt = now.subtract(const Duration(days: 23)).millisecondsSinceEpoch ~/ 1000
    ];
    await File('${dir.path}/audio.bin').writeAsBytes([1, 0, 0, 0, 42]);
    final sync = LocalWalSyncImpl(_Listener(),
        now: () => now,
        jobPoller: poller,
        persistWals: (_) async {},
        jobStatusFetcher: (id) async => id == 'gone'
            ? const SyncJobFetch(SyncJobFetchOutcome.notFound)
            : SyncJobFetch(SyncJobFetchOutcome.ok,
                SyncJobStatusResponse(jobId: id, status: id == 'done' ? 'completed' : 'processing')));
    sync.testWals = wals;
    expect(deviceCatchUpLocal(wals, now: now).start, isNull);
    await sync.reconcileUploadedWals();
    expect(wals[0].status, WalStatus.synced);
    expect(wals[1].status, WalStatus.uploaded, reason: 'first missing read is not terminal proof');
    expect(wals[2].jobPendingConfirmedAt, now.millisecondsSinceEpoch ~/ 1000);
    now = now.add(const Duration(minutes: 5));
    await sync.reconcileUploadedWals();
    expect(wals[1].status, WalStatus.miss);
    expect(wals[1].retryCount, 0);
    final local = deviceCatchUpLocal(List.of(wals), now: now);
    expect(local.hasPending, isTrue);
    final today = _wal(now, status: WalStatus.uploaded)..uploadedAt = now.millisecondsSinceEpoch ~/ 1000;
    final span = deviceCatchUpLocal([...wals, today], now: now);
    expect(span.start, now);
    expect(span.end, now.add(const Duration(minutes: 1)));
  });

  test('span uses latest contiguous pending run and never crosses its day header', () {
    final end = DateTime(2026, 10, 28, 0, 1);
    final span = pendingCatchUpSpan([
      (DateTime(2026, 10, 5), DateTime(2026, 10, 5, 1)),
      (end.subtract(const Duration(minutes: 3)), end),
    ]);
    expect(span, (DateTime(2026, 10, 28), end));
  });
}
