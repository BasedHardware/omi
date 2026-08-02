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

        let popover = NSPopover()
        popover.behavior = .transient
        popover.contentSize = NSSize(width: 320, height: 380)
        popover.contentViewController = NSHostingController(rootView: StatusView())
        // Deliberately no `appearance` override, here or process-wide. This popover is a system
        // surface, so it follows the system: forcing light meant dark-mode users got a white sheet
        // among their dark menu bar extras, and the vibrancy behind it had nothing to blend with.
        self.popover = popover

        // The icon answers "is it listening?" without a click, so it has to follow the engine
        // rather than be set once at launch.
        Engine.shared.$isCapturing
            .removeDuplicates()
            .sink { [weak self] capturing in
                self?.item?.button?.image = capturing ? ContextMark.menuBar : ContextMark.menuBarPaused
            }
            .store(in: &cancellables)
    }

    @objc private func toggle() {
        guard let popover, let button = item?.button else { return }
        if popover.isShown {
            popover.performClose(nil)
        } else {
            popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
            // An `.accessory` app's popover opens behind the active app's windows otherwise.
            NSApp.activate(ignoringOtherApps: true)
        }
    }
}
