import AVFoundation
import Foundation

/// The phone-mic capture state machine. Owns every decision: sequencing of
/// permission -> session -> engine bring-up, retry policy, interruption and
/// route-change recovery, and teardown ordering. All state is confined to
/// `controlQueue`; the other PhoneMic classes are mechanism only.
///
/// Recovery is self-healing and native: Dart is only informed of state so it
/// can keep its own recording state and UI in sync — it never re-activates the
/// session or restarts capture on interruptions (its stall watchdog remains as
/// an outer safety net that calls stop()+start()).
final class PhoneMicController {
    private enum State {
        case idle
        case starting
        case running
        case interrupted
        case rebuilding
    }

    private static let bringUpRetryDelay: TimeInterval = 0.35
    private static let maxStartRetries = 2
    private static let resumeTickInterval: TimeInterval = 3.0

    private let controlQueue = DispatchQueue(label: "com.omi.phonemic.control", qos: .userInitiated)
    private let audioQueue = DispatchQueue(label: "com.omi.phonemic.audio", qos: .userInitiated)
    private let generation = PhoneMicGeneration()
    private let emitter: PhoneMicEventEmitter
    private var monitor: PhoneMicInterruptionMonitor?
    private var engine: PhoneMicCaptureEngine?

    private var state: State = .idle
    private var pendingStop = false
    private var pendingStartCompletions: [(Result<Void, Error>) -> Void] = []
    private var pendingStopCompletions: [() -> Void] = []
    private var startRetriesUsed = 0
    private var rebuildRetryScheduled = false
    private var resumeTicker: DispatchSourceTimer?

    init(flutterApi: PhoneMicFlutterApi) {
        self.emitter = PhoneMicEventEmitter(api: flutterApi, generation: generation)
        self.monitor = PhoneMicInterruptionMonitor(controlQueue: controlQueue) { [weak self] event in
            self?.handleMonitorEvent(event)
        }
    }

    // MARK: - Public API (callable from any thread; completions on main)

    func start(completion: @escaping (Result<Void, Error>) -> Void) {
        controlQueue.async { [weak self] in
            self?.handleStart(completion)
        }
    }

    func stop(completion: @escaping () -> Void) {
        controlQueue.async { [weak self] in
            self?.handleStop(completion)
        }
    }

    var isRecording: Bool {
        controlQueue.sync {
            switch state {
            case .running, .interrupted, .rebuilding: return true
            case .idle, .starting: return false
            }
        }
    }

    // MARK: - Command handling (controlQueue)

    private func handleStart(_ completion: @escaping (Result<Void, Error>) -> Void) {
        switch state {
        case .running:
            DispatchQueue.main.async { completion(.success(())) }
        case .starting, .rebuilding, .interrupted:
            // An active session already exists (cannot happen through the Dart
            // arbiter); resolve together with the in-flight bring-up/recovery.
            pendingStartCompletions.append(completion)
        case .idle:
            state = .starting
            startRetriesUsed = 0
            pendingStartCompletions.append(completion)
            monitor?.startObserving()
            emitter.emitState(.starting)
            NSLog("[PhoneMic] starting, route %@", PhoneMicSessionConfigurator.describeCurrentRoute())
            checkPermissionThenBringUp()
        }
    }

    private func handleStop(_ completion: @escaping () -> Void) {
        switch state {
        case .idle:
            DispatchQueue.main.async { completion() }
        case .starting:
            // Permission prompt or retry timer in flight — finish the stop when
            // the bring-up reaches its next decision point.
            pendingStop = true
            pendingStopCompletions.append(completion)
        case .running, .interrupted, .rebuilding:
            pendingStopCompletions.append(completion)
            finishStop()
        }
    }

    // MARK: - Bring-up (initial start)

    private func checkPermissionThenBringUp() {
        switch PhoneMicPermissionGate.current() {
        case .granted:
            performStartBringUp()
        case .denied:
            failStart(code: "permission_denied", message: "Microphone permission denied")
        case .undetermined:
            PhoneMicPermissionGate.request { [weak self] granted in
                self?.controlQueue.async {
                    guard let self, self.state == .starting else { return }
                    if granted {
                        self.performStartBringUp()
                    } else {
                        self.failStart(code: "permission_denied", message: "Microphone permission denied")
                    }
                }
            }
        }
    }

    private func performStartBringUp() {
        guard state == .starting else { return }
        if pendingStop {
            failStart(code: "start_aborted", message: "stop() superseded start()")
            return
        }
        guard let failure = attemptBringUp() else {
            enterRunning()
            return
        }
        if startRetriesUsed < Self.maxStartRetries {
            startRetriesUsed += 1
            NSLog("[PhoneMic] bring-up failed (%@), retry %d", failure.code, startRetriesUsed)
            controlQueue.asyncAfter(deadline: .now() + Self.bringUpRetryDelay) { [weak self] in
                guard let self, self.state == .starting else { return }
                self.performStartBringUp()
            }
        } else {
            failStart(code: failure.code, message: failure.message)
        }
    }

    /// Session config + fresh engine + converter + tap + engine start.
    /// Returns nil on success. Always builds a brand-new engine so no stale
    /// engine/converter state can survive a route generation.
    private func attemptBringUp() -> (code: String, message: String)? {
        do {
            try PhoneMicSessionConfigurator.configureAndActivate()
        } catch {
            return ("session_config_failed", error.localizedDescription)
        }

        teardownEngine()
        let epoch = generation.advance()
        let newEngine = PhoneMicCaptureEngine(
            audioQueue: audioQueue,
            onConvertedData: { [weak self] data, epoch in
                self?.emitter.emitFrame(data, epoch: epoch)
            },
            onConvertError: { [weak self] error, epoch in
                self?.controlQueue.async {
                    self?.handleConvertError(error, epoch: epoch)
                }
            }
        )
        do {
            try newEngine.buildAndInstallTap(epoch: epoch)
        } catch PhoneMicCaptureEngine.EngineError.formatInvalid {
            return ("format_invalid", "Audio input format unavailable or invalid")
        } catch PhoneMicCaptureEngine.EngineError.converterInitFailed {
            return ("converter_init_failed", "Could not build PCM16/16kHz converter")
        } catch {
            return ("engine_start_failed", error.localizedDescription)
        }
        do {
            try newEngine.startEngine()
        } catch {
            newEngine.teardown()
            return ("engine_start_failed", error.localizedDescription)
        }
        engine = newEngine
        monitor?.bindEngine(newEngine.engine)
        return nil
    }

    private func enterRunning() {
        cancelResumeTicker()
        state = .running
        NSLog("[PhoneMic] running, route %@", PhoneMicSessionConfigurator.describeCurrentRoute())
        emitter.emitState(.running)
        resolvePendingStarts(.success(()))
        if pendingStop {
            finishStop()
        }
    }

    private func failStart(code: String, message: String) {
        NSLog("[PhoneMic] start failed: %@ (%@)", code, message)
        generation.invalidate()
        teardownEngine()
        monitor?.stopObserving()
        cancelResumeTicker()
        state = .idle
        pendingStop = false
        emitter.emitState(.idle)
        resolvePendingStarts(.failure(PhoneMicPigeonError(code: code, message: message, details: nil)))
        resolvePendingStops()
    }

    // MARK: - Stop

    private func finishStop() {
        pendingStop = false
        cancelResumeTicker()
        // Epoch invalidation happens-before the tap removal and the .idle
        // emission, so any frame still racing through audioQueue/main is
        // dropped by the emitter: no frame is delivered after stop() resolves.
        generation.invalidate()
        monitor?.stopObserving()
        teardownEngine()
        // Barrier: every conversion block enqueued before the tap was removed
        // has run (their emissions are epoch-dead and will be dropped on main).
        audioQueue.sync {}
        state = .idle
        NSLog("[PhoneMic] stopped")
        emitter.emitState(.idle)
        resolvePendingStops()
        resolvePendingStarts(.failure(PhoneMicPigeonError(code: "start_aborted", message: "stopped", details: nil)))
    }

    // MARK: - Monitor events (controlQueue)

    private func handleMonitorEvent(_ event: PhoneMicInterruptionMonitor.Event) {
        switch event {
        case .interruptionBegan:
            guard state == .running || state == .rebuilding else { return }
            NSLog("[PhoneMic] interruption began")
            enterInterrupted()

        case .interruptionEnded(let shouldResume):
            guard state == .interrupted else { return }
            NSLog("[PhoneMic] interruption ended shouldResume=%d", shouldResume ? 1 : 0)
            // Without shouldResume we stay interrupted: the recording intent
            // persists and the ticker/call-observer keep probing.
            if shouldResume {
                attemptResume()
            }

        case .allCallsEnded, .appBecameActive:
            guard state == .interrupted else { return }
            attemptResume()

        case .routeChanged(let reason):
            guard state == .running else { return }
            NSLog("[PhoneMic] route changed (%lu), rebuilding: %@",
                  reason.rawValue, PhoneMicSessionConfigurator.describeCurrentRoute())
            beginRebuild()

        case .engineConfigChanged:
            guard state == .running else { return }
            NSLog("[PhoneMic] engine configuration changed, rebuilding")
            beginRebuild()

        case .mediaServicesReset:
            // Every audio object is invalid after a mediaserverd reset; the
            // rebuild path already recreates engine + converter from scratch.
            switch state {
            case .running, .rebuilding:
                NSLog("[PhoneMic] media services reset, rebuilding")
                emitter.emitError(code: "media_services_reset", message: "media services were reset; rebuilding capture")
                state = .running
                beginRebuild()
            case .interrupted:
                attemptResume()
            case .idle, .starting:
                break
            }
        }
    }

    private func enterInterrupted() {
        generation.invalidate()
        teardownEngine()
        state = .interrupted
        emitter.emitState(.interrupted)
        armResumeTicker()
    }

    /// Probe a resume from .interrupted. Failure is silent by design — during
    /// an active phone call setActive keeps failing until the call ends, and
    /// flapping interrupted/rebuilding events every tick would spam Dart.
    private func attemptResume() {
        guard state == .interrupted else { return }
        if attemptBringUp() == nil {
            NSLog("[PhoneMic] resumed after interruption")
            enterRunning()
        }
    }

    private func beginRebuild() {
        state = .rebuilding
        emitter.emitState(.rebuilding)
        if attemptBringUp() == nil {
            enterRunning()
            return
        }
        guard !rebuildRetryScheduled else { return }
        rebuildRetryScheduled = true
        controlQueue.asyncAfter(deadline: .now() + Self.bringUpRetryDelay) { [weak self] in
            guard let self else { return }
            self.rebuildRetryScheduled = false
            guard self.state == .rebuilding else { return }
            if self.attemptBringUp() == nil {
                self.enterRunning()
            } else {
                // Fall back to interrupted; the resume ticker keeps trying.
                self.emitter.emitError(code: "rebuild_failed", message: "capture rebuild failed; retrying in background")
                self.enterInterrupted()
            }
        }
    }

    private func handleConvertError(_ error: PhoneMicConverterPipeline.ConvertError, epoch: UInt64) {
        // Errors from a superseded epoch are stale by definition.
        guard generation.matches(epoch), state == .running else { return }
        switch error {
        case .formatDrift:
            // A route/config change beat its own notification — rebuild now.
            NSLog("[PhoneMic] converter format drift, rebuilding")
            beginRebuild()
        case .allocationFailed, .converter:
            emitter.emitError(code: "converter_failed", message: "audio conversion failed; rebuilding capture")
            beginRebuild()
        }
    }

    // MARK: - Helpers (controlQueue)

    private func teardownEngine() {
        engine?.teardown()
        engine = nil
    }

    private func armResumeTicker() {
        cancelResumeTicker()
        let ticker = DispatchSource.makeTimerSource(queue: controlQueue)
        ticker.schedule(
            deadline: .now() + Self.resumeTickInterval,
            repeating: Self.resumeTickInterval
        )
        ticker.setEventHandler { [weak self] in
            self?.attemptResume()
        }
        ticker.resume()
        resumeTicker = ticker
    }

    private func cancelResumeTicker() {
        resumeTicker?.cancel()
        resumeTicker = nil
    }

    private func resolvePendingStarts(_ result: Result<Void, Error>) {
        guard !pendingStartCompletions.isEmpty else { return }
        let completions = pendingStartCompletions
        pendingStartCompletions = []
        DispatchQueue.main.async {
            for completion in completions {
                completion(result)
            }
        }
    }

    private func resolvePendingStops() {
        guard !pendingStopCompletions.isEmpty else { return }
        let completions = pendingStopCompletions
        pendingStopCompletions = []
        DispatchQueue.main.async {
            for completion in completions {
                completion()
            }
        }
    }
}
