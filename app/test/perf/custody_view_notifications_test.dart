import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/services/wals/wal.dart';
import '../support/custody_test_helpers.dart';

void main() {
  test('automatic custody updates do not notify the Home recordings view', () async {
    final dir = await custodyDirectory();
    final ledger = await custodyLedger();
    final view = LocalRecordingsProvider(ledger: ledger);
    await view.refresh();
    // Initial constructor refresh is serialized with the explicit refresh.
    await Future<void>.delayed(Duration.zero);
    var notifications = 0;
    view.addListener(() => notifications++);
    for (var i = 0; i < 20; i++) {
      final file = File('${dir.path}/device-$i.bin');
      await file.writeAsBytes([1, 0, 0, 0, 5]);
      await ledger.addExternalWal(
          Wal(
              timerStart: 1720000000 + i,
              codec: BleAudioCodec.opus,
              seconds: 1,
              storage: WalStorage.disk,
              status: WalStatus.miss,
              filePath: 'device-$i.bin'),
          admittedGeneration: ledger.sessionGeneration);
    }
    expect(view.recordings, isEmpty);
    expect(notifications, 0);
    view.dispose();
    await dir.delete(recursive: true);
  });
}
