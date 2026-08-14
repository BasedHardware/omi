import AppKit
import SwiftUI

/// Which way a coach mark's arrow points, and how far along the card's edge it sits.
struct TutorialArrow: Equatable {
    enum Edge { case top, bottom }
    let edge: Edge
    /// Horizontal offset from the card's centre, in points, after clamping. The arrow tracks the
    /// target even when the card had to be pushed sideways to stay on screen.
    let offset: CGFloat
}

/// Presentation state the card needs but the step machine has no business owning.
@MainActor
final class TutorialOverlayChrome: ObservableObject {
    @Published var arrow: TutorialArrow?
    /// True while the card is showing over another app's window, where it has to read as an overlay
    /// rather than as a document.
    @Published var isCoachMark = false
}

/// The tutorial's one window: a small card that is positioned, not centred.
///
/// Deliberately *not* a full-screen overlay. A transparent window covering the display would swallow
/// the scroll and the clicks the tutorial is asking for — the user cannot "scroll around on this
/// page" through a sheet of glass — so the window is only ever as big as the card, and everything
/// outside it belongs to whatever is underneath.
@MainActor
final class TutorialOverlay {
    static let shared = TutorialOverlay()

    /// One width for every step. Coach marks and cards are the same object as far as the user is
    /// concerned, and a width that changed between steps made the card jump sideways mid-flow.
    ///
    /// 470 rather than the 420 it was: the mark now stands beside the copy and takes a fixed 56 pt
    /// out of every line, so the same headline role has ~50 pt less to work with. Measured by
    /// rendering every card in the flow at both widths rather than guessed at.
    static let width: CGFloat = 470

    /// Gap between a card and the thing it points at, big enough that the arrow reads as an arrow.
    private static let gap: CGFloat = 14

    private var window: TutorialOverlayWindow?
    private var hosting: NSHostingView<TutorialCardView>?
    private let chrome = TutorialOverlayChrome()
    private weak var model: TutorialModel?
    /// The display this step chose, so a centred card does not chase the pointer from one screen to
    /// the other every second. Re-decided per step, never per tick.
    private var stepScreen: NSScreen?

    var isVisible: Bool { window?.isVisible ?? false }

    /// **The machine the card on screen is really driving**, read off the hosting view rather than
    /// off the reference this type keeps beside it.
    ///
    /// The two can disagree, and the whole rebinding rule in `show` is about the one way they can: a
    /// second run replaces `model` while the card keeps rendering the first. Only a reader that goes
    /// through the root view can tell, which is why this exists — `TutorialResumeTests` asserts it,
    /// and there is nothing else in the product a source-level check could look at.
    var machineOnScreen: TutorialModel? { hosting?.rootView.model }

    /// Shows (or re-lays-out) the card for `step`.
    func show(model: TutorialModel, step: TutorialStep) {
        guard !step.isTerminal else { return hide() }
        // **The window outlives a run; the card's binding must not.** The window and its hosting view
        // are built once and kept, and the card inside is bound to whichever `TutorialModel` built
        // it — so a second run would go on rendering, and go on driving, the machine that already
        // finished: an empty card whose buttons answer nothing. That is no longer hypothetical:
        // a resumed walkthrough (`TutorialResume`) is a second `TutorialModel` in the same process,
        // and it is the change that makes this reachable.
        let isANewMachine = self.model !== model
        self.model = model
        chrome.isCoachMark = step.target != nil
        stepScreen = nil

        // Rebound only on a window that was already standing. A window built here builds its hosting
        // view around *this* model, and replacing that root view immediately would cost the first
        // card of every run a layout pass: `fittingSize` answers zero for one pass after a root view
        // is replaced (see `fittingHeight`), so the card would be pinned to its 96 pt floor until the
        // next tick moved it.
        let window: TutorialOverlayWindow
        if let standing = self.window {
            window = standing
            if isANewMachine { hosting?.rootView = TutorialCardView(model: model, chrome: chrome) }
        } else {
            window = makeWindow(for: model)
        }
        self.window = window
        // Rebound on every step, for the same reason the card's root view is: a resumed run is a
        // second `TutorialModel` in this process, and an Escape route captured once would end the
        // walkthrough that already finished.
        window.onEscape = { [weak model] in model?.skip() }

        layout(step: step)

        // A card is a thing to press, so it takes key status and activates: this app is an accessory
        // and is almost never frontmost, and a SwiftUI button in an inactive window spends the user's
        // first click on activation even with `acceptsFirstMouse` — measured on a live walkthrough,
        // where "Start" had to be pressed twice and still did nothing.
        //
        // A coach mark does not, because the user is being asked to work in another window and taking
        // focus off the browser mid-scroll would be taking the lesson away from them. Neither does
        // the beat waiting on Claude, whose next keystroke belongs to somebody else's composer —
        // the rule is `TutorialStep.takesFocusOnEntry`, where it can be read and asserted.
        if step.takesFocusOnEntry {
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
        } else {
            window.orderFrontRegardless()
        }
    }

    /// Re-runs placement for the current step. Called on every poll tick, so a window the user moved
    /// takes its coach mark with it.
    ///
    /// Re-orders as well as re-positions. A coach mark that another floating window has buried is not
    /// a coach mark — and this app shares the floating level with anything else the user happens to
    /// run. Ordering front is not activating: it never takes focus away from what they are doing.
    func reposition() {
        guard let model, !model.step.isTerminal, let window else { return }
        layout(step: model.step)
        // Ordered front whether or not it was visible. An overlay that has been hidden — by another
        // app, by a Space change, by anything at all — must come back on its own while a step is still
        // running; the earlier version bailed out when it was invisible, which made "hidden once" mean
        // "hidden for the rest of the tutorial".
        window.orderFrontRegardless()
    }

    func hide() {
        window?.orderOut(nil)
        chrome.arrow = nil
    }

    // MARK: - Construction

    private func makeWindow(for model: TutorialModel) -> TutorialOverlayWindow {
        let window = TutorialOverlayWindow(
            contentRect: NSRect(x: 0, y: 0, width: Self.width, height: 200),
            styleMask: [.borderless],
            backing: .buffered,
            defer: false)
        window.isOpaque = false
        window.backgroundColor = .clear
        // The card draws its own shadow in SwiftUI; a window shadow would trace the transparent
        // rectangle around it.
        window.hasShadow = false
        window.level = .floating
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
        window.hidesOnDeactivate = false
        window.isReleasedWhenClosed = false
        window.isMovableByWindowBackground = false

        // A plain container holds the hosting view. Making an `NSHostingView` the `contentView` of a
        // borderless window re-enters AppKit's window-sizing negotiation and crashes on macOS 26 —
        // the same reason `RewindWindow` wraps its own.
        let container = TutorialFirstMouseView(
            frame: NSRect(origin: .zero, size: window.frame.size))
        container.autoresizingMask = [.width, .height]
        window.contentView = container

        // Autoresizing rather than constraints, and `.intrinsicContentSize` rather than min/max: the
        // window is sized *from* the card, so the card must never be sized from the window.
        //
        // The first version of this did the opposite — SwiftUI measured itself through a
        // `GeometryReader` and handed the size back to resize the window, while the hosting view was
        // pinned to all four edges of the container. That is a feedback loop: the new window height
        // squeezes the content, the squeezed content measures shorter, the window shrinks again. On a
        // live walkthrough the card collapsed to 54 pt with its footer wrapped into three lines and
        // then stopped drawing altogether. Reading `fittingSize` closes the loop: it is the card's
        // *ideal* height at a fixed width, and nothing about the window feeds into it.
        let hosting = TutorialFirstMouseHostingView(
            rootView: TutorialCardView(model: model, chrome: chrome))
        hosting.sizingOptions = [.intrinsicContentSize]
        hosting.translatesAutoresizingMaskIntoConstraints = true
        hosting.frame = NSRect(x: 0, y: 0, width: Self.width, height: 200)
        hosting.autoresizingMask = [.width, .height]
        container.addSubview(hosting)
        self.hosting = hosting
        return window
    }

    /// The card's ideal height at `Self.width`, straight from the hosting view.
    ///
    /// Recomputed on every tick as well as on every step, because the content genuinely changes
    /// height while a step is on screen: a result list appears, an error line wraps, a thumbnail
    /// loads.
    private func fittingHeight() -> CGFloat {
        guard let hosting else { return 200 }
        hosting.layoutSubtreeIfNeeded()
        let ideal = hosting.fittingSize.height
        // A floor rather than a trust: `fittingSize` answers zero for one pass after the root view is
        // replaced, and a zero-height window is a window the user cannot see or click.
        return max(96, ideal.rounded(.up))
    }

    // MARK: - Placement

    private func layout(step: TutorialStep) {
        guard let window, let model else { return }
        let size = NSSize(width: Self.width, height: fittingHeight())

        let target = model.targetFrame
        // Claude's window is not a coach-mark target — nothing points at it — but it is the thing
        // the card has to stand clear of, and it decides which display this card belongs on just as
        // firmly as a target would. `claudeFrame` is nil on every step that is not one of the two.
        let claude = model.claudeFrame
        let screen = screenFor(target ?? claude)
        var frame = NSRect(origin: .zero, size: size)
        var arrow: TutorialArrow?

        switch (step.target, target) {
        case (.timelineTrack, .some(let rect)):
            // Above the track, pointing down at it.
            frame.origin = CGPoint(x: rect.midX - size.width / 2, y: rect.maxY + Self.gap)
            arrow = TutorialArrow(edge: .bottom, offset: 0)

        case (.searchAllButton, .some(let rect)):
            // Below the pill, pointing up at it.
            frame.origin = CGPoint(
                x: rect.midX - size.width / 2, y: rect.minY - Self.gap - size.height)
            arrow = TutorialArrow(edge: .top, offset: 0)

        case (.timelineWindow, .some(let rect)):
            frame.origin = CGPoint(x: rect.midX - size.width / 2, y: rect.midY - size.height / 2)

        case (.searchPanel, .some(let rect)):
            frame = Self.under(size, panel: rect, in: screen.visibleFrame, margin: Self.gap)
            arrow = TutorialArrow(edge: .top, offset: 0)

        default:
            // No target, or a target that could not be located: the step says where it would rather
            // be, and there is no arrow either way.
            let visible = screen.visibleFrame
            switch step.placement {
            case .centred:
                frame.origin = CGPoint(
                    x: visible.midX - size.width / 2,
                    y: visible.midY - size.height / 2 + visible.height * 0.04)
            case .outOfTheWay:
                // The capture beat opens a page and asks the user to scroll it. A card in the middle
                // of the screen would be sitting on the very thing it just told them to read, so it
                // stands down into the corner and waits.
                frame.origin = CGPoint(
                    x: visible.maxX - size.width - Self.gap * 2,
                    y: visible.minY + Self.gap * 2)
            case .clearOfClaude:
                frame = Self.parked(
                    size, in: visible, clearOf: claude, margin: Self.gap * 2)
            }
        }

        let clamped = clamp(frame, into: screen.visibleFrame)
        if let existing = arrow, let rect = target {
            // The arrow follows the target after clamping, so a card pushed sideways still points at
            // the right thing — up to the point where it would fall off the card's own edge, where
            // pointing at nothing in particular is better than pointing off-card.
            let limit = max(0, size.width / 2 - 26)
            let offset = min(max(rect.midX - clamped.midX, -limit), limit)
            arrow = TutorialArrow(edge: existing.edge, offset: offset)
        }
        chrome.arrow = arrow

        // Nothing after this line may feed back into `fittingHeight()`: the card is measured at a
        // fixed width, so resizing the window cannot change what it measured.
        guard window.frame != clamped else { return }
        window.setFrame(clamped, display: true)
        window.contentView?.frame = NSRect(origin: .zero, size: clamped.size)
        hosting?.frame = NSRect(origin: .zero, size: clamped.size)
    }

    /// **A card parked beside another application's window, never on the middle of it.**
    ///
    /// Pure, and separated from `NSScreen`, for the same reason `OnboardingWindow.placement` is: the
    /// failure it prevents depends entirely on geometry the machine it was written on does not have.
    /// `TutorialTests` sweeps it; nothing here can be checked by looking at one screen.
    ///
    /// The defect it fixes was reported in one sentence — *when it opens the Claude window, the flow
    /// window blocks the view* — and the two obvious repairs are both wrong. Lowering the card's
    /// level leaves it exactly where it was, invisible under Claude and still swallowing the clicks
    /// aimed at it. Hiding it takes away the coaching the user still needs, on the one beat where
    /// they are being asked to do something in an app they have never used this way. The card has to
    /// be *somewhere else*, and somewhere else has to be computed from where Claude actually is.
    ///
    /// The order of preference, and why:
    ///
    /// 1. **Beside it**, in whichever band has the room — the widest of the two, so a Claude nudged
    ///    to one side of a big display puts the card on the open side rather than in the sliver.
    /// 2. **Above, then below.** A window that spans the width still usually leaves a band, and the
    ///    top one is preferred because Claude's composer — the thing the user has to type Return
    ///    into — is at the foot of its window.
    /// 3. **The top trailing corner**, when the window covers the usable area outright. Nothing is
    ///    genuinely clear at that point, and this is the least-wrong overlap for the same reason: it
    ///    is off the column the answer streams down and well away from the composer.
    ///
    /// `occluder` nil means Claude could not be found — not running yet, no window on screen, a
    /// display unplugged. Then the card takes the trailing edge, which is the part of a display least
    /// likely to hold the window an app just opened, and never the centre, which is the part most
    /// likely to.
    ///
    /// `margin` is passed rather than read from `Self.gap` because this is `nonisolated` — the whole
    /// point is that it can be swept off the main actor — and a `@MainActor` type's own statics are
    /// not reachable from there.
    nonisolated static func parked(
        _ size: NSSize, in visible: NSRect, clearOf occluder: CGRect?, margin: CGFloat
    ) -> NSRect {
        let middle = visible.midY - size.height / 2
        let trailingEdge = visible.maxX - size.width - margin

        guard let occluder, !occluder.isEmpty, occluder.intersects(visible) else {
            return NSRect(x: trailingEdge, y: middle, width: size.width, height: size.height)
        }

        let leading = occluder.minX - visible.minX
        let trailing = visible.maxX - occluder.maxX
        if max(leading, trailing) >= size.width + margin {
            // Centred in its band rather than jammed against the screen edge: the card reads as
            // standing beside the window, which is what it is doing.
            let x =
                trailing >= leading
                ? occluder.maxX + (trailing - size.width) / 2
                : visible.minX + (leading - size.width) / 2
            return NSRect(x: x, y: middle, width: size.width, height: size.height)
        }

        // Horizontally over the window's own centre for the bands above and below it — the card is
        // beside the *conversation* either way, and lining it up with the window it is talking about
        // is easier to connect than a card in an unrelated corner.
        let centred = min(
            max(occluder.midX - size.width / 2, visible.minX + margin),
            max(visible.minX + margin, trailingEdge))
        if visible.maxY - occluder.maxY >= size.height + margin {
            return NSRect(
                x: centred, y: visible.maxY - size.height - margin,
                width: size.width, height: size.height)
        }
        if occluder.minY - visible.minY >= size.height + margin {
            return NSRect(
                x: centred, y: visible.minY + margin, width: size.width, height: size.height)
        }
        return NSRect(
            x: trailingEdge, y: visible.maxY - size.height - margin,
            width: size.width, height: size.height)
    }

    /// **A card coaching the real search panel: under its foot, never across its face.**
    ///
    /// Pure, and separated from `NSScreen`, for the same reason `parked` is — the failure it guards
    /// against is a fact about a display geometry the machine this was written on does not have.
    ///
    /// The panel is not an occluder to be stood beside; its window is 1112 pt wide and the side bands
    /// on a laptop are 179 pt, which is far narrower than this card. So there is only one axis to
    /// work with,
    /// and only one end of it: the panel's **top** edge is the prompt bar — the field the beat is
    /// asking somebody to type into, and the one part of the surface a card may never be laid over.
    /// Its bottom edge is the last row of a grid that scrolls. The card goes under the bottom.
    ///
    /// **`panel` is the panel's own frame, never a rectangle assembled here.** The search surface
    /// sizes itself to its content, so a shape rebuilt out of `SearchLayout` constants is a guess
    /// that goes wrong the moment a row lands — the production caller reads
    /// `SearchBarWindow.panelFrame` through `TutorialTargetLocator`, and the test that exercises this
    /// asks `SearchBarWindow` for its own placement rather than doing the arithmetic itself.
    ///
    /// **Where it stops being possible, and what happens then.** At the tallest the panel is allowed
    /// to be it leaves about 140 pt under it on a 13" display, and this card is taller than that.
    /// There is no placement that both fits and clears — so it takes the bottom of the screen and
    /// overlaps the panel's foot, which costs the user part of the last visible row of results and
    /// costs them nothing they are being asked to touch. The one invariant that survives every
    /// geometry is the one worth stating: **the card's top edge never rises above the panel's
    /// midpoint**, so the field, the query chip and the `↵ Ask Claude` affordance are never
    /// underneath it.
    nonisolated static func under(
        _ size: NSSize, panel: CGRect, in visible: NSRect, margin: CGFloat
    ) -> NSRect {
        let x = min(
            max(panel.midX - size.width / 2, visible.minX + 8),
            max(visible.minX + 8, visible.maxX - size.width - 8))
        let wanted = panel.minY - margin - size.height
        return NSRect(
            x: x.rounded(), y: max(visible.minY + 8, wanted).rounded(),
            width: size.width, height: size.height)
    }

    private func clamp(_ frame: NSRect, into bounds: NSRect) -> NSRect {
        var result = frame
        result.origin.x = min(max(frame.origin.x, bounds.minX + 8), bounds.maxX - frame.width - 8)
        result.origin.y = min(max(frame.origin.y, bounds.minY + 8), bounds.maxY - frame.height - 8)
        return result
    }

    /// The screen the target is on, falling back to the pointer's screen — never `NSScreen.main`,
    /// which on a menu-bar-only app is routinely the display the user is not looking at.
    private func screenFor(_ target: CGRect?) -> NSScreen {
        if let target, let screen = NSScreen.screens.first(where: { $0.frame.intersects(target) }) {
            stepScreen = screen
            return screen
        }
        // Decided once per step. Asking the pointer every tick made a centred card hop between
        // displays as the mouse moved, which is the opposite of something to read.
        if let stepScreen { return stepScreen }
        let pointer = NSEvent.mouseLocation
        let chosen = NSScreen.screens.first(where: { NSMouseInRect(pointer, $0.frame, false) })
            ?? NSScreen.screens.first
            ?? NSScreen.main!
        stepScreen = chosen
        return chosen
    }
}

// MARK: - Window and views

/// Borderless windows refuse key status by default, and this one has buttons to press.
///
/// Module-internal rather than file-private only so `TutorialTests` can press Escape on a real one:
/// the Escape route below is the only way off this card without a pointer, and a rule about the one
/// way out is a rule that has to be executed rather than read.
final class TutorialOverlayWindow: NSWindow {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }

    /// **Escape ends the walkthrough**, the same thing the `Skip` control does.
    ///
    /// It closes a real dead end. This card is borderless, so `performClose:` and ⌘W do nothing to
    /// it; nothing in `Tutorial/` carried a `keyboardShortcut`; and `Skip` was reachable by pointer
    /// only. The onboarding cinematic immediately before it *does* take Escape
    /// (`OnboardingWindow`), so the user is taught the key and then it silently stops working on a
    /// floating card sitting on top of everything they own.
    ///
    /// **In `sendEvent`, and that is the whole of its scope.** A window only receives key events
    /// while it is key, which is exactly the steps whose card is the thing being interacted with
    /// (`TutorialStep.takesFocusOnEntry`). On a coach-mark step the overlay deliberately never takes
    /// focus — the user is working in somebody else's window — and Escape there belongs to that
    /// window, not to this one. A process-wide monitor would take it from them, which is the defect
    /// this fix must not trade for.
    /// What Escape runs. Handed in by the controller rather than reached for through the view tree:
    /// the card is rebound to a new `TutorialModel` on a resumed run, and a window holding its own
    /// reference to the first one would end the walkthrough that already finished.
    var onEscape: (() -> Void)?

    override func sendEvent(_ event: NSEvent) {
        if event.type == .keyDown, event.keyCode == Self.escapeKeyCode, let onEscape {
            MainActor.assumeIsolated { onEscape() }
            return
        }
        super.sendEvent(event)
    }

    /// Named rather than `53` at the point of use, like every other reading of this key in the
    /// package.
    private static let escapeKeyCode: UInt16 = 53
}

// An accessory app is never the active application when a coach mark appears, and AppKit spends the
// first click activating the window instead of delivering it. Without these two overrides every
// card's first button press is swallowed.
private final class TutorialFirstMouseView: NSView {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}

private final class TutorialFirstMouseHostingView<Content: View>: NSHostingView<Content> {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}
