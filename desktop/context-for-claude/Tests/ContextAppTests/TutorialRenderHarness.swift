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
/// **It used to render the found-it grid and there is no longer one to render.** The search beats
/// drew their own field and their own two-across grid of results on this card, which is the defect
/// the current pass fixed: the tutorial now opens the *real* `SearchBarWindow`, so what a person has
/// to look at is no longer a card imitating a search panel — it is a short coach mark that has to
/// stay short, stay legible, and say something true in each of the states the real panel can leave it
/// in. Those states are most of the cases below. The panel itself is `SearchRenderHarness`'s subject
/// and is deliberately not re-rendered here.
///
/// **It also renders the two beats that draw a physical action**, which are the only cards carrying
/// a moving illustration: the launch gesture pressing itself on a keyboard's bottom row, and two
/// fingers sweeping a trackpad with the timeline travelling under them. A still frame of a loop is
/// not a judgement of the loop and is not offered as one — what these frames answer is the question
/// a headless test cannot, which is whether the drawing reads as the object it is claiming to be at
/// the size a 470 pt card affords it.
///
/// The same two rules `SearchRenderHarness` obeys, for the same reasons:
///
/// - **A live view and a run loop, never `ImageRenderer`.** The card's surface is `InkGlassSurface`,
///   an `.behindWindow` material, and an offscreen renderer has no window for it to be behind — it
///   would draw the scrim over nothing and report a card nobody will ever see.
/// - **Nothing of the user's is ever captured.** A opaque backdrop window covers the exact rectangle
///   that gets grabbed, so the frame contains this harness's own windows and the synthetic desktop
///   under them and nothing else. Every event the world reports below is fabricated on the spot.
final class TutorialRenderHarness: XCTestCase {

    private var outputDirectory: URL {
        URL(
            fileURLWithPath: ProcessInfo.processInfo.environment["CONTEXT_TUTORIAL_RENDER_DIR"]
                ?? NSTemporaryDirectory() + "tutorial-renders")
    }

    @MainActor
    func testRenderTheTutorialCards() throws {
        try XCTSkipUnless(
            ProcessInfo.processInfo.environment["CONTEXT_TUTORIAL_RENDER"] == "1",
            "on-screen render harness; set CONTEXT_TUTORIAL_RENDER=1 to run it")
        _ = InkTestFonts.registered

        let directory = outputDirectory
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        NSApplication.shared.setActivationPolicy(.accessory)

        var written: [String] = []
        for (name, appearance, desktop, build) in Self.cases() {
            let world = TutorialWorld()
            let model = build(world)
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
    ///
    /// Two of these carry an arrow, because both search beats are coach marks now — one hanging under
    /// the "Search All" pill, one standing under the real panel — and an arrow changes the card's
    /// width and its padding. A render that only ever showed the armless form would not be showing
    /// what ships.
    ///
    /// In flow order, so the sequence reads the way a first run does: the launch gesture, the swipe,
    /// then the search beats.
    @MainActor
    private static func cases()
        -> [(String, NSAppearance.Name, Fixtures.Desktop, (TutorialWorld) -> TutorialModel)]
    {
        [
            // The two beats that ask for a *physical action* and draw it. Both are loops, so a still
            // capture catches whichever beat the 1.6 s spin above happened to land on — the row may
            // be up, the fingers may be mid-lift. These frames are here to check the composition:
            // that the row reads as a keyboard's bottom row, that the pad reads as a trackpad and not
            // a window, that two fingers are legible as two, and that none of it overflows a 470 pt
            // card. The motion itself is judged in the running app, which is the only place it exists.
            ("00-open-timeline", .aqua, .midGrey, { $0.modelAtTheChordBeat() }),
            (
                "01-open-timeline-rebound", .aqua, .midGrey,
                { world in
                    world.chord = "⌘⇧K"
                    return world.modelAtTheChordBeat()
                }
            ),
            ("02-timeline-swipe", .aqua, .midGrey, { $0.modelAtTheTimelineBeat() }),
            ("03-timeline-swipe-darksystem-black", .darkAqua, .black, { $0.modelAtTheTimelineBeat() }),

            // "Click Search All, just up there." The beat that no longer swallows the press.
            ("04-find-moments", .aqua, .midGrey, { $0.modelAtTheFindMomentsBeat() }),
            // The panel is up and nothing has been typed into it yet. The card's whole job here is to
            // stay out of the way of a surface that is doing the work.
            ("05-asking", .aqua, .midGrey, { $0.modelAtTheQueryBeat() }),
            // A real question that really found nothing, said as itself.
            (
                "06-found-nothing", .aqua, .midGrey,
                { world in
                    let model = world.modelAtTheQueryBeat()
                    world.report(.answered(query: "zzzz nothing matches", results: 0))
                    return model
                }
            ),
            // The real panel came back with real hits. Continue lights; nothing is drawn twice.
            (
                "07-found", .aqua, .midGrey,
                { world in
                    let model = world.modelAtTheQueryBeat()
                    world.report(.answered(query: "throughput", results: 12))
                    return model
                }
            ),
            // One of them pressed: the panel has closed itself and the timeline is back at that
            // moment. The card must not still be asking for a click.
            (
                "08-travelled", .aqua, .midGrey,
                { world in
                    let model = world.modelAtTheQueryBeat()
                    world.report(.answered(query: "throughput", results: 12))
                    world.report(.openedMoment(at: 1_700_000_000, hasPicture: true))
                    return model
                }
            ),
            // The same, for a moment with no picture left — a spoken line, or a frame retention has
            // already unlinked. The aside is the only difference and it has to be the honest one.
            (
                "09-travelled-no-picture", .aqua, .midGrey,
                { world in
                    let model = world.modelAtTheQueryBeat()
                    world.report(.answered(query: "invoice", results: 4))
                    world.report(.openedMoment(at: 1_700_000_000, hasPicture: false))
                    return model
                }
            ),
            // Escape, with nothing found. The one state this card grows a button for, because the
            // gate it serves cannot be waived.
            (
                "10-panel-closed", .aqua, .midGrey,
                { world in
                    let model = world.modelAtTheQueryBeat()
                    world.report(.closed)
                    return model
                }
            ),
            (
                "11-found-darksystem-black", .darkAqua, .black,
                { world in
                    let model = world.modelAtTheQueryBeat()
                    world.report(.answered(query: "throughput", results: 12))
                    return model
                }
            ),
            (
                "12-found-lightsystem-white", .aqua, .white,
                { world in
                    let model = world.modelAtTheQueryBeat()
                    world.report(.answered(query: "throughput", results: 12))
                    return model
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
        // **`.screenSaver`, not `.floating`.** The backdrop is the entire privacy guarantee, and the
        // frame it guards is written to a file on disk. At `.floating` it only clears *this*
        // process's windows: another application's panel, notification or overlay sits at the same
        // level or above it, lands inside the captured rectangle, and is then somebody's real screen
        // in a PNG. Measured rather than assumed — two frames of an earlier run of these render
        // harnesses came back with a browser's window furniture and its coloured reflections along
        // the edge. Anything left
        // floating above this window ends up in the capture, so it goes above the levels an ordinary
        // application window can reach.
        backdrop.level = .screenSaver
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
        // One rung above the backdrop, so the card is the thing the capture is of rather than the
        // synthetic desktop alone.
        window.level = NSWindow.Level(rawValue: NSWindow.Level.screenSaver.rawValue + 1)
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

/// A world that answers every gate honestly enough to reach the search beats, and then reports
/// whatever the real search panel would have reported.
///
/// **Nothing here is a search.** The tutorial cannot run one any more — that is the change this
/// harness exists to show — so the world's whole search vocabulary is `report`, which hands the model
/// a `SearchPanelEvent` exactly as `SearchPanelWatch` hands it one in the app. No row, no count and
/// no moment below came from the user's capture database; they are literals in this file.
@MainActor
final class TutorialWorld {

    /// The shortcut as the shortcut layer prints it, which is the only thing the tutorial learns
    /// about it and therefore the only thing that decides which of the two launch drawings the card
    /// puts up. The pair's spelling by default, because that is what ships; set it to `"⌘⇧K"` to
    /// look at the chip that types a rebind instead.
    var chord = "⌘ + ⌘"

    private var timelineIsVisible = false
    private var searchPanelIsVisible = false
    private var hotkeyFired: (() -> Void)?
    private var dragTravelled: (() -> Void)?
    private var searchPanelHappened: ((SearchPanelEvent) -> Void)?

    /// Tells the model what the real panel just did, and keeps the world's own idea of whether the
    /// panel is on screen in step with it — the model asks on entry to a beat, and a world that said
    /// "open" after reporting `.closed` would be answering two ways at once.
    func report(_ event: SearchPanelEvent) {
        switch event {
        case .opened: searchPanelIsVisible = true
        case .closed: searchPanelIsVisible = false
        case .answered, .openedMoment: break
        }
        searchPanelHappened?(event)
    }

    /// A model driven — through the real gates, never by poking state — to the beat that asks for
    /// the launch gesture.
    func modelAtTheChordBeat() -> TutorialModel {
        let model = TutorialModel(environment: environment())
        model.begin()
        model.advance()  // invitation → collectFrames
        model.poll()
        model.advance()  // collectFrames → openActivity
        precondition(model.step == .openActivity, "the harness did not reach the chord beat")
        return model
    }

    /// One beat on: the user really pressed the chord, and the drag beat opened the timeline. This is
    /// the state the drag demonstration is drawn in.
    ///
    /// The window is no longer marked visible before the keypress. It used to be, because the chord
    /// itself opened the timeline and the model read whether it was on screen as it entered the step;
    /// the chord opens the Activity search panel now, and the beat being entered is what puts a
    /// timeline up (`environment.presentTimeline`). Nothing here pokes the model — the keypress goes
    /// through the observer the model armed, exactly as the shortcut layer delivers it.
    ///
    /// The panel the chord opened is closed again on the way into this beat, which is what leaves the
    /// drag demonstration drawn over a timeline rather than under a floating slab.
    func modelAtTheTimelineBeat() -> TutorialModel {
        let model = modelAtTheChordBeat()
        report(.opened)  // the chord opens the search panel
        hotkeyFired?()  // openActivity → timeline
        precondition(model.step == .timeline, "the harness did not reach the drag beat")
        precondition(timelineIsVisible, "the drag beat has to have opened a timeline to drag")
        return model
    }

    /// And one further: they dragged, so the demonstration has stopped and the pill beat is up.
    func modelAtTheFindMomentsBeat() -> TutorialModel {
        let model = modelAtTheTimelineBeat()
        dragTravelled?()
        model.advance()  // timeline → findMoments
        precondition(model.step == .findMoments, "the harness did not reach the pill beat")
        return model
    }

    /// The same, one beat further on: the user pressed the real pill and the real panel came up.
    func modelAtTheQueryBeat() -> TutorialModel {
        let model = modelAtTheFindMomentsBeat()
        report(.opened)  // findMoments → query
        precondition(model.step == .query, "the harness did not reach the search beat")
        return model
    }

    private func environment() -> TutorialEnvironment {
        var environment = TutorialEnvironment()
        environment.pollInterval = nil
        environment.screenIsGranted = { true }
        environment.frameCount = { _ in TutorialModel.frameTarget }
        environment.openPage = { _ in true }
        environment.activityChord = { self.chord }
        environment.activityChordIsArmed = { true }
        environment.watchForActivityHotkey = { self.hotkeyFired = $0 }
        environment.stopWatchingActivityHotkey = { self.hotkeyFired = nil }
        environment.watchForDrag = { self.dragTravelled = $0 }
        environment.stopWatchingDrag = { self.dragTravelled = nil }
        environment.presentTimeline = { self.timelineIsVisible = true }
        environment.timelineIsVisible = { self.timelineIsVisible }
        environment.watchSearchPanel = { self.searchPanelHappened = $0 }
        environment.stopWatchingSearchPanel = { self.searchPanelHappened = nil }
        environment.searchPanelIsVisible = { self.searchPanelIsVisible }
        environment.presentSearchPanel = { self.report(.opened) }
        environment.dismissSearchPanel = { self.report(.closed) }
        environment.locateTarget = { _ in nil }
        return environment
    }
}
