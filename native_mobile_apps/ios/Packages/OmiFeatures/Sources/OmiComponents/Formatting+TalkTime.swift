import Foundation

public extension Formatting {
    /// "45s", "3m 20s", "1h 5m": how long someone spoke.
    static func talkTime(_ seconds: Double) -> String {
        Duration.seconds(max(0, seconds.rounded()))
            .formatted(.units(allowed: [.hours, .minutes, .seconds], width: .narrow, maximumUnitCount: 2))
    }
}
