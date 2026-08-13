import AppKit
import ContextCore
import SwiftUI
import XCTest

@testable import ContextApp

/// Renders the Activity surface as it really composites — live views, in a real window, over a
/// synthetic desktop — and writes the frames out for a person to look at.
///
/// **Skipped unless `CONTEXT_ACTIVITY_RENDER=1`** (and `CONTEXT_ACTIVITY_RENDER_DIR` moves the
/// output). It puts windows on screen and shells out to `screencapture`, neither of which belongs in
/// a hermetic suite; it is a tool for looking at the thing, run by hand, and the claims that have to
/// hold every time live in `ActivityCompositionTests`.
///
/// The two rules `SearchRenderHarness` states, obeyed here for the same reasons:
///
/// - **Live views and a run loop, never `ImageRenderer`.** The day header occludes with
///   `.regularMaterial` and the window is `.behindWindow` glass; an offscreen renderer has no window
///   for either to be behind, so it would draw the pinned header over nothing — and the header is
///   precisely what several of these cases exist to judge.
/// - **Nothing of the user's is ever captured.** A full-screen opaque backdrop window covers the
///   exact rectangle that gets grabbed, so a frame contains this harness's own windows and the
///   synthetic desktop under them and nothing else. Every day, conversation, frame and thumbnail
///   below is fabricated on the spot — `ActivitySurface(days:kind:)` takes no store, so nothing
///   drawn here can reach the capture database.
///
/// **What these frames cannot show: a populated hour rail.** The store-less initialiser fills
/// `ActivityStore.days` and nothing else, so `momentCount(for:)` is `nil` and `density(for:)` is
/// twenty-four zeroes — which is the rail's honest "this day has not been read yet" state (an em
/// dash and flat bars), not its resting one. The rail's geometry, its direction and its breakpoint
/// are all visible; its bar weights are not.
final class ActivityRenderHarness: XCTestCase {

    private var outputDirectory: URL {
        URL(
            fileURLWithPath: ProcessInfo.processInfo.environment["CONTEXT_ACTIVITY_RENDER_DIR"]
                ?? NSTemporaryDirectory() + "activity-renders")
    }

    /// The width the surface gets in the window's default frame — the lower panel's width, because
    /// that is the one place `ActivitySurface` mounts.
    private static let surfaceWidth: CGFloat = SearchLayout.panelWidth
    private static let surfaceHeight: CGFloat = SearchLayout.defaultResultsBodyHeight
    /// Comfortably under `ActivityHourRail.breakpoint`, and derived from it rather than a literal:
    /// the case exists to prove that number, so it has to be that number it is measured against.
    private static let narrowSurfaceWidth = ActivityHourRail.breakpoint - 60

    @MainActor
    func testRenderTheActivitySurface() throws {
        try XCTSkipUnless(
            ProcessInfo.processInfo.environment["CONTEXT_ACTIVITY_RENDER"] == "1",
            "on-screen render harness; set CONTEXT_ACTIVITY_RENDER=1 to run it")
        _ = InkTestFonts.registered

        let directory = outputDirectory
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let thumbnails = try Fixtures.thumbnails(in: directory)

        NSApplication.shared.setActivationPolicy(.accessory)

        let mixed = Fixtures.days(Fixtures.oneMixedDay, thumbnails: thumbnails)
        let several = Fixtures.days(Fixtures.fiveDays, thumbnails: thumbnails)

        let noPictures = Fixtures.days(Fixtures.dayWithoutPictures, thumbnails: [])

        let cases:
            [(name: String, days: [ActivityDay], kind: ActivityKind, width: CGFloat, scroll: CGFloat)] = [
            // Ten minutes after install: no days at all. The one state whose whole content is a
            // sentence, so the sentence has to be the right one.
            ("00-empty", [], .everything, Self.surfaceWidth, 0),
            // Conversations with their strips indented under them, and loose runs standing on their
            // own — the arrangement the whole surface is an argument for.
            ("01-one-day-mixed", mixed, .everything, Self.surfaceWidth, 0),
            ("02-several-days", several, .everything, Self.surfaceWidth, 0),
            // The same stream scrolled off its first day, which is the only state that can answer
            // whether the day header really pins and whether it really occludes what slides under it.
            ("02b-several-days-scrolled", several, .everything, Self.surfaceWidth, 420),
            // Soloed. The indent collapses and every row states its own time, so these two are where
            // the gutter is easiest to catch drifting off the content it is timing.
            ("03-screens-only", several, .screen, Self.surfaceWidth, 0),
            ("04-conversations-only", several, .conversations, Self.surfaceWidth, 0),
            // Every tile's picture is gone — a real and ordinary state, since retention unlinks
            // files. What has to show is the app, not a broken-image glyph.
            ("05-missing-thumbnails", noPictures, .everything, Self.surfaceWidth, 0),
            // Under the breakpoint: the rail is dropped rather than squeezed, and the list takes the
            // width back.
            ("06-narrow", mixed, .everything, Self.narrowSurfaceWidth, 0),
        ]

        var written: [String] = []
        for (name, days, kind, width, scroll) in cases {
            // Both system appearances for every case. **The pair is expected to be identical**:
            // `WindowGlass.wear` pins the window through `InkGlass.pin`, so this surface is light on
            // a Dark Mac too, and the Dark pass is what proves the pin rather than assuming it. Two
            // frames that differ mean the pin has come off — or that something else got into the
            // capture.
            for (appearance, suffix) in [
                (NSAppearance.Name.aqua, "light"), (NSAppearance.Name.darkAqua, "dark"),
            ] {
                written.append(
                    try render(
                        name: "\(name)-\(suffix)", days: days, kind: kind, width: width,
                        scroll: scroll, appearance: appearance, in: directory))
            }
        }

        print("\n=== activity surface renders ===")
        for path in written { print(path) }
        print("================================\n")
    }

    // MARK: - Rendering

    /// Puts the surface on screen over a synthetic desktop and captures the desktop's rectangle.
    @MainActor
    private func render(
        name: String,
        days: [ActivityDay],
        kind: ActivityKind,
        width: CGFloat,
        scroll: CGFloat,
        appearance: NSAppearance.Name,
        in directory: URL
    ) throws -> String {
        NSApp.appearance = NSAppearance(named: appearance)

        let screen = try XCTUnwrap(NSScreen.main)
        // The window the surface really lives in, less the parts this harness is not the subject of:
        // the same glass, the same inset, the same title-bar band the prompt bar is kept out of.
        // The bar itself is `SearchRenderHarness`'s subject and is deliberately not redrawn here.
        let windowSize = NSSize(
            width: width + SearchLayout.windowInset * 2,
            height: Self.surfaceHeight + SearchLayout.titleBarInset + SearchLayout.windowInset)
        // A frame of synthetic desktop around it, so the glass and the shadow have something real to
        // sit on and the whole capture is ours.
        let inset: CGFloat = 34
        // Clamped into the visible frame: `screencapture -R` refuses a rectangle that runs off the
        // display.
        let visible = screen.visibleFrame
        let wanted = NSSize(
            width: min(windowSize.width + inset * 2, visible.width),
            height: min(windowSize.height + inset * 2, visible.height))
        let backdropFrame = NSRect(
            x: (visible.midX - wanted.width / 2).rounded(),
            y: (visible.midY - wanted.height / 2).rounded(),
            width: wanted.width.rounded(),
            height: wanted.height.rounded())

        let backdrop = NSWindow(
            contentRect: backdropFrame, styleMask: [.borderless], backing: .buffered, defer: false)
        backdrop.isOpaque = true
        backdrop.hasShadow = false
        // **`.screenSaver`, not `.floating`.** The backdrop is the whole privacy guarantee, and at
        // `.floating` it is only above *this* process's windows — another app's panel, notification
        // or overlay sits at the same level or higher and lands inside the captured rectangle. That
        // is not a cosmetic flaw in a frame; it is somebody's real screen in a file. Measured, not
        // assumed: two frames of an earlier run of this harness came back with a browser's window
        // furniture along the top edge.
        backdrop.level = .screenSaver
        backdrop.contentView = {
            let view = NSImageView(frame: NSRect(origin: .zero, size: backdropFrame.size))
            view.image = Fixtures.desktop
            view.imageScaling = .scaleAxesIndependently
            return view
        }()
        backdrop.orderFrontRegardless()

        let windowFrame = NSRect(
            x: backdropFrame.minX + inset, y: backdropFrame.minY + inset,
            width: windowSize.width, height: windowSize.height)
        // The shipped window's shape: same style mask, same `WindowGlass.wear(_:as: .titled)`, same
        // `InkGlassView` container as `SearchBarWindow.present`. The level is the one deliberate
        // difference — it has to clear the backdrop above, and window level is not something a frame
        // can show.
        let window = NSWindow(
            contentRect: windowFrame,
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false)
        window.title = SearchBarWindow.title
        window.isReleasedWhenClosed = false
        WindowGlass.wear(window, as: .titled)
        window.level = NSWindow.Level(rawValue: NSWindow.Level.screenSaver.rawValue + 1)

        let root = InkGlassView(
            frame: NSRect(origin: .zero, size: windowFrame.size), style: .fullBleed)
        root.autoresizingMask = [.width, .height]
        window.contentView = root
        root.layoutSubtreeIfNeeded()

        let hosting = NSHostingView(
            rootView: SearchGlassPanel {
                ActivitySurface(days: days, kind: kind)
                    .frame(width: width, height: Self.surfaceHeight, alignment: .topLeading)
            }
            .padding(.horizontal, SearchLayout.windowInset)
            .padding(.bottom, SearchLayout.windowInset)
            .padding(.top, SearchLayout.titleBarInset))
        hosting.sizingOptions = [.minSize, .maxSize]
        hosting.translatesAutoresizingMaskIntoConstraints = false
        root.addSubview(hosting)
        NSLayoutConstraint.activate([
            hosting.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            hosting.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            hosting.topAnchor.constraint(equalTo: root.topAnchor),
            hosting.bottomAnchor.constraint(equalTo: root.bottomAnchor),
        ])
        window.orderFrontRegardless()

        // A run loop, not a sleep: the material samples the desktop through the window server, the
        // thumbnails decode on a detached task, and SwiftUI settles its layout — none of which
        // happens on a blocked thread.
        spin(seconds: 1.6)

        if scroll > 0 {
            let scroller = try XCTUnwrap(
                Self.verticalScroller(in: root),
                "the stream did not overflow its window, so there is nothing to scroll")
            scroller.scroll(downBy: scroll)
            // Long enough for the pinned header to settle and for the rows now under the reading
            // line to report themselves to the rail.
            spin(seconds: 0.8)
        }

        let url = directory.appendingPathComponent("\(name).png")
        let captured = capture(rect: backdropFrame, on: screen, to: url)

        window.orderOut(nil)
        backdrop.orderOut(nil)
        spin(seconds: 0.2)
        try XCTSkipUnless(
            captured, "the window server refused the capture — a locked or sleeping display")
        return url.path
    }

    @MainActor
    private func spin(seconds: TimeInterval) {
        let deadline = Date().addingTimeInterval(seconds)
        while Date() < deadline {
            RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.02))
        }
    }

    /// `screencapture -R`, over the rectangle the backdrop window fully covers.
    ///
    /// A rectangle and not the screen: the machine this runs on has the user's own work open, and a
    /// full-screen grab of it is not something a test may take. The rect is the backdrop's, which is
    /// opaque and on top, so the frame contains nothing but this harness's windows.
    ///
    /// Returns false when the window server refused — a locked or sleeping display — so the caller
    /// can put its windows away before skipping. It deliberately does not fall back to an offline
    /// composite the way `SearchRenderHarness` does: both the pinned day header and the window's
    /// ground are materials, and a frame with neither in it would be a picture of a surface that
    /// does not ship. A missing frame is a failure of the machine, not of the surface.
    private func capture(rect: NSRect, on screen: NSScreen, to url: URL) -> Bool {
        // `screencapture` measures from the top-left of the primary display; AppKit from the
        // bottom-left of the whole desktop space.
        let primaryHeight = NSScreen.screens.first?.frame.maxY ?? screen.frame.maxY
        let top = primaryHeight - rect.maxY

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
        process.arguments = [
            "-x", "-o",
            "-R\(Int(rect.minX)),\(Int(top)),\(Int(rect.width)),\(Int(rect.height))",
            url.path,
        ]
        process.standardError = FileHandle.nullDevice
        do {
            try process.run()
        } catch {
            return false
        }
        process.waitUntilExit()
        return process.terminationStatus == 0
            && FileManager.default.fileExists(atPath: url.path)
    }

    /// The stream's own vertical scroll view — the tallest one whose content overflows it.
    ///
    /// Found by walking the tree rather than held onto, because the view SwiftUI builds is the one
    /// worth driving: every moment strip is a scroll view too, and they scroll the other way.
    private static func verticalScroller(in view: NSView) -> NSScrollView? {
        var found: [NSScrollView] = []
        func walk(_ node: NSView) {
            if let scroll = node as? NSScrollView,
                let document = scroll.documentView,
                document.frame.height > scroll.contentView.bounds.height + 1
            {
                found.append(scroll)
            }
            node.subviews.forEach(walk)
        }
        walk(view)
        return found.max { $0.contentView.bounds.height < $1.contentView.bounds.height }
    }
}

extension NSScrollView {
    /// Scrolls `points` down from the top, whichever way round the document is flipped.
    @MainActor
    fileprivate func scroll(downBy points: CGFloat) {
        guard let document = documentView else { return }
        let clip = contentView.bounds.height
        let travel = max(0, document.frame.height - clip)
        let offset = min(points, travel)
        contentView.scroll(to: NSPoint(x: 0, y: document.isFlipped ? offset : travel - offset))
        reflectScrolledClipView(contentView)
    }
}

// MARK: - Fabricated data

extension ActivityRenderHarness {

    /// Everything the harness draws. **All of it is invented** — no conversation, frame or count
    /// here came from the user's capture database, and the pictures are generated on the spot.
    ///
    /// Days are built through `ActivityComposer.compose`, never assembled by hand: attachment,
    /// clustering and day counts are the rules this surface is made of, so a frame drawn from
    /// hand-arranged rows would be a picture of an arrangement the app cannot produce.
    @MainActor
    enum Fixtures {

        /// One fabricated day, as the composer's two inputs: what was said, and what was on screen.
        struct Draft {
            let daysAgo: Int
            /// Conversations, as start time on that day plus how long they ran.
            var sessions: [(hour: Int, minute: Int, minutes: Double, app: String?, lines: Int)] = []
            /// Runs of screen capture. A run inside a conversation's window becomes its attached
            /// strip; the rest cluster on `ActivityComposer.momentClusterGap`.
            var runs: [(hour: Int, minute: Int, count: Int, everyMinutes: Int)] = []
            /// What the day header counts, which is the whole day rather than the sample the strips
            /// draw. `nil` keeps the two the same.
            var total: Int?
        }

        private static let calendar = Calendar.current

        /// Real app names, so `RewindAppIcon` resolves the icons this machine actually has — plus
        /// one that exists nowhere, which is what draws `RewindPalette`'s monogram disc instead.
        static let apps = ["Safari", "Notes", "Terminal", "Mail", "Finder", "Fathom"]

        static let previews = [
            "we went over the migration plan and what is left before the beta",
            "the invoice went out on Friday, finance is copied",
            "let's park the rename until after the release",
        ]

        // MARK: The cases

        /// Conversations with attached strips, and loose runs between them. The 10 AM run is
        /// deliberately fourteen frames long — past `ActivityComposer.momentsPerStrip` — so the
        /// strip has to say "8 of 14 moments" rather than quietly showing eight.
        static let oneMixedDay: [Draft] = [
            Draft(
                daysAgo: 0,
                sessions: [
                    (9, 12, 34, "Zoom", 96),
                    (13, 2, 62, "Google Meet", 214),
                    (16, 40, 3.5, nil, 5),
                ],
                runs: [(9, 14, 5, 6), (10, 5, 14, 2), (13, 10, 6, 8), (18, 10, 4, 7)],
                total: 1_204)
        ]

        /// Five days, deliberately unalike: a full one, a day of screens with nobody talking, a day
        /// of talk with the screen off, and two ordinary ones. The header's subtitle drops the
        /// clause it has no count for, so a run of identical days would never show that.
        static let fiveDays: [Draft] = [
            Draft(
                daysAgo: 0,
                sessions: [(9, 12, 34, "Zoom", 96), (15, 20, 18, "Slack", 41)],
                runs: [(9, 14, 5, 6), (11, 30, 11, 3), (15, 24, 4, 4)],
                total: 964),
            Draft(daysAgo: 1, runs: [(8, 40, 9, 5), (14, 5, 12, 4), (21, 15, 6, 6)], total: 1_881),
            Draft(
                daysAgo: 2,
                sessions: [(10, 0, 45, "Google Meet", 180), (12, 30, 8, nil, 12), (17, 5, 21, "Zoom", 63)]),
            Draft(
                daysAgo: 3,
                sessions: [(14, 15, 26, "Zoom", 74)],
                runs: [(14, 18, 6, 4), (19, 40, 8, 3)],
                total: 402),
            Draft(daysAgo: 4, sessions: [(11, 45, 12, "FaceTime", 30)], runs: [(11, 47, 4, 3)], total: 96),
        ]

        /// One day whose frames all lost their pictures. The worst case for the fallback tile.
        static let dayWithoutPictures: [Draft] = [
            Draft(
                daysAgo: 0,
                sessions: [(9, 12, 34, "Zoom", 96)],
                runs: [(9, 14, 6, 5), (12, 20, 9, 4)],
                total: 311)
        ]

        // MARK: Building

        /// Composes drafts into the stream the surface renders. `thumbnails` empty means every frame
        /// has lost its picture.
        static func days(_ drafts: [Draft], thumbnails: [String]) -> [ActivityDay] {
            var sessions: [SessionSummary] = []
            var screens: [Date: ActivityDayScreen] = [:]
            var momentID: Int64 = 1

            for draft in drafts {
                // Walked by calendar rather than by 86,400 seconds: a day with a DST transition in
                // it is not 24 hours long, and a key that is not the local start of the day is a day
                // the composer files under a different header than the one it drew.
                let today = calendar.startOfDay(for: Date())
                let start = calendar.date(byAdding: .day, value: -draft.daysAgo, to: today) ?? today
                for (index, spec) in draft.sessions.enumerated() {
                    sessions.append(
                        session(
                            // Unique across days without the caller having to keep a ledger.
                            id: Int64(draft.daysAgo * 100 + index + 1),
                            start: clock(start, hour: spec.hour, minute: spec.minute),
                            minutes: spec.minutes, app: spec.app, lines: spec.lines))
                }

                var moments: [ActivityMoment] = []
                for run in draft.runs {
                    for step in 0..<run.count {
                        moments.append(
                            moment(
                                id: momentID,
                                at: clock(
                                    start, hour: run.hour,
                                    minute: run.minute + step * run.everyMinutes),
                                thumbnails: thumbnails))
                        momentID += 1
                    }
                }
                guard !moments.isEmpty else { continue }
                screens[start] = screen(moments, total: draft.total)
            }

            return ActivityComposer.compose(
                sessions: sessions, screen: screens, calendar: calendar)
        }

        private static func clock(_ day: Date, hour: Int, minute: Int) -> Date {
            calendar.date(byAdding: .minute, value: hour * 60 + minute, to: day) ?? day
        }

        private static func session(
            id: Int64, start: Date, minutes: Double, app: String?, lines: Int
        ) -> SessionSummary {
            SessionSummary(
                id: id,
                startedAt: start.timeIntervalSince1970,
                endedAt: start.addingTimeInterval(minutes * 60).timeIntervalSince1970,
                durationSeconds: minutes * 60,
                appHint: app,
                lineCount: lines,
                bothSidesPresent: true,
                preview: previews[Int(id) % previews.count])
        }

        private static func moment(id: Int64, at timestamp: Date, thumbnails: [String])
            -> ActivityMoment
        {
            let app = apps[Int(id) % apps.count]
            return ActivityMoment(
                id: id,
                timestamp: timestamp,
                appName: app,
                bundleId: nil,
                windowTitle: "\(app) — \(ActivityFormat.time(timestamp))",
                imagePath: thumbnails.isEmpty ? nil : thumbnails[Int(id) % thumbnails.count])
        }

        /// The day's shape, counted the way `ActivityStore.project` counts it: exact local-hour
        /// buckets, an exact total, and the sample the strips draw kept separate from both.
        private static func screen(_ moments: [ActivityMoment], total: Int?) -> ActivityDayScreen {
            var hourCounts = [Int](repeating: 0, count: 24)
            for moment in moments {
                hourCounts[calendar.component(.hour, from: moment.timestamp)] += 1
            }
            return ActivityDayScreen(
                total: total ?? moments.count, hourCounts: hourCounts, sampled: moments)
        }

        // MARK: Pictures

        /// A synthetic desktop. Not a photograph and not the user's wallpaper: it exists to give the
        /// glass something with structure to blur, and to be the only thing in the frame that is not
        /// this harness's own window.
        static let desktop: NSImage = {
            let size = NSSize(width: 1600, height: 1200)
            return NSImage(size: size, flipped: false) { rect in
                let gradient = NSGradient(colors: [
                    NSColor(calibratedRed: 0.16, green: 0.20, blue: 0.26, alpha: 1),
                    NSColor(calibratedRed: 0.55, green: 0.58, blue: 0.62, alpha: 1),
                    NSColor(calibratedRed: 0.24, green: 0.26, blue: 0.30, alpha: 1),
                ])!
                gradient.draw(in: rect, angle: 35)
                NSColor.white.withAlphaComponent(0.10).setFill()
                for index in 0..<9 {
                    let x = rect.width * CGFloat(index) / 9
                    NSBezierPath(ovalIn: NSRect(x: x, y: rect.height * 0.2, width: 180, height: 180))
                        .fill()
                }
                return true
            }
        }()

        /// Writes a handful of fake "screenshots" to disk, so the tiles decode through the real
        /// `FrameLoader` path rather than through a stand-in for it.
        static func thumbnails(in directory: URL) throws -> [String] {
            let hues: [NSColor] = [
                .init(calibratedRed: 0.95, green: 0.96, blue: 0.97, alpha: 1),
                .init(calibratedRed: 0.12, green: 0.13, blue: 0.16, alpha: 1),
                .init(calibratedRed: 0.90, green: 0.93, blue: 0.99, alpha: 1),
                .init(calibratedRed: 0.99, green: 0.95, blue: 0.90, alpha: 1),
            ]
            var paths: [String] = []
            for (index, hue) in hues.enumerated() {
                let size = NSSize(width: 1200, height: 800)
                let image = NSImage(size: size, flipped: false) { rect in
                    hue.setFill()
                    rect.fill()
                    // Some furniture, so a tile reads as a screenshot rather than as a swatch.
                    let ink = hue.brightnessComponent > 0.5 ? NSColor.black : NSColor.white
                    ink.withAlphaComponent(0.08).setFill()
                    NSRect(x: 0, y: rect.height - 60, width: rect.width, height: 60).fill()
                    ink.withAlphaComponent(0.14).setFill()
                    for row in 0..<9 {
                        let y = rect.height - 140 - CGFloat(row) * 54
                        let width = rect.width * (0.3 + CGFloat((row * 37) % 60) / 100)
                        NSRect(x: 70, y: y, width: width, height: 20).fill()
                    }
                    return true
                }
                let url = directory.appendingPathComponent("activity-thumb-\(index).png")
                let data = NSBitmapImageRep(data: image.tiffRepresentation!)!
                    .representation(using: .png, properties: [:])!
                try data.write(to: url)
                paths.append(url.path)
            }
            return paths
        }
    }
}
