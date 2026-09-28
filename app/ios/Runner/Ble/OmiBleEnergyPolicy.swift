import Foundation

/// Pure resource-use policy shared by the native BLE manager and its tests.
enum OmiBleEnergyPolicy {
    static let batteryHistoryMinimumIntervalMs: Int64 = 60 * 60 * 1_000

    static func shouldPersistBatteryReading(
        previousLevel: Int?,
        previousTimestampMs: Int64?,
        level: Int,
        nowMs: Int64
    ) -> Bool {
        guard let previousLevel, let previousTimestampMs else { return true }
        if level != previousLevel { return true }
        if nowMs - previousTimestampMs >= batteryHistoryMinimumIntervalMs { return true }
        return false
    }
}

/// Pure decoder for the append-only Omi Diagnostics GATT value.
enum OmiBleFirmwareDiagnostics {
    static func parse(_ data: Data, timestampMs: Int64) -> [String: Any]? {
        guard data.count >= 25, data[0] != 0 else { return nil }
        func u32(_ offset: Int) -> UInt32 {
            UInt32(data[offset]) | (UInt32(data[offset + 1]) << 8) |
                (UInt32(data[offset + 2]) << 16) | (UInt32(data[offset + 3]) << 24)
        }
        func known(_ value: UInt32) -> Any {
            value == UInt32.max ? NSNull() : NSNumber(value: value)
        }
        let reset = u32(1)
        let flags: [String] = [
            "RESET_PIN", "RESET_SOFTWARE", "RESET_BROWNOUT", "RESET_POR",
            "RESET_WATCHDOG", "RESET_DEBUG", "RESET_SECURITY", "RESET_LOW_POWER_WAKE",
            "RESET_CPU_LOCKUP", "RESET_PARITY", "RESET_PLL", "RESET_CLOCK", "RESET_HARDWARE",
            "RESET_USER", "RESET_TEMPERATURE", "RESET_BOOTLOADER", "RESET_FLASH",
        ]
        let names = reset == UInt32.max ? [] : flags.enumerated().compactMap { bit, name in
            reset & (UInt32(1) << bit) != 0 ? name : nil
        }
        let battery = Int(data[9]) | (Int(data[10]) << 8)
        return [
            "ts": timestampMs, "version": Int(data[0]),
            "reset_cause_raw": known(reset), "reset_cause_names": names,
            "uptime_s": u32(5),
            "battery_mv": battery == 0xffff ? NSNull() : NSNumber(value: battery),
            "charging": data[11] == 0xff ? NSNull() : NSNumber(value: data[11] == 1),
            "mic_overrun_count": known(u32(13)),
            "ble_tx_drop_count": known(u32(17)),
            "storage_error_count": known(u32(21)),
        ]
    }
}

enum OmiBleRssiDiagnostics {
    static func trend(samples: [(ts: Int64, rssi: Int64)], nowMs: Int64) -> String {
        let recent = samples.filter { $0.ts >= nowMs - 15_000 }
        if recent.isEmpty { return "gap" }
        if recent.count < 2 { return "unknown" }
        let third = max(1, recent.count / 3)
        let oldest = recent.prefix(third).map { $0.rssi }.reduce(0, +) / Int64(third)
        let newest = recent.suffix(third).map { $0.rssi }.reduce(0, +) / Int64(third)
        return oldest - newest >= 10 ? "fading" : "sudden"
    }

    static func ageMs(samples: [(ts: Int64, rssi: Int64)], nowMs: Int64) -> Int64 {
        samples.last.map { max(0, nowMs - $0.ts) } ?? -1
    }
}
