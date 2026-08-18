import AppKit
import ContextCore
import XCTest

@testable import ContextApp

/// Renders the timeline track — the real `RewindTrackView`, over a synthetic day — and writes the
/// frames out for a person to look at, beside a fixture that reproduces the two defects they replace.
///
/// **Skipped unless `CONTEXT_TRACK_RENDER=1`.** It writes files and it reads the icons of whichever
/// apps are installed on the machine running it, so it is a hand-run tool rather than a claim. The
/// claims that have to hold every time are in `RewindTests`, which is pure: the badge orientation is
/// asserted there on read-back pixels, and the palette's brand, solidity and ring-contrast floors are
/// asserted there over all 2 503 emittable colours.
///
/// **Why this exists.** Two defects were reported by a person looking at the strip and neither was
/// visible in any test the app had, because both are properties of a picture:
///
/// - *"The logos in timeline appear inverted."* They were, vertically — the badge used
///   `NSImage.draw(in:from:operation:fraction:)`, which ignores a flipped context, and the track view
///   is flipped. A logo mirrored about its horizontal axis is obvious in a render and invisible in
///   every assertion anyone would think to write about a `draw` call.
/// - *"The colors need to be more solid, more vibrant, more variety."* The palette swept one
///   continuous arc, so 41% of apps landed in green and the yellow-green crossing rendered khaki. A
///   day came out as long runs of washed-out olive. Also a fact about a picture.
///
/// So the before/after pair is the whole argument, and it is reproduced here rather than described:
/// `LegacyTrackFixture` draws the same day with the retired palette constants and the retired image
/// call. Nothing in the app uses it.
///
/// **Real icons on purpose.** The synthetic day is built from apps that ship with macOS, because the
/// inversion is only legible on real artwork — a monogram disc is symmetric enough to hide it, which
/// is exactly how this shipped. No user data is read: the blocks are fabricated here and the only
/// thing taken from the machine is `NSWorkspace`'s icon for a system app.
final class RewindTrackRenderHarness: XCTestCase {

    private var outputDirectory: URL {
        URL(
            fileURLWithPath: ProcessInfo.processInfo.environment["CONTEXT_TRACK_RENDER_DIR"]
                ?? NSTemporaryDirectory() + "track-renders")
    }

    @MainActor
    func testRenderTheTimelineTrack() throws {
        try XCTSkipUnless(
            ProcessInfo.processInfo.environment["CONTEXT_TRACK_RENDER"] == "1",
            "render harness; set CONTEXT_TRACK_RENDER=1 to run it")

        let directory = outputDirectory
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        let width: CGFloat = 1_100
        let day = Self.syntheticDay()

        let shipped = RewindTrackView(
            frame: NSRect(x: 0, y: 0, width: width, height: RewindTrackView.height))
        shipped.apply(
            blocks: day.blocks, frames: [], trackStart: day.start, trackSpan: day.span,
            playheadAt: day.start + day.span * 0.42)

        let legacy = LegacyTrackFixture(
            frame: NSRect(x: 0, y: 0, width: width, height: RewindTrackView.height))
        legacy.blocks = day.blocks
        legacy.trackStart = day.start
        legacy.trackSpan = day.span
        legacy.playheadAt = day.start + day.span * 0.42

        try write(Self.onSheet(legacy), to: directory, named: "before-track")
        try write(Self.onSheet(shipped), to: directory, named: "after-track")

        // Zoomed into four hours, where the segments are wide enough that the badges are unambiguous
        // and the icon orientation is plain at a glance.
        let zoomStart = day.start + 5 * 3_600
        let zoomSpan = 4 * 3_600.0
        shipped.apply(
            blocks: day.blocks, frames: [], trackStart: zoomStart, trackSpan: zoomSpan,
            playheadAt: zoomStart + zoomSpan * 0.5)
        legacy.trackStart = zoomStart
        legacy.trackSpan = zoomSpan
        legacy.playheadAt = zoomStart + zoomSpan * 0.5
        try write(Self.onSheet(legacy), to: directory, named: "before-zoomed")
        try write(Self.onSheet(shipped), to: directory, named: "after-zoomed")

        // The palettes side by side, one row per app, so the "more solid, more variety" half can be
        // read off without hunting for two adjacent segments.
        try write(Self.swatchSheet(apps: day.apps), to: directory, named: "palette-swatches")

        print("[track] frames written to \(directory.path)")
    }

    // MARK: - The synthetic day

    private struct Day {
        let start: Double
        let span: Double
        let blocks: [ActivityBlock]
        let apps: [String]
    }

    /// Apps that ship with macOS, so their real icons resolve on any machine this runs on, plus the
    /// two the developer actually lives in.
    private static let dayApps = [
        "Finder", "Safari", "Mail", "Messages", "Notes", "Music", "Photos", "Terminal",
        "Preview", "Calendar", "Xcode", "System Settings",
    ]

    @MainActor
    private static func syntheticDay() -> Day {
        // 08:00 on a fixed date, twelve hours wide. Fixed rather than "now" so two runs of this
        // harness produce comparable pictures.
        let start = 1_785_052_800.0
        let span = 12 * 3_600.0
        var blocks: [ActivityBlock] = []
        var cursor = start
        var index = 0
        // Lengths that look like a real day: a couple of long stretches, a lot of short ones.
        let lengths: [Double] = [
            52, 8, 14, 96, 6, 22, 11, 140, 9, 17, 38, 7, 26, 63, 12, 19, 84, 10, 31, 15, 47, 23,
        ]
        while cursor < start + span {
            let app = dayApps[index % dayApps.count]
            let length = lengths[index % lengths.count] * 60
            blocks.append(
                ActivityBlock(
                    app: app, window: nil, startedAt: cursor,
                    endedAt: min(start + span, cursor + length), sampleText: nil))
            cursor += length
            index += 1
        }
        return Day(start: start, span: span, blocks: blocks, apps: dayApps)
    }

    // MARK: - Rendering

    /// The track on a window-coloured sheet with a margin, so the render looks like the strip in the
    /// timeline window rather than a bar cropped to its own bounds.
    @MainActor
    private static func onSheet(_ track: NSView) -> NSBitmapImageRep {
        let margin: CGFloat = 16
        let sheet = SheetView(
            frame: NSRect(
                x: 0, y: 0, width: track.bounds.width + margin * 2,
                height: track.bounds.height + margin * 2))
        track.setFrameOrigin(NSPoint(x: margin, y: margin))
        sheet.addSubview(track)
        // The timeline window is glass pinned to Aqua (`InkGlass.appearanceName`), so the sheet and
        // every system semantic on it — the badge ring, the playhead, the hour labels — resolve the
        // way they do in the product rather than in whatever appearance the test runner inherited.
        sheet.appearance = InkGlass.appearance
        let rep = sheet.bitmapImageRepForCachingDisplay(in: sheet.bounds)!
        sheet.cacheDisplay(in: sheet.bounds, to: rep)
        track.removeFromSuperview()
        return rep
    }

    /// One row per app: the shipped swatch against the retired one, at the same size.
    @MainActor
    private static func swatchSheet(apps: [String]) -> NSBitmapImageRep {
        let rowHeight: CGFloat = 34
        let view = SwatchSheet(
            frame: NSRect(x: 0, y: 0, width: 720, height: rowHeight * CGFloat(apps.count) + 40))
        view.apps = apps
        view.appearance = InkGlass.appearance
        let rep = view.bitmapImageRepForCachingDisplay(in: view.bounds)!
        view.cacheDisplay(in: view.bounds, to: rep)
        return rep
    }

    private func write(_ rep: NSBitmapImageRep, to directory: URL, named name: String) throws {
        let data = try XCTUnwrap(rep.representation(using: .png, properties: [:]))
        try data.write(to: directory.appendingPathComponent("\(name).png"))
    }
}

// MARK: - Fixtures

/// A plain backdrop in the window's own colour.
private final class SheetView: NSView {
    override var isFlipped: Bool { true }
    override func draw(_ dirtyRect: NSRect) {
        NSColor.windowBackgroundColor.setFill()
        bounds.fill()
    }
}

/// The track **as it was**: the retired palette constants and the retired image call.
///
/// A fixture, not a fallback — nothing in the app reaches this, and it exists only so the before/after
/// pair can be put side by side. It is deliberately the same geometry as `RewindTrackView` so the two
/// renders differ in exactly the two things that changed.
private final class LegacyTrackFixture: NSView {
    var blocks: [ActivityBlock] = []
    var trackStart: Double = 0
    var trackSpan: Double = 1
    var playheadAt: Double?

    override var isFlipped: Bool { true }

    /// One saturation and one brightness over a uniform `[0°, 220°)` sweep — the arc that put 41% of
    /// apps in green and rendered the 60°–95° crossing as khaki.
    private func legacyColour(for app: String) -> NSColor {
        let key = app.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let hue = Double(RewindPalette.stableHash(key) % 2_503) / 2_503 * 220
        return NSColor(hue: CGFloat(hue / 360), saturation: 0.52, brightness: 0.70, alpha: 1)
    }

    private var barRect: NSRect {
        NSRect(x: 0, y: (bounds.height - 26) / 2 - 6, width: bounds.width, height: 26)
    }

    private func x(for instant: Double) -> CGFloat {
        CGFloat((instant - trackStart) / trackSpan) * bounds.width
    }

    override func draw(_ dirtyRect: NSRect) {
        let bar = barRect
        let shape = NSBezierPath(roundedRect: bar, xRadius: 6, yRadius: 6)
        NSColor.quaternaryLabelColor.setFill()
        shape.fill()

        NSGraphicsContext.saveGraphicsState()
        shape.addClip()
        for block in blocks {
            let left = max(0, x(for: block.startedAt))
            let width = max(2, min(bounds.width, x(for: block.endedAt)) - left)
            legacyColour(for: block.app).setFill()
            NSRect(x: left, y: bar.minY, width: width, height: bar.height).fill()
        }
        NSGraphicsContext.restoreGraphicsState()

        NSColor.separatorColor.setStroke()
        shape.lineWidth = 1
        shape.stroke()

        // Badges, longest-first with the same overlap rejection, so the two renders place the same
        // set of icons and only their orientation differs.
        let size: CGFloat = 18
        var placed: [CGFloat] = []
        for block in blocks.sorted(by: { $0.durationSeconds > $1.durationSeconds }) {
            let left = max(0, x(for: block.startedAt))
            let right = min(bounds.width, x(for: block.endedAt))
            guard right - left >= 4 else { continue }
            let centre = min(max((left + right) / 2, size / 2 + 1), bounds.width - size / 2 - 1)
            guard !placed.contains(where: { abs($0 - centre) < size + 5 }) else { continue }
            placed.append(centre)

            let rect = NSRect(x: centre - size / 2, y: bar.midY - size / 2, width: size, height: size)
            NSColor.controlBackgroundColor.setFill()
            NSBezierPath(ovalIn: rect.insetBy(dx: -1.5, dy: -1.5)).fill()
            let icon = MainActor.assumeIsolated { AppIconCache.shared.icon(appName: block.app) }
            if let icon {
                NSGraphicsContext.saveGraphicsState()
                NSBezierPath(ovalIn: rect).addClip()
                // **The defect.** Four arguments, so `respectFlipped` is false and the artwork is
                // laid out bottom-left in a top-left view: every logo mirrored.
                icon.draw(in: rect, from: .zero, operation: .sourceOver, fraction: 1)
                NSGraphicsContext.restoreGraphicsState()
            } else {
                legacyColour(for: block.app).setFill()
                NSBezierPath(ovalIn: rect).fill()
            }
        }

        if let playheadAt {
            let rect = NSRect(
                x: x(for: playheadAt) - 1.5, y: bar.minY - 4, width: 3, height: bar.height + 8)
            let path = NSBezierPath(roundedRect: rect, xRadius: 1.5, yRadius: 1.5)
            NSColor.labelColor.setFill()
            path.fill()
        }
    }
}

/// Retired swatch beside shipped swatch, one row per app.
private final class SwatchSheet: NSView {
    var apps: [String] = []

    override var isFlipped: Bool { true }

    override func draw(_ dirtyRect: NSRect) {
        NSColor.windowBackgroundColor.setFill()
        bounds.fill()

        let heading: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 11, weight: .semibold),
            .foregroundColor: NSColor.labelColor,
        ]
        NSAttributedString(string: "app", attributes: heading).draw(at: NSPoint(x: 16, y: 12))
        NSAttributedString(string: "before  (one arc, s 0.52 / b 0.70)", attributes: heading)
            .draw(at: NSPoint(x: 180, y: 12))
        NSAttributedString(string: "after  (bands, s 0.92)", attributes: heading)
            .draw(at: NSPoint(x: 460, y: 12))

        let label: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 11, weight: .regular),
            .foregroundColor: NSColor.labelColor,
        ]
        for (index, app) in apps.enumerated() {
            let y = 40 + CGFloat(index) * 34
            NSAttributedString(string: app, attributes: label).draw(at: NSPoint(x: 16, y: y + 7))

            let key = app.lowercased()
            let legacyHue = Double(RewindPalette.stableHash(key) % 2_503) / 2_503 * 220
            NSColor(hue: CGFloat(legacyHue / 360), saturation: 0.52, brightness: 0.70, alpha: 1)
                .setFill()
            NSBezierPath(
                roundedRect: NSRect(x: 180, y: y, width: 250, height: 26), xRadius: 5, yRadius: 5
            ).fill()

            RewindPalette.nsColor(forApp: app).setFill()
            NSBezierPath(
                roundedRect: NSRect(x: 460, y: y, width: 250, height: 26), xRadius: 5, yRadius: 5
            ).fill()

            let band = RewindPalette.band(forApp: app)
            NSAttributedString(
                string: band.name,
                attributes: [
                    .font: NSFont.systemFont(ofSize: 10, weight: .semibold),
                    .foregroundColor: NSColor.white,
                ]
            ).draw(at: NSPoint(x: 470, y: y + 7))
        }
    }
}
