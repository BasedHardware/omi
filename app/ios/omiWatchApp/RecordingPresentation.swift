import Combine
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

enum RecordingPresentationPhase: Equatable {
    case idle
    case animating
    case elapsedTimer

    var showsRecordingRipple: Bool {
        self == .animating
    }
}

@MainActor
final class RecordingPresentationController: ObservableObject {
    typealias Now = () -> Date
    typealias Sleep = (TimeInterval) async throws -> Void

    @Published private(set) var phase: RecordingPresentationPhase = .idle

    private let now: Now
    private let sleep: Sleep
    private var activeStartDate: Date?

    init(
        now: @escaping Now = Date.init,
        sleep: @escaping Sleep = { duration in
            try await Task<Never, Never>.sleep(nanoseconds: UInt64(duration * 1_000_000_000))
        }
    ) {
        self.now = now
        self.sleep = sleep
    }

    func update(isRecording: Bool, startedAt: Date?) async {
        activeStartDate = startedAt

        guard isRecording, let startedAt else {
            phase = .idle
            return
        }

        let remaining = RecordingPresentation.animationTimeRemaining(startedAt: startedAt, now: now())
        guard remaining > 0 else {
            phase = .elapsedTimer
            return
        }

        phase = .animating

        do {
            try await sleep(remaining)
        } catch {
            return
        }

        guard !Task.isCancelled, activeStartDate == startedAt else { return }
        phase = .elapsedTimer
    }
}
