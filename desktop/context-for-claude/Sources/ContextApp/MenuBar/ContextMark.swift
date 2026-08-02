import AppKit

/// The Context for Claude mark: a round head with two eyes and two little legs.
///
/// Drawn as vectors rather than shipped as a PNG so it stays crisp at any menu bar height and on
/// any display scale, and marked as a template image so macOS owns the colour — it inverts itself
/// for light and dark menu bars, and dims correctly when the item is inactive. A bitmap would need
/// four assets and would still be wrong on the fifth display.
///
/// The geometry is deliberately heavier than the source drawing. At 18 pt a hairline outline
/// disappears into a busy menu bar, so the stroke is thickened and the eyes enlarged until the
/// silhouette survives at the size it is actually used.
@MainActor
enum ContextMark {
    /// Menu bar height. macOS scales template images down cleanly but not up, so this is drawn at
    /// the size it is displayed.
    static let menuBarSize = CGSize(width: 18, height: 18)

    static let menuBar: NSImage = image(size: menuBarSize)

    /// A struck-through variant for the paused state, so the menu bar answers "is it listening?"
    /// without a click.
    static let menuBarPaused: NSImage = image(size: menuBarSize, struckThrough: true)

    static func image(size: CGSize, struckThrough: Bool = false) -> NSImage {
        let image = NSImage(size: size, flipped: false) { _ in
            draw(in: size, struckThrough: struckThrough)
            return true
        }
        image.isTemplate = true
        return image
    }

    /// All coordinates are expressed against a 20×20 design box and scaled, so the proportions hold
    /// at every size.
    private static func draw(in size: CGSize, struckThrough: Bool) {
        let s = min(size.width, size.height) / 20
        func p(_ x: CGFloat, _ y: CGFloat) -> NSPoint { NSPoint(x: x * s, y: y * s) }

        NSColor.black.setStroke()
        NSColor.black.setFill()

        // Head. Sits high in the box to leave the legs room; slightly wider than tall, as drawn.
        let head = NSBezierPath(ovalIn: NSRect(
            x: 3.4 * s, y: 5.9 * s, width: 13.2 * s, height: 12.6 * s))
        head.lineWidth = 1.9 * s
        head.stroke()

        // Eyes. Vertical ovals, set just below the centre line of the head.
        for x in [7.9, 12.1] as [CGFloat] {
            NSBezierPath(ovalIn: NSRect(
                x: (x - 0.78) * s, y: 11.0 * s, width: 1.56 * s, height: 2.1 * s)).fill()
        }

        // Legs. Straight down out of the head, then a short foot curving outward.
        let legs = NSBezierPath()
        legs.lineWidth = 1.7 * s
        legs.lineCapStyle = .round
        legs.lineJoinStyle = .round

        legs.move(to: p(7.7, 6.4))
        legs.line(to: p(7.3, 3.3))
        legs.curve(to: p(5.8, 2.6), controlPoint1: p(7.2, 2.7), controlPoint2: p(6.5, 2.5))

        legs.move(to: p(12.3, 6.4))
        legs.line(to: p(12.7, 3.3))
        legs.curve(to: p(14.2, 2.6), controlPoint1: p(12.8, 2.7), controlPoint2: p(13.5, 2.5))
        legs.stroke()

        guard struckThrough else { return }
        let slash = NSBezierPath()
        slash.lineWidth = 1.7 * s
        slash.lineCapStyle = .round
        slash.move(to: p(3.2, 3.0))
        slash.line(to: p(16.8, 17.4))
        slash.stroke()
    }
}
