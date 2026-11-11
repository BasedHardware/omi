import AppKit

/// **The one process-wide key monitor this app installs on purpose, and the only thing allowed to
/// hold it.**
///
/// `NSEvent.addLocalMonitorForEvents(matching: .keyDown)` runs inside `NSApplication`'s dispatch,
/// ahead of every window in the process, and a handler that returns `nil` deletes the key press for
/// the whole application. That makes an *abandoned* recorder monitor indistinguishable, from the
/// user's side, from a keyboard that stopped working — and it is not a hypothetical: this monitor is
/// installed by a SwiftUI view and the removal it used to depend on was `.onDisappear`.
///
/// Two properties are the whole point of this type, and neither is a conditional somebody has to
/// remember to write:
///
/// 1. **One process, one recorder monitor.** `arm` replaces whatever was armed before, so no
///    sequence of view rebuilds can leave two installed. The `Armed` token is what makes that safe:
///    a stale view's `disarm` names the monitor *it* armed, and a token that has been superseded is
///    a no-op rather than a teardown of the live recorder.
/// 2. **A monitor cannot outlive the window that armed it.** The liveness question is asked *inside
///    the handler* — the one code path that cannot be skipped, because it is the same code that
///    would otherwise do the consuming. A recorder is a control in a window that is on screen; if
///    that window is gone or off screen, the monitor removes itself and hands the key press back
///    untouched. No `onDisappear`, no `deinit`, and no window observer has to fire for that to
///    happen.
///
/// Ordering out the Settings window is the case that motivated it. `SettingsWindow` keeps its window
/// (`isReleasedWhenClosed = false`) and hides it, so the hosting view is never removed from a view
/// hierarchy and SwiftUI has no reason to run `onDisappear` — while the only reference to the
/// monitor token was `@State` inside that view. A monitor orphaned that way could never be removed
/// again for the life of the process.
///
/// Whether a key press is *the recorder's at all* stays in `ShortcutRecorderScope`, which is the
/// other half of the rule and is asserted separately: **a recorder only ever hears the window it is
/// drawn in.**
@MainActor
final class ShortcutRecorderMonitor {

    static let shared = ShortcutRecorderMonitor()

    /// Names one arming, so a `disarm` from a view that has already been replaced cannot tear down
    /// the monitor its successor installed.
    struct Armed: Equatable {
        fileprivate let generation: UInt64
    }

    /// - Parameters:
    ///   - install: how a monitor is registered, returning whatever token has to be handed back to
    ///     remove it. Injected only so the decision below can be executed in a headless suite: a
    ///     test process can neither install a real monitor nor make a window key.
    ///   - remove: the matching teardown.
    ///   - recorderWindow: **the window a recorder could be drawn in right now**, or `nil` when there
    ///     is none. The default states the liveness fact once and owner-independently: a recorder is
    ///     a control in a window that is on screen, so a Settings window that has been ordered out is
    ///     the same answer as no Settings window at all. A test hands in one it made, or `nil` for
    ///     the abandonment — which is why this is a window rather than a `Bool` the caller computes.
    init(
        install: @escaping @MainActor (@escaping (NSEvent) -> NSEvent?) -> Any? = { handler in
            NSEvent.addLocalMonitorForEvents(matching: [.keyDown], handler: handler)
        },
        remove: @escaping @MainActor (Any) -> Void = { NSEvent.removeMonitor($0) },
        recorderWindow: @escaping @MainActor () -> NSWindow? = {
            guard let window = SettingsWindow.window, window.isVisible else { return nil }
            return window
        }
    ) {
        self.install = install
        self.remove = remove
        self.recorderWindow = recorderWindow
    }

    private let install: @MainActor (@escaping (NSEvent) -> NSEvent?) -> Any?
    private let remove: @MainActor (Any) -> Void
    private let recorderWindow: @MainActor () -> NSWindow?

    private var monitor: Any?
    private var consume: ((NSEvent) -> NSEvent?)?
    private var generation: UInt64 = 0

    /// Whether a monitor is installed right now. The property a test can ask about self-eviction
    /// with, and the one a leak is visible in.
    var isArmed: Bool { monitor != nil }

    /// Installs the recorder's monitor, replacing any previous one.
    ///
    /// - Parameter consume: what to do with a key press that really is the recorder's. Returning
    ///   `nil` swallows it, which is correct *only* for the window the recorder is drawn in — this
    ///   type is what guarantees the handler is never asked about anything else.
    @discardableResult
    func arm(_ consume: @escaping (NSEvent) -> NSEvent?) -> Armed {
        evict()
        generation &+= 1
        let armed = Armed(generation: generation)
        self.consume = consume
        // The decision crosses back as a `Bool` rather than as the event: `NSEvent` is not `Sendable`,
        // and "swallow it" is the whole of what `deliver` decided anyway.
        monitor = install { [weak self] event in
            let swallow = MainActor.assumeIsolated { () -> Bool in
                guard let self else { return false }
                return self.deliver(event, in: event.window) == nil
            }
            return swallow ? nil : event
        }
        return armed
    }

    /// Removes the monitor `armed` installed, and nothing else.
    ///
    /// A superseded token is a no-op on purpose: SwiftUI rebuilds this pane on every record, clear
    /// and app activation, and the replacement's `onAppear` arms before the old view's `onDisappear`
    /// runs. Without the token that ordering would leave the field showing "…" over no monitor.
    func disarm(_ armed: Armed) {
        guard armed.generation == generation else { return }
        evict()
    }

    /// The decision, with the event's window handed in rather than read off the event, because that
    /// is the one thing a synthesised `NSEvent` cannot carry — and it is the input every branch here
    /// turns on.
    func deliver(_ event: NSEvent, in eventWindow: NSWindow?) -> NSEvent? {
        // **Liveness first, and inside the handler.** A recorder is a control in a window that is on
        // screen. No such window means whatever armed this is gone — so the monitor removes itself
        // here and the key press carries on to whoever it was really for.
        guard let recorder = recorderWindow() else {
            evict()
            return event
        }
        guard ShortcutRecorderScope.belongsToTheRecorder(eventWindow, settingsWindow: recorder),
            let consume
        else { return event }
        return consume(event)
    }

    private func evict() {
        if let monitor { remove(monitor) }
        monitor = nil
        consume = nil
    }
}
