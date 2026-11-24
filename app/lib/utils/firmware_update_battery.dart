/// The lowest battery an Omi firmware update may start at, unless it is charging.
const int kFirmwareUpdateMinBattery = 30;

/// Charging is sufficient; otherwise a known battery must meet the update threshold.
bool canStartFirmwareUpdate({required int batteryLevel, required bool isCharging}) =>
    isCharging || batteryLevel >= kFirmwareUpdateMinBattery;
