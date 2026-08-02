import AppKit
import ContextCore
import SwiftUI
import XCTest

@testable import ContextApp

/// Renders the tutorial's card as it really composites — a live view, in a real window, over a
/// synthetic desktop — and writes the frames out for a person to look at.
///
/// **Skipped unless `CONTEXT_TUTORIAL_RENDER=1`.** It puts a window on screen and shells out to
/// `screencapture`, neither of which belongs in a hermetic suite; it is a tool for looking at the
/// thing, and the assertions that have to hold every time live in `TutorialTests`.
///
/// It exists for one beat in particular. The found-it card was a column of text rows and was reported
/// as such — *"this after search after onboarding needs to show results in tabular form with screen if
/// any. This list with only text looks so bland."* That is a judgement about a picture, and the only
/// honest way to check a fix for it is to produce the picture. The states below are the ones the grid
/// has to survive: every result with a screen, a result whose screen retention already removed, a
/// spoken line among screens, and the card after one has been tapped.
///
/// The same two rules `SearchRenderHarness` obeys, for the same reasons:
///
/// - **A live view and a run loop, never `ImageRenderer`.** The card's surface is `InkGlassSurface`,
///   an `.behindWindow` material, and an offscreen renderer has no window for it to be behind — it
///   would draw the scrim over nothing and report a card nobody will ever see.
/// - **Nothing of the user's is ever captured.** A opaque backdrop window covers the exact rectangle
///   that gets grabbed, so the frame contains this harness's own windows and the synthetic desktop
///   under them and nothing else. Every row and every picture below is fabricated on the spot.
final class TutorialRenderHarness: XCTestCase {

    private var outputDirectory: URL {
        URL(
            fileURLWithPath: ProcessInfo.processInfo.environment["CONTEXT_TUTORIAL_RENDER_DIR"]
                ?? NSTemporaryDirectory() + "tutorial-renders")
    }

    @MainActor
    func testRenderTheFoundItCard() throws {
        try XCTSkipUnless(
            ProcessInfo.processInfo.environment["CONTEXT_TUTORIAL_RENDER"] == "1",
            "on-screen render harness; set CONTEXT_TUTORIAL_RENDER=1 to run it")
        _ = InkTestFonts.registered

        let directory = outputDirectory
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let pictures = try Fixtures.thumbnails(in: directory)

        NSApplication.shared.setActivationPolicy(.accessory)

        var written: [String] = []
        for (name, appearance, desktop, build) in Self.cases(pictures: pictures) {
            let world = TutorialWorld()
            let model = world.modelAtTheQueryBeat()
            build(world, model)
            written.append(
                try render(
                    name: name, model: model, desktop: Fixtures.desktopImage(desktop),
                    appearance: appearance, in: directory))
        }

        print("\n=== tutorial card renders ===")
        for path in written { print(path) }
        print("=============================\n")
    }

    /// state × system appearance × desktop. The Dark pass is what proves the card's light pin rather
    /// than assuming it, and the two desktops are the extremes the glass has to stay legible over.
    @MainActor
    private static func cases(
        pictures: [String]
    ) -> [(String, NSAppearance.Name, Fixtures.Desktop, (TutorialWorld, TutorialModel) -> Void)] {
        [
            // Before anything is typed: the field, and nothing claimed.
            ("00-asking", .aqua, .midGrey, { _, _ in }),
            // The beat the report was about.
            (
                "01-found-four-screens", .aqua, .midGrey,
                { world, model in
                    world.results = TutorialWorld.screens(pictures: pictures)
                    model.search("throughput")
                }
            ),
            // One tapped. The chosen card carries the weight; nothing larger appears under the grid.
            (
                "02-found-and-chosen", .aqua, .midGrey,
                { world, model in
                    world.results = TutorialWorld.screens(pictures: pictures)
                    model.search("throughput")
                    if let first = model.results.first { model.choose(first) }
                }
            ),
            // Retention unlinked two of the pictures, and one result is speech. Both wells have to
            // read as deliberate rather than as images that failed to load.
            (
                "03-found-mixed", .aqua, .midGrey,
                { world, model in
                    world.results = TutorialWorld.mixed(pictures: pictures)
                    model.search("invoice")
                }
            ),
            // A spoken result tapped: the one case that still earns the larger preview, because the
            // card the user pressed had no picture of its own.
            (
                "04-spoken-chosen", .aqua, .midGrey,
                { world, model in
                    world.results = TutorialWorld.mixed(pictures: pictures)
                    model.search("invoice")
                    if let spoken = model.results.first(where: { !$0.isScreen }) { model.choose(spoken) }
                }
            ),
            (
                "05-found-four-screens-darksystem-black", .darkAqua, .black,
                { world, model in
                    world.results = TutorialWorld.screens(pictures: pictures)
                    model.search("throughput")
                }
            ),
            (
                "06-found-four-screens-lightsystem-white", .aqua, .white,
                { world, model in
                    world.results = TutorialWorld.screens(pictures: pictures)
                    model.search("throughput")
                }
            ),
        ]
    }

    // MARK: - Rendering

    /// Puts the card on screen over a synthetic desktop and captures the desktop's rectangle.
    @MainActor
    private func render(
        name: String,
        model: TutorialModel,
        desktop: NSImage,
        appearance: NSAppearance.Name,
        in directory: URL
    ) throws -> String {
        NSApp.appearance = NSAppearance(named: appearance)

        let screen = try XCTUnwrap(NSScreen.main)

        // Hosted exactly the way `TutorialOverlay` hosts it — a plain container with the hosting view
        // inside it, sized from the card's own ideal height and never the other way round. Making an
        // `NSHostingView` a borderless window's `contentView` re-enters AppKit's window sizing and
        // crashes, which is why the shipped overlay wraps its own.
        let hosting = NSHostingView(
            rootView: TutorialCardView(model: model, chrome: TutorialOverlayChrome()))
        hosting.sizingOptions = [.intrinsicContentSize]
        hosting.frame = NSRect(x: 0, y: 0, width: TutorialOverlay.width, height: 200)
        hosting.layoutSubtreeIfNeeded()
        let card = NSSize(
            width: TutorialOverlay.width, height: max(96, hosting.fittingSize.height.rounded(.up)))

        // The captured rectangle: the card plus a frame of synthetic desktop around it, so the shadow
        // and the glass have something real to sit on and the whole capture is ours.
        let inset: CGFloat = 40
        let visible = screen.visibleFrame
        let wanted = NSSize(
            width: min(card.width + inset * 2, visible.width),
            height: min(card.height + inset * 2, visible.height))
        let backdropFrame = NSRect(
            x: (visible.midX - wanted.width / 2).rounded(),
            y: (visible.midY - wanted.height / 2).rounded(),
            width: wanted.width.rounded(),
            height: wanted.height.rounded())

        let backdrop = NSWindow(
            contentRect: backdropFrame, styleMask: [.borderless], backing: .buffered, defer: false)
        backdrop.isOpaque = true
        backdrop.hasShadow = false
        backdrop.level = .floating
        backdrop.contentView = {
            let view = NSImageView(frame: NSRect(origin: .zero, size: backdropFrame.size))
            view.image = desktop
            view.imageScaling = .scaleAxesIndependently
            return view
        }()
        backdrop.orderFrontRegardless()

        let cardFrame = NSRect(
            x: backdropFrame.minX + inset, y: backdropFrame.minY + inset,
            width: card.width, height: card.height)
        let window = NSPanel(
            contentRect: cardFrame,
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false)
        window.isOpaque = false
        window.backgroundColor = .clear
        // The shipped configuration: the card draws its own shadow in SwiftUI, so a window shadow
        // would trace the transparent rectangle around it.
        window.hasShadow = false
        window.level = .popUpMenu
        InkGlass.pin(window)

        let container = NSView(frame: NSRect(origin: .zero, size: cardFrame.size))
        hosting.frame = container.bounds
        hosting.autoresizingMask = [.width, .height]
        container.addSubview(hosting)
        window.contentView = container
        window.orderFrontRegardless()

        // A run loop, not a sleep: the material samples the desktop through the window server and the
        // pictures decode on a detached task, neither of which happens on a blocked thread.
        spin(seconds: 1.6)

        let url = directory.appendingPathComponent("\(name).png")
        XCTAssertTrue(
            capture(rect: backdropFrame, on: screen, to: url),
            "screencapture refused the rectangle — is the display locked or asleep?")

        window.orderOut(nil)
        backdrop.orderOut(nil)
        spin(seconds: 0.2)
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
    /// full-screen grab of it is not something a test may take.
    @discardableResult
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
        return process.terminationStatus == 0 && FileManager.default.fileExists(atPath: url.path)
    }
}

// MARK: - Fabricated data

/// A world that answers every gate honestly enough to reach the search beat, and hands back invented
/// results when it gets there.
///
/// **All of it is invented.** No row here came from the user's capture database and the pictures are
/// generated on the spot by `Fixtures.thumbnails`.
@MainActor
final class TutorialWorld {
    var results: [TutorialMemory] = []

    private var timelineIsVisible = false
    private var hotkeyFired: (() -> Void)?
    private var dragTravelled: (() -> Void)?

    /// A model driven — through the real gates, never by poking state — to the beat under test.
    func modelAtTheQueryBeat() -> TutorialModel {
        var environment = TutorialEnvironment()
        environment.pollInterval = nil
        environment.screenIsGranted = { true }
        environment.storeIsReadable = { true }
        environment.frameCount = { _ in TutorialModel.frameTarget }
        environment.search = { _ in self.results }
        environment.frameNear = { instant in
            TutorialMoment(
                at: instant, app: "Arc", windowTitle: "Comparing throughput — arc.net",
                imagePath: self.previewPath)
        }
        environment.openPage = { _ in true }
        environment.timelineChord = { "⌘⌘" }
        environment.timelineChordIsArmed = { true }
        environment.watchForTimelineHotkey = { self.hotkeyFired = $0 }
        environment.stopWatchingTimelineHotkey = { self.hotkeyFired = nil }
        environment.watchForDrag = { self.dragTravelled = $0 }
        environment.stopWatchingDrag = { self.dragTravelled = nil }
        environment.presentTimeline = { self.timelineIsVisible = true }
        environment.timelineIsVisible = { self.timelineIsVisible }
        environment.locateTarget = { _ in nil }

        let model = TutorialModel(environment: environment)
        model.begin()
        model.advance()  // invitation → collectFrames
        model.poll()
        model.advance()  // collectFrames → openTimeline
        timelineIsVisible = true
        hotkeyFired?()  // openTimeline → timeline
        dragTravelled?()
        model.advance()  // timeline → findMoments
        model.advance()  // findMoments → query
        precondition(model.step == .query, "the harness did not reach the search beat")
        return model
    }

    /// The larger preview's picture, for the one state that still shows one.
    var previewPath: String {
        (ProcessInfo.processInfo.environment["CONTEXT_TUTORIAL_RENDER_DIR"]
            ?? NSTemporaryDirectory() + "tutorial-renders") + "/thumb-0.png"
    }

    /// Four screens, deliberately varied: a very long title, a short one, a domain, an app with no
    /// site at all.
    static func screens(pictures: [String]) -> [TutorialMemory] {
        let rows: [(String, String, String, Double)] = [
            (
                "Comparing M4 Max and RTX 4090 throughput on long-context inference — arc.net", "Arc",
                "tab Close Tab New Tab Search Tabs Update Aura/Icons/New/Default/search Open Profile "
                    + "throughput tokens per second", 12
            ),
            ("Inbox", "Mail", "throughput numbers from the benchmark thread", 41),
            (
                "SearchBarView.swift — context-for-claude", "Cursor",
                "func throughput(for frames: [RewindFrame]) -> Double", 63
            ),
            ("Benchmarks · archit-lal.github.example.io", "Arc", "sustained throughput chart", 190),
        ]
        return rows.enumerated().map { index, row in
            memory(
                index: index, title: row.0, app: row.1, text: row.2, minutesAgo: row.3,
                path: pictures[index % pictures.count])
        }
    }

    /// The same page with retention having taken two of the pictures, and a spoken line among them.
    static func mixed(pictures: [String]) -> [TutorialMemory] {
        var rows = screens(pictures: pictures)
        rows[1] = memory(
            index: 1, title: "Invoice 2026-07 — now.hdfcbank.example.com", app: "Arc",
            text: "Invoice 2026-07 · amount due · billing address", minutesAgo: 41, path: nil)
        rows[3] = TutorialMemory(
            at: Date().timeIntervalSince1970 - 190 * 60,
            when: "earlier",
            text: "I'll send the invoice over before Friday, the one from last month",
            app: "zoom.us",
            kind: "said")
        return rows
    }

    private static func memory(
        index: Int, title: String, app: String, text: String, minutesAgo: Double, path: String?
    ) -> TutorialMemory {
        let at = Date().timeIntervalSince1970 - minutesAgo * 60
        return TutorialMemory(
            at: at, when: ContextTime.describe(at), text: text, app: app, kind: "screen",
            window: title,
            frame: path.map {
                RewindFrame(
                    id: Int64(index + 1), capturedAt: at, appName: app, bundleId: nil,
                    windowTitle: title, ocrText: nil, imagePath: $0)
            })
    }
}
