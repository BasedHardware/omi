import AppKit
import ContextCore
import SwiftUI

/// **The app's main window.** One titled, resizable window holding the search surface, kept for the
/// life of the process.
///
/// AppKit-owned rather than a SwiftUI scene, for the same reason `RewindWindow` and
/// `OnboardingWindow` are: there is no `WindowGroup` anywhere in this app, so a scene here would be a
/// second window the user could summon by accident. What it borrows from `RewindWindow` is the whole
/// construction of a titled window in this app — `WindowGlass.wear(_:as: .titled)`, an `InkGlassView`
/// container with the hosting view constrained inside it, `isReleasedWhenClosed = false` — because
/// this is now the same *kind* of object that file already describes.
///
/// **It used to be a Spotlight.** A borderless, non-activating `NSPanel` that came up on ⌘⌘⇧, took
/// key status without activating the app, sized itself to its own content on every keystroke, and
/// closed on Escape. Everything in that list is a property of a summoned overlay, and every one of
/// them is wrong for a window somebody works in: an Escape swallowed at the window level eats the key
/// from every field and popover inside it, a frame that re-derives itself from the content undoes the
/// user's own drag on the next keystroke, and a surface that destroys its query when a result is
/// opened cannot be the thing you come back to. The quick-Spotlight flow is deliberately given up;
/// there is exactly one search surface and this is it.
@MainActor
final class SearchBarWindow {

    /// What the window is called — in its title bar, in the Window menu, and in ⌘-Tab.
    ///
    /// "Activity" and not "Search": search is what the bar at the top does, and the window is the
    /// place the app's own record of this Mac is read. The menu bar's row says the same word.
    static let title = "Activity"

    /// Where AppKit remembers the frame between launches. Namespaced with the app's other
    /// `context.*` defaults.
    static let frameAutosaveName = "context.activity.window"

    private static var current: NSWindow?

    /// The window's own rectangle, in AppKit screen coordinates, or nil when it is not on screen.
    ///
    /// Read by anything that has to stand *beside* this surface rather than on it — today the
    /// tutorial's coach mark, which coaches the real window and must not sit over the field the user
    /// is being asked to type in. Nil is still an ordinary answer: the window is closable, and a user
    /// who closed it has closed it.
    static var panelFrame: NSRect? {
        guard let window = current, window.isVisible else { return nil }
        return window.frame
    }

    /// Opens the window, or brings the existing one forward with its query and results intact.
    ///
    /// Idempotent and never a toggle. A second call activates the app, brings the window front, puts
    /// the keyboard back in the field and selects whatever is already typed — the Spotlight bargain,
    /// minus the half of it that made a second press *close* the thing you were looking at.
    ///
    /// - Parameter prefill: a question to start from. This is the seam the timeline's "Search All"
    ///   pill plugs into — `RewindWindow.present(onSearch:)` hands its query straight through, so the
    ///   two surfaces share one bar rather than each growing their own.
    static func present(prefill: String = "") {
        if let window = current {
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            NotificationCenter.default.post(
                name: refocusNotification, object: nil,
                userInfo: prefill.isEmpty ? nil : [prefillKey: prefill])
            // Announced on this branch too. "The window was asked for" is the fact observers care
            // about, and a second press of the pill leaves them holding it either way.
            SearchPanelWatch.report(.opened)
            return
        }

        // The screen the pointer is on, not `NSScreen.main`: with two displays `main` is whichever
        // holds the key window, which is routinely the one the user is not looking at — and a window
        // that opens on the other monitor may as well not have opened. Only the *first* open is
        // placed this way; after that `setFrameAutosaveName` has the user's own frame.
        let pointer = NSEvent.mouseLocation
        guard let screen = NSScreen.screens.first(where: { NSMouseInRect(pointer, $0.frame, false) })
            ?? NSScreen.main
        else {
            ContextLog.error("no screen available to present the main window", "search")
            return
        }

        let window = NSWindow(
            contentRect: defaultFrame(on: screen),
            // An ordinary document-ish window: one the user keeps open, moves, resizes and closes.
            // `.fullSizeContentView` is what lets the glass run edge to edge under the title bar;
            // `SearchLayout.titleBarInset` is what keeps the prompt bar out from under the traffic
            // lights.
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false)
        window.title = title
        window.minSize = SearchLayout.minimumWindowSize
        window.isReleasedWhenClosed = false
        // Deliberately not `.floating`, and this is the single largest change in this file. A panel
        // that hovers over every other window is right for something summoned for two seconds and
        // wrong for the window the app opens on: something always on top is something to fight rather
        // than something to read. Ordinary level, ordinary collection behaviour.
        window.level = .normal

        // The window-side half of the glass, which for a titled window is four properties that have
        // to agree — see `RewindWindow`, which wears it the same way. The light pin matters twice
        // over here: `Ink` is light in both system appearances, and this window's field is an
        // `NSTextField` whose `Ink.nsPrimary` resolves against its *view's* appearance rather than
        // SwiftUI's environment, so on a Dark Mac an unpinned window puts near-white type on
        // near-white glass.
        WindowGlass.wear(window, as: .titled)

        // CRITICAL: Use a container view instead of making NSHostingView the contentView directly.
        // When NSHostingView IS the contentView, it tries to negotiate window sizing through
        // updateWindowContentSizeExtremaIfNecessary and updateAnimatedWindowSize, causing re-entrant
        // constraint updates that crash in _postWindowNeedsUpdateConstraints. Wrapping in a
        // container breaks that "I own this window" relationship.
        //
        // Auto Layout and not frame-and-autoresizing, which is what this surface used while it was a
        // panel: a resizable window with a minimum size is a thing only constraints express. The
        // hosting view keeps `[.minSize, .maxSize]` and drops `.intrinsicContentSize`, which would
        // pin it to its SwiftUI ideal size and stop it expanding.
        let container = InkGlassView(
            frame: NSRect(origin: .zero, size: window.frame.size), style: .fullBleed)
        container.autoresizingMask = [.width, .height]
        window.contentView = container
        container.layoutSubtreeIfNeeded()

        let hosting = NSHostingView(
            rootView: SearchBarView(
                initialQuery: prefill,
                // **A provider, not the store.** This window is built once and lives for the life of
                // the process, and the store opens lazily on the engine's own queue — so a window
                // opened at launch would capture `nil` forever and render as permanently empty with
                // no error path. Asked for on every read instead, so the surface heals the moment
                // capture opens one. Still the app's single store: a second connection would be a
                // second migration racing the first.
                store: { Engine.shared.contextStore },
                onOpenMoment: { moment in open(moment) },
                onOpenActivityMoment: { moment in
                    travel(to: moment.timestamp.timeIntervalSince1970, hasPicture: moment.imagePath != nil)
                }))
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
        // Retained here because `NSWindow.delegate` is weak, and it is a delegate rather than two
        // notification observers because both facts it carries are facts about *this* window.
        delegate = SearchWindowDelegate()
        window.delegate = delegate
        // Last, so the frame above is only ever the *first-run* placement: with a stored frame this
        // moves the window to wherever the user left it.
        window.setFrameAutosaveName(frameAutosaveName)
        window.makeKeyAndOrderFront(nil)
        // A regular app with a Dock icon: the window has to come with the app in front of it, or the
        // keystrokes the user is about to type go to whatever they were in.
        NSApp.activate(ignoringOtherApps: true)
        ContextLog.info("main window presented (key: \(window.isKeyWindow))", "search")
        // Once the window is genuinely on screen. Anything listening for this — the tutorial's search
        // beat — is being told a fact about the display, so it is announced after the display has it
        // and not before.
        SearchPanelWatch.report(.opened)
    }

    /// **Activating a result: open the timeline there.**
    ///
    /// The one place a found moment becomes a window operation. `capturedAt` is the instant for both
    /// kinds of result — a screen hit carries its frame's capture time, a conversation hit carries
    /// the moment the line was spoken — so a single call covers both and neither kind can drift into
    /// a different meaning of "when".
    ///
    /// **It used to close this surface afterwards, and that was a property of the panel.** A floating
    /// slab sitting over the timeline covers the exact thing the user just asked to see, so it got
    /// out of the way — at the cost of the query, the results and the selection, which the next open
    /// rebuilt from nothing. A main window has no such problem and no such excuse: the timeline
    /// arrives in front, this window stays where it is, and the page of results the user was reading
    /// is still there when they come back to it.
    ///
    /// The announcement is still last, so an observer sees "a result was activated" after the window
    /// operation it describes rather than before it.
    ///
    /// Declining when the store is not open yet is the same rule the menu bar and the global
    /// shortcut already follow: a timeline over nothing is worse than no timeline.
    private static func open(_ moment: SearchMoment) {
        // `frame != nil` and not `kind == .screen`: what the fact is about is whether there is a
        // picture of that instant to travel back to, and a screen whose file retention already
        // unlinked has no more of one than a spoken line does.
        travel(to: moment.capturedAt, hasPicture: moment.frame != nil)
    }

    /// Sends the timeline to an instant, from whichever body named it.
    ///
    /// One path for both bodies: a result card and an activity tile are asking for the same thing,
    /// and two copies of this is how one of them ends up not reporting the trip, or opening a second
    /// timeline that cannot reach Settings.
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
        SearchPanelWatch.report(.openedMoment(at: instant, hasPicture: hasPicture))
    }

    /// `userInfo` key carrying a prefill through `refocusNotification`.
    static let prefillKey = "prefill"

    private static var delegate: SearchWindowDelegate?

    /// Fires when the window is presented or becomes key, so the field takes the keyboard and selects
    /// whatever is already typed.
    static let refocusNotification = Notification.Name("context.search.refocus")

    static var isVisible: Bool { current?.isVisible ?? false }

    /// **Where the window opens on a machine that has never moved it.** Upper third, horizontally
    /// centred — a prompt bar belongs where the eye already is, not at the optical centre of the
    /// display.
    ///
    /// A first-run default and nothing more: `setFrameAutosaveName` overwrites it with the user's own
    /// frame from the second launch onwards.
    ///
    /// Clamped to the screen, because the default size is taller than a 13" display's visible frame
    /// leaves room for at the naive upper-third placement.
    static func defaultFrame(on screen: NSScreen) -> NSRect {
        defaultFrame(in: screen.visibleFrame)
    }

    /// The same placement as a pure function of a visible rectangle, so the tutorial's coach mark can
    /// be tested against the window's real geometry on a display the test machine does not have.
    static func defaultFrame(in visible: NSRect) -> NSRect {
        let size = SearchLayout.defaultWindowSize
        let width = min(size.width, visible.width)
        let height = min(size.height, visible.height)
        let x = visible.midX - width / 2
        let y = max(visible.minY, visible.maxY - height - visible.height * 0.10)
        return NSRect(x: x.rounded(), y: y.rounded(), width: width, height: height)
    }
}

// MARK: - What the real search surface just did

/// One thing that really happened on the real search surface.
///
/// Every case is a fact about the *shipped* window — that it was asked for, the read that finished,
/// the card somebody pressed — and nothing here can be produced by asking. That is the whole reason
/// it exists: the tutorial's search beats used to draw their own field and their own grid of results
/// on a coach card, teaching a surface that does not exist. They watch these events instead, so what
/// the user learns to press is the real pill and what answers them is the real window.
///
/// The timeline used to listen too, and stood aside on `.opened`. That was right while search was a
/// borderless slab that landed over it; it is gone with the panel.
enum SearchPanelEvent: Equatable, Sendable {
    /// **The window was asked for**, and is now front and focused. Sent on a fresh open *and* on a
    /// press that brought an already-open window forward.
    ///
    /// The distinction matters more than it used to. The window is persistent, so "it is on screen"
    /// is very nearly always true and says nothing about the user — what this reports is the *ask*,
    /// which is the fact the tutorial's pill beat is gated on.
    case opened
    /// The window is gone — closed by the user, since nothing in the app closes it. Sent from the
    /// window's own `windowWillClose`, which is the only place that sees the red button.
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

// MARK: - The window's own two facts

/// The two things the main window has to say about itself, and nobody else can.
///
/// A delegate rather than notification observers because both are facts about *this* window, and
/// because the close is one only AppKit knows about: the red button is not a code path this app owns.
/// It used to be — the panel had a `dismiss()` that every route went through, which is what let the
/// announcement be made by hand. A window the user closes with the mouse would have gone away in
/// silence, leaving the tutorial's query beat coaching a field that is no longer on screen.
@MainActor
private final class SearchWindowDelegate: NSObject, NSWindowDelegate {

    /// **The field takes the keyboard back whenever the window becomes key.** A window the user
    /// clicked back into, ⌘-Tabbed to, or brought forward from the Dock is a window they want to type
    /// in — this surface's whole content is one text field and a page of results that field drives.
    /// `refocusNotification` is the one signal for it, so `present` and this cannot disagree about
    /// what "the window is ready to be typed in" means.
    func windowDidBecomeKey(_ notification: Notification) {
        NotificationCenter.default.post(name: SearchBarWindow.refocusNotification, object: nil)
    }

    /// **The window is going away, whoever closed it.** `isReleasedWhenClosed` is false, so what
    /// closing costs is only the window being on screen: the instance, the query, the results and the
    /// selection all survive, and the next `present()` is the same window with the same page in it.
    func windowWillClose(_ notification: Notification) {
        SearchPanelWatch.report(.closed)
    }
}

// MARK: - What is not here any more
//
// **The `NSWindow` subclass.** A borderless panel refuses key status by default and had to override
// `canBecomeKey`; a titled window takes it, and main status with it, without being asked.
//
// **The window-level Escape swallow.** `sendEvent` intercepted keyCode 53 and closed the surface,
// because a non-activating panel in an app that was never activated does not route key events
// through `NSApplication`'s dispatch, and the field's own `cancelOperation:` therefore only fired
// while the field editor held focus. On a main window that override is a liability rather than a
// belt: it would eat Escape from every field, popover and date picker inside the window — including
// the filter block's own `DatePicker`. The field editor's `cancelOperation:` path survives in
// `SearchBarView`, pointed at *clearing the query*, which is what Escape means in a search field
// that is not a dismissable overlay.
//
// **The first-mouse views.** `acceptsFirstMouse` existed because an `.accessory` app is never
// frontmost when a summoned panel appears, so AppKit spent the first click activating. This app ships
// with a Dock icon and `present` activates it, so an ordinary window's ordinary first click is the
// click the user meant.
