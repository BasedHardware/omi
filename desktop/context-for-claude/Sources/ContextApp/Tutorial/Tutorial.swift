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
        // The real timeline, with its real "Search All" button wired back into the step machine — so
        // G9 advances because the user pressed the actual control, not because they read about it.
        // The same wiring the shell uses (`ContextApp.swift`), plus one extra: the pill also tells the
        // step machine it was pressed, so G9 advances because the user pressed the real control.
        //
        // The pill deliberately does *not* open `SearchBarWindow` during the tutorial. That bar routes
        // a question to Claude, which is the beat two steps later and is gated on `QueryStamp`; this
        // beat is "find the moment again and jump back to it", which needs a result and a timestamp
        // this app can actually show. Opening both would put two query fields on screen at once.
        environment.presentTimeline = { [weak self] in
            guard let store = self?.store else { return }
            RewindWindow.present(
                store: store,
                onOpenSettings: { SettingsWindow.present() },
                onSearch: { _ in self?.model?.searchPillWasPressed() })
        }

        let model = TutorialModel(environment: environment)
        self.model = model
        model.begin()
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
