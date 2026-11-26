import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/home/firmware_update.dart';
import 'package:omi/services/wals/wal.dart';

Wal _wal(String device) => Wal(
      timerStart: 1700000000,
      codec: BleAudioCodec.opus,
      seconds: 30,
      storage: WalStorage.sdcard,
      status: WalStatus.miss,
      device: device,
    );

void main() {
  test('counts only recordings from the pendant being updated', () {
    final wals = [_wal('pendant-a'), _wal('pendant-b'), _wal('pendant-a')];
    expect(unsyncedRecordingsOnPendant(wals, 'pendant-a'), 2);
    expect(unsyncedRecordingsOnPendant(wals, 'pendant-b'), 1);
  });

  test('recordings left from a previous pendant do not block the current one', () {
    expect(unsyncedRecordingsOnPendant([_wal('previous-pendant')], 'current-pendant'), 0);
  });
}
