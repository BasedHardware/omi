import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/firmware_update_battery.dart';

void main() {
  for (final (name, battery, charging, allowed) in [
    ('unknown blocks', -1, false, false),
    ('unknown while charging allows', -1, true, true),
    ('low blocks', kFirmwareUpdateMinBattery - 1, false, false),
    ('low while charging allows', kFirmwareUpdateMinBattery - 1, true, true),
    ('at threshold allows', kFirmwareUpdateMinBattery, false, true),
    ('above threshold allows', kFirmwareUpdateMinBattery + 1, false, true),
    ('zero blocks', 0, false, false),
  ]) {
    test(name, () {
      expect(canStartFirmwareUpdate(batteryLevel: battery, isCharging: charging), allowed);
    });
  }
}
