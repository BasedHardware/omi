import ContextCore
import AppKit
import Combine
import SwiftUI

/// Owns the menu bar item and the popover behind it.
///
/// Hand-built on `NSStatusItem` rather than SwiftUI's `MenuBarExtra` for one reason: `MenuBarExtra`
/// will not tell you where its button is. Onboarding ends by saying "I live up here", and without a
/// frame that sentence points at a strip of thirty near-identical glyphs. `NSStatusItem.button`
/// has a real window, so the frame is exact, needs no permissions, and stays correct however full
/// the menu bar is.
@MainActor
final class StatusItemController: NSObject {
    static let shared = StatusItemController()

    private var item: NSStatusItem?
    private var popover: NSPopover?
    private var cancellables: Set<AnyCancellable> = []

    /// The icon's frame in global, top-left-origin coordinates — the space `CGWarpMouseCursorPosition`
    /// and the spotlight overlay both work in. Nil before the item exists.
    var iconFrame: CGRect? {
        guard let button = item?.button, let window = button.window else { return nil }
        let inScreen = window.convertToScreen(button.convert(button.bounds, to: nil))
        guard let primary = NSScreen.screens.first else { return nil }
        // AppKit is bottom-left off the primary screen; CoreGraphics is top-left.
        return CGRect(
            x: inScreen.origin.x,
            y: primary.frame.maxY - inScreen.origin.y - inScreen.height,
            width: inScreen.width,
            height: inScreen.height
        )
    }

    func install() {
        guard item == nil else { return }

        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.image = ContextMark.menuBar
        item.button?.imagePosition = .imageOnly
        item.button?.target = self
        item.button?.action = #selector(toggle)
        item.button?.toolTip = "Context for Claude"
        self.item = item

        self.popover = Self.makePopover()

        // The icon answers "is it listening?" without a click, so it has to follow the engine
        // rather than be set once at launch — and it follows `health` rather than a boolean, because
        // two glyphs over one boolean drew a recorder whose screen half had been dead since the
        // previous afternoon exactly like a healthy one.
        Engine.shared.$health
            .removeDuplicates()
            .sink { [weak self] health in
                self?.item?.button?.image = Self.mark(for: health)
                self?.item?.button?.toolTip = Self.tooltip(for: health)
            }
            .store(in: &cancellables)
    }

    /// The popover, built the way it ships.
    ///
    /// A factory rather than six lines inside `install()`, because its height is the thing that broke
    /// and nothing outside this file could see it: a test can build this and measure it, and cannot
    /// install a status item.
    ///
    /// **The height belongs to the content, and must not be pinned again.** This was `320 × 380` over
    /// a `StatusView` that measures 384 pt in the plainest state and past 470 pt in the reported one —
    /// both Claude surfaces named in one sentence that wraps to two lines, the account line under it,
    /// and an upload error under that. SwiftUI answers an under-proposed `VStack` by shrinking the
    /// children that can shrink, and every line in the connection/account block is
    /// `.fixedSize(horizontal: false, vertical: true)` exactly so that it will not — so those three
    /// sentences were laid out on top of one another and the block was unreadable. Nothing clipped,
    /// nothing logged, and it had to be reported from a screenshot.
    ///
    /// `.preferredContentSize` is the size `NSPopover` reads, and it is the only sizing option that
    /// also grows the panel *while it is open*, which is when this block changes:
    /// `ConversationUploader` publishes its backlog and its errors into a popover the user is already
    /// looking at. The width stays `StatusView.popoverWidth`, applied by the view itself; nothing here
    /// needs to know it.
    static func makePopover() -> NSPopover {
        let popover = NSPopover()
        popover.behavior = .transient
        let content = NSHostingController(rootView: StatusView())
        content.sizingOptions = [.preferredContentSize]
        popover.contentViewController = content
        // Pinned light, like every other surface this app draws.
        //
        // This reverses an earlier decision, and the reason is worth keeping: the popover used to
        // follow the system on the argument that it is a system surface sitting beside other menu
        // bar extras. That argument loses to a stronger one — the popover is *this app's* panel, and
        // when the onboarding card, the timeline, settings and the coach marks are all light frosted
        // glass, a popover that is near-black on a Dark machine is the one surface that does not look
        // like the product. `.appearance` on the popover reaches its content view controller, so the
        // vibrancy behind it and `Ink`'s dynamic colours resolve in the same appearance the rest of
        // the app's glass does — which is also what keeps the label ladder's contrast measurements
        // true here.
        popover.appearance = InkGlass.appearance
        return popover
    }

    /// The glyph for each health state. A pure function so the mapping is assertable without a menu
    /// bar — there is no way to read an `NSStatusItem`'s image back in a test target that never
    /// installs one.
    static func mark(for health: CaptureHealth) -> NSImage {
        switch health {
        case .capturing: return ContextMark.menuBar
        case .degraded: return ContextMark.menuBarDegraded
        case .off: return ContextMark.menuBarPaused
        }
    }

    static func tooltip(for health: CaptureHealth) -> String {
        switch health {
        case .capturing: return "Context for Claude — capturing"
        case .degraded: return "Context for Claude — part of capture has stopped. Click for details."
        case .off: return "Context for Claude — not capturing"
        }
    }

    @objc private func toggle() {
        guard let popover, let button = item?.button else { return }
        if popover.isShown {
            popover.performClose(nil)
        } else {
            // Only on the opening half. Counting the close too would double every visit and make
            // "how many people open the menu bar item" read as twice the truth.
            ContextAnalytics.record(.surfaceOpened(.menuBar))
            popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
            // An `.accessory` app's popover opens behind the active app's windows otherwise.
            NSApp.activate(ignoringOtherApps: true)
        }
    }
}
