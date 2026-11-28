import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/devices/connectors/limitless_connection.dart';
import 'package:omi/services/wals/flash_page_wal_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

/// A Limitless pendant that reports [flashStatus] for its flash storage.
class _FakePendant implements LimitlessDeviceConnection {
  _FakePendant(this.flashStatus, {this.acknowledge});

  Map<String, int> flashStatus;
  final Future<int?> Function(int)? acknowledge;

  @override
  Future<Map<String, int>?> getStorageStatus() async => flashStatus;

  @override
  Future<Map<String, String>> getDeviceInfo() async => {'modelNumber': 'Limitless Pendant'};

  @override
  Future<int?> acknowledgeProcessedData(int upToIndex) async {
    final scripted = acknowledge;
    if (scripted == null) return upToIndex;
    return await scripted(upToIndex);
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Map<String, int> _flash({required int oldest, required int newest}) =>
    {'oldest_flash_page': oldest, 'newest_flash_page': newest, 'current_storage_session': 1};

FlashPageWalSyncImpl _syncFor(_FakePendant pendant) => FlashPageWalSyncImpl(_Listener())
  ..testDevice = BtDevice(id: 'limitless-1', name: 'Limitless', type: DeviceType.limitless, rssi: -40)
  ..testConnection = pendant;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    // Transcribe Later stays off, so the pendant's flash pages are listed.
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('listing the same pendant backlog again keeps its recording id', () async {
    final pendant = _FakePendant(_flash(oldest: 1000, newest: 1099));
    final sync = _syncFor(pendant);

    await sync.refreshWalsFromDevice();
    final listed = (await sync.getMissingWals()).single;

    // Discovery runs again on every wake and sync pass. Wal.id is
    // device_timerStart, so the clock moving on must not change it.
    await Future<void>.delayed(const Duration(milliseconds: 1100));
    await sync.refreshWalsFromDevice();
    final relisted = (await sync.getMissingWals()).single;
    expect(relisted, isNot(same(listed)), reason: 'each listing builds a new entry');
    expect(relisted.id, listed.id);

    // The pendant recorded more after the same first page: same recording, longer.
    pendant.flashStatus = _flash(oldest: 1000, newest: 1199);
    await sync.refreshWalsFromDevice();
    final grown = (await sync.getMissingWals()).single;
    expect(grown.id, listed.id);
    expect(grown.storageTotalBytes, 1199);
    expect(grown.seconds, 280);
  });

  test('a transfer that stopped part-way keeps the recording id when the pendant is listed again', () async {
    final pendant = _FakePendant(_flash(oldest: 1000, newest: 1099));
    final sync = _syncFor(pendant);

    await sync.refreshWalsFromDevice();
    final listed = (await sync.getMissingWals()).single;

    // A stalled or cancelled transfer moves the listed recording past the pages it
    // saved and acknowledged (as _syncWal does), and the pendant drops those pages.
    listed.storageOffset = 1050;
    pendant.flashStatus = _flash(oldest: 1050, newest: 1099);
    await sync.refreshWalsFromDevice();
    final rest = (await sync.getMissingWals()).single;

    expect(rest.id, listed.id);
    expect(rest.storageOffset, 1050);
    expect(rest.seconds, 70);
  });

  test('refresh preserves the locally durable cursor while the pendant holds its ACK', () async {
    final pendant = _FakePendant(_flash(oldest: 1000, newest: 1099));
    final sync = _syncFor(pendant);

    await sync.refreshWalsFromDevice();
    final listed = (await sync.getMissingWals()).single;
    listed.storageOffset = 1050;

    // A held ACK leaves the device's oldest pointer behind the pages already
    // persisted locally. Refresh must not reset the next read to page 1000.
    await sync.refreshWalsFromDevice();
    final resumed = (await sync.getMissingWals()).single;

    expect(resumed.id, listed.id);
    expect(resumed.storageOffset, 1050);
    expect(resumed.storageTotalBytes, 1099);
    expect(resumed.seconds, 70);
  });

  test('refresh keeps cached flash WALs when the connection drops during enumeration', () async {
    final pendant = _FakePendant(_flash(oldest: 1000, newest: 1099));
    final sync = _syncFor(pendant);
    await sync.refreshWalsFromDevice();
    final listed = (await sync.getMissingWals()).single;

    sync.testConnection = null;
    var connectionRequests = 0;
    sync.testEnsureConnection = (_) async {
      connectionRequests++;
      return connectionRequests == 1 ? pendant : null;
    };

    expect(await sync.refreshWalsFromDevice(), isFalse);
    final retained = await sync.getMissingWals();
    expect(connectionRequests, 2);
    expect(retained.single.id, listed.id);
    expect(retained.single.storageOffset, listed.storageOffset);
  });

  test('batch-mode flash listing skip is neutral for device inventory confirmation', () async {
    final preferences = SharedPreferencesUtil();
    preferences.batchModeEnabled = true;
    addTearDown(() => preferences.batchModeEnabled = false);
    final sync = _syncFor(_FakePendant(_flash(oldest: 1000, newest: 1099)));

    expect(await sync.refreshWalsFromDevice(), isTrue);
  });

  test('partial drain resumes after durable pages even when their ACK is withheld', () {
    expect(
      FlashPageWalSyncImpl.resumePageAfterDurablePage(startPage: 100, lastDurablePageIndex: 149),
      150,
    );
    expect(
      FlashPageWalSyncImpl.resumePageAfterDurablePage(startPage: 100, lastDurablePageIndex: 99),
      100,
    );
  });

  test('bulk synced deletion continues after a flash page ACK refusal', () async {
    final attempted = <int>[];
    final pendant = _FakePendant(
      _flash(oldest: 100, newest: 200),
      acknowledge: (index) async {
        attempted.add(index);
        return index == 100 ? 99 : index;
      },
    );
    final first = Wal(
      timerStart: 1700000000,
      codec: BleAudioCodec.opus,
      seconds: 30,
      status: WalStatus.synced,
      storage: WalStorage.flashPage,
      device: 'limitless-1',
      storageTotalBytes: 100,
      fileNum: 100,
    );
    final second = Wal(
      timerStart: 1700000060,
      codec: BleAudioCodec.opus,
      seconds: 30,
      status: WalStatus.synced,
      storage: WalStorage.flashPage,
      device: 'limitless-1',
      storageTotalBytes: 200,
      fileNum: 200,
    );
    final sync = _syncFor(pendant)..testWals = [first, second];

    await expectLater(sync.deleteAllSyncedWals(), throwsStateError);

    expect(attempted, [100, 200]);
    expect(sync.testWals, [first], reason: 'the later page with a complete ACK is still removed');
  });
}
