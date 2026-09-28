import Foundation

// Pure resource-use policy, adapted from the upstream maintained
// implementation at `app/ios/Runner/Ble/OmiBleEnergyPolicy.swift`
// (branch omi/main). The battery-persistence rule is platform-neutral and
// retained verbatim in behavior; the CoreBluetooth-typed diagnostics/RSSI
// decoders stay with the Apple transport (they consume `Data` and platform
// types and are not needed off-Apple).

public enum OmiBleEnergyPolicy {
    public static let batteryHistoryMinimumIntervalMs: Int64 = 60 * 60 * 1_000

    /// Persist a battery reading only when the level changed or at most one
    /// history entry per hour — bounds journal writes for the life of a
    /// connection.
    public static func shouldPersistBatteryReading(
        previousLevel: Int?,
        previousTimestampMs: Int64?,
        level: Int,
        nowMs: Int64
    ) -> Bool {
        guard let previousLevel, let previousTimestampMs else { return true }
        if level != previousLevel { return true }
        if nowMs - previousTimestampMs >= batteryHistoryMinimumIntervalMs {
            return true
        }
        return false
    }
}
