import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/wal_file_manager.dart';

class _FakeListener implements IWalSyncListener {
  int walUpdatedCount = 0;
  @override
  void onWalUpdated() => walUpdatedCount++;
  @override
  void onWalSynced(Wal wal, {conversation}) {}
}

Wal _wal({required int start, String? ownerUid}) => Wal(
      timerStart: start,
      codec: BleAudioCodec.opus,
      seconds: 30,
      ownerUid: ownerUid,
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory tempDir;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    tempDir = await Directory.systemTemp.createTemp('wal_owner_uid_test_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (MethodCall methodCall) async {
        if (methodCall.method == 'getApplicationDocumentsDirectory') return tempDir.path;
        return null;
      },
    );
    await WalFileManager.init();
  });

  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
  });

  group('Wal ownerUid serialization', () {
    test('round-trips through toJson/fromJson', () {
      final wal = _wal(start: 1000, ownerUid: 'account-a');
      final json = wal.toJson();
      expect(json['owner_uid'], 'account-a');
      final restored = Wal.fromJson(json);
      expect(restored.ownerUid, 'account-a');
    });

    test('fromJson tolerates a missing owner_uid (pre-upgrade data)', () {
      final restored = Wal.fromJson({
        'timer_start': 1000,
        'codec': 'BleAudioCodec.opus',
        'seconds': 30,
      });
      expect(restored.ownerUid, isNull);
    });

    test("'legacy' sentinel round-trips", () {
      final restored = Wal.fromJson(_wal(start: 3000, ownerUid: 'legacy').toJson());
      expect(restored.ownerUid, 'legacy');
    });
  });

  test('full account handover: foreign records are not admitted, stay on disk; null and legacy records load for anyone',
      () async {
    // Account A session: one stamped live WAL, one unstamped (pre-upgrade), one legacy.
    SharedPreferences.setMockInitialValues({'uid': 'account-a'});
    await SharedPreferencesUtil.init();
    final syncA = LocalWalSyncImpl(_FakeListener());
    syncA.testWals = [
      _wal(start: 1000, ownerUid: 'account-a'),
      _wal(start: 2000, ownerUid: null),
      _wal(start: 3000, ownerUid: 'legacy'),
    ];
    await WalFileManager.saveWals([...syncA.testWals]);

    // Account A logs out: retiring records get back-stamped with A's uid.
    syncA.clearUserData();
    var onDisk = await WalFileManager.loadWals();
    final stamped = onDisk.where((w) => w.timerStart == 1000).toList();
    expect(stamped, isNotEmpty);
    expect(stamped.first.ownerUid, 'account-a', reason: 'clearUserData back-stamps unstamped retiring records');

    // Process death + account B signs in on the same device.
    SharedPreferences.setMockInitialValues({'uid': 'account-b'});
    await SharedPreferencesUtil.init();
    final syncB = LocalWalSyncImpl(_FakeListener());
    syncB.start();
    await syncB.walReady;

    // B's session admits only null/legacy records; A-stamped stays parked.
    expect(syncB.testWals.map((w) => w.timerStart), containsAll([2000, 3000]));
    expect(syncB.testWals.map((w) => w.timerStart), isNot(contains(1000)),
        reason: 'account A-stamped record must not enter B session');

    // B persists something: A's record must survive on disk (side list).
    syncB.testWals = [...syncB.testWals, _wal(start: 5000, ownerUid: 'account-b')];
    await WalFileManager.saveWals([
      ...syncB.testWals,
      ...onDisk.where((w) => w.timerStart == 1000),
    ]);
    onDisk = await WalFileManager.loadWals();
    expect(onDisk.map((w) => w.timerStart), containsAll([1000, 2000, 3000, 5000]),
        reason: 'no account data is lost across the handover');
  });
}
