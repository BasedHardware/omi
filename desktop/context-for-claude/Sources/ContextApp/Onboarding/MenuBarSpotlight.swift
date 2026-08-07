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

        // CoreGraphics hands back a top-left origin measured from the primary display; `NSWindow`
        // wants bottom-left. `ScreenSpace` owns that conversion and is tested against monitor
        // arrangements nobody has plugged in while running the suite — including the one this used
        // to get wrong, where `NSScreen.screens.first` is not the display at (0, 0).
        guard let flipped = ScreenSpace.live.appKit(from: framed) else { return }

        let window = overlay ?? {
            let w = SpotlightPanel(
                contentRect: flipped, styleMask: [.borderless, .nonactivatingPanel],
                backing: .buffered, defer: false)
            SpotlightWindow.configure(w)
            // Above the menu bar *and* above the settings spotlight, and never in the way: the whole
            // point is that the user can still click the icon being pointed at.
            w.level = NSWindow.Level(rawValue: Int(CGWindowLevelForKey(.statusWindow)) + 1)
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

/// A ring that breathes, so the eye finds it against a busy menu bar.
///
/// White over a dark halo, not the accent. This lands on the menu bar, which is the system's own
/// surface and is routinely dark *and* routinely light, so nothing that is a single colour is
/// guaranteed to show up on it — including `Ink.accent`. White plus a halo carries both grounds, and
/// white is the neutral INV-UI-1 asks for. Two passes, the same treatment `SettingsSpotlightCanvas`
/// uses over System Settings, and for the same reason.
private final class SpotlightRingView: NSView {
    private let halo = CAShapeLayer()
    private let ring = CAShapeLayer()

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.addSublayer(halo)
        layer?.addSublayer(ring)
        halo.fillColor = NSColor.clear.cgColor
        halo.strokeColor = NSColor.black.withAlphaComponent(0.5).cgColor
        halo.lineWidth = 5
        ring.fillColor = NSColor.clear.cgColor
        ring.strokeColor = NSColor.white.withAlphaComponent(0.96).cgColor
        ring.lineWidth = 2
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError("not used") }

    override func layout() {
        super.layout()
        let inset = halo.lineWidth
        let path = CGPath(ellipseIn: bounds.insetBy(dx: inset, dy: inset), transform: nil)
        for layer in [halo, ring] {
            layer.frame = bounds
            layer.path = path
        }
    }

    func begin() {
        ring.removeAllAnimations()
        halo.removeAllAnimations()
        guard !InkReduceMotion.isEnabled else {
            ring.opacity = 1
            halo.opacity = 1
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
        halo.add(pulse, forKey: "pulse")

        let breathe = CABasicAnimation(keyPath: "transform.scale")
        breathe.fromValue = 0.86
        breathe.toValue = 1.0
        breathe.duration = 0.9
        breathe.autoreverses = true
        breathe.repeatCount = .infinity
        breathe.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
        ring.add(breathe, forKey: "breathe")
        halo.add(breathe, forKey: "breathe")
    }
}
