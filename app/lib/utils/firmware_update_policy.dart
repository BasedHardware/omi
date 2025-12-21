const int minFirmwareUpdateBatteryPercent = 15;

bool isBatteryLevelTooLowForFirmwareUpdate(int batteryLevel) {
  return batteryLevel >= 0 && batteryLevel < minFirmwareUpdateBatteryPercent;
}
