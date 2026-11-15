import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_frame_encoder.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/wal_file_manager.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../integration_test/perf/heavy_upload_fixture.dart';

class _Paths extends PathProviderPlatform {
  _Paths(this.path);
  final String path;
  @override
  Future<String?> getApplicationDocumentsPath() async => path;
}

class _Listener implements IWalSyncListener {
  final synced = <Wal>[];
  int updates = 0;
  @override
  void onWalUpdated() => updates++;
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) => synced.add(wal);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('real WAL upload and reconciliation complete synthetic files, retaining held backlog', () async {
    SharedPreferences.setMockInitialValues({'uid': 'perf-upload-test'});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();
    addTearDown(SyncRateLimiter.instance.clear);
    final directory = await Directory.systemTemp.createTemp('omi-heavy-upload-test-');
    addTearDown(() => directory.delete(recursive: true));
    final previousPaths = PathProviderPlatform.instance;
    PathProviderPlatform.instance = _Paths(directory.path);
    addTearDown(() => PathProviderPlatform.instance = previousPaths);
    await WalFileManager.init();
    var now = DateTime.now();
    final fixture = HeavyUploadFixture();
    expect(fixture.accepting, isFalse);
    fixture.accepting = true;
    final listener = _Listener();
    final persisted = <List<WalStatus>>[];
    final local = LocalWalSyncImpl(listener,
        now: () => now,
        uploadGate: fixture.gate,
        jobStatusFetcher: fixture.fetchJob,
        persistWals: (wals) async => persisted.add(wals.map((w) => w.status).toList()));
    addTearDown(local.stop);
    final payload = encodeWalFrames(List.generate(500, (_) => [0xf8, 0xff, 0xfe]));
    final wals = <Wal>[];
    for (var i = 0; i < 4; i++) {
      final start = now.subtract(Duration(minutes: i * 20 + 60)).millisecondsSinceEpoch ~/ 1000;
      final name = 'audio_omiperf_${start}_$i.bin';
      await File('${directory.path}/$name').writeAsBytes(payload);
      wals.add(Wal(
          timerStart: start,
          codec: BleAudioCodec.opus,
          seconds: 5,
          status: WalStatus.miss,
          storage: WalStorage.disk,
          device: 'phone',
          ownerUid: 'perf-upload-test',
          filePath: name,
          totalFrames: 500,
          holdForUser: i == 3));
    }
    local.testWals = wals;
    await local.syncAll();
    expect(fixture.acceptedFiles, 3);
    expect(fixture.acceptedBytes, payload.length * 3);
    expect(wals.take(3).map((w) => w.status), everyElement(WalStatus.uploaded));
    expect(wals.last.status, WalStatus.miss);
    expect(fixture.completedJobs, 0);
    // Production defer is honored, including when the synthetic server is ready.
    await local.reconcileUploadedWals();
    expect(fixture.completedJobs, 0);
    now = now.add(const Duration(seconds: 21));
    await local.reconcileUploadedWals();
    expect(wals.take(3).map((w) => w.status), everyElement(WalStatus.synced));
    expect(wals.last.status, WalStatus.miss);
    expect(fixture.completedJobs, fixture.acceptedJobs);
    expect(listener.synced, hasLength(3));
    expect(listener.updates, greaterThan(0));
    expect(persisted.last.take(3), everyElement(WalStatus.synced));
  });

  test('unknown synthetic jobs cannot silently succeed', () async {
    await expectLater(HeavyUploadFixture().fetchJob('not-a-fixture-job'), throwsStateError);
  });
}
