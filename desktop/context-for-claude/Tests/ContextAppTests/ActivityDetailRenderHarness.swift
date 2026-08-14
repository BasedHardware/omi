import AppKit
import ContextCore
import SwiftUI
import XCTest

@testable import ContextApp

/// Renders the Activity **detail** — the screen a row on the spine opens into — as it really
/// composites, and writes the frames out for a person to look at.
///
/// A file of its own rather than more cases inside `ActivityRenderHarness`, because the two harnesses
/// have different subjects: that one draws the spine, this one draws what a click on it opens. The
/// class name keeps `ActivityRenderHarness` as a prefix on purpose, so the documented
/// `--filter ActivityRenderHarness` run still renders both surfaces in one pass.
///
/// **Skipped unless `CONTEXT_ACTIVITY_RENDER=1`** (`CONTEXT_ACTIVITY_RENDER_DIR` moves the output),
/// for the reasons the sibling harness states: it puts windows on screen and shells out to
/// `screencapture`, and the claims that must hold every time live in `ActivityDetailTests`.
///
/// The two rules the sibling states are obeyed here too. **Live views and a run loop, never
/// `ImageRenderer`** — the panel is `.behindWindow` glass and an offscreen renderer has no window for
/// it to be behind. **Nothing of the user's is ever captured** — a full-screen opaque backdrop covers
/// the exact rectangle that is grabbed, and every conversation, memory, task and transcript line
/// below is fabricated on the spot. `ActivityDetailModel(state:)` takes no reader at all, so nothing
/// drawn here can reach the account.
final class ActivityRenderHarnessDetail: XCTestCase {

    private var outputDirectory: URL {
        URL(
            fileURLWithPath: ProcessInfo.processInfo.environment["CONTEXT_ACTIVITY_RENDER_DIR"]
                ?? NSTemporaryDirectory() + "activity-renders")
    }

    /// The room the detail really gets: the search panel's lower body, which is the one place
    /// `ActivitySurface` — and therefore this screen — mounts.
    private static let surfaceWidth: CGFloat = SearchLayout.panelWidth
    private static let surfaceHeight: CGFloat = SearchLayout.maximumResultsBodyHeight

    @MainActor
    func testRenderTheActivityDetail() throws {
        try XCTSkipUnless(
            ProcessInfo.processInfo.environment["CONTEXT_ACTIVITY_RENDER"] == "1",
            "on-screen render harness; set CONTEXT_ACTIVITY_RENDER=1 to run it")
        _ = InkTestFonts.registered

        let directory = outputDirectory
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        NSApplication.shared.setActivationPolicy(.accessory)

        let cases:
            [(
                name: String, request: ActivityDetailRequest, state: ActivityDetailModel.State,
                transcript: Bool, focused: Set<String>
            )] = [
                // **The screen the reference draws, and the one this harness exists to check.** A
                // conversation opens on its *summary*: the account's overview, the metadata chips,
                // what an app made of it, and the action items — with the lines behind the header's
                // control rather than in front of everything else.
                (
                    "20-conversation-summary", Fixtures.accountConversation,
                    .read(Fixtures.accountBody), false, []
                ),
                // …and the other pane, which is one press away. Its header is the reference's drawer
                // header: the word, the count, the way back and the one control from the reference's
                // toolbar this app can honour.
                (
                    "21-conversation-transcript", Fixtures.accountConversation,
                    .read(Fixtures.accountBody), true, []
                ),
                // …and the pane as an action item's `Source` control leaves it: the same transcript,
                // scrolled to the line the account says the commitment came from and with that line
                // marked. It is the whole reason a summary-first screen is navigable rather than
                // merely shorter, and it is reachable only by a press — hence the harness knob.
                (
                    "21b-conversation-transcript-focused", Fixtures.accountConversation,
                    .read(Fixtures.accountBody), true, Fixtures.focusedSegmentIDs
                ),
                // A session only this Mac heard: no emoji, no summary, no category, and no second
                // pane — its lines *are* the conversation, over a sentence saying why. It is also
                // the one source that really does know which voice was yours, which is the only
                // thing that puts a line on the trailing edge.
                (
                    "22-conversation-local", Fixtures.localConversation, .read(Fixtures.localBody),
                    false, []
                ),
                // The read that has not come back yet. The header is already whole — this is what
                // makes a slow account cost the body and nothing else.
                ("23-conversation-reading", Fixtures.accountConversation, .reading, false, []),
                // The state the account is actually in a good deal of the time. A sentence somebody
                // can act on, and a way to ask again.
                (
                    "24-conversation-rate-limited", Fixtures.accountConversation,
                    .unread(ActivityDetailCopy.rateLimited), false, []
                ),
                // The other failure worth looking at: one the user fixes.
                (
                    "25-conversation-signed-out", Fixtures.accountConversation,
                    .unread(ActivityDetailCopy.signedOut), false, []
                ),
                // Read, and genuinely empty. Not a failure, and it must not look like one.
                (
                    "26-conversation-no-transcript", Fixtures.accountConversation,
                    .read(
                        ActivityConversationBody(
                            overview: Fixtures.overview, category: "work", source: "Desktop")),
                    true, []
                ),
                // The account finished and made nothing of it. Three chips and a sentence saying so
                // — the reference's page is never this bare because of sections we dropped.
                (
                    "27-conversation-no-summary", Fixtures.accountConversation,
                    .read(ActivityConversationBody(source: "Desktop", lines: Fixtures.accountBody.lines)),
                    false, []
                ),
                // The account is still working on it, which is why the page is thin.
                (
                    "28-conversation-processing", Fixtures.accountConversation,
                    .read(ActivityConversationBody(source: "Desktop", status: .processing)), false, []
                ),
                // …and the account gave up on it, which is a different sentence with no wait in it.
                (
                    "29-conversation-failed", Fixtures.accountConversation,
                    .read(
                        ActivityConversationBody(
                            source: "Desktop", status: .failed, lines: Fixtures.accountBody.lines)),
                    false, []
                ),
                // A memory, with the conversation that was running at the time — and the caveat that
                // keeps that from being a provenance claim.
                ("30-memory", Fixtures.memory, .reading, false, []),
                // …and one kept in a minute nothing else was happening in.
                ("31-memory-alone", Fixtures.memoryAlone, .reading, false, []),
                ("32-task-open", Fixtures.task, .reading, false, []),
                ("33-task-done", Fixtures.taskDone, .reading, false, []),
            ]

        var written: [String] = []
        for (name, request, state, transcript, focused) in cases {
            // Both system appearances, and **the pair is expected to be identical**: `InkGlass.pin`
            // holds this surface light on a Dark Mac, and the Dark pass is what proves the pin.
            for (appearance, suffix) in [
                (NSAppearance.Name.aqua, "light"), (NSAppearance.Name.darkAqua, "dark"),
            ] {
                written.append(
                    try render(
                        name: "\(name)-\(suffix)", request: request, state: state,
                        showsTranscript: transcript, focused: focused, appearance: appearance,
                        in: directory))
            }
        }

        print("\n=== activity detail renders ===")
        for path in written { print(path) }
        print("===============================\n")
    }

    // MARK: - Rendering

    @MainActor
    private func render(
        name: String,
        request: ActivityDetailRequest,
        state: ActivityDetailModel.State,
        showsTranscript: Bool,
        focused: Set<String>,
        appearance: NSAppearance.Name,
        in directory: URL
    ) throws -> String {
        NSApp.appearance = NSAppearance(named: appearance)

        let screen = try XCTUnwrap(NSScreen.main)
        let windowSize = NSSize(
            width: Self.surfaceWidth + SearchLayout.shadowMargin * 2,
            height: Self.surfaceHeight + SearchLayout.shadowMargin * 2)
        let inset: CGFloat = 34
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
        // `.screenSaver`, not `.floating`: the backdrop is the whole privacy guarantee, and at
        // `.floating` another application's panel can sit above it and land inside the capture.
        backdrop.level = .screenSaver
        backdrop.contentView = {
            let view = NSImageView(frame: NSRect(origin: .zero, size: backdropFrame.size))
            view.image = ActivityRenderHarness.Fixtures.desktop
            view.imageScaling = .scaleAxesIndependently
            return view
        }()
        backdrop.orderFrontRegardless()

        let windowFrame = NSRect(
            x: backdropFrame.minX + inset, y: backdropFrame.minY + inset,
            width: windowSize.width, height: windowSize.height)
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
                ActivityDetailView(
                    request: request, model: ActivityDetailModel(state: state), onBack: {},
                    showsTranscript: showsTranscript, focusedSegmentIDs: focused
                )
                .frame(
                    width: Self.surfaceWidth, height: Self.surfaceHeight, alignment: .topLeading)
            }
            .padding(SearchLayout.shadowMargin))
        hosting.frame = root.bounds
        hosting.autoresizingMask = [.width, .height]
        root.addSubview(hosting)
        window.contentView = root
        window.orderFrontRegardless()

        // A run loop, not a sleep: the glass samples the desktop through the window server and
        // SwiftUI settles its layout, neither of which happens on a blocked thread.
        spin(seconds: 1.4)

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

    /// `screencapture -R`, over the rectangle the backdrop window fully covers — never the screen,
    /// which on this machine has the user's own work on it.
    private func capture(rect: NSRect, on screen: NSScreen, to url: URL) -> Bool {
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
}

// MARK: - Fabricated data

extension ActivityRenderHarnessDetail {

    /// Everything these frames draw. **All of it is invented** — no conversation, transcript line,
    /// memory or task here came from the user's account or from their capture database.
    @MainActor
    enum Fixtures {
        private static let started = Date().addingTimeInterval(-4 * 3_600)

        static let overview =
            "Finance wants the enterprise tier held until the beta lands. Priya owns the migration "
            + "plan through the rollout, and the rename waits until after the release."

        static let accountConversation = ActivityDetailRequest.conversation(
            ActivityConversation(
                id: "conv-1", source: .account, title: "Pricing review with finance", emoji: "📊",
                startedAt: started, duration: 22 * 60, overview: overview))

        static let localConversation = ActivityDetailRequest.conversation(
            ActivityConversation(
                // The only title a local session can have — see `ActivityConversation`. A fixture
                // naming the app would draw a picture of a headline the app cannot produce.
                id: ActivityConversation.localID(7), source: .local,
                title: ActivityConversation.untitled,
                startedAt: started.addingTimeInterval(2 * 3_600), duration: 6 * 60, segmentCount: 6))

        /// The whole of what a read buys: the summary half the reference puts first, and a
        /// transcript long enough to run past the panel's fold so the other pane shows the scroll
        /// rather than a page that happens to fit.
        static let accountBody = ActivityConversationBody(
            overview: overview,
            category: "work",
            source: "Desktop",
            actionItems: [
                // One with the segments the account says it came from, so the frame shows `Source`…
                ActivityActionItem(
                    id: "a1", text: "Send the migration plan to Priya before Thursday",
                    isCompleted: false, sourceSegmentIDs: ["s2"]),
                // …and one without, which is the far commoner shape and says `Transcript` instead.
                ActivityActionItem(
                    id: "a2", text: "Write the rollback steps down", isCompleted: false,
                    sourceSegmentIDs: []),
                ActivityActionItem(
                    id: "a3", text: "Book the room for the beta review", isCompleted: true,
                    sourceSegmentIDs: []),
            ],
            appResults: [
                // **Markdown, because that is what an app really sends.** Every reading on this
                // screen was written by a language model and arrives with `**bold**` sub-headings
                // and `- ` bullets in it; a fixture of one flat paragraph is a fixture that cannot
                // fail when the renderer stops rendering. Under the fold, so the frame shows the
                // whole shape rather than the disclosure control.
                ActivityAppResult(
                    id: "r1",
                    content: """
                        **Decisions**
                        - The enterprise tier is held until the beta ships.
                        - The migration plan goes out Thursday morning.

                        **Still open**
                        - Nobody has said who owns the rename once the release is out — the thread \
                        most likely to be dropped between now and then.
                        """)
            ],
            lines: script.enumerated().map { index, line in
                ActivityTranscriptLine(
                    id: "s\(index)", speaker: index.isMultiple(of: 2) ? "Priya" : "Marcus",
                    isYou: false, text: line, offset: Double(index) * 23 + 4)
            })

        /// The local half: `Hit.kind` is exactly the claim "this one was you", so this is the only
        /// body with a line on the trailing edge — and the only field of the summary half a capture
        /// database can honestly fill is where the lines were heard.
        static let localBody = ActivityConversationBody(
            source: ActivityDetailCopy.localSourceLabel,
            lines: script.prefix(6).enumerated().map { index, line in
                ActivityTranscriptLine(
                    id: "l\(index)", speaker: index.isMultiple(of: 2) ? "You" : "Someone else",
                    isYou: index.isMultiple(of: 2), text: line, offset: Double(index) * 17)
            })

        /// The line the first action item above says it came from. The same id the transcript
        /// fixture gives that line, so the mark lands on the sentence the commitment was made in
        /// rather than on whichever line happened to be third.
        static let focusedSegmentIDs: Set<String> = ["s2"]

        private static let script = [
            "Where did we land on the enterprise tier?",
            "We're holding it until the beta ships — finance would rather not price two things at once.",
            "That works. Does the migration plan still go out Thursday?",
            "Thursday morning. I'll copy you both when it does.",
            "One more thing: the rename.",
            "After the release. Nobody wants to do a rename and a migration in the same week.",
            "Agreed. I'll write the rollback steps down before Thursday so we're not doing it live.",
            "Send them to me when they're written and I'll read them through.",
        ]

        static let memory = ActivityDetailRequest(
            subject: .memory(
                ActivityMemory(
                    id: "m1",
                    text: "Finance is copied on every invoice from now on, and invoices live in the "
                        + "finance folder rather than in email.",
                    timestamp: started.addingTimeInterval(11 * 60))),
            during: conversation)

        static let memoryAlone = ActivityDetailRequest(
            subject: .memory(
                ActivityMemory(
                    id: "m2", text: "Reads the weekly digest on Sunday evenings, not Monday.",
                    timestamp: started.addingTimeInterval(6 * 3_600))),
            during: nil)

        static let task = ActivityDetailRequest(
            subject: .task(
                ActivityTask(
                    id: "t1", text: "Send the migration plan to Priya before Thursday",
                    isCompleted: false, timestamp: started.addingTimeInterval(14 * 60))),
            during: conversation)

        static let taskDone = ActivityDetailRequest(
            subject: .task(
                ActivityTask(
                    id: "t2", text: "Book the room for the beta review", isCompleted: true,
                    timestamp: started.addingTimeInterval(18 * 60))),
            during: conversation)

        /// The conversation the memory and task details show as "what was happening then".
        private static let conversation = ActivityConversation(
            id: "conv-1", source: .account, title: "Pricing review with finance", emoji: "📊",
            startedAt: started, duration: 22 * 60, segmentCount: 0, overview: overview,
            momentCount: 6)
    }
}
