import AppKit
import ContextCore
import SwiftUI

/// The timeline window, owned by AppKit rather than by SwiftUI.
///
/// There is no `WindowGroup` anywhere in this app — every window is owned by its own type — so this
/// follows `OnboardingWindow`'s structure exactly: a `@MainActor` enum holding a `static current`,
/// the screen chosen from the pointer rather than `NSScreen.main`, and `isReleasedWhenClosed = false`
/// so closing the window keeps the instance and its loaded day alive for the next open.
///
/// **This is the app's second window now, not its first.** Activity is what the app opens on
/// (`SearchBarWindow`), and the timeline is what a *moment* opens into: a result card, an activity
/// tile, the panel's own Timeline pill, or the menu bar's row.
///
/// **It used to stand aside whenever the search panel came up, and that is deliberately not coming
/// back.** `SearchPanelEvent.opened` never meant "a window appeared" — it meant "present() was
/// called", including on a panel already on screen — and a window ordered out on that fact had no
/// `.closed` coming to bring it back. The panel dismisses itself on Escape and dismisses itself the
/// moment it opens this window, so there is nothing left for a yield to solve.
@MainActor
enum RewindWindow {

    /// Large enough that a 1600 px frame is not the limiting factor, and small enough to open
    /// comfortably on a 13" display.
    ///
    /// `nonisolated` because `SettingsMetrics` reads both from a `View`'s body: the Settings window
    /// opens at exactly this rectangle rather than at one of its own, so that the two windows this
    /// app puts on screen are the same object at different contents. A main-actor constant would be
    /// an error in the Swift 6 language mode there.
    nonisolated static let defaultSize = NSSize(width: 1180, height: 760)
    nonisolated static let minimumSize = NSSize(width: 820, height: 560)

    /// How often an open timeline looks for captures made since it read its day.
    ///
    /// Deliberately slow. The capture tick is three seconds and nobody sits watching a timeline for
    /// the next frame to appear, so this exists so a window left open all afternoon is not still
    /// claiming the day ended at the hour it was opened — not so the track animates. Each tick costs
    /// one `COUNT(*)` over an indexed range (`RewindModel.hasUnreadCaptures`) and reads nothing
    /// further unless that count moved.
    static let liveRefreshInterval: TimeInterval = 30

    private static var current: NSWindow?
    private static var model: RewindModel?
    private static var liveRefreshTimer: Timer?

    /// Opens the window, or brings the existing one forward with its state intact.
    ///
    /// - Parameters:
    ///   - store: the capture database. Injected rather than opened here so the app's single store
    ///     is reused; opening a second writer would be a second migration racing the first.
    static func present(
        store: ContextStore,
        onOpenSettings: @escaping () -> Void = {},
        onSearch: @escaping (String) -> Void = { _ in }
    ) {
        if let window = current {
            // The day this window holds was read when it was last opened, and capture has gone on
            // writing since. Opening the timeline again is exactly the moment to catch up — without
            // it the track stops at whatever hour the first open happened to fall on, for the rest
            // of the process. Nothing the user left in place moves; see `RewindModel.refresh`.
            model?.refresh()
            // Activation stays, on this branch and the two below. The timeline is secondary now, but
            // every route into it is an explicit ask — a result card, a menu row, the chord — and an
            // app that answers one by ordering a window in behind whatever is frontmost has not
            // answered it.
            //
            // **Ahead of the key-status ask, not after it**, which is the order the whole raise path
            // had backwards. `makeKeyWindow` is documented as a no-op while the application is
            // inactive — the window is ordered in and simply is not key — so asking for key status
            // first and activation second is asking in the one order that cannot work. Key status no
            // longer *depends* on activation landing (see `RewindWindowFrame`), but nothing is served
            // by asking in the wrong order either.
            raise(window)
            return
        }

        // The screen the pointer is on, not `NSScreen.main`. With two displays `main` is whichever
        // holds the key window, which is routinely the one the user is not looking at.
        let pointer = NSEvent.mouseLocation
        guard let screen = NSScreen.screens.first(where: { NSMouseInRect(pointer, $0.frame, false) })
            ?? NSScreen.main
        else {
            ContextLog.error("no screen available to present the timeline", "rewind")
            return
        }

        let model = RewindModel(store: store)
        Self.model = model

        let window = RewindWindowFrame(
            contentRect: centredFrame(on: screen),
            // Titled and resizable: unlike onboarding, this is a document-ish window the user keeps
            // open, moves, and resizes. The title bar is transparent and the title hidden so the
            // spec's centred mode title is the only thing that reads as one.
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            // **Escape closes it**, and the route is an init parameter so there is no such thing as a
            // timeline built without one — see `RewindWindowFrame`. `dismiss()` rather than `close()`,
            // so the loaded day survives for the next open exactly as the X leaves it.
            onEscape: { dismiss() })
        window.isMovableByWindowBackground = true
        window.minSize = minimumSize
        window.isReleasedWhenClosed = false
        window.title = RewindView.modeTitle
        // Deliberately not `.floating`: this window is worked *in*, and something always on top of
        // every other window is something to fight rather than something to read.
        window.level = .normal

        // The window-side half of the glass, which for a titled window is four properties that have
        // to agree: the light pin on the *window* (pinning only the content leaves the title bar and
        // the traffic lights in the system's appearance — a dark bar on a white sheet), a transparent
        // ground so the material blurs the desktop rather than a sheet AppKit painted, AppKit's own
        // shadow kept because the frame is the panel's edge here, and a title bar the glass runs edge
        // to edge underneath. All of it is `WindowGlass`, so this window and settings cannot drift.
        WindowGlass.wear(window, as: .titled)

        // CRITICAL: Use a container view instead of making NSHostingView the contentView directly.
        // When NSHostingView IS the contentView of a borderless window, it tries to negotiate
        // window sizing through updateWindowContentSizeExtremaIfNecessary and updateAnimatedWindowSize,
        // causing re-entrant constraint updates that crash in _postWindowNeedsUpdateConstraints.
        // Wrapping in a container breaks that "I own this window" relationship.
        //
        // The hosting view is constrained to the glass *host* rather than handed to
        // `InkGlassView.setContent`, which is the seam a floating panel uses: `setContent` is
        // frame-and-autoresizing, and this window is resizable with a minimum size that only Auto
        // Layout expresses. It is the same rectangle either way — `.fullBleed` is inset 0, so the
        // panel fills its host exactly — and every part of the ground stays AppKit's, which is the
        // property that matters. `RewindView` therefore paints no background of its own.
        //
        // sizingOptions: Remove .intrinsicContentSize so the hosting view can expand beyond
        // its SwiftUI ideal size. Keep .minSize and .maxSize for proper min/max constraints.
        // Setting [] removes ALL sizing info (broken). Default includes .intrinsicContentSize
        // which pins the view to its ideal size (prevents expansion). [.minSize, .maxSize] is correct.
        // The shared glass, full-bleed: no corner and no shadow of its own, because the window frame
        // already owns both. Everything the app draws on glass goes through this one component.
        let container = InkGlassView(
            frame: NSRect(origin: .zero, size: window.frame.size), style: .fullBleed)
        container.autoresizingMask = [.width, .height]
        window.contentView = container
        container.layoutSubtreeIfNeeded()

        let hosting = NSHostingView(
            rootView: RewindView(model: model, onOpenSettings: onOpenSettings, onSearch: onSearch))
        hosting.sizingOptions = [.minSize, .maxSize]
        hosting.translatesAutoresizingMaskIntoConstraints = false
        container.addSubview(hosting)
        NSLayoutConstraint.activate([
            hosting.leadingAnchor.constraint(equalTo: container.leadingAnchor),
            hosting.trailingAnchor.constraint(equalTo: container.trailingAnchor),
            hosting.topAnchor.constraint(equalTo: container.topAnchor),
            hosting.bottomAnchor.constraint(equalTo: container.bottomAnchor),
        ])

        current = window
        startLiveRefresh()
        raise(window)
    }

    /// Brings the timeline forward **and makes it the key window**, in the order that works.
    ///
    /// One function rather than the same two lines at three call sites, because the two lines are
    /// order-sensitive and the order is the part that was wrong: `NSApp.activate` first, then the key
    /// ask. It is not a formality — see `RewindWindowFrame` for what a timeline that never becomes
    /// key costs, and `TimelineKeyStatusTests` for the assertion that it does.
    private static func raise(_ window: NSWindow) {
        NSApp.activate(ignoringOtherApps: true)
        window.makeKeyAndOrderFront(nil)
    }

    /// Keeps an open timeline level with what capture is writing.
    ///
    /// Only while the window is actually on screen, and never in the middle of a settle: `refresh()`
    /// moves nothing by construction, but a re-span behind a gesture that is still landing is a risk
    /// worth not taking for a catch-up nobody is waiting on. A hidden window catches up on its next
    /// `present`, which is the moment it matters.
    ///
    /// The tick itself is a `Task` because both halves of the catch-up — the count and the day —
    /// happen off the main actor now. What the timer does here is decide whether to ask; the model
    /// owns the asking, so this window never has to know which read is safe to run where.
    private static func startLiveRefresh() {
        liveRefreshTimer?.invalidate()
        let timer = Timer(timeInterval: liveRefreshInterval, repeats: true) { _ in
            MainActor.assumeIsolated {
                guard current?.isVisible == true, let model else { return }
                Task { @MainActor in await model.refreshIfCapturesLanded() }
            }
        }
        RunLoop.main.add(timer, forMode: .common)
        liveRefreshTimer = timer
    }

    /// Opens the timeline **at a moment**, or moves an already-open one to it.
    ///
    /// The seam a search result travels through, and the reason it exists: `present(store:…)` opens
    /// whatever day the model last had — today, on a first open — so a card for last Tuesday could
    /// only ever open the wrong day. There was no way to say *when* from outside this file at all,
    /// which is why the search surface's result cards shipped inert.
    ///
    /// Correct whether or not the window is already up, and that is the whole of its contract:
    ///
    /// - **Closed.** `present` builds the model and the window; the instant is held by the model
    ///   (`pendingFocus`) and consumed by the opening read, so the day that opens *is* the moment's
    ///   day rather than the newest one being replaced a frame later.
    /// - **Open on another day.** The model loads that day and parks the playhead on the nearest
    ///   capture to the instant.
    /// - **Open on the same day.** No re-read; the playhead moves and the window comes forward.
    ///
    /// - Parameter instant: Unix epoch seconds — a `SearchMoment.capturedAt`, which is the frame's
    ///   capture time for a screen hit and the line's start for a spoken one.
    static func present(
        store: ContextStore,
        at instant: Double,
        onOpenSettings: @escaping () -> Void = {},
        onSearch: @escaping (String) -> Void = { _ in }
    ) {
        // Present first, then aim. The other order would ask a model that does not exist yet.
        present(store: store, onOpenSettings: onOpenSettings, onSearch: onSearch)
        focus(instant)
    }

    /// Moves an already-open timeline to `instant` and brings it forward.
    ///
    /// Returns false when there is no timeline to move — which is a state a caller may legitimately
    /// want to know about rather than a failure, so it is reported rather than logged. Callers that
    /// simply want the moment on screen should use `present(store:at:)`, which cannot fail this way.
    @discardableResult
    static func focus(_ instant: Double) -> Bool {
        guard let model else { return false }
        model.focus(on: instant)
        // A timeline behind the surface that just handed it a moment is a timeline the user has to
        // go looking for, so bringing it forward is part of aiming it.
        if let window = current { raise(window) }
        return true
    }

    /// Hides the window without discarding the loaded day.
    ///
    /// A close is the user's statement about this window and nothing else may undo it: nothing in the
    /// app orders the timeline back in on its own, and the only routes back on screen are the ones a
    /// person takes on purpose — `present`, `focus`, the menu row, the chord.
    static func dismiss() {
        current?.orderOut(nil)
    }

    static var isVisible: Bool { current?.isVisible ?? false }

    private static func centredFrame(on screen: NSScreen) -> NSRect {
        let visible = screen.visibleFrame
        let size = NSSize(
            width: min(defaultSize.width, visible.width - 40),
            height: min(defaultSize.height, visible.height - 40))
        return NSRect(
            x: (visible.midX - size.width / 2).rounded(),
            y: (visible.midY - size.height / 2).rounded(),
            width: size.width,
            height: size.height)
    }
}

// MARK: - Window

/// The timeline's window, so that **Escape closes it**.
///
/// The reported dead end, and this window is the one in the screenshot: *"Every window that gets
/// launched by a hotkey should also be dismissed by the same hotkey, right now I have no way to exit
/// this without clicking X."* It is `.titled` and `.closable`, so the X works and so does ⌘W — and
/// Escape, which is the first key anyone reaches for on a surface filling their display, did nothing at
/// all. The panel this window opens *from* has taken Escape since it shipped (`SearchPanel`), so a user
/// is taught the key on one surface and then finds it dead on the next one.
///
/// **In `sendEvent`, and the original comment here had the reason right.** It said a `cancelOperation:`
/// that runs only if nothing in the SwiftUI tree claims Escape first is a promise this file cannot keep —
/// and 1.0.5 shipped exactly that promise and broke exactly that way. What the comment could not say was
/// the other half: a window only receives key events while it is key, and this one never was, so the
/// intercept it defended was never reached either. Both halves are fixed below, and neither alone is
/// enough — which is why this window went out wrong twice.
///
/// **The date pill's popover is the one thing this could have taken a key from, and it does not need a
/// case.** `NSPopover` puts its content in a child window; while that window is key, Escape is dispatched
/// there and the popover closes on it, so this override is never reached. If it declines key status the
/// timeline closes instead — and takes the popover with it, because `orderOut` carries child windows —
/// which is the same thing ⌘W has always done and leaves nothing stranded either way.
///
/// **An `NSPanel` with `.nonactivatingPanel`, and that is the fix rather than a detail of it.**
///
/// The Escape route above shipped in 1.0.4 and did not work, for a reason no test in the package could
/// see: *the window never became key*, so `sendEvent` never received a `keyDown` to intercept. Measured
/// on the real class — `canBecomeKey` was already `true` and always had been, `.titled` gives that for
/// free, and `WindowGlass.wear`, the style mask and this subclass are all innocent. What failed is the
/// *assignment*: `makeKeyWindow` is documented as a no-op while the application is inactive, and the
/// `NSApp.activate(ignoringOtherApps:)` that was supposed to make it active is deprecated as of macOS 14
/// and simply does not always activate. Measured in `TimelineKeyStatusTests`: an ordinary titled window
/// of an inactive process orders in visible, reports `canBecomeKey == true`, and is not key — which is
/// grey traffic lights and a dead Escape, exactly as reported.
///
/// `.nonactivatingPanel` is what takes key status **without** waiting on activation, and it is the same
/// answer this app already measured its way to for the search surface — see `SearchBarWindow`, where a
/// plain window "orders in but does not become key while the app is not frontmost" and every keystroke
/// went to whatever was already in front. The timeline is the second surface to be bitten by it. The
/// window is otherwise unchanged: still `.titled`, still resizable, still carrying all three traffic
/// lights (asserted), still `.normal` level.
///
/// The three panel defaults that would be wrong here are set in `init` rather than left to the call
/// site, for the reason `onEscape` is an init parameter: a timeline built without them is not a window
/// to be fixed later, it is a defect with no runtime signal. `hidesOnDeactivate` is the loud one —
/// `NSPanel` defaults it to `true`, which would order the timeline off screen every time the user
/// switched apps.
///
/// Module-internal rather than file-private only so `TimelineEscapeTests` can press Escape on a real
/// one, for the reason `TutorialOverlayWindow` is: the one way out of a window is exactly the rule that
/// has to be executed rather than read, since reading it is what let its absence ship.
final class RewindWindowFrame: NSPanel {

    /// What Escape runs. Handed in by whoever builds the window rather than reached for from here — the
    /// window has no business knowing which type owns it.
    ///
    /// **An init parameter rather than `TutorialOverlayWindow`'s settable optional**, which is the whole
    /// of the difference between this and that card: an optional leaves "a timeline with no way out" a
    /// constructible state, and a `present()` that quietly stopped assigning it would put the reported
    /// dead end straight back with every test still green. There is no such window to build now.
    private let onEscape: () -> Void

    init(contentRect: NSRect, styleMask: NSWindow.StyleMask, onEscape: @escaping () -> Void) {
        self.onEscape = onEscape
        // Unioned here rather than asked of the caller. The caller's mask says what the window *is* —
        // titled, closable, resizable — and this bit says how it takes key status, which is this
        // type's own business and the one thing it must not be possible to construct one without.
        super.init(
            contentRect: contentRect, styleMask: styleMask.union(.nonactivatingPanel),
            backing: .buffered, defer: false)
        // A panel that only takes key status "if needed" leaves it with whatever held it before, which
        // is the state this class exists to end.
        becomesKeyOnlyIfNeeded = false
        // Not a floating panel: `isFloatingPanel` is `true` by default on `NSPanel` and puts the window
        // at `.floating`, and the timeline is worked *in* — see `present`, which says so at length.
        // Setting it also returns the level to `.normal`.
        isFloatingPanel = false
        // **The default that would hurt.** `NSPanel` hides on deactivation; a timeline that vanished
        // every time the user looked at another app would be a worse dead end than the one being fixed.
        hidesOnDeactivate = false
    }

    /// Already `true` for a `.titled` window and stated anyway, because it is the claim the reported
    /// failure was mistaken for and the one every other window in this app has to override — those are
    /// all `.borderless`, which is what actually defaults to `false`.
    override var canBecomeKey: Bool { true }

    /// **`true`, unlike every other panel here.** `NSPanel` refuses main status by default and the
    /// search surface keeps that refusal deliberately, because a non-activating panel that claims main
    /// drags the app forward. This window is *asking* to be the thing in front — and a titled window
    /// that is key but not main draws its traffic lights grey, which is the symptom that started this.
    override var canBecomeMain: Bool { true }

    /// **Escape is taken in `sendEvent`, which is the earliest layer this window owns.**
    ///
    /// Three shipped attempts converge here, and each one narrowed the problem:
    ///
    /// 1. **1.0.4 — `sendEvent`, window never key.** The intercept was right and unreachable: AppKit
    ///    delivers key events only to the key window, and this one never became key. Fixed by the panel
    ///    change above; proven on the real build, where the traffic lights now come up full colour.
    /// 2. **1.0.5 — `cancelOperation(_:)`, never invoked.** With key status fixed, Escape still did
    ///    nothing on the shipped app while **⌘W closed the window immediately**. That pair is the
    ///    measurement: ⌘W dispatches through the main menu's key equivalent, so the keyboard was live and
    ///    the window was key — and `cancelOperation:` specifically never ran. It arrives only via
    ///    `interpretKeyEvents` → `doCommandBySelector:`, at the *end* of a chain that `performKeyEquivalent:`
    ///    and the SwiftUI hosting view both sit in front of, so anything in that content claiming the key
    ///    first makes a window-level `cancelOperation` unreachable.
    /// 3. **Here.** `sendEvent` is the one layer above all of it: `NSWindow.sendEvent` is what *calls*
    ///    `performKeyEquivalent:` and what feeds the responder chain, so taking the key here cannot be
    ///    swallowed by anything inside the window.
    ///
    /// **This is not the 1.0.4 code restored.** The guard that came with it is gone, because it was a
    /// second defect: `(firstResponder as? NSTextView)?.isFieldEditor == true` cannot tell a field that is
    /// merely focused from one being edited — AppKit installs and focuses a field editor the moment
    /// anything editable appears — so one untouched control disabled the only keyboard exit for the life
    /// of the window. See `midEditText` for what replaced it and how narrow it now is.
    override func sendEvent(_ event: NSEvent) {
        if event.type == .keyDown, event.keyCode == Self.escapeKeyCode {
            // **The two lines that make the next live test a measurement rather than a guess, and
            // `milestone` rather than `info` because the last one was not readable.** Every round of
            // this bug has been argued from a window that logs nothing, so a repro could never
            // separate "the key never arrived" from "it arrived and the dismissal failed" — and the
            // line written to settle it went out at `info`, which `Log.swift` documents as invisible
            // to `log show` without `--info` and evicted from the ring buffer in minutes. An absent
            // `info` line proves nothing about the key; an absent `milestone` line does.
            //
            // Both branches speak, so the three outcomes are distinguishable on the next run: the
            // window declined the key, the window took it and the dismissal failed, or neither line
            // is there and the key never reached this window at all.
            guard midEditText == nil else {
                ContextLog.milestone(
                    "Escape reached the timeline window; a composition is holding it", "rewind")
                super.sendEvent(event)
                return
            }
            ContextLog.milestone("Escape taken at the timeline window; dismissing", "rewind")
            MainActor.assumeIsolated { onEscape() }
            return
        }
        super.sendEvent(event)
    }

    /// Text that genuinely owns Escape right now — **an in-progress input-method composition, and
    /// nothing else.**
    ///
    /// The guard this replaced asked "is a field editor focused", which is true from the instant any
    /// editable control appears and stays true with nothing typed in it. Measured against real AppKit
    /// (`TimelineEscapeTests`): an `NSTextView` does not claim `cancelOperation:` when it is idle, and it
    /// does not claim it with uncommitted text either — it claims Escape only when it has something of
    /// its own to cancel. Marked text is that state, and it is the one where taking the key would destroy
    /// work: cancelling a half-composed CJK or accented character is what Escape means mid-composition,
    /// and closing the window instead would throw the composition away with it.
    ///
    /// **It cannot become a dead end**, and that is the half worth asserting: passing the key on clears
    /// the composition, so the marked range is empty by the next press and that one leaves the window.
    /// Two Escapes at the very worst.
    ///
    /// **The half a hermetic test cannot reach**, said plainly rather than implied by a green suite: a
    /// test process has no input method, so `setMarkedText` raises the flag but leaves no composition for
    /// AppKit to cancel, and the key travels on instead of being consumed. `TimelineEscapeTests` therefore
    /// exercises this state and asserts only the dead-end rule, not which press closed the window. If this
    /// guard is ever suspected of holding Escape on a real Mac, the composition case is the one place it
    /// could, and it needs a live IME to reproduce.
    private var midEditText: NSTextView? {
        guard let editor = firstResponder as? NSTextView, editor.hasMarkedText() else { return nil }
        return editor
    }

    /// **Kept even though `sendEvent` now takes Escape first**, and not as a second route to the same
    /// place. `NSPanel` closes a closable panel on Escape by itself, and its `close()` is not this app's
    /// dismissal: `RewindWindow.dismiss` orders the window out so the loaded day survives exactly as the
    /// X leaves it. Overriding this is what stops AppKit stepping over that contract on any path that
    /// still reaches the responder chain — the composition case above, most obviously.
    override func cancelOperation(_ sender: Any?) {
        onEscape()
    }

    /// Named rather than `53` at the point of use, like every other reading of this key in the package.
    private static let escapeKeyCode: UInt16 = 53
}
