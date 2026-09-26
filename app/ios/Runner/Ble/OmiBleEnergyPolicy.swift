import Foundation

/// Pure resource-use policy shared by the native BLE manager and its tests.
enum OmiBleEnergyPolicy {
    static let batteryHistoryMinimumIntervalMs: Int64 = 15 * 60 * 1_000
    static let batteryHistoryMeaningfulDelta = 5
    static let lowBatteryThreshold = 20

    static func shouldPollRssi(diagnosticsEnabled: Bool, peripheralConnected: Bool) -> Bool {
        diagnosticsEnabled && peripheralConnected
    }

    static func shouldPersistBatteryReading(
        previousLevel: Int?,
        previousTimestampMs: Int64?,
        level: Int,
        nowMs: Int64
    ) -> Bool {
        guard let previousLevel, let previousTimestampMs else { return true }
        if abs(level - previousLevel) >= batteryHistoryMeaningfulDelta { return true }
        if nowMs - previousTimestampMs >= batteryHistoryMinimumIntervalMs { return true }

        let crossedLowBatteryThreshold =
            (previousLevel < lowBatteryThreshold && level >= lowBatteryThreshold) ||
            (previousLevel >= lowBatteryThreshold && level < lowBatteryThreshold)
        return crossedLowBatteryThreshold
    }
}
