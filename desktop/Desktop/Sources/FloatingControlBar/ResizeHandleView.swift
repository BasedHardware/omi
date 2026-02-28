import SwiftUI
import AppKit

// MARK: - Resize Handle NSViewRepresentable

/// NSViewRepresentable that adds a bottom-right corner resize handle.
/// Always active — not gated by the draggableBarEnabled toggle.
struct ResizeHandleView: NSViewRepresentable {
    weak var targetWindow: NSWindow?

    func makeNSView(context: Context) -> ResizeHandleNSView {
        let view = ResizeHandleNSView()
        view.targetWindow = targetWindow
        return view
    }

    func updateNSView(_ nsView: ResizeHandleNSView, context: Context) {
        nsView.targetWindow = targetWindow
    }
}

class ResizeHandleNSView: NSView {
    weak var targetWindow: NSWindow?
    private var initialMouseLocation: NSPoint = .zero
    private var initialWindowFrame: NSRect = .zero

    override func resetCursorRects() {
        addCursorRect(bounds, cursor: .crosshair)
    }

    override func mouseDown(with event: NSEvent) {
        initialMouseLocation = NSEvent.mouseLocation
        initialWindowFrame = targetWindow?.frame ?? .zero
        (targetWindow as? FloatingControlBarWindow)?.isUserResizing = true
    }

    override func mouseUp(with event: NSEvent) {
        (targetWindow as? FloatingControlBarWindow)?.isUserResizing = false
    }

    override func mouseDragged(with event: NSEvent) {
        guard let window = targetWindow else { return }
        let current = NSEvent.mouseLocation
        let deltaX = current.x - initialMouseLocation.x
        let deltaY = current.y - initialMouseLocation.y

        // Anchor top-left: keep frame.maxY fixed, expand right and down.
        let minW: CGFloat = 430
        let minH: CGFloat = 250
        let newWidth  = max(minW, initialWindowFrame.width  + deltaX)
        let newHeight = max(minH, initialWindowFrame.height - deltaY) // screen-y up = drag down = height grows

        let newOriginY = initialWindowFrame.maxY - newHeight
        window.setFrame(
            NSRect(x: initialWindowFrame.minX, y: newOriginY, width: newWidth, height: newHeight),
            display: true
        )
    }

    override var acceptsFirstResponder: Bool { false }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}

// MARK: - Resize Grip Visual

/// Three staggered diagonal dots — standard macOS resize-grip indicator.
struct ResizeGripShape: View {
    var body: some View {
        Canvas { context, size in
            let r: CGFloat = 1.5
            let positions: [(CGFloat, CGFloat)] = [
                (size.width - r * 2, r * 2),
                (size.width - r * 2 - 4, r * 2 + 4),
                (size.width - r * 2 - 8, r * 2 + 8),
            ]
            for (cx, cy) in positions {
                let rect = CGRect(x: cx - r, y: cy - r, width: r * 2, height: r * 2)
                context.fill(Path(ellipseIn: rect), with: .foreground)
            }
        }
    }
}
