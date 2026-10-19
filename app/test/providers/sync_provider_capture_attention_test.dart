import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';
import 'package:omi/services/wals/local_wal_sync.dart' show WalRetentionRisk;
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// How SyncProvider feeds the capture wedge monitor from the WAL inventory:
/// recordings (grouped fragments, not files), upload-eligible WALs only, the
/// storage row ending with its own retention observation, and the monitor
/// resetting when user state clears.

class _FakePhone {
  WalRetentionRisk? retentionRisk;
}

class _FakeSyncs {
  _FakeSyncs(this.wals);

  final List<Wal> wals;
  final phone = _FakePhone();

  Future<List<Wal>> getAllWals() async => List<Wal>.of(wals);

  Future<void> refreshWalsFromDevice({String? firmwareVersion}) async {}

  bool get isStorageSyncing => false;
  bool get isSdCardSyncing => false;

  void clearUserData() {}
}

class _FakeWalService implements IWalService {
  _FakeWalService(this.syncs);
  final _FakeSyncs syncs;

  @override
  void start() {}

  @override
  Future stop() async {}

  @override
  void subscribe(IWalServiceListener subscription, Object context) {}

  @override
  void unsubscribe(Object context) {}

  @override
  dynamic getSyncs() => syncs;
}

Wal _wal(int startSeconds,
        {WalStatus status = WalStatus.miss,
        WalStorage storage = WalStorage.disk,
        bool onDeviceOnly = false,
        int seconds = 60,
        int retryCount = 0}) =>
    Wal(
      timerStart: startSeconds,
      codec: BleAudioCodec.opus,
      seconds: seconds,
      status: status,
      storage: storage,
      onDeviceOnly: onDeviceOnly,
      retryCount: retryCount,
      device: 'phone',
    );

CaptureWedgeMonitor _monitor() => CaptureWedgeMonitor(
      featureGate: () async => true,
      track: (_, __) {},
      bleRetry: (_) async {},
      transferRetry: () async {},
      appBuild: () => '1',
      platform: () => 'ios',
    );

Future<SyncProvider> _provider(_FakeSyncs syncs, CaptureWedgeMonitor monitor) async {
  SharedPreferences.setMockInitialValues({});
  await SharedPreferencesUtil.init();
  SyncRateLimiter.instance.clear();
  final provider = SyncProvider(
    walService: _FakeWalService(syncs),
    startBackgroundSync: false,
    captureWedgeMonitor: monitor,
  );
  await provider.initialized;
  return provider;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('the upload stall counts grouped recordings, not WAL fragments', () async {
    final now = DateTime.now();
    final base = now.subtract(const Duration(hours: 3)).millisecondsSinceEpoch ~/ 1000;
    final syncs = _FakeSyncs([
      // One continuous recording: five one-minute fragments back to back.
      for (var i = 0; i < 5; i++) _wal(base + i * 60, seconds: 60),
    ]);
    final monitor = _monitor();
    final provider = await _provider(syncs, monitor);
    addTearDown(provider.dispose);
    addTearDown(monitor.dispose);

    await provider.refreshWals();
    expect(monitor.uploadStall, isNotNull, reason: 'a 3h-old backlog with no upload declares the stall');
    expect(monitor.uploadStall!.pendingCount, 1, reason: 'five consecutive fragments are one recording');
    expect(monitor.uploadStall!.pendingSeconds, 5 * 60, reason: 'kept-audio seconds still sum across fragments');
  });

  test('local-only and terminal WALs never declare an upload stall', () async {
    final now = DateTime.now();
    final base = now.subtract(const Duration(hours: 3)).millisecondsSinceEpoch ~/ 1000;
    final syncs = _FakeSyncs([
      _wal(base, onDeviceOnly: true, seconds: 60),
      _wal(base + 60, status: WalStatus.outsideRecoveryWindow, seconds: 60),
      _wal(base + 120, status: WalStatus.corrupted, seconds: 60),
    ]);
    final monitor = _monitor();
    final provider = await _provider(syncs, monitor);
    addTearDown(provider.dispose);
    addTearDown(monitor.dispose);

    await provider.refreshWals();
    expect(monitor.uploadStall, isNull, reason: 'nothing in the inventory can still upload');
  });

  test('the kept-audio duration sums the upload-eligible set only', () async {
    final now = DateTime.now();
    final base = now.subtract(const Duration(hours: 3)).millisecondsSinceEpoch ~/ 1000;
    final syncs = _FakeSyncs([
      // One retryable waiting fragment still moving toward an upload.
      _wal(base, seconds: 60),
      // Retry-exhausted failures keep status=miss but are Offline Sync's
      // terminal attention: their hours must not read as audio this upload
      // stall is holding.
      _wal(base + 60, retryCount: 3, seconds: 60 * 60),
      _wal(base + 120, retryCount: 5, seconds: 60 * 60),
      // Local-only (on-device STT) audio never joins a cloud drain.
      _wal(base + 180, onDeviceOnly: true, seconds: 60 * 60),
    ]);
    final monitor = _monitor();
    final provider = await _provider(syncs, monitor);
    addTearDown(provider.dispose);
    addTearDown(monitor.dispose);

    await provider.refreshWals();
    expect(monitor.uploadStall, isNotNull, reason: 'the one eligible waiting WAL still declares the stall');
    expect(monitor.uploadStall!.pendingCount, 1, reason: 'only the retryable fragment groups');
    expect(monitor.uploadStall!.pendingSeconds, 60, reason: 'terminal failures and local-only audio do not sum in');
  });

  test('the storage row follows its own retention observation, not upload progress', () async {
    final syncs = _FakeSyncs(const []);
    final monitor = _monitor();
    final provider = await _provider(syncs, monitor);
    addTearDown(provider.dispose);
    addTearDown(monitor.dispose);

    syncs.phone.retentionRisk = WalRetentionRisk(
      engagedAt: DateTime.now(),
      retainedCount: 720,
      blockedCount: 1,
      reason: 'disk_reserve',
    );
    await provider.refreshWals();
    expect(monitor.storageAtRisk, isNotNull);

    // An upload completing must not read as recovered disk.
    monitor.onUploadCompleted();
    expect(monitor.storageAtRisk, isNotNull);

    // The disk admitting a write again ends the row.
    syncs.phone.retentionRisk = null;
    await provider.refreshWals();
    expect(monitor.storageAtRisk, isNull);
  });

  test('clearUserData resets the capture monitor for the next account', () async {
    final syncs = _FakeSyncs(const []);
    final monitor = _monitor();
    final provider = await _provider(syncs, monitor);
    addTearDown(provider.dispose);
    addTearDown(monitor.dispose);

    syncs.phone.retentionRisk = WalRetentionRisk(
      engagedAt: DateTime.now(),
      retainedCount: 720,
      blockedCount: 1,
      reason: 'disk_reserve',
    );
    await provider.refreshWals();
    expect(monitor.hasUnseenCaptureAttention.value, isTrue);

    provider.clearUserData();
    expect(monitor.storageAtRisk, isNull, reason: 'the previous account\'s rows must not leak into the next login');
    expect(monitor.hasUnseenCaptureAttention.value, isFalse, reason: 'the bell resets with the account');
  });
}
