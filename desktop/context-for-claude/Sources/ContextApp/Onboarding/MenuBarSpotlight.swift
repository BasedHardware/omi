import AppKit

/// Points at the menu bar icon when onboarding says "I live up here".
///
/// Telling someone where an app lives is not the same as showing them. A menu bar is a crowded
/// strip of near-identical glyphs, and "up here" resolves to about thirty candidates — so this
/// finds the real status item, draws a ring around it, and walks the cursor there slowly enough to
/// be followed. The user ends up with their pointer on the thing, which is the only explanation
/// that survives closing the window.
///
/// Nothing here is decoration: the ring is drawn at the item's actual screen position, discovered
/// from the window server rather than guessed, so it stays correct however full the menu bar is.
@MainActor
enum MenuBarSpotlight {
    private static var overlay: NSWindow?
    private static var glide: Task<Void, Never>?

    /// Rings the status item and glides the cursor to it. Safe to call when the item cannot be
    /// found — it simply does nothing rather than pointing at empty space.
    static func show(moveCursor: Bool = true) {
        guard let rect = statusItemFrame() else { return }

        present(around: rect)
        guard moveCursor, !InkReduceMotion.isEnabled else { return }
        glide?.cancel()
        glide = Task { await glideCursor(to: CGPoint(x: rect.midX, y: rect.midY)) }
    }

    static func hide() {
        glide?.cancel()
        glide = nil
        overlay?.orderOut(nil)
        overlay = nil
    }

    // MARK: - Finding the item

    /// The status item's frame, straight from the item that owns it.
    ///
    /// This used to search `CGWindowListCopyWindowInfo` for a window on the status layer belonging
    /// to this process. It found nothing — a `MenuBarExtra` button is not in that list — so the
    /// ring never appeared and the cursor never moved. Owning an `NSStatusItem` makes the frame a
    /// property rather than a search.
    private static func statusItemFrame() -> CGRect? {
        StatusItemController.shared.iconFrame
    }

    // MARK: - The ring

    private static func present(around rect: CGRect) {
        let padding: CGFloat = 14
        let framed = rect.insetBy(dx: -padding, dy: -padding)

        // CoreGraphics hands back top-left origin; NSWindow wants bottom-left off the primary
        // screen. Getting this backwards puts the ring at the bottom of the display.
        guard let primary = NSScreen.screens.first else { return }
        let flipped = NSRect(
            x: framed.origin.x,
            y: primary.frame.maxY - framed.origin.y - framed.height,
            width: framed.width,
            height: framed.height
        )

        let window = overlay ?? {
            let w = NSWindow(
                contentRect: flipped, styleMask: [.borderless], backing: .buffered, defer: false)
            w.isOpaque = false
            w.backgroundColor = .clear
            w.hasShadow = false
            // Above the menu bar itself, and never in the way: the whole point is that the user can
            // still click the icon being pointed at.
            w.level = NSWindow.Level(rawValue: Int(CGWindowLevelForKey(.statusWindow)) + 1)
            w.ignoresMouseEvents = true
            w.collectionBehavior = [.canJoinAllSpaces, .stationary, .fullScreenAuxiliary, .ignoresCycle]
            w.contentView = SpotlightRingView(frame: NSRect(origin: .zero, size: flipped.size))
            overlay = w
            return w
        }()

        window.setFrame(flipped, display: true)
        window.contentView?.frame = NSRect(origin: .zero, size: flipped.size)
        window.orderFrontRegardless()
        (window.contentView as? SpotlightRingView)?.begin()
    }

    // MARK: - The cursor

    /// Walks the pointer to `target` over ~1.1 s on an ease-out curve.
    ///
    /// Deliberately slow. Teleporting the cursor is disorienting and teaches nothing — the movement
    /// *is* the instruction, so it has to be followable. Uses `CGWarpMouseCursorPosition`, which
    /// needs no Accessibility grant.
    private static func glideCursor(to target: CGPoint) async {
        let start = currentCursorPosition()
        let distance = hypot(target.x - start.x, target.y - start.y)
        // Already there; moving would be a twitch rather than a gesture.
        guard distance > 24 else { return }

        let steps = 55
        let frame = Duration.milliseconds(20)
        for step in 1...steps {
            if Task.isCancelled { return }
            let t = Double(step) / Double(steps)
            let eased = 1 - pow(1 - t, 3)
            let point = CGPoint(
                x: start.x + (target.x - start.x) * eased,
                y: start.y + (target.y - start.y) * eased
            )
            CGWarpMouseCursorPosition(point)
            // Without this the warp suppresses real mouse input briefly, and the user's own
            // movement fights ours for a beat after we stop.
            CGAssociateMouseAndMouseCursorPosition(1)
            try? await Task.sleep(for: frame)
        }
    }

    private static func currentCursorPosition() -> CGPoint {
        guard let primary = NSScreen.screens.first else { return NSEvent.mouseLocation }
        let location = NSEvent.mouseLocation
        return CGPoint(x: location.x, y: primary.frame.maxY - location.y)
    }
}

// MARK: - Ring

/// A ring that breathes, so the eye finds it against a busy menu bar. Drawn in the accent and not
/// in either end of the label ladder: this one lands on the menu bar, which is the system's own
/// surface and is routinely dark *and* routinely light, so nothing else is guaranteed to show up.
private final class SpotlightRingView: NSView {
    private let ring = CAShapeLayer()

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.addSublayer(ring)
        ring.fillColor = NSColor.clear.cgColor
        ring.strokeColor = Ink.nsAccent.withAlphaComponent(0.9).cgColor
        ring.lineWidth = 2
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError("not used") }

    override func layout() {
        super.layout()
        let inset = ring.lineWidth
        let path = CGPath(ellipseIn: bounds.insetBy(dx: inset, dy: inset), transform: nil)
        ring.frame = bounds
        ring.path = path
    }

    func begin() {
        ring.removeAllAnimations()
        guard !InkReduceMotion.isEnabled else {
            ring.opacity = 1
            return
        }
        let pulse = CABasicAnimation(keyPath: "opacity")
        pulse.fromValue = 1.0
        pulse.toValue = 0.35
        pulse.duration = 0.9
        pulse.autoreverses = true
        pulse.repeatCount = .infinity
        pulse.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
        ring.add(pulse, forKey: "pulse")

        let breathe = CABasicAnimation(keyPath: "transform.scale")
        breathe.fromValue = 0.86
        breathe.toValue = 1.0
        breathe.duration = 0.9
        breathe.autoreverses = true
        breathe.repeatCount = .infinity
        breathe.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
        ring.add(breathe, forKey: "breathe")
    }
}
