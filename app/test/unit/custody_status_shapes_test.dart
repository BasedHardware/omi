import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/sync_job_poller.dart';
import 'package:omi/services/wals/sync_job_policy.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/wal_file_manager.dart';

class _Listener implements IWalSyncListener {
  int acknowledgements = 0;
  @override
  void onWalUpdated() {}
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) => acknowledgements++;
}

/// Every answer the backend can give, from its exhaustive custody property test.
Map<String, List<SyncJobStatusResponse>> _shapes() {
  final fixture = jsonDecode(File('../backend/tests/fixtures/custody_status_shapes.json').readAsStringSync());
  SyncJobStatusResponse response(dynamic shape) => SyncJobStatusResponse.fromJson({
        'job_id': 'bp_upload',
        'status': shape['status'],
        'reason_code': shape['reason_code'],
        'poll_after_ms': shape['poll_after_ms'],
        'total_files': 1,
        'total_segments': 2,
      });
  return {
    for (final name in ['resolved', 'unresolved']) name: [for (final shape in fixture[name]) response(shape)],
  };
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory dir;
  var now = DateTime.utc(2026, 11, 2);
  setUp(() async {
    now = DateTime.utc(2026, 11, 2);
    SharedPreferences.setMockInitialValues({'autoRemoveSyncedCopies': true, 'autoRemoveSyncedCopiesDays': 1});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();
    SyncJobPoller.instance.resetForTesting(clock: () => now);
    dir = await Directory.systemTemp.createTemp('custody_status_shapes_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (call) async => dir.path,
    );
    await WalFileManager.init();
  });
  tearDown(() async {
    SyncRateLimiter.instance.clear();
    SyncJobPoller.instance.resetForTesting();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    await dir.delete(recursive: true);
  });

  test('no answer for an upload with an unresolved unit acknowledges custody', () {
    final unresolved = _shapes()['unresolved']!;
    expect(unresolved, isNotEmpty);
    for (final status in unresolved) {
      final policy = syncJobTerminalPolicy(status: status.status, isTerminal: status.isTerminal);
      expect(policy, isNot(SyncJobTerminalPolicy.acknowledge), reason: status.status);
      expect(syncJobFailureIsPermanent(status), isFalse, reason: status.status);
    }
  });

  test('only the all-terminal completed answer acknowledges', () {
    final acknowledging = _shapes()['resolved']!.where(
        (s) => syncJobTerminalPolicy(status: s.status, isTerminal: s.isTerminal) == SyncJobTerminalPolicy.acknowledge);
    expect(acknowledging.map((s) => s.status).toSet(), {'completed'});
  });

  test('real reconciliation keeps 14-day-old bytes for every unresolved answer', () async {
    for (final status in _shapes()['unresolved']!) {
      final listener = _Listener();
      final sync = LocalWalSyncImpl(listener,
          now: () => now,
          persistWals: (_) async {},
          jobStatusFetcher: (_) async => SyncJobFetch(SyncJobFetchOutcome.ok, status));
      final file = await File('${dir.path}/audio_unresolved.bin').writeAsBytes([1, 2, 3, 4, 5]);
      final wal = Wal(
          timerStart: now.subtract(const Duration(days: 14)).millisecondsSinceEpoch ~/ 1000,
          codec: BleAudioCodec.opus,
          seconds: 31,
          status: WalStatus.uploaded,
          storage: WalStorage.disk,
          device: 'omi',
          filePath: 'audio_unresolved.bin')
        ..jobId = status.jobId;
      sync.testWals = [wal];
      await sync.reconcileUploadedWals();
      expect(listener.acknowledgements, 0, reason: status.status);
      expect(wal.status, isNot(WalStatus.synced), reason: status.status);
      expect(wal.syncedAt, 0, reason: status.status);
      expect(await sync.enforceSyncedCopyRetentionForTesting(), 0, reason: status.status);
      expect(await file.readAsBytes(), [1, 2, 3, 4, 5], reason: status.status);
      await sync.stop();
      SyncJobPoller.instance.resetForTesting(clock: () => now);
    }
  });
}
