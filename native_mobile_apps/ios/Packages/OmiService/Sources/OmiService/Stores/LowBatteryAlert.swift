/// One low-battery notification per discharge: it fires when the Omi drops below `low` and
/// re-arms only after a charge above `rearm`, so a level wobbling around 15 % notifies once.
public struct LowBatteryAlert: Equatable, Sendable {
    public static let low = 15
    public static let rearm = 30

    /// Already notified for this discharge.
    public private(set) var alerted: Bool

    public init(alerted: Bool = false) {
        self.alerted = alerted
    }

    /// Feeds a reading; `true` when this reading should notify.
    public mutating func update(_ level: Int) -> Bool {
        if level > Self.rearm {
            alerted = false
            return false
        }
        guard level < Self.low, !alerted else { return false }
        alerted = true
        return true
    }

    /// Below this the battery shows in orange.
    public static func isLow(_ level: Int) -> Bool {
        level < low
    }
}
