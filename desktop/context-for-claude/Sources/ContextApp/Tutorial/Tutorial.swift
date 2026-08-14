import AppKit
import ContextCore

/// The tutorial's public face. This is the whole API the app shell needs:
///
/// ```swift
/// Tutorial.start()                     // after onboarding's last card
/// Tutorial.start(store: myStore)       // when the caller already holds the capture database
/// Tutorial.start(resumingAt: beat)     // a process picking up a run a previous one was in
/// ```
///
/// `store` is optional because the app's writable store is owned privately by `Engine`, and the
/// tutorial only ever reads. Passing nil opens a read-only WAL reader, which never blocks the writer;
/// on a machine that has not captured anything yet there is nothing to open, and the steps that need
/// the store say so rather than inventing numbers.
@MainActor
enum Tutorial {
    /// - Parameter resume: the beat `TutorialResume` recorded, for a launch that found a walkthrough
    ///   in progress (`ContextAppDelegate.landing`). Nil starts at the top, which is what onboarding's
    ///   hand-off wants. The record is a *starting point* and never a claim about the world — see
    ///   `TutorialModel.begin(resumingAt:)` for what a resumed run re-reads rather than trusts.
    static func start(store: ContextStore? = nil, resumingAt resume: TutorialStep? = nil) {
        TutorialController.shared.start(store: store, resumingAt: resume)
    }

    static var isRunning: Bool { TutorialController.shared.isRunning }

    /// Ends the tutorial from outside — a quit, a window closing under it, a user who reached for the
    /// menu bar instead. Tears down every overlay it put up.
    static func abandon() {
        TutorialController.shared.abandon()
    }

    /// The real "Search All" pill in the real timeline was pressed.
    ///
    /// **The tutorial never takes this press, and that is the fix.** It used to: during the search
    /// beat this answered `true`, the shell's `guard` swallowed the press, and the bar the user had
    /// just been taught to click never opened — the beat drew its own field and its own grid of
    /// results on a coach card instead. What they learned was a surface that only exists during the
    /// tutorial.
    ///
    /// The press falls through to `SearchBarWindow.present` now, exactly as it does from the menu bar
    /// and from every other run of the app. The tutorial watches the panel that comes up
    /// (`SearchPanelWatch`) and advances because it really did — the same principle the timeline beat
    /// is built on, where the window the user learns to summon is opened by their own keypress.
    ///
    /// - Returns: `false`, always. The `Bool` is what is left of the interception: the shell still
    ///   guards on it (`ContextApp.swift`, owned by another change in flight), and that guard and
    ///   this return value are deleted together — `onSearch` becomes a bare
    ///   `SearchBarWindow.present(prefill: query)`, which is already what `StatusView` and
    ///   `TutorialEnvironment.presentTimeline` hand the same window.
    static func searchPillWasPressed() -> Bool { false }
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

    func start(store injected: ContextStore?, resumingAt resume: TutorialStep? = nil) {
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
        model.begin(resumingAt: resume)
        startTicking(every: environment.pollInterval)
    }

    func abandon() {
        model?.abandon()
        stopTicking()
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
