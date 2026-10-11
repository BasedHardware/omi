import Foundation

/// Pure resource-use policy shared by the native BLE manager and its tests.
enum OmiBleEnergyPolicy {
    static let batteryHistoryMinimumIntervalMs: Int64 = 60 * 60 * 1_000

    /// UserDefaults accepts property-list values only. Unknown charging state
    /// is omitted until the device reports it.
    static func batteryHistoryEntry(timestampMs: Int64, level: Int, charging: Bool?) -> [String: Any] {
        var entry: [String: Any] = ["ts": timestampMs, "level": level]
        if let charging { entry["charging"] = charging }
        return entry
    }

    /// Backfill the newest battery point's charging flag, but only when that
    /// point is recent: stamping the state observed now onto a hours-old
    /// sample would mislabel historical battery data.
    static let batteryBackfillMaxAgeMs: Int64 = 15 * 60 * 1_000

    static func backfillLatestBatteryCharging(
        _ history: [[String: Any]], charging: Bool, nowMs: Int64
    ) -> [[String: Any]]? {
        guard let latest = history.last, latest["charging"] == nil else { return nil }
        guard let ts = latest["ts"] as? Int64, nowMs - ts <= batteryBackfillMaxAgeMs else { return nil }
        var updated = history
        updated[updated.count - 1]["charging"] = charging
        return updated
    }

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
        var result: [String: Any] = [
            "ts": timestampMs, "version": Int(data[0]),
            "reset_cause_names": names,
            "uptime_s": u32(5),
        ]
        if reset != UInt32.max { result["reset_cause_raw"] = NSNumber(value: reset) }
        if battery != 0xffff { result["battery_mv"] = NSNumber(value: battery) }
        if data[11] != 0xff { result["charging"] = NSNumber(value: data[11] == 1) }
        for (key, offset) in [("mic_overrun_count", 13), ("ble_tx_drop_count", 17), ("storage_error_count", 21)] {
            let value = u32(offset)
            if value != UInt32.max { result[key] = NSNumber(value: value) }
        }
        if data.count >= 30 {
            for (key, offset) in [("last_off_charger_mv", 25), ("charge_pin_edges", 27)] {
                let value = Int(data[offset]) | (Int(data[offset + 1]) << 8)
                if value != 0xffff { result[key] = NSNumber(value: value) }
            }
            if data[29] == 0 || data[29] == 1 { result["soc_frozen"] = NSNumber(value: data[29] == 1) }
        }
        return result
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

/// Attributes one recovery interval to the event that started it.
struct OmiBleReconnectDiagnostics {
    private var pendingTimestampMs: Int64?

    mutating func recordEvent(timestampMs: Int64, eventType: String, isManual: Bool) {
        if isManual {
            pendingTimestampMs = nil
            return
        }
        // Failed retry attempts belong to the outstanding loss. A newly lost
        // physical link starts its own interval instead of inheriting an old one.
        if eventType == "disconnect" || pendingTimestampMs == nil {
            pendingTimestampMs = timestampMs
        }
    }

    mutating func recovered(atMs: Int64, hadConnection: Bool) -> (eventTimestampMs: Int64, durationMs: Int64)? {
        guard let timestamp = pendingTimestampMs else { return nil }
        pendingTimestampMs = nil
        guard hadConnection else { return nil }
        return (timestamp, max(0, atMs - timestamp))
    }

    func retainedHistory<T>(
        _ history: [T], nowMs: Int64, retentionMs: Int64, limit: Int, timestampOf: (T) -> Int64
    ) -> [T] {
        let recent = history.filter { timestampOf($0) >= nowMs - retentionMs }
        // Keep one unresolved outage through count truncation, while respecting
        // both age retention and the ring's total entry limit.
        if limit > 0, let pending = recent.lastIndex(where: { timestampOf($0) == pendingTimestampMs }),
           pending < recent.count - limit {
            return [recent[pending]] + recent.suffix(limit - 1)
        }
        return Array(recent.suffix(limit))
    }

    mutating func backfilledHistory<T>(
        _ history: [T], nowMs: Int64, hadConnection: Bool,
        timestampOf: (T) -> Int64, withDuration: (T, Int64) -> T
    ) -> [T]? {
        guard let recovery = recovered(atMs: nowMs, hadConnection: hadConnection),
              let index = history.lastIndex(where: { timestampOf($0) == recovery.eventTimestampMs }) else { return nil }
        var result = history
        result[index] = withDuration(history[index], recovery.durationMs)
        return result
    }
}
