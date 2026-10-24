import Foundation
import Observation
import OmiCore
import OmiDevice
import OmiExtras
import OmiNetwork
import OmiService

/// Feeds the app's state to its extensions: the recording and Omi's runs to Live Activities, the
/// Omi's battery, open tasks and the newest conversation to the widgets. It only observes the
/// stores; nothing in them knows about extensions.
@MainActor
final class ExtrasBridge {
    typealias State = OmiActivityAttributes.ContentState

    private let environment: AppEnvironment
    private let activities = LiveActivityController()
    private let widgets = WidgetPublisher()
    /// The run the agent card follows, until it ends.
    private var shownRunID: String?
    private var clockRollover: (at: Date, task: Task<Void, Never>)?
    /// Leaves stopped time off the recording's clock.
    private var pauseClock = CapturePauseClock()
    /// The recording card's last content, to close it with.
    private var shownCapture: State?

    init(environment: AppEnvironment) {
        self.environment = environment
        let capture = environment.capture
        CaptureIntentAction.handler = { command in
            switch command {
            case .stop: await capture.stop()
            case .pause: capture.pause()
            case .resume: await capture.resume()
            }
        }
        observe { $0.publishCapture() }
        observe { $0.publishAgent() }
        observe { $0.publishWidgets() }
    }

    /// Runs `apply` now and again after every change to what it read.
    private func observe(_ apply: @escaping @MainActor (ExtrasBridge) -> Void) {
        withObservationTracking {
            apply(self)
        } onChange: { [weak self] in
            // Fires before the change lands; re-read once it has.
            Task { @MainActor in self?.observe(apply) }
        }
    }

    // MARK: Recording

    private func publishCapture() {
        let capture = environment.capture
        guard case let .live(since) = capture.phase, let source = capture.source else {
            clockRollover?.task.cancel()
            clockRollover = nil
            // Over: the card shows Finished with the final time for its brief exit.
            if let shown = shownCapture {
                activities.finish(.capture, with: shown.ended(at: .now), linger: LiveActivityController.endedLinger)
            }
            shownCapture = nil
            return
        }
        let now = Date.now
        let clock = pauseClock.observe(since: since, paused: capture.isPaused, now: now)
        // Live, or kept on the phone and transcribed later (Transcribe later, or the connection dropped).
        let status: State.CaptureStatus = capture.isPaused ? .paused : capture.isBuffering ? .recording : .listening
        let state = State.capture(
            id: String(since.timeIntervalSince1970), startedAt: clock.startedAt, source: Self.source(source), status: status,
            elapsed: clock.elapsed, canPause: source != .watch, now: now
        )
        shownCapture = state
        activities.show(state, for: .capture)
        if status != .paused { scheduleClockRollover(at: state.clockEnd) }
    }

    private static func source(_ source: CaptureStore.Source) -> State.Source {
        switch source {
        case .device: .omi
        case .phone: .iPhone
        case .watch: .watch
        }
    }

    /// The card's clock range ends at the next hour; extend it then, even if nobody spoke.
    private func scheduleClockRollover(at end: Date) {
        guard clockRollover?.at != end else { return }
        clockRollover?.task.cancel()
        clockRollover = (end, Task { @MainActor [weak self] in
            try? await Task.sleep(for: .seconds(max(1, end.timeIntervalSinceNow + 1)))
            guard !Task.isCancelled else { return }
            self?.publishCapture()
        })
    }

    // MARK: Omi at work

    private func publishAgent() {
        let agent = environment.agent
        let active = agent.activeRuns
        if let run = active.first(where: { $0.id == shownRunID }) ?? active.first {
            shownRunID = run.id
            activities.show(state(for: run, phase: .working, others: active.count - 1), for: .agent)
            return
        }
        guard let id = shownRunID else { return }
        shownRunID = nil
        // Dismissed in the app: nothing left to show.
        guard let run = agent.runs[id] else {
            activities.show(nil, for: .agent)
            return
        }
        let phase: State.Phase = if case .done = run.state { .finished } else { .failed }
        activities.finish(.agent, with: state(for: run, phase: phase, others: 0), linger: LiveActivityController.finishedLinger)
    }

    private func state(for run: AgentStore.Run, phase: State.Phase, others: Int) -> State {
        let step: String = switch run.state {
        case let .working(step): step
        case .starting, .done, .failed: ""
        }
        return State(
            id: run.id, phase: phase, startedAt: run.startedAt,
            // A finished run's clock stops at the end.
            elapsed: phase == .working ? nil : max(0, Int(Date.now.timeIntervalSince(run.startedAt))), taskID: run.id,
            title: String(run.taskTitle.prefix(120)), step: String(step.prefix(80)), otherRuns: max(0, others)
        )
    }

    // MARK: Widgets

    private func publishWidgets() {
        guard case .ready = environment.session.phase else {
            if environment.session.phase == .signedOut { widgets.clear() }
            return
        }
        let devices = environment.devices
        widgets.publish(device: devices.paired.map {
            DeviceSnapshot(
                name: $0.name.isEmpty ? "Omi" : $0.name, connected: devices.connection == .connected,
                battery: devices.connection == .connected ? devices.battery : nil
            )
        })
        if environment.tasks.phase == .loaded {
            widgets.publish(upNext: UpNextPicker.snapshot(environment.tasks.tasks.filter { $0.owner != .other }.map {
                UpNextPicker.Candidate(id: $0.id, title: $0.description, due: $0.dueAt, isOpen: !$0.isCompleted)
            }))
        }
        if environment.conversations.phase == .loaded {
            widgets.publish(latest: environment.conversations.conversations.first { $0.status == .completed }.map {
                LatestSnapshot(id: $0.id, title: $0.title, at: $0.date, taskCount: $0.actionItemCount, duration: $0.duration)
            })
        }
    }
}
