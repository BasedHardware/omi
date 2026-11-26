import Foundation

// Compiled only into the Ruby test's temporary controller fixture. Production
// timer policy is unchanged; schedule/advance execute on its real control queue.
final class ManualProgressTimer {
    static var now: TimeInterval = 0
    static var current: ManualProgressTimer!
    let queue: DispatchQueue
    private var deadline: TimeInterval = .infinity
    private var interval: TimeInterval = 0
    private var handler: (() -> Void)?
    private var active = false

    init(queue: DispatchQueue) {
        self.queue = queue
        Self.current = self
    }

    func schedule(deadline: TimeInterval, repeating: TimeInterval, leeway: DispatchTimeInterval) {
        self.deadline = deadline
        interval = repeating
    }

    func setEventHandler(handler: @escaping () -> Void) { self.handler = handler }
    func resume() { active = true }
    func cancel() { active = false }

    static func advance(to target: TimeInterval) {
        let timer = current!
        timer.queue.sync {
            precondition(target >= now)
            while timer.active && timer.deadline <= target {
                now = timer.deadline
                timer.deadline += timer.interval
                timer.handler?()
            }
            now = target
        }
        // Emitters deliver on main; wait for that queue's barrier rather than
        // assigning wall-clock timing to the virtual timer.
        var delivered = false
        DispatchQueue.main.async { delivered = true }
        waitUntil({ delivered }, "manual heartbeat delivery")
    }
}

func replayRecoveryHeartbeat(deliverDuringResume: Bool) {
    let world = ReplayWorld()
    let writers = WriterBox()
    let controller = world.makeBatchController(writers: writers)
    guard case .success = startBatch(controller, 7) else {
        preconditionFailure("manual batch pacing: start failed")
    }
    let beforeInterrupt = world.sink.deliveries.count
    world.monitorBox.monitor!.fire(.interruptionBegan)
    waitUntil({
        world.sink.deliveries.dropFirst(beforeInterrupt).contains { $0.state == "interrupted" }
    }, "manual batch interrupted")
    ManualProgressTimer.advance(to: 1)
    ManualProgressTimer.advance(to: 1.9)

    let fastBeatCount = resumeBatchAndObserveProgress(world, afterSignal: {
        if deliverDuringResume {
            // Fire the preserved deadline before the helper waits for running.
            // The former post-wait baseline would swallow this valid beat.
            ManualProgressTimer.advance(to: 2)
        }
    }, observe: {
        ManualProgressTimer.advance(to: 3.9)
    })
    ManualProgressTimer.advance(to: 5.9)
    precondition(progressCount(world.sink) == fastBeatCount,
        "preserved fast beat must return to the healthy cadence")
    ManualProgressTimer.advance(to: 6)
    precondition(progressCount(world.sink) == fastBeatCount + 1,
        "healthy cadence must resume four seconds after the preserved beat")
    stop(controller)
    print("manual recovery heartbeat passed: \(deliverDuringResume ? "immediate" : "pending")")
}
