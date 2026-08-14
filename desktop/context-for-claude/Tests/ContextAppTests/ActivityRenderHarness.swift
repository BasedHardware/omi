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
///   below is fabricated on the spot — the store-less `ActivitySurface` initialiser takes neither a
///   store nor an account, so nothing drawn here can reach the capture database or the network.
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

    /// The width and height the surface gets on the search panel's lower panel, because that is the
    /// one place `ActivitySurface` mounts. The height is the panel's ceiling, which is what the
    /// spine is given flat — see the mounting point in `SearchBarView`.
    private static let surfaceWidth: CGFloat = SearchLayout.panelWidth
    private static let surfaceHeight: CGFloat = SearchLayout.maximumResultsBodyHeight
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
        let localOnly = Fixtures.days(Fixtures.dayWithNoAccount, thumbnails: thumbnails)

        let cases:
            [(
                name: String, days: [ActivityDay], kind: ActivityKind, width: CGFloat,
                scroll: CGFloat, reachable: Bool, settled: Bool
            )] = [
                // Ten minutes after install: no days at all. The one state whose whole content is a
                // sentence, so the sentence has to be the right one.
                ("00-empty", [], .all, Self.surfaceWidth, 0, true, true),
                // Conversations with their strips indented under them, memories and tasks standing on
                // the clock in their own right, and loose runs between them — the arrangement the
                // whole surface is an argument for.
                ("01-one-day-mixed", mixed, .all, Self.surfaceWidth, 0, true, true),
                ("02-several-days", several, .all, Self.surfaceWidth, 0, true, true),
                // The same stream scrolled off its first day, which is the only state that can answer
                // whether the day header really pins and whether it really occludes what slides under
                // it.
                ("02b-several-days-scrolled", several, .all, Self.surfaceWidth, 420, true, true),
                // One frame per chip. Soloed, the indent collapses and every row states its own time,
                // so these are where the gutter is easiest to catch drifting off its content.
                ("03-conversations-only", several, .conversations, Self.surfaceWidth, 0, true, true),
                ("04-memories-only", several, .memories, Self.surfaceWidth, 0, true, true),
                ("05-tasks-only", several, .tasks, Self.surfaceWidth, 0, true, true),
                ("06-rewind-only", several, .rewind, Self.surfaceWidth, 0, true, true),
                // Every tile's picture is gone — a real and ordinary state, since retention unlinks
                // files. What has to show is the app, not a broken-image glyph.
                ("07-missing-thumbnails", noPictures, .all, Self.surfaceWidth, 0, true, true),
                // Under the breakpoint: the rail is dropped rather than squeezed, and the list takes
                // the width back.
                ("08-narrow", mixed, .all, Self.narrowSurfaceWidth, 0, true, true),
                // Nobody signed in: only this Mac's own screen moments, and the corner still counting.
                // This is also the only frame that renders the "so far · still counting" branch.
                ("09-no-account", localOnly, .all, Self.surfaceWidth, 0, false, false),
                // Soloed to a kind that lives entirely in the account, with no account. The empty
                // copy here must not read as "you have no memories".
                ("10-no-account-memories", [], .memories, Self.surfaceWidth, 0, false, true),
            ]

        var written: [String] = []
        for (name, days, kind, width, scroll, reachable, settled) in cases {
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
                        scroll: scroll, reachable: reachable, settled: settled,
                        appearance: appearance, in: directory))
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
        reachable: Bool,
        settled: Bool,
        appearance: NSAppearance.Name,
        in directory: URL
    ) throws -> String {
        NSApp.appearance = NSAppearance(named: appearance)

        let screen = try XCTUnwrap(NSScreen.main)
        // The window the surface really lives in, less the parts this harness is not the subject of:
        // the same glass and the same clear margin the panel's shadow falls into. The prompt bar
        // above it is `SearchRenderHarness`'s subject and is deliberately not redrawn here.
        let windowSize = NSSize(
            width: width + SearchLayout.shadowMargin * 2,
            height: Self.surfaceHeight + SearchLayout.shadowMargin * 2)
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
        // The shipped surface's shape: the same borderless window, the same transparent ground with
        // no window shadow of its own, and the panel wearing `InkGlass` inside it — exactly what
        // `SearchBarWindow.present` puts up. The level is the one deliberate difference — it has to
        // clear the backdrop above, and window level is not something a frame can show.
        let window = NSPanel(
            contentRect: windowFrame,
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false)
        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = false
        window.isReleasedWhenClosed = false
        InkGlass.pin(window)
        window.level = NSWindow.Level(rawValue: NSWindow.Level.screenSaver.rawValue + 1)

        let root = NSView(frame: NSRect(origin: .zero, size: windowFrame.size))
        root.autoresizingMask = [.width, .height]

        let hosting = NSHostingView(
            rootView: SearchGlassPanel {
                ActivitySurface(
                    days: days, kind: kind, accountReachable: reachable, corpusSettled: settled
                )
                .frame(width: width, height: Self.surfaceHeight, alignment: .topLeading)
            }
            .padding(SearchLayout.shadowMargin))
        hosting.frame = root.bounds
        hosting.autoresizingMask = [.width, .height]
        root.addSubview(hosting)
        window.contentView = root
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

    /// Everything the harness draws. **All of it is invented** — no conversation, memory, task,
    /// frame or count here came from the user's capture database or from their account, and the
    /// pictures are generated on the spot.
    ///
    /// Days are built through `ActivityComposer.compose`, never assembled by hand: attachment,
    /// clustering and day counts are the rules this surface is made of, so a frame drawn from
    /// hand-arranged rows would be a picture of an arrangement the app cannot produce.
    @MainActor
    enum Fixtures {

        /// One fabricated day, as the composer's two inputs: what was said, and what was on screen.
        struct Draft {
            let daysAgo: Int
            /// Conversations the account knows about, with the title and emoji the mockup shows.
            var conversations: [(hour: Int, minute: Int, minutes: Double, emoji: String, title: String)] =
                []
            /// Conversations only this Mac heard. Deliberately kept clear of the account's windows in
            /// every fixture below, because an overlapping one is *dropped* — see
            /// `ActivityComposer.merge`, and the composition test that pins it.
            var sessions: [(hour: Int, minute: Int, minutes: Double, app: String?, lines: Int)] = []
            /// Memories, as when the account kept them.
            var memories: [(hour: Int, minute: Int, text: String)] = []
            /// Tasks, and whether they are done.
            var tasks: [(hour: Int, minute: Int, text: String, done: Bool)] = []
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
                conversations: [
                    (9, 12, 34, "🎬", "Team Refines Omi Update Video"),
                    (13, 2, 62, "📊", "Pricing review with finance"),
                ],
                sessions: [(16, 40, 3.5, nil, 5)],
                // **One of these carries a category prefix and the others do not**, because that is
                // what the account really sends: generated memories run to a template, and
                // `ActivityFormat.memoryCopy` splits the repeated half off as a quiet label over the
                // sentence. A fixture set of plain sentences would render every memory through the
                // unlabelled branch and no frame would ever show the split.
                memories: [
                    (11, 20, "Working style: prefers async written updates over standups."),
                    (11, 26, "The beta ships behind a flag, so the rename can wait."),
                    (17, 5, "Finance is copied on every invoice from now on."),
                ],
                tasks: [
                    (11, 22, "Send the migration plan to Priya before Thursday", false),
                    (11, 40, "Book the room for the beta review", true),
                    (17, 8, "Reply to the invoice thread", false),
                ],
                runs: [(9, 14, 5, 6), (10, 5, 14, 2), (13, 10, 6, 8), (18, 10, 4, 7)],
                total: 1_204)
        ]

        /// Five days, deliberately unalike: a full one, a day of screens with nobody talking, a day
        /// of talk with the screen off, a day of nothing but what the account kept, and an ordinary
        /// one. The header's subtitle drops the clause it has no count for, so a run of identical
        /// days would never show that.
        static let fiveDays: [Draft] = [
            Draft(
                daysAgo: 0,
                conversations: [(9, 12, 34, "🎬", "Team Refines Omi Update Video")],
                sessions: [(15, 20, 18, "Slack", 41)],
                memories: [
                    (11, 34, "Wants the update video under two minutes."),
                    (16, 2, "Priya owns the migration plan through the beta."),
                ],
                tasks: [(11, 36, "Cut the intro down to one line", false)],
                runs: [(9, 14, 5, 6), (11, 30, 11, 3), (15, 24, 4, 4)],
                total: 964),
            Draft(daysAgo: 1, runs: [(8, 40, 9, 5), (14, 5, 12, 4), (21, 15, 6, 6)], total: 1_881),
            Draft(
                daysAgo: 2,
                conversations: [(10, 0, 45, "🧭", "Planning the migration order")],
                sessions: [(12, 30, 8, nil, 12), (17, 5, 21, "Zoom", 63)],
                tasks: [
                    (10, 50, "Write down the rollback steps", true),
                    (17, 30, "Ask legal about the retention window", false),
                ]),
            Draft(
                daysAgo: 3,
                // A labelled memory beside an unlabelled one in the same run, so a soloed frame shows
                // both branches of the split — and shows that the dash lands on the first line of
                // each whichever branch it took.
                memories: [
                    (14, 20, "Reads the weekly digest on Sunday evenings, not Monday."),
                    (14, 24, "Filing: keeps invoices in the finance folder, never in email."),
                ]),
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

        /// A signed-out Mac: no account, so no titles, no emoji, no memories and no tasks — and the
        /// screen moments and the sessions this machine heard for itself, which have to survive.
        static let dayWithNoAccount: [Draft] = [
            Draft(
                daysAgo: 0,
                sessions: [(9, 12, 34, "Zoom", 96), (16, 40, 3.5, nil, 5)],
                runs: [(9, 14, 5, 6), (12, 5, 9, 3)],
                total: 743)
        ]

        // MARK: Building

        /// Composes drafts into the stream the surface renders. `thumbnails` empty means every frame
        /// has lost its picture.
        static func days(_ drafts: [Draft], thumbnails: [String]) -> [ActivityDay] {
            var sessions: [SessionSummary] = []
            var account = ActivityAccountFeed()
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
                for (index, spec) in draft.conversations.enumerated() {
                    let began = clock(start, hour: spec.hour, minute: spec.minute)
                    account.conversations.append(
                        ActivityAccountConversation(
                            id: "conv-\(draft.daysAgo)-\(index)",
                            title: spec.title,
                            emoji: spec.emoji,
                            startedAt: began.timeIntervalSince1970,
                            finishedAt: began.addingTimeInterval(spec.minutes * 60)
                                .timeIntervalSince1970,
                            overview: nil))
                }
                for (index, spec) in draft.memories.enumerated() {
                    account.memories.append(
                        ActivityAccountMemory(
                            id: "mem-\(draft.daysAgo)-\(index)",
                            content: spec.text,
                            at: clock(start, hour: spec.hour, minute: spec.minute)
                                .timeIntervalSince1970))
                }
                for (index, spec) in draft.tasks.enumerated() {
                    account.tasks.append(
                        ActivityAccountTask(
                            id: "task-\(draft.daysAgo)-\(index)",
                            text: spec.text,
                            completed: spec.done,
                            at: clock(start, hour: spec.hour, minute: spec.minute)
                                .timeIntervalSince1970))
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
                sessions: sessions, account: account, screen: screens, calendar: calendar)
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
