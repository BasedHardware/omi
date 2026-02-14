import Cocoa
import SwiftUI

// MARK: - Notification Names

extension Notification.Name {
    static let floatingBarDragDidStart = Notification.Name("floatingBarDragDidStart")
    static let floatingBarDragDidEnd = Notification.Name("floatingBarDragDidEnd")
}

// MARK: - Draggable Area View

/// NSViewRepresentable that enables window dragging from within SwiftUI.
struct DraggableAreaView: NSViewRepresentable {
    let targetWindow: NSWindow?

    func makeNSView(context: Context) -> NSView {
        let view = DraggableNSView()
        view.targetWindow = targetWindow
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {}

    class DraggableNSView: NSView {
        weak var targetWindow: NSWindow?
        private var initialLocation: NSPoint?

        override func mouseDown(with event: NSEvent) {
            initialLocation = event.locationInWindow
            NotificationCenter.default.post(name: .floatingBarDragDidStart, object: nil)
        }

        override func mouseUp(with event: NSEvent) {
            super.mouseUp(with: event)
            NotificationCenter.default.post(name: .floatingBarDragDidEnd, object: nil)
            initialLocation = nil
        }

        override func mouseDragged(with event: NSEvent) {
            guard let targetWindow = targetWindow, let initialLocation = initialLocation else {
                return
            }

            let currentLocation = event.locationInWindow
            let newOrigin = NSPoint(
                x: targetWindow.frame.origin.x + (currentLocation.x - initialLocation.x),
                y: targetWindow.frame.origin.y + (currentLocation.y - initialLocation.y)
            )

            NSAnimationContext.beginGrouping()
            NSAnimationContext.current.duration = 0
            targetWindow.setFrameOrigin(newOrigin)
            NSAnimationContext.endGrouping()
        }
    }
}
