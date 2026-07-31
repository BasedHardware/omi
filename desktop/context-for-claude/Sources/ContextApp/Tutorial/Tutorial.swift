import AppKit
import ContextCore

/// The tutorial's public face. This is the whole API the app shell needs:
///
/// ```swift
/// Tutorial.start()                 // after onboarding's last card
/// Tutorial.start(store: myStore)   // when the caller already holds the capture database
/// ```
///
/// `store` is optional because the app's writable store is owned privately by `Engine`, and the
/// tutorial only ever reads. Passing nil opens a read-only WAL reader, which never blocks the writer;
/// on a machine that has not captured anything yet there is nothing to open, and the steps that need
/// the store say so rather than inventing numbers.
@MainActor
enum Tutorial {
    static func start(store: ContextStore? = nil) {
        TutorialController.shared.start(store: store)
    }

    static var isRunning: Bool { TutorialController.shared.isRunning }

    /// Ends the tutorial from outside — a quit, a window closing under it, a user who reached for the
    /// menu bar instead. Tears down every overlay it put up.
    static func abandon() {
        TutorialController.shared.abandon()
    }

    /// The real "Search All" pill in the real timeline was pressed.
    ///
    /// The shell asks before opening its search bar, so the one real control serves both: during the
    /// beat that asked for it the tutorial takes the press and answers true, and everywhere else this
    /// is one boolean and the bar opens exactly as it always did. That is what lets the timeline be
    /// opened by the user's own shortcut — there is no second, tutorial-only copy of the window with
    /// different buttons wired behind it.
    ///
    /// - Returns: whether the tutorial consumed the press.
    static func searchPillWasPressed() -> Bool {
        TutorialController.shared.searchPillWasPressed()
    }
}

/// Owns the step machine, the poll timer, and the window the cards live in.
///
/// The split matters: `TutorialModel` is the part whose honesty is testable and therefore holds no
/// windows, while everything that cannot be asserted without a screen lives here.
@MainActor
final class TutorialController {
    static let shared = TutorialController()

    private var model: TutorialModel?
    private var ticker: Task<Void, Never>?
    /// Held for the run so the read-only reader is not opened per query. Released on teardown.
    private var store: ContextStore?

    var isRunning: Bool {
        guard let model else { return false }
        return !model.step.isTerminal
    }

    func start(store injected: ContextStore?) {
        if let model, !model.step.isTerminal {
            // Already walking: bring the current card back rather than starting a second machine.
            TutorialOverlay.shared.show(model: model, step: model.step)
            return
        }

        // The app's own writer first, a read-only WAL reader second. Two connections to one database
        // are safe, but the engine's store is already open and already migrated — reaching for it means
        // the tutorial reads exactly what capture just wrote, with no second open to go wrong.
        let resolved = injected ?? Engine.shared.contextStore ?? (try? ContextStore(readOnly: true))
        if resolved == nil {
            ContextLog.error("tutorial: no capture store to read; steps that need it will say so", "tutorial")
        }
        store = resolved

        var environment = TutorialEnvironment.live(store: resolved)
        environment.presentOverlay = { [weak self] step in
            guard let model = self?.model else { return }
            TutorialOverlay.shared.show(model: model, step: step)
        }
        environment.dismissOverlay = { TutorialOverlay.shared.hide() }

        let model = TutorialModel(environment: environment)
        self.model = model
        model.begin()
        startTicking(every: environment.pollInterval)
    }

    func abandon() {
        model?.abandon()
        stopTicking()
    }

    /// The pill press, offered to the running step machine. False when nothing is running or the
    /// current beat is not the one that asked for it, which is what leaves the shell's own behaviour
    /// untouched everywhere else.
    func searchPillWasPressed() -> Bool {
        model?.searchPillWasPressed() ?? false
    }

    /// One timer for the whole tutorial: the model's own polling and the overlay's re-anchoring.
    ///
    /// Re-anchoring on the same tick as polling is deliberate — the coach mark's position and the
    /// state it describes are then never a frame apart.
    private func startTicking(every interval: Double?) {
        stopTicking()
        guard let interval, interval > 0 else { return }
        ticker = Task { [weak self] in
            while !Task.isCancelled {
                guard let self, let model = self.model, !model.step.isTerminal else { return }
                model.poll()
                TutorialOverlay.shared.reposition()
                if model.step.isTerminal {
                    self.stopTicking()
                    return
                }
                try? await Task.sleep(for: .seconds(interval))
            }
        }
    }

    private func stopTicking() {
        ticker?.cancel()
        ticker = nil
    }
}
