import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:shared_preferences/shared_preferences.dart';

// Regression coverage for the bug: with auto-sync turned OFF the Auto Sync page
// showed no device recordings at all, because offline files were only ever
// enumerated as the first step of a full sync. The page now calls
// discoverDeviceWals(), which enumerates the device and refreshes the list
// regardless of the auto-sync opt-out. Manual sync then works off that list.

/// Fake syncs object returned by [_FakeWalService.getSyncs]. SyncProvider treats
/// getSyncs() as dynamic, so only the members it actually calls are needed here.
class _FakeSyncs {
  int refreshCalls = 0;
  final List<Wal> _discovered = [];

  void seedDeviceHasOfflineRecording() {
    _discovered
      ..clear()
      ..add(Wal(timerStart: 1000, codec: BleAudioCodec.pcm16, seconds: 120, status: WalStatus.miss));
  }

  // Mirrors the real WalSyncs.refreshWalsFromDevice(): enumerate the device into
  // the cache that getAllWals() then returns.
  Future<void> refreshWalsFromDevice() async {
    refreshCalls++;
  }

  Future<List<Wal>> getAllWals() async => List<Wal>.of(_discovered);
}

class _FakeWalService implements IWalService {
  final _FakeSyncs syncs;
  _FakeWalService(this.syncs);

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

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('discoverDeviceWals enumerates the device then surfaces its recordings', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();

    final syncs = _FakeSyncs();
    final provider = SyncProvider(walService: _FakeWalService(syncs), startBackgroundSync: false);
    await provider.initialized;

    // Startup refreshWals() loaded the (empty) cache without hitting the device.
    expect(provider.allWals, isEmpty);
    final callsAfterStartup = syncs.refreshCalls;

    // Device now has an offline recording; opening the page discovers it.
    syncs.seedDeviceHasOfflineRecording();
    await provider.discoverDeviceWals();

    expect(syncs.refreshCalls, callsAfterStartup + 1, reason: 'discovery must query the device');
    expect(provider.allWals, hasLength(1), reason: 'the discovered recording must be listed');
    expect(provider.pendingWals, hasLength(1), reason: 'a miss WAL lists as pending → manual sync available');
    provider.dispose();
  });

  test('discovery lists recordings even when auto-sync is disabled', () async {
    SharedPreferences.setMockInitialValues({'autoSyncOfflineRecordings': false});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();
    expect(SharedPreferencesUtil().autoSyncOfflineRecordings, isFalse);

    final syncs = _FakeSyncs()..seedDeviceHasOfflineRecording();
    final provider = SyncProvider(walService: _FakeWalService(syncs), startBackgroundSync: false);
    await provider.initialized;

    await provider.discoverDeviceWals();

    // The reported bug: with auto-sync off the list was empty. It must not be.
    expect(provider.allWals, hasLength(1));
    provider.dispose();
  });
}
