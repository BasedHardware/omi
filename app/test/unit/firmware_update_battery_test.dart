import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/firmware_update_battery.dart';

void main() {
  for (final (name, battery, charging, allowed) in [
    ('unknown blocks', -1, false, false),
    ('unknown while charging allows', -1, true, true),
    ('previous minimum blocks', 15, false, false),
    ('zero while charging allows', 0, true, true),
    ('29% blocks', 29, false, false),
    ('low while charging allows', kFirmwareUpdateMinBattery - 1, true, true),
    ('approved 30% minimum allows', 30, false, true),
    ('above threshold allows', kFirmwareUpdateMinBattery + 1, false, true),
    ('zero blocks', 0, false, false),
  ]) {
    test(name, () {
      expect(canStartFirmwareUpdate(batteryLevel: battery, isCharging: charging), allowed);
    });
  }
}
