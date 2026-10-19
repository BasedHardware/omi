import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/sync_job_poller.dart';
import 'package:omi/services/wals/sync_job_policy.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/wal_file_manager.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {
    fail('A privacy denial must never acknowledge local audio');
  }
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
    now = DateTime(2026, 10, 18);
    limiter.clockForTesting = () => now;
    SyncJobPoller.instance.resetForTesting(clock: () => now);
    dir = await Directory.systemTemp.createTemp('sync_status_privacy_');
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

  // The backend exercises these same fence inputs against the HTTP handler
  // with reconciliation both on and off. Here the real consumer/poller proves
  // the resulting legacy statuses preserve retained audio.
  final privacyCases =
      jsonDecode(File('../backend/tests/fixtures/sync_status_privacy_cases.json').readAsStringSync()) as List<dynamic>;
  for (final privacyCase in privacyCases) {
    for (final state in ['expired', 'queued', 'processing', 'failed', 'partial_failure']) {
      test('privacy ${privacyCase['case']} with legacy $state retains audio', () async {
        var requests = 0;
        final response = state == 'expired'
            ? null
            : SyncJobStatusResponse.fromJson({
                'job_id': 'job-1',
                'status': state,
                'total_segments': 1,
                'processed_segments': 0,
                'successful_segments': 0,
                'failed_segments': 0,
                'reason_code': 'sync_worker_stale',
              });
        final fetchOutcome = syncJobFetchOutcomeForStatusCode(response == null ? 404 : 200);
        if (response != null) {
          expect(
            syncJobTerminalPolicy(status: response.status, isTerminal: response.isTerminal),
            response.isTerminal ? SyncJobTerminalPolicy.retry : SyncJobTerminalPolicy.wait,
          );
          expect(syncJobFailureIsPermanent(response), isFalse);
        }
        final sync = LocalWalSyncImpl(
          _Listener(),
          now: () => now,
          persistWals: (_) async {},
          jobStatusFetcher: (_) async {
            requests++;
            return SyncJobFetch(fetchOutcome, response);
          },
        );
        final wal = pending(1);
        final file = await File('${dir.path}/audio_1.bin').writeAsBytes([1, 2]);
        sync.testWals = [wal];
        await sync.reconcileUploadedWals();
        if (state == 'expired') {
          expect(wal.status, WalStatus.uploaded, reason: 'one missing read is not proof');
          now = now.add(SyncJobPoller.missingConfirmationInterval);
          await sync.reconcileUploadedWals();
          expect(requests, 2);
        }
        final waiting = state == 'queued' || state == 'processing';
        expect(wal.status, waiting ? WalStatus.uploaded : WalStatus.miss);
        expect(wal.jobId, waiting ? 'job-1' : isNull);
        expect(wal.retryCount, state == 'failed' || state == 'partial_failure' ? 1 : 0);
        expect(await file.readAsBytes(), [1, 2], reason: 'a privacy denial cannot ACK or delete local audio');
        if (!waiting) {
          final previous = requests;
          await sync.reconcileUploadedWals();
          expect(requests, previous, reason: 'the old handle has been retired');
        }
      });
    }
  }

  test('transient status 503 backs off without clearing the job or audio', () async {
    var requests = 0;
    final sync = LocalWalSyncImpl(
      _Listener(),
      now: () => now,
      persistWals: (_) async {},
      jobStatusFetcher: (_) async {
        requests++;
        return SyncJobFetch(syncJobFetchOutcomeForStatusCode(503));
      },
    );
    final wal = pending(1);
    final file = await File('${dir.path}/audio_1.bin').writeAsBytes([1, 2]);
    sync.testWals = [wal];
    await sync.reconcileUploadedWals();
    now = now.add(const Duration(seconds: 59));
    await sync.reconcileUploadedWals();
    expect(requests, 1);
    now = now.add(const Duration(seconds: 1));
    await sync.reconcileUploadedWals();
    expect(requests, 2);
    expect(wal.status, WalStatus.uploaded);
    expect(wal.jobId, 'job-1');
    expect(wal.retryCount, 0);
    expect(await file.readAsBytes(), [1, 2]);
  });
}
