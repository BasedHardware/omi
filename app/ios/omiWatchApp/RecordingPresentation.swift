import Foundation

struct RecordingPresentation {
    static let animationDuration: TimeInterval = 5

    static func animationTimeRemaining(startedAt: Date, now: Date) -> TimeInterval {
        max(0, animationDuration - elapsedTime(startedAt: startedAt, now: now))
    }

    static func elapsedTime(startedAt: Date, now: Date) -> TimeInterval {
        max(0, now.timeIntervalSince(startedAt))
    }
}
