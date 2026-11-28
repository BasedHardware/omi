import Foundation

public extension DeviceSnapshot {
    /// The battery widgets refresh themselves every 15 minutes; the app reloads them sooner only
    /// for what a glance should catch: connecting, disconnecting, another Omi, a first level, a
    /// 5-point move, or crossing the low-battery mark. Background reloads come out of a daily budget.
    func needsReload(from old: DeviceSnapshot?) -> Bool {
        guard let old else { return true }
        if old.name != name || old.connected != connected { return true }
        guard let level = battery, let previous = old.battery else { return (battery == nil) != (old.battery == nil) }
        if abs(level - previous) >= 5 { return true }
        return (level <= Self.lowMark) != (previous <= Self.lowMark)
    }

    static let lowMark = 20
}

public extension OmiActivityAttributes.ContentState {
    /// A running clock (`Text(timerInterval:)`) reserves the width of its range's longest value, so
    /// the range ends at the next full hour: "12:34" fits the island, "1:02:03" only once needed.
    /// The app republishes at that hour to extend it.
    static func clockEnd(since start: Date, now: Date) -> Date {
        let hours = (max(0, now.timeIntervalSince(start)) / 3600).rounded(.down) + 1
        return start.addingTimeInterval(hours * 3600)
    }
}
