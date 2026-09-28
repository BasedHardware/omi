import Foundation

// Resource-use policy delegating to the shared C++ middleware (`omi_device`).
// The battery-persistence rule is retained verbatim in behavior from the
// upstream maintained `app/ios/Runner/Ble/OmiBleEnergyPolicy.swift`
// (branch omi/main); the CoreBluetooth-typed diagnostics/RSSI decoders stay
// with the Apple transport (they consume `Data` and platform types and are
// not needed off-Apple).

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
        Policy.deviceShouldPersistBatteryReading(
            previousLevel: previousLevel.map(Int32.init),
            previousTimestampMs: previousTimestampMs,
            level: Int32(level), nowMs: nowMs)
    }
}
