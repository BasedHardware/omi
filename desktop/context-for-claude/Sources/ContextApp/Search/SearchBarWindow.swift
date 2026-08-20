import AppKit
import ContextCore
import SwiftUI

/// The floating prompt bar. One borderless window, on the display the pointer is on.
///
/// AppKit-owned rather than a SwiftUI scene, for the same reason `OnboardingWindow` is: there is no
/// `WindowGroup` anywhere in this app, so a scene here would be a window the user could summon by
/// accident. This follows that file's structure deliberately — same `static current`, same
/// pointer-screen rule, same `isReleasedWhenClosed = false` so the window survives being closed.
///
/// **It was briefly a titled main window, and it is a Spotlight again.** Everything a summoned
/// overlay is — borderless, non-activating, key without pulling the app forward, sized to its own
/// content, gone on Escape and gone the moment you click anywhere else
/// (`dismissIfTheUserClickedAway`) — is in this file rather than in a window the user has to keep,
/// move and close. What survived the round trip is the Activity spine, which now answers inside the panel
/// before anything is typed (see `SearchBarView`), and the store provider, which is what lets a panel
/// built before capture opened its database heal itself instead of rendering empty forever.
@MainActor
final class SearchBarWindow {
    /// The window is the whole surface — both panels, the gap between them, and the clear margin the
    /// shadows fall into. Every number comes from `SearchLayout`, so the window and the view can
    /// never disagree about how tall the content is.
    ///
    /// `showingNote` is the taller state: the bar grows one line when it has something to say about
    /// where the question went.
    static func surfaceSize(showingNote: Bool = false) -> NSSize {
        NSSize(
            width: SearchLayout.surfaceWidth,
            height: SearchLayout.surfaceHeight(showingNote: showingNote))
    }

    private static var current: NSWindow?

    /// The panel's own rectangle, in AppKit screen coordinates, or nil when it is not up.
    ///
    /// Read by anything that has to stand *beside* this surface rather than on it — today the
    /// tutorial's coach mark, which coaches the real panel and must not sit over the field the user
    /// is being asked to type in. Nil is an ordinary answer and every caller has to live with it: the
    /// panel is closed far more often than it is open.
    ///
    /// The window includes `SearchLayout.shadowMargin` of clear margin on every side, which is
    /// deliberate — a card placed against this rectangle clears the shadow too.
    static var panelFrame: NSRect? {
        guard let window = current, window.isVisible else { return nil }
        return window.frame
    }

    /// Opens the bar, or brings it forward and re-focuses the field if it is already up.
    ///
    /// - Parameter prefill: a question to start from. This is the seam the timeline's "Search All"
    ///   pill plugs into — `RewindWindow.present(onSearch:)` hands its query straight through, so the
    ///   two surfaces share one bar rather than each growing their own.
    static func present(prefill: String = "") {
        if let window = current {
            window.alphaValue = 1
            window.makeKeyAndOrderFront(nil)
            // The panel is already up and already holds a composed corpus, so the right thing is
            // main's: keep every row on screen and ask the account what changed. Bounded by
            // `ActivityStore.revalidationCooldown`, which is why hammering the hotkey is one
            // request. The other branch does not need this — a freshly mounted surface calls
            // `start()`, and `start()` on an already-started store revalidates.
            ActivitySpine.shared.store.revalidate()
            NotificationCenter.default.post(
                name: refocusNotification, object: nil,
                userInfo: prefill.isEmpty ? nil : [prefillKey: prefill])
            // Announced on this branch too. "The panel is up" is the fact observers care about, and a
            // second press of the pill on an already-open bar leaves them holding it either way.
            SearchPanelWatch.report(.opened)
            return
        }

        // The screen the pointer is on, not `NSScreen.main`: `main` is whichever screen holds the key
        // window, which is routinely the one the user is not looking at — and a search bar that opens
        // on the other monitor may as well not have opened.
        let pointer = NSEvent.mouseLocation
        guard let screen = NSScreen.screens.first(where: { NSMouseInRect(pointer, $0.frame, false) })
            ?? NSScreen.main
        else {
            ContextLog.error("no screen available to present the search bar", "search")
            return
        }

        let frame = barFrame(on: screen)
        // `.nonactivatingPanel`, and this is the whole reason the bar is an `NSPanel` rather than an
        // `NSWindow` like the onboarding card.
        //
        // A plain borderless window orders in but does **not** become key while the app is not
        // frontmost: `NSApp.activate` is asynchronous and unreliable, so every keystroke went to
        // whatever was already in front — measured, with the field still showing its placeholder
        // while the text landed in another app. A non-activating panel takes key status *without*
        // activating the app, which is exactly the Spotlight-style behaviour this surface needs.
        let window = SearchPanel(
            contentRect: frame,
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        window.isFloatingPanel = true
        window.becomesKeyOnlyIfNeeded = false
        // The window-side half of the glass: transparent ground, the light pin, and no window shadow.
        //
        // `.floating` is right for this surface twice over. Once for the ordinary reason — the panels
        // draw the broad ambient shadow themselves, inside the window, which is the only shadow that
        // can follow their rounded corners. And once for a reason peculiar to this window: the
        // surface is not one rectangle but *two* panels with a gap between them, and AppKit's window
        // shadow traces the frame, so leaving it on would draw a shadow straight across the gap and
        // weld them back into the single slab this design exists to stop being.
        //
        // The pin is not cosmetic either. `InkGlass` is light in both system appearances, and the
        // bar's field is an `NSTextField` whose `Ink.nsPrimary` resolves against its *view's*
        // appearance rather than SwiftUI's environment — so on a Dark Mac an unpinned window puts
        // near-white type on a near-white panel. Pinning the window is what makes the AppKit half of
        // this surface agree with the SwiftUI half.
        WindowGlass.wear(window, as: .floating)
        window.level = .floating
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        window.isReleasedWhenClosed = false
        // **Still false, and the click-outside dismissal below is why it stays false.** Hiding on
        // deactivation is the wrong rule for this window twice: the app is routinely *not* frontmost
        // while the panel is up — that is what `.nonactivatingPanel` buys — so "the app deactivated"
        // fires for things that have nothing to do with this panel, and a window that hides rather
        // than closes leaves `SearchPanelWatch` with no `.closed` to report. The panel goes away on a
        // click outside it, through `dismiss()`, like every other route out of it.
        window.hidesOnDeactivate = false
        window.animationBehavior = .utilityWindow

        // A plain container, with the hosting view *inside* it.
        //
        // Making an `NSHostingView` the `contentView` of a borderless window crashes on macOS 26
        // inside `_postWindowNeedsUpdateConstraints`. Hosting it as a subview of an ordinary `NSView`
        // is the same layout and does not.
        let root = FirstMouseView(frame: NSRect(origin: .zero, size: frame.size))
        root.autoresizingMask = [.width, .height]

        let hosting = FirstMouseHostingView(
            rootView: SearchBarView(
                // **A provider, not the store.** The store opens lazily on the engine's own queue, so
                // a panel summoned in the second after launch would capture `nil` and render as empty
                // with no error path. Asked for on every read instead, so the surface heals the moment
                // capture opens one. Still the app's single store: a second connection would be a
                // second migration racing the first.
                store: { Engine.shared.contextStore },
                // The application's Activity store, not one this panel builds. This window is
                // rebuilt on every `present()` — `dismiss()` drops `current`, so the reuse branch
                // above is only ever taken while the bar is already up — and a spine owned by the
                // view would therefore re-page the whole account every time the bar is summoned.
                spine: ActivitySpine.shared.store,
                onDismiss: { dismiss() },
                onHeightChange: { height in resize(to: height) },
                onOpenMoment: { moment in open(moment) },
                onOpenActivityMoment: { moment in
                    travel(to: moment.timestamp.timeIntervalSince1970, hasPicture: moment.imagePath != nil)
                },
                onOpenTimeline: { openTheTimeline() },
                onOpenSettings: { openSettings() }))
        hosting.frame = root.bounds
        hosting.autoresizingMask = [.width, .height]
        root.addSubview(hosting)

        window.contentView = root
        window.setFrame(frame, display: true)

        current = window
        observeKeyStatus(window)
        // No `NSApp.activate`. The panel takes key status on its own, and activating the app as well
        // would pull the user out of whatever they were doing for no gain.
        window.makeKeyAndOrderFront(nil)
        // Key status is not focus. SwiftUI's `@FocusState` only reaches the field once the hosting
        // view is the window's first responder, and AppKit does not hand it over on its own for a
        // borderless panel — measured: `isKeyWindow` was true while the field still showed its
        // placeholder and the keystrokes went to the app behind. The async pass is the one that
        // sticks, because SwiftUI installs the field's responder on the next runloop turn.
        window.makeFirstResponder(hosting)
        DispatchQueue.main.async {
            MainActor.assumeIsolated {
                guard current === window else { return }
                window.makeFirstResponder(hosting)
                NotificationCenter.default.post(name: SearchBarWindow.refocusNotification, object: nil)
            }
        }
        // The shared chrome cue, which already honours the system UI-sound setting on its own.
        Sound.effect(.swoosh)
        ContextLog.info("search bar presented (key: \(window.isKeyWindow))", "search")
        // Last, once the window is genuinely on screen. Anything listening for this — the tutorial's
        // search beat — is being told a fact about the display, so it is announced after the display
        // has it and not before.
        SearchPanelWatch.report(.opened)
        // **This branch and not the one above**, which is the difference between "the surface was
        // opened" and "a key was pressed at a surface that was already up". Here rather than at the
        // callers because there are five of them — the gesture, the bound shortcut, the menu bar,
        // the timeline's "Search All" pill and the tutorial's own button — and a per-caller emit
        // would have measured whichever ones somebody remembered.
        //
        // Not implied by `cfc_gesture_fired`: that counts the gesture, which also *closes* an open
        // panel and fires from a Mac where the panel never appeared at all. This is the app's
        // primary surface, and it was the only one in `Surface` with no emitter.
        ContextAnalytics.record(.surfaceOpened(.search))
    }

    /// **Activating a result: open the timeline there, then get out of the way.**
    ///
    /// The one place a found moment becomes a window operation. `capturedAt` is the instant for both
    /// kinds of result — a screen hit carries its frame's capture time, a conversation hit carries
    /// the moment the line was spoken — so a single call covers both and neither kind can drift into
    /// a different meaning of "when".
    ///
    /// `frame != nil` and not `kind == .screen`: what the fact is about is whether there is a picture
    /// of that instant to travel back to, and a screen whose file retention already unlinked has no
    /// more of one than a spoken line does.
    private static func open(_ moment: SearchMoment) {
        travel(to: moment.capturedAt, hasPicture: moment.frame != nil)
    }

    /// Sends the timeline to an instant, from whichever body named it, and closes this panel.
    ///
    /// One path for both bodies: a result card and an activity tile are asking for the same thing,
    /// and two copies of this is how one of them ends up not reporting the trip, or opening a second
    /// timeline that cannot reach Settings.
    ///
    /// The order is load-bearing in both directions:
    ///
    /// - **Present first.** `RewindWindow.present(store:at:)` is what activates the app and takes key
    ///   status; doing it after the panel closed would leave a moment on screen behind whatever the
    ///   user was in.
    /// - **Then dismiss.** A floating search panel sitting over the timeline is covering the exact
    ///   thing the user just asked to see. It closes rather than hides, which is what this surface
    ///   has always done — the next open rebuilds it, ready for the next question.
    ///
    /// Declining when the store is not open yet is the same rule the menu bar and the global
    /// shortcut already follow: a timeline over nothing is worse than no timeline.
    private static func travel(to instant: Double, hasPicture: Bool) {
        guard let store = Engine.shared.contextStore else {
            ContextLog.error("cannot open a moment before the capture database is open", "search")
            return
        }
        RewindWindow.present(
            store: store,
            at: instant,
            // The same two handlers the menu bar and the global shortcut hand it, because the window
            // this opens is the same window: one that could not reach Settings, or whose "Search All"
            // pill did nothing, would be a second-class timeline reachable only from here.
            onOpenSettings: { SettingsWindow.present() },
            onSearch: { query in SearchBarWindow.present(prefill: query) })
        // Announced before the panel goes, so an observer sees "a result was activated" followed by
        // "the panel closed" rather than the other way round — the close is a *consequence* of the
        // activation here, and an observer that saw it first would read the beat as abandoned.
        SearchPanelWatch.report(.openedMoment(at: instant, hasPicture: hasPicture))
        dismiss()
    }

    /// **The timeline, asked for by name** — what the bar's "Timeline" pill does.
    ///
    /// Not `travel(to:)` with an instant invented for the occasion: the pill names no moment, so the
    /// timeline opens on whatever day it already holds, and reporting `.openedMoment` for a trip
    /// nobody asked for would tell every observer a card was activated. `ContextAppDelegate` owns the
    /// presentation — the store guard and the two hand-offs — because the menu bar's own row opens
    /// exactly this window, and a second reconstruction of three arguments is how one of them quietly
    /// stops being passed.
    ///
    /// It dismisses for the same reason activating a result does: this panel floats, and a Spotlight
    /// that stays on top of the window it just opened is covering the thing it was asked for.
    private static func openTheTimeline() {
        ContextAnalytics.record(.surfaceOpened(.activity))
        ContextAppDelegate.openTimeline()
        dismiss()
    }

    /// **Settings, and the panel gets out of the way** — what the bar's gear does.
    ///
    /// The same hand-off shape as the pill above, and for the same reason: this surface is a
    /// Spotlight, and a Spotlight that stays up over the window it just opened is covering the thing
    /// the user asked for. Settings is a real window they will move, resize and read; the panel is a
    /// 1112 pt slab in the upper third of the same display.
    ///
    /// It is a hand-off rather than a dismissal caused by the click, and the difference is
    /// load-bearing: `SearchResignation` deliberately exempts *any* window of ours taking focus,
    /// because the tutorial's coach card and the filter block's own date popover are windows of ours
    /// too and closing on those would break both. So the routes that really mean "leave" have to say
    /// so explicitly, here, rather than being inferred from focus moving.
    private static func openSettings() {
        ContextAnalytics.record(.surfaceOpened(.settings))
        SettingsWindow.present()
        dismiss()
    }

    /// `userInfo` key carrying a prefill through `refocusNotification`.
    static let prefillKey = "prefill"

    /// Both halves of "does this panel have the keyboard": taking it, and losing it.
    ///
    /// SwiftUI can only take focus once the window is key, and that happens *after* `present()`
    /// returns for a panel that never activates the app. Re-asserting focus on `didBecomeKey` is what
    /// makes the field typeable on the first open rather than the second.
    ///
    /// Losing it is the Spotlight rule — see `dismissIfTheUserClickedAway`.
    private static func observeKeyStatus(_ window: NSWindow) {
        keyObserver = NotificationCenter.default.addObserver(
            forName: NSWindow.didBecomeKeyNotification, object: window, queue: .main
        ) { _ in
            MainActor.assumeIsolated {
                NotificationCenter.default.post(name: SearchBarWindow.refocusNotification, object: nil)
            }
        }
        // **The gesture itself, not the focus change it happens to cause.**
        //
        // This was `didResignKeyNotification`, and a real launch disproved it in 375 ms: the log read
        // `search bar presented (key: true)` and then `dismissed by a click outside it`, with nobody
        // having touched anything. A `.nonactivatingPanel` is ordered in under whatever application is
        // frontmost — it takes key, that application takes it straight back, and to a key-resignation
        // rule that is indistinguishable from the user clicking away. The app opened and shut itself.
        //
        // A global mouse monitor asks the question directly. It only ever receives events delivered to
        // *other* applications, which is what makes the exemptions structural rather than guessed:
        // a click inside the panel is ours and never arrives here, and neither is a click on Settings,
        // the timeline, or the tutorial's card — all windows of this app. What does arrive is exactly
        // the gesture this feature is named after.
        clickAwayMonitor = NSEvent.addGlobalMonitorForEvents(
            matching: [.leftMouseDown, .rightMouseDown, .otherMouseDown]
        ) { _ in
            MainActor.assumeIsolated { dismissIfTheUserClickedAway(from: window) }
        }
    }

    private static var keyObserver: NSObjectProtocol?
    private static var clickAwayMonitor: Any?


    /// **Click anywhere else and the panel goes** — the last thing a summoned overlay owed the user.
    ///
    /// **`didResignKey` on the panel, and deliberately not `didResignActive` on the application.**
    /// This window is a `.nonactivatingPanel`: it takes the keyboard *without* bringing the app
    /// forward, so for the whole of its life some other application is the active one and this app is
    /// not. "The app deactivated" is therefore not a fact about this panel at all — it fires when the
    /// user leaves whichever of *our other* windows happened to be frontmost, and it does not fire
    /// when the user clicks from this panel into the browser behind it, which is the exact gesture
    /// this exists to answer. Key status is the one thing this window really holds and really loses.
    ///
    /// **The decision is taken a runloop turn late, and that is load-bearing.** AppKit resigns the
    /// old key window *before* it makes the new one key, so asked synchronously "is anything of ours
    /// key now?" the honest answer is always no — including when the user just pressed this panel's
    /// own gear. Deferring lets the new key window exist before it is asked about.
    ///
    /// What is exempt, and why each one, is `SearchResignation`. Nothing here dismisses a panel some
    /// other route already closed, which is what keeps `SearchPanelWatch.report(.closed)` at exactly
    /// one per real dismissal even though `travel(to:)` opens the timeline — taking key away from
    /// this panel — and then dismisses it itself.
    private static func dismissIfTheUserClickedAway(from window: NSWindow) {
        // Where the pointer was when the click landed. A global monitor only carries clicks bound for
        // other applications, but the panel spans a real rectangle on a real screen and a click can
        // land on a window *behind* it that is not ours — so the rectangle is still the question.
        guard Self.clickLandedOutside(NSEvent.mouseLocation, panel: window.frame) else { return }
        guard resignation(of: window).closesThePanel else { return }
        ContextLog.info("search bar dismissed by a click outside it", "search")
        dismiss()
    }

    /// Whether a click at `point` fell outside the panel.
    ///
    /// Pure, because the rest of this decision cannot be built in a headless suite and this half can:
    /// it is the whole difference between "the user clicked somewhere else" and the focus churn that
    /// a non-activating panel produces just by existing. The rectangle is the window's, so it
    /// includes `SearchLayout.shadowMargin` — a click in the panel's own shadow is a click on the
    /// panel, which is what a user pointing at its edge means.
    nonisolated static func clickLandedOutside(_ point: NSPoint, panel: NSRect) -> Bool {
        !panel.contains(point)
    }

    /// Reads the five questions `SearchResignation` answers off AppKit, and nothing else.
    ///
    /// Split from the decision so the decision is a value a test can hold: none of these five states
    /// can be produced in a headless suite, and all five of them are exemptions somebody has to be
    /// able to argue with.
    static func resignation(of window: NSWindow) -> SearchResignation {
        SearchResignation(
            panelIsStillTheOpenOne: current === window,
            panelTookKeyBack: window.isKeyWindow,
            // Any *visible* window of ours that now holds focus. Closed-but-retained windows are all
            // over this app (`isReleasedWhenClosed = false` everywhere), and one of those answering
            // "yes, I am main" would make the panel undismissable.
            anotherWindowOfOursHasFocus: NSApp.windows.contains { other in
                other !== window && other.isVisible && (other.isKeyWindow || other.isMainWindow)
            },
            aSheetOrModalIsUp: NSApp.modalWindow != nil
                || NSApp.windows.contains { $0.attachedSheet != nil },
            aSystemSecurityPromptIsUp: securityAgents.contains(
                NSWorkspace.shared.frontmostApplication?.bundleIdentifier ?? ""))
    }

    /// The processes macOS puts the login-Keychain password sheet up from.
    ///
    /// `com.apple.SecurityAgent` is read from the identifier of
    /// `Security.framework/…/MachServices/SecurityAgent.bundle`, not guessed. It matters here because
    /// `SessionStore.load()` runs off the main thread (`OmiAuth`), so its prompt — "Context for
    /// Claude wants to use your confidential information" — can arrive while this panel is up and
    /// while the runloop is free to answer. It is another application's window, so nothing in
    /// `NSApp.windows` knows about it; the frontmost application is what does.
    private static let securityAgents: Set<String> = ["com.apple.SecurityAgent"]

    /// Fires when `present()` is called on an already-open bar, so the field takes focus again.
    static let refocusNotification = Notification.Name("context.search.refocus")

    static var isVisible: Bool { current?.isVisible ?? false }

    /// **What the panel really is right now**, for the chord that toggles it.
    ///
    /// Read off `NSWindow` on every ask rather than kept as a flag: `current` survives a close
    /// (`isReleasedWhenClosed = false` everywhere in this app), so "we have a window" and "there is a
    /// panel on screen" are different facts and only the second one is the question. `isKeyWindow`
    /// rather than `NSApp.isActive` for the reason `HotkeyToggle.Presence` gives at length — this panel
    /// holds the keyboard while the app is not the active application, by design.
    static var presence: HotkeyToggle.Presence {
        guard let window = current, window.isVisible else { return .closed }
        return HotkeyToggle.Presence(isOnScreen: true, hasKeyboardFocus: window.isKeyWindow)
    }

    /// **The chord that opens this panel is the chord that closes it.**
    ///
    /// - Parameter presence: how to find out what the panel is doing. `nil` means the real read above,
    ///   resolved in the body rather than as a default argument because default arguments are evaluated
    ///   outside the main actor and `presence` is isolated to it (the same reason
    ///   `LiveShortcutBindings.init` resolves its registry inside). A caller overrides it only to assert
    ///   the three transitions, none of which a headless process can produce — a test cannot make a
    ///   window key.
    static func hotkeyToggle(
        presence: (() -> HotkeyToggle.Presence)? = nil
    ) -> HotkeyToggle {
        HotkeyToggle(
            presence: presence ?? { Self.presence },
            show: { present() },
            dismiss: { dismiss() })
    }

    /// What a global shortcut runs. Both of this app's chords land here, because both open this window.
    @discardableResult
    static func toggle() -> HotkeyPress { hotkeyToggle().press() }

    /// Closes the bar and tells everyone who was watching it that it is gone.
    ///
    /// **The announcement is before the guard, not after it, and that is load-bearing.** A
    /// `dismiss()` of an already-closed bar is exactly the shape that reaches here after some *other*
    /// path already closed the window (a result being opened, a second dismissal racing the first),
    /// and every observer has to hear about it either way. Reporting `.closed` unconditionally makes
    /// "the panel is not up" and "nothing is still waiting on it" the same statement; every observer
    /// of this event is idempotent for the same reason.
    static func dismiss() {
        SearchPanelWatch.report(.closed)
        // **The Escape route dies with the panel that owned it.** `ActivityDetailEscape` is a
        // process-wide hold armed by a view and released by that view's `onDisappear` — and a hosting
        // view in a window being closed has no reason to run one. A hold left behind makes the *next*
        // panel's Escape run a route into a surface that is no longer on screen: the key does nothing
        // and the panel stays up. The surface clears it on appear too; this is the same statement made
        // at teardown, where it does not depend on anything being mounted again to be true.
        ActivityDetailEscape.shared.release()
        guard let window = current else { return }
        current = nil
        if let keyObserver {
            NotificationCenter.default.removeObserver(keyObserver)
            self.keyObserver = nil
        }
        // Before `orderOut`: a monitor still installed here would answer for a window this call is
        // in the middle of closing.
        if let clickAwayMonitor {
            NSEvent.removeMonitor(clickAwayMonitor)
            self.clickAwayMonitor = nil
        }
        window.orderOut(nil)
        window.close()
    }

    /// Upper third, horizontally centred. A prompt bar belongs where the eye already is, not at the
    /// optical centre of the display.
    ///
    /// Clamped to the screen: the surface is a tall two-panel object now, and on a 13" display the
    /// naive upper-third placement puts its bottom edge past the dock.
    static func barFrame(on screen: NSScreen, showingNote: Bool = false) -> NSRect {
        defaultFrame(in: screen.visibleFrame, showingNote: showingNote)
    }

    /// The same placement as a pure function of a visible rectangle, so the tutorial's coach mark can
    /// be tested against the panel's real geometry on a display the test machine does not have.
    static func defaultFrame(in visible: NSRect, showingNote: Bool = false) -> NSRect {
        let size = surfaceSize(showingNote: showingNote)
        let x = visible.midX - size.width / 2
        let wanted = visible.maxY - size.height - visible.height * 0.10
        let y = max(visible.minY, wanted)
        return NSRect(x: x.rounded(), y: y.rounded(), width: size.width, height: size.height)
    }

    /// Grows or shrinks the window around its **top** edge.
    ///
    /// Around the top and not the centre because the bar is the thing the user is looking at and
    /// typing into: a window that re-centres itself when a status line appears moves the field out
    /// from under the cursor mid-sentence.
    static func resize(to height: CGFloat) {
        guard let window = current else { return }
        let frame = window.frame
        guard abs(frame.height - height) > 0.5 else { return }
        window.setFrame(
            NSRect(x: frame.minX, y: frame.maxY - height, width: frame.width, height: height),
            display: true,
            animate: false)
    }

}

// MARK: - The panel lost the keyboard. Was that the user clicking away from it?

/// Everything that was true a runloop turn after the search panel resigned key status, and the one
/// question it is asked.
///
/// **A value, because every field is an exemption and an exemption is an argument.** The rule the
/// user asked for is one sentence — click anywhere else and the panel goes — but "anywhere else" is
/// the interesting half, and getting it wrong is not a cosmetic failure: a panel that vanishes when
/// its own gear opens Settings has a gear that does nothing, and a panel that vanishes when the
/// login-Keychain sheet appears takes the question away from somebody who is in the middle of
/// answering a password prompt for it. None of these five states can be produced in a headless
/// suite, so the read is in `SearchBarWindow.resignation(of:)` and the decision is here.
struct SearchResignation: Equatable {

    /// The panel this is about is still the one `SearchBarWindow` has open.
    ///
    /// False when some other route already closed it — `travel(to:)` presents the timeline, which
    /// takes key away from this panel, and *then* dismisses it deliberately. That dismissal has
    /// already announced `.closed`; a second one from here would tell every observer the panel closed
    /// twice, and `TutorialModel` reads exactly that event to decide whether the panel is still its
    /// to take away.
    var panelIsStillTheOpenOne: Bool

    /// The keyboard came back to the panel before this ran — a popover closing, a field editor being
    /// rebuilt. Nothing happened from the user's side, so nothing happens from ours.
    var panelTookKeyBack: Bool

    /// Another window of **this app** now has the keyboard.
    ///
    /// The exemption that carries the most weight. The panel is the only route to Settings and one of
    /// the routes to the timeline, and both of those come forward and activate the app — so the
    /// panel losing key to them is the panel *working*, not the user leaving it. The tutorial's coach
    /// card is here too: a card the user is meant to press takes key on entry
    /// (`TutorialStep.takesFocusOnEntry`), and a panel that closed itself at that moment would take
    /// the coached surface off screen in the middle of the beat that is teaching it. So is any
    /// popover the panel puts up — a date picker in the filter block is a window of ours as far as
    /// AppKit is concerned.
    ///
    /// It is deliberately "another window of ours" rather than "a window this panel opened". The two
    /// differ only for a timeline the user already had open behind the panel, and treating that as a
    /// click-away would mean the app closing its own search panel because the user glanced at its own
    /// window — the wrong side to err on for a surface Escape closes instantly anyway.
    var anotherWindowOfOursHasFocus: Bool

    /// A modal session is running, or a sheet is attached to one of our windows. A sheet's parent
    /// window is not key while the sheet is up, and a panel that closed itself underneath one would
    /// be answering for a click the user never made.
    var aSheetOrModalIsUp: Bool

    /// macOS is showing the login-Keychain password sheet (or another `SecurityAgent` prompt).
    ///
    /// It belongs to another process, so it looks exactly like the user clicking into another
    /// application — and it is the one case where that reading is wrong, because the prompt was
    /// raised *by this app*, on the user's behalf, without being asked for. See
    /// `SearchBarWindow.securityAgents`.
    var aSystemSecurityPromptIsUp: Bool

    /// Whether the panel should close. True only when none of the exemptions applies.
    var closesThePanel: Bool {
        guard panelIsStillTheOpenOne else { return false }
        return !panelTookKeyBack && !anotherWindowOfOursHasFocus && !aSheetOrModalIsUp
            && !aSystemSecurityPromptIsUp
    }
}

// MARK: - What the real search surface just did

/// One thing that really happened on the real search surface.
///
/// Every case is a fact about the *shipped* panel — the window that came up, the read that finished,
/// the card somebody pressed — and nothing here can be produced by asking. That is the whole reason
/// it exists: the tutorial's search beats used to draw their own field and their own grid of results
/// on a coach card, teaching a surface that does not exist. They watch these events instead, so what
/// the user learns to press is the real pill and what answers them is the real panel.
///
/// The timeline used to listen too, and ordered itself out on `.opened`. That is gone and stays gone:
/// `.opened` means "present() was called", including on a panel already on screen, and a window
/// ordered out on that fact had no `.closed` coming to bring it back.
enum SearchPanelEvent: Equatable, Sendable {
    /// The panel is on screen. Sent on a fresh open *and* on a press that re-focused one already up,
    /// because the fact is about the display and not about how it got there.
    case opened
    /// The panel is gone, whichever route closed it — Escape, a click anywhere outside it, a result
    /// being activated, the Timeline pill. Always sent, even for a dismissal that found nothing to
    /// close — see `SearchBarWindow.dismiss`.
    case closed
    /// A real read finished.
    ///
    /// - Parameters:
    ///   - query: what was asked, trimmed. **Empty is a real value and means something specific**:
    ///     the panel opens by reading the newest captures with nothing typed, so an observer waiting
    ///     for somebody to genuinely search for something has to be able to tell that read apart from
    ///     a question. Folding the two together would let the search beat's gate be satisfied by the
    ///     bar merely opening.
    ///   - results: how many moments came back. Zero for a read that failed as well as for one that
    ///     genuinely found nothing — the panel says which in its own copy, and nothing downstream may
    ///     treat "could not look" as an answer.
    case answered(query: String, results: Int)
    /// One of those results was activated, and the timeline has travelled to it.
    ///
    /// - Parameters:
    ///   - at: the moment, in Unix epoch seconds.
    ///   - hasPicture: whether a captured frame survives for that instant. False for a spoken line
    ///     and for a screen whose file retention has already unlinked.
    case openedMoment(at: Double, hasPicture: Bool)
}

/// Who is listening to the real search surface.
///
/// A registry of closures rather than `NotificationCenter`, for the same reason
/// `GlobalShortcuts.addObserver` is one: the token makes a second `start` impossible to leak, the
/// payload is a typed value rather than a `userInfo` dictionary every reader has to re-parse, and
/// nothing here is discoverable by an observer that was never handed the type.
///
/// Observers are told, never asked. Nothing in here can make the panel do anything.
@MainActor
enum SearchPanelWatch {
    private static var observers: [UUID: (SearchPanelEvent) -> Void] = [:]

    /// - Returns: a token to hand back to `removeObserver`. Observers are additive; registering a
    ///   second one never replaces the first.
    @discardableResult
    static func addObserver(_ observe: @escaping (SearchPanelEvent) -> Void) -> UUID {
        let token = UUID()
        observers[token] = observe
        return token
    }

    static func removeObserver(_ token: UUID) {
        observers[token] = nil
    }

    /// Tells every observer. Copied first so an observer that removes itself — or registers another —
    /// while being told cannot mutate the collection being iterated.
    static func report(_ event: SearchPanelEvent) {
        for observe in Array(observers.values) { observe(event) }
    }
}

// MARK: - Window

/// Borderless panels refuse key status by default, which would leave the field untypeable.
///
/// `canBecomeMain` stays false on purpose: a non-activating panel that claims main status drags the
/// app forward, which is the thing `.nonactivatingPanel` exists to avoid.
private final class SearchPanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }

    /// Escape, intercepted where interception is guaranteed.
    ///
    /// Belt to the field's own braces. `SearchField`'s delegate already reports Escape as
    /// `cancelOperation:`, but only while the field editor holds focus — this catches it when focus has
    /// moved to the target pill, where a bar that would not close is the worst possible state. Return
    /// is deliberately **not** handled here: the field owns submitting, and intercepting it in two
    /// places is how it ends up handled in neither.
    ///
    /// `sendEvent` rather than a local `NSEvent` monitor because a monitor does not see these events at
    /// all — measured: the field took Escape and dropped its focus while the monitor was never called.
    /// For a non-activating panel in an app that was never activated, key events do not go through
    /// `NSApplication`'s dispatch.
    override func sendEvent(_ event: NSEvent) {
        if event.type == .keyDown {
            switch event.keyCode {
            case 53:  // Escape
                MainActor.assumeIsolated {
                    // **A detail pushed over the spine takes Escape first.** On this panel the key
                    // means "back" while there is somewhere to go back to, and "close" only when
                    // there is not — a user reading a conversation who presses Escape is leaving the
                    // conversation, not the app's whole surface.
                    //
                    // Asked here rather than in the field's `cancelOperation:` because this override
                    // does not call `super`: it swallows Escape before the field editor ever sees
                    // it, which is deliberate (see above) and means every Escape rule on this window
                    // has to live at this one point. `consume()` both answers and clears, so the
                    // second press closes the panel.
                    //
                    // **Said out loud, at `milestone`.** A hold left behind by a panel that was
                    // dismissed with a detail open makes this key do nothing visible at all — the
                    // route runs against a surface that is no longer on screen and the panel stays
                    // up — which is exactly the "Escape worked earlier in this session and does not
                    // now" report. Which of the two things happened is not inferable from the
                    // outside, so the panel states it, and at the one level that survives long
                    // enough to be read back (see `Log.swift`).
                    let wentBackToTheSpine = ActivityDetailEscape.shared.consume()
                    ContextLog.milestone(
                        "Escape taken at the search panel (back to the spine: \(wentBackToTheSpine))",
                        "search")
                    guard !wentBackToTheSpine else { return }
                    SearchBarWindow.dismiss()
                }
                return
            default:
                break
            }
        }
        super.sendEvent(event)
    }
}

// MARK: - First mouse
//
// The panel does not activate the app, so this process is routinely not frontmost when the bar
// appears. By default AppKit spends the first click activating the window and never delivers it to
// the control underneath — the user's first click into the field would do nothing at all. This
// codebase has been bitten by exactly that before; accepting first mouse is what makes the first
// click count.

private final class FirstMouseView: NSView {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}

private final class FirstMouseHostingView<Content: View>: NSHostingView<Content> {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}
