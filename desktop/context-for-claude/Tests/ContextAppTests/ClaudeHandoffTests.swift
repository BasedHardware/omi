import XCTest

@testable import ContextApp

/// The one place in this app that can quit another app.
///
/// Every test here is about the same thing: `terminate` is a destructive, user-visible act — it can
/// take a conversation somebody is in the middle of — so it may only happen on evidence that it will
/// achieve something, and only when the user has agreed to it. The first version of this code
/// terminated any running Claude on the strength of "it is running", which is not evidence of
/// anything; `testARunningClaudeLaunchedAfterWeRegisteredIsNeverTerminated` is the regression.
@MainActor
final class ClaudeHandoffTests: XCTestCase {

    /// A Claude that records whether anybody asked it to quit.
    private final class FakeClaude {
        var terminateCalls = 0
        var quitsWhenAsked: Bool
        private(set) var launchedAt: Date?

        init(launchedAt: Date?, quitsWhenAsked: Bool = true) {
            self.launchedAt = launchedAt
            self.quitsWhenAsked = quitsWhenAsked
        }

        var running: ClaudeHandoff.RunningClaude {
            ClaudeHandoff.RunningClaude(
                launchedAt: launchedAt,
                terminate: { self.terminateCalls += 1 },
                hasQuit: { self.quitsWhenAsked && self.terminateCalls > 0 })
        }
    }

    private let registeredAt = Date(timeIntervalSince1970: 1_700_000_000)

    private func probe(
        _ claudes: [FakeClaude],
        registeredAt: Date?,
        mechanism: ClaudeRouter.Mechanism = .prefilledTab(
            surface: .chat, url: URL(string: "claude://claude.ai/new?q=x")!)
    ) -> ClaudeHandoff.Probe {
        ClaudeHandoff.Probe(
            isInstalled: { true },
            running: { claudes.map(\.running) },
            registeredAt: { registeredAt },
            route: { query in
                .success(
                    ClaudeRouter.Delivery(
                        target: .claudeApp, mechanism: mechanism,
                        deliveredCharacters: query.count, wasTruncated: false))
            },
            copyToClipboard: { _ in },
            // Answers at once: the live one polls for ten seconds, and a test that waited on that
            // would be a test nobody runs.
            waitForExit: { _, done in done() })
    }

    private func ask(
        _ claudes: [FakeClaude], registeredAt: Date?, restartingFirst: Bool
    ) -> TutorialClaudeAsk? {
        let probe = probe(claudes, registeredAt: registeredAt)
        var answer: TutorialClaudeAsk?
        ClaudeHandoff.ask(
            "what was I reading", restartingFirst: restartingFirst, probe: probe
        ) { answer = $0 }
        return answer
    }

    // MARK: - The decision, on its own

    func testARestartIsNeededOnlyWhenClaudePredatesTheRegistration() {
        let before = registeredAt.addingTimeInterval(-60)
        let after = registeredAt.addingTimeInterval(60)
        XCTAssertTrue(ClaudeHandoff.restartIsNeeded(launchedAt: before, registeredAt: registeredAt))
        XCTAssertFalse(ClaudeHandoff.restartIsNeeded(launchedAt: after, registeredAt: registeredAt))
    }

    /// Neither unknown is a licence to quit somebody's app. A launch date AppKit would not give us
    /// and a registration that is not on disk are both *absence* of evidence.
    func testAnUnknownDateOnEitherSideIsNotEvidence() {
        XCTAssertFalse(ClaudeHandoff.restartIsNeeded(launchedAt: nil, registeredAt: registeredAt))
        XCTAssertFalse(
            ClaudeHandoff.restartIsNeeded(launchedAt: registeredAt.addingTimeInterval(-60), registeredAt: nil))
        XCTAssertFalse(ClaudeHandoff.restartIsNeeded(launchedAt: nil, registeredAt: nil))
    }

    // MARK: - What the handoff actually does

    /// **The regression.** A Claude launched after we wrote our config already has us, so quitting
    /// it destroys the user's session and buys nothing. It must not be touched.
    func testARunningClaudeLaunchedAfterWeRegisteredIsNeverTerminated() {
        let claude = FakeClaude(launchedAt: registeredAt.addingTimeInterval(300))
        let answer = ask([claude], registeredAt: registeredAt, restartingFirst: false)

        XCTAssertEqual(claude.terminateCalls, 0, "we quit an app that already had our config")
        XCTAssertEqual(answer, .prompted(restarted: false, mayNotReachMe: false))
    }

    /// And consent does not change that. Somebody agreeing to a restart that would achieve nothing
    /// is not a reason to take their conversation.
    func testConsentDoesNotTerminateAClaudeThatDoesNotNeedIt() {
        let claude = FakeClaude(launchedAt: registeredAt.addingTimeInterval(300))
        let answer = ask([claude], registeredAt: registeredAt, restartingFirst: true)

        XCTAssertEqual(claude.terminateCalls, 0)
        XCTAssertEqual(answer, .prompted(restarted: false, mayNotReachMe: false))
    }

    /// No registration on disk: restarting would not give Claude an entry it does not have, so the
    /// quit is pointless and does not happen.
    func testNothingIsTerminatedWhenThereIsNoRegistrationToHaveMissed() {
        let claude = FakeClaude(launchedAt: Date(timeIntervalSince1970: 1))
        let answer = ask([claude], registeredAt: nil, restartingFirst: true)

        XCTAssertEqual(claude.terminateCalls, 0)
        XCTAssertEqual(answer, .prompted(restarted: false, mayNotReachMe: false))
    }

    /// A stale Claude and no consent: still not touched, and the answer says the reach may be stale
    /// so no card can imply the tools are reachable.
    func testAStaleClaudeIsNotTerminatedWithoutConsent() {
        let claude = FakeClaude(launchedAt: registeredAt.addingTimeInterval(-300))
        let answer = ask([claude], registeredAt: registeredAt, restartingFirst: false)

        XCTAssertEqual(claude.terminateCalls, 0, "declining a restart has to mean declining it")
        XCTAssertEqual(answer, .prompted(restarted: false, mayNotReachMe: true))
    }

    /// The one path that quits anything: stale, and asked for.
    func testAStaleClaudeIsRestartedOnlyWhenTheUserAgreed() {
        let claude = FakeClaude(launchedAt: registeredAt.addingTimeInterval(-300))
        let answer = ask([claude], registeredAt: registeredAt, restartingFirst: true)

        XCTAssertEqual(claude.terminateCalls, 1)
        XCTAssertEqual(answer, .prompted(restarted: true, mayNotReachMe: false))
    }

    /// `terminate` is a request, and an app with unsaved state may refuse it. What comes back has to
    /// describe what happened, not what was attempted — a Claude still running never re-read
    /// anything, so this is not a restart and the reach is still stale.
    func testAClaudeThatRefusesToQuitIsNotReportedAsRestarted() {
        let claude = FakeClaude(
            launchedAt: registeredAt.addingTimeInterval(-300), quitsWhenAsked: false)
        let answer = ask([claude], registeredAt: registeredAt, restartingFirst: true)

        XCTAssertEqual(claude.terminateCalls, 1, "it was asked")
        XCTAssertEqual(
            answer, .prompted(restarted: false, mayNotReachMe: true),
            "an attempted restart is not a restart")
    }

    /// Two Claudes, one of each: only the one a restart would help is asked to quit.
    func testOnlyTheStaleProcessIsAskedToQuit() {
        let stale = FakeClaude(launchedAt: registeredAt.addingTimeInterval(-300))
        let fresh = FakeClaude(launchedAt: registeredAt.addingTimeInterval(300))
        let answer = ask([stale, fresh], registeredAt: registeredAt, restartingFirst: true)

        XCTAssertEqual(stale.terminateCalls, 1)
        XCTAssertEqual(fresh.terminateCalls, 0, "a process that already had our config was quit")
        XCTAssertEqual(answer, .prompted(restarted: true, mayNotReachMe: false))
    }

    // MARK: - Nothing running

    func testNoRunningClaudeIsJustAHandover() {
        let answer = ask([], registeredAt: registeredAt, restartingFirst: true)
        XCTAssertEqual(answer, .prompted(restarted: false, mayNotReachMe: false))
    }

    /// A machine with no Claude Desktop reports itself rather than looking like a pre-fill.
    func testAMissingClaudeIsItsOwnAnswer() {
        var copied: [String] = []
        let probe = ClaudeHandoff.Probe(
            isInstalled: { false },
            running: { [] },
            registeredAt: { self.registeredAt },
            route: { _ in .failure(.unavailable("no")) },
            copyToClipboard: { copied.append($0) },
            waitForExit: { _, done in done() })

        var answer: TutorialClaudeAsk?
        ClaudeHandoff.ask("what was I reading", restartingFirst: true, probe: probe) { answer = $0 }
        XCTAssertEqual(answer, .notInstalled)
        XCTAssertEqual(copied, ["what was I reading"], "and the question is somewhere to paste from")
    }

    // MARK: - Which Claude the question lands in

    /// The regression. The tutorial shipped routing through `claude://code/new`, so "open Claude and
    /// type the first thing in" dropped the user into the **Code tab** — the wrong product for the
    /// beat, and not what the card had just promised.
    ///
    /// Asserted on the URL the handoff's own surface constant produces, through the real
    /// `prefillURL`, because the alternative — routing for real — opens Claude on whoever is running
    /// the suite. The expected value is not this change's invention: `claude://claude.ai/new?q=…` is
    /// the documented "new chat with prefilled prompt (not sent)" link in *Open Claude Desktop with a
    /// link* (support.claude.com/en/articles/14729294), and it is the `ClaudeAIPath.New` branch of the
    /// installed app's own URL handler, which builds `/new?q=…` and navigates to it.
    func testTheTutorialHandsOffToANewChatAndNotTheCodeTab() throws {
        XCTAssertEqual(ClaudeHandoff.surface, .chat)
        let url = try XCTUnwrap(
            ClaudeRouter.prefillURL(for: "what was I working on today?", surface: ClaudeHandoff.surface))
        XCTAssertEqual(url.scheme, "claude", url.absoluteString)
        XCTAssertEqual(url.host, "claude.ai", url.absoluteString)
        XCTAssertEqual(url.path, "/new", url.absoluteString)
        XCTAssertNotEqual(url.host, "code", "the Code tab is not where the tutorial's question goes")
        let components = try XCTUnwrap(URLComponents(url: url, resolvingAgainstBaseURL: false))
        XCTAssertEqual(
            components.queryItems,
            [URLQueryItem(name: "q", value: "what was I working on today?")],
            "the prompt still arrives pre-filled, and `q` is what fills it")
    }

    /// The degrade chain is unchanged by the surface move: only a real pre-fill may look like one.
    func testOnlyARealPrefillOnTheChatSurfaceReportsAPrefill() {
        let chat = ClaudeRouter.Mechanism.prefilledTab(
            surface: .chat, url: URL(string: "claude://claude.ai/new?q=x")!)
        XCTAssertTrue(chat.note.contains("chat"), chat.note)
        XCTAssertFalse(chat.note.contains("Claude Code"), chat.note)
        XCTAssertFalse(ClaudeRouter.Mechanism.clipboard.note.contains("prompt"))
    }

    /// No `claude://` handler is the clipboard branch, and it is never a pre-fill.
    func testNoSchemeHandlerIsReportedAsTheClipboard() {
        let probe = probe([], registeredAt: registeredAt, mechanism: .clipboard)
        var answer: TutorialClaudeAsk?
        ClaudeHandoff.ask("what was I reading", restartingFirst: false, probe: probe) { answer = $0 }
        XCTAssertEqual(answer, .copiedInstead)
        XCTAssertFalse(answer?.didPrefill ?? true)
    }
}
