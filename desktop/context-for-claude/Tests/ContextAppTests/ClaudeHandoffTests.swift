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
            surface: .chat, url: URL(string: "claude://claude.ai/new?q=x")!),
        serverIsLoaded: ClaudeServerLiveness.State = .unknown
    ) -> ClaudeHandoff.Probe {
        ClaudeHandoff.Probe(
            desktopIsInstalled: { true },
            running: { claudes.map(\.running) },
            registeredAt: { registeredAt },
            route: { query, target in
                .success(
                    ClaudeRouter.Delivery(
                        target: target, mechanism: mechanism,
                        deliveredCharacters: query.count, wasTruncated: false))
            },
            copyToClipboard: { _ in },
            // Answers at once: the live one polls for ten seconds, and a test that waited on that
            // would be a test nobody runs.
            waitForExit: { _, done in done() },
            // `.unknown` by default so every test above this line keeps asserting the date rule it
            // was written for; the liveness cases name it explicitly.
            serverIsLoaded: { serverIsLoaded })
    }

    /// Every restart test below is about the Claude **app**, so the target is named rather than left
    /// to `SettingsStore.shared` — a test that read the real preference would pass or fail depending
    /// on what the person running it had picked in Settings.
    private func ask(
        _ claudes: [FakeClaude],
        registeredAt: Date?,
        restartingFirst: Bool,
        serverIsLoaded: ClaudeServerLiveness.State = .unknown
    ) -> TutorialClaudeAsk? {
        let probe = probe(claudes, registeredAt: registeredAt, serverIsLoaded: serverIsLoaded)
        var answer: TutorialClaudeAsk?
        ClaudeHandoff.ask(
            "what was I reading", to: .claudeApp, restartingFirst: restartingFirst, probe: probe
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

    // MARK: - A live server outranks the date

    /// **The regression this whole seam exists for.**
    ///
    /// A user ran the tutorial and Claude answered its suggested question with "I don't have access
    /// to what you were reading before this conversation started" — having called no tool at all.
    /// The MCP server process had died four minutes earlier (the app bundle was replaced underneath
    /// it) and Claude does not respawn a server that dies, so that Claude had our registration and
    /// none of our tools.
    ///
    /// Every date-based check said it was fine, and that is the bug: Claude had launched *after* we
    /// registered, so `restartIsNeeded(launchedAt:registeredAt:)` answered false, the handoff
    /// reported `mayNotReachMe: false`, and the card told the user to press Return and wait for a
    /// proof beat that could never fire. Observed liveness has to be able to overrule the proxy.
    func testAClaudeWhoseServerDiedNeedsARestartEvenThoughItPostdatesTheRegistration() {
        let launchedAfterWeRegistered = registeredAt.addingTimeInterval(300)
        XCTAssertFalse(
            ClaudeHandoff.restartIsNeeded(
                launchedAt: launchedAfterWeRegistered, registeredAt: registeredAt),
            "precondition: the date proxy on its own sees nothing wrong here")

        XCTAssertTrue(
            ClaudeHandoff.restartIsNeeded(
                launchedAt: launchedAfterWeRegistered, registeredAt: registeredAt,
                serverIsLoaded: .notServingClaudeDesktop),
            "a Claude with no live server of ours cannot call our tools, whenever it launched")
    }

    /// And the user is told so rather than left waiting. Declining the restart has to produce
    /// `mayNotReachMe`, because that is the flag the proof beat reads to say "quitting and reopening
    /// Claude is what fixes it" instead of "press Return and I will notice".
    func testADeadServerIsAdmittedToTheUserInsteadOfWaitingSilently() {
        let claude = FakeClaude(launchedAt: registeredAt.addingTimeInterval(300))
        let answer = ask(
            [claude], registeredAt: registeredAt, restartingFirst: false,
            serverIsLoaded: .notServingClaudeDesktop)

        XCTAssertEqual(claude.terminateCalls, 0, "they declined; nothing may be quit")
        XCTAssertEqual(
            answer, .prompted(restarted: false, mayNotReachMe: true),
            "the card must not imply the tools are reachable when no server is running")
    }

    /// The other direction, and a live false positive before this landed: we rewrite the config
    /// whenever the app starts, so a Claude that launched two minutes *before* that write looks stale
    /// by date while it is demonstrably serving our tools. Offering to quit it would cost somebody
    /// their conversation to fix nothing.
    func testAClaudeThatIsDemonstrablyServingOurToolsIsNeverRestarted() {
        let launchedBeforeWeRewroteTheConfig = registeredAt.addingTimeInterval(-140)
        XCTAssertTrue(
            ClaudeHandoff.restartIsNeeded(
                launchedAt: launchedBeforeWeRewroteTheConfig, registeredAt: registeredAt),
            "precondition: the date proxy alone would quit this Claude")

        let claude = FakeClaude(launchedAt: launchedBeforeWeRewroteTheConfig)
        let answer = ask(
            [claude], registeredAt: registeredAt, restartingFirst: true,
            serverIsLoaded: .servingClaudeDesktop)

        XCTAssertEqual(claude.terminateCalls, 0, "we quit a Claude that was already serving our tools")
        XCTAssertEqual(answer, .prompted(restarted: false, mayNotReachMe: false))
    }

    /// A probe that could not read the process table is not evidence, and must not start quitting
    /// applications on its own. It leaves the date rule exactly as it was.
    func testAnUnreadableProcessTableChangesNothing() {
        for launchedAt in [registeredAt.addingTimeInterval(-300), registeredAt.addingTimeInterval(300)] {
            XCTAssertEqual(
                ClaudeHandoff.restartIsNeeded(
                    launchedAt: launchedAt, registeredAt: registeredAt, serverIsLoaded: .unknown),
                ClaudeHandoff.restartIsNeeded(launchedAt: launchedAt, registeredAt: registeredAt),
                "`.unknown` has to be a no-op, not a vote")
        }
    }

    /// The consent question the card asks has to come from the same evidence the handoff acts on.
    /// A card that says "it has not read me yet" while the handoff quietly decides otherwise is how
    /// a user gets asked to give up a session for no reason.
    func testTheConsentQuestionAgreesWithTheLivenessEvidence() {
        let claude = FakeClaude(launchedAt: registeredAt.addingTimeInterval(300))
        XCTAssertTrue(
            ClaudeHandoff.restartIsNeeded(
                for: .claudeApp,
                probe: probe([claude], registeredAt: registeredAt, serverIsLoaded: .notServingClaudeDesktop)))
        XCTAssertFalse(
            ClaudeHandoff.restartIsNeeded(
                for: .claudeApp,
                probe: probe([claude], registeredAt: registeredAt, serverIsLoaded: .servingClaudeDesktop)))
    }

    /// Liveness is about this Mac's process table, not about any one Claude — but with no Claude
    /// running there is nothing to restart, so a dead server still has to end in a plain handover.
    func testADeadServerWithNoClaudeRunningIsStillJustAHandover() {
        let answer = ask(
            [], registeredAt: registeredAt, restartingFirst: true,
            serverIsLoaded: .notServingClaudeDesktop)
        XCTAssertEqual(
            answer, .prompted(restarted: false, mayNotReachMe: false),
            "launching Claude fresh loads the server, so there is nothing to warn about")
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
            desktopIsInstalled: { false },
            running: { [] },
            registeredAt: { self.registeredAt },
            route: { _, _ in .failure(.unavailable("no")) },
            copyToClipboard: { copied.append($0) },
            waitForExit: { _, done in done() })

        var answer: TutorialClaudeAsk?
        ClaudeHandoff.ask(
            "what was I reading", to: .claudeApp, restartingFirst: true, probe: probe
        ) { answer = $0 }
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
        ClaudeHandoff.ask(
            "what was I reading", to: .claudeApp, restartingFirst: false, probe: probe
        ) { answer = $0 }
        XCTAssertEqual(answer, .copiedInstead)
        XCTAssertFalse(answer?.didPrefill ?? true)
    }

    // MARK: - The target the user actually chose

    /// A store on its own defaults suite, so nothing here reads the preference of whoever is running
    /// the suite, and nothing here leaves one behind.
    private func makeSettings(_ target: ClaudeRouter.Target) -> SettingsStore {
        let suite = "context.handoff.tests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        addTeardownBlock { UserDefaults.standard.removePersistentDomain(forName: suite) }
        let store = SettingsStore(defaults: defaults, appliesToRunningApp: false)
        store.claudeTarget = target
        return store
    }

    /// A probe that records which target reached `ClaudeRouter` and answers the way the real router
    /// would for it — a pre-filled tab for the app, a running CLI for the terminal.
    private func routingProbe(
        desktopIsInstalled: Bool = true,
        running: [FakeClaude] = [],
        registeredAt: Date? = nil,
        routing: @escaping (ClaudeRouter.Target) -> Void = { _ in },
        copying: @escaping (String) -> Void = { _ in }
    ) -> ClaudeHandoff.Probe {
        ClaudeHandoff.Probe(
            desktopIsInstalled: { desktopIsInstalled },
            running: { running.map(\.running) },
            registeredAt: { registeredAt },
            route: { query, target in
                routing(target)
                let mechanism: ClaudeRouter.Mechanism =
                    target == .terminal
                    ? .terminal(cli: "/opt/homebrew/bin/claude", handler: "Ghostty")
                    : .prefilledTab(surface: .chat, url: URL(string: "claude://claude.ai/new?q=x")!)
                return .success(
                    ClaudeRouter.Delivery(
                        target: target, mechanism: mechanism,
                        deliveredCharacters: query.count, wasTruncated: false))
            },
            copyToClipboard: copying,
            waitForExit: { _, done in done() })
    }

    /// **The regression.** The handoff hard-coded `.claudeApp`, which left
    /// `Settings → Agents → Claude target` writing a key that nothing read: picking Terminal changed
    /// nothing at all, and a control that changes nothing is worse than no control, because the user
    /// believes it. Asserted for **both** values of the dropdown, on the target that reaches the
    /// router and on the answer that comes back.
    func testTheHandoffRoutesToTheTargetChosenInSettings() {
        for target in ClaudeRouter.Target.allCases {
            var routed: [ClaudeRouter.Target] = []
            var answer: TutorialClaudeAsk?
            ClaudeHandoff.ask(
                "what was I reading", restartingFirst: false,
                settings: makeSettings(target), probe: routingProbe(routing: { routed.append($0) })
            ) { answer = $0 }

            XCTAssertEqual(routed, [target], "the dropdown has to decide where the question goes")
            switch target {
            case .claudeApp:
                XCTAssertEqual(answer, .prompted(restarted: false, mayNotReachMe: false))
            case .terminal:
                XCTAssertEqual(answer, .ranInTerminal(handler: "Ghostty"))
            }
        }
    }

    /// The CLI needs no desktop app. Gating the terminal target on Claude Desktop would fail the one
    /// machine the target exists for: a Mac with `claude` on it and nothing in `/Applications`.
    func testTheTerminalTargetDoesNotNeedClaudeDesktopInstalled() {
        var copied: [String] = []
        var answer: TutorialClaudeAsk?
        ClaudeHandoff.ask(
            "what was I reading", to: .terminal, restartingFirst: false,
            probe: routingProbe(desktopIsInstalled: false, copying: { copied.append($0) })
        ) { answer = $0 }

        XCTAssertEqual(answer, .ranInTerminal(handler: "Ghostty"))
        XCTAssertTrue(copied.isEmpty, "nothing needed the clipboard: the question was handed over")
    }

    /// And it never takes somebody's Claude session to do it. A `claude` process is new every time
    /// and reads `~/.claude.json` as it starts, so there is no stale config a restart could fix —
    /// quitting the app they are using would be a cost that buys this handoff nothing.
    func testTheTerminalTargetNeverQuitsTheClaudeTheUserIsUsing() {
        let stale = FakeClaude(launchedAt: registeredAt.addingTimeInterval(-300))
        var answer: TutorialClaudeAsk?
        ClaudeHandoff.ask(
            "what was I reading", to: .terminal, restartingFirst: true,
            probe: routingProbe(running: [stale], registeredAt: registeredAt)
        ) { answer = $0 }

        XCTAssertEqual(stale.terminateCalls, 0, "the CLI target quit an app it does not even use")
        XCTAssertEqual(answer, .ranInTerminal(handler: "Ghostty"))
    }

    /// So the card must not ask for that consent either. The question "may I close and reopen
    /// Claude?" is only honest when the answer would change something.
    func testTheConsentQuestionIsOnlyEverAskedForTheAppTarget() {
        let stale = FakeClaude(launchedAt: registeredAt.addingTimeInterval(-300))
        let probe = probe([stale], registeredAt: registeredAt)

        XCTAssertTrue(ClaudeHandoff.restartIsNeeded(for: .claudeApp, probe: probe))
        XCTAssertFalse(ClaudeHandoff.restartIsNeeded(for: .terminal, probe: probe))
        XCTAssertTrue(
            ClaudeHandoff.restartIsNeeded(settings: makeSettings(.claudeApp), probe: probe),
            "the settings-reading form has to agree with the explicit one")
        XCTAssertFalse(ClaudeHandoff.restartIsNeeded(settings: makeSettings(.terminal), probe: probe))
    }

    /// No `claude` command is its own answer, and not the app's. The two say to install different
    /// things, and telling somebody to install an app they already have wastes their afternoon.
    func testAMissingClaudeCommandIsNotReportedAsAMissingApp() {
        var copied: [String] = []
        let probe = ClaudeHandoff.Probe(
            desktopIsInstalled: { true },
            running: { [] },
            registeredAt: { self.registeredAt },
            route: { _, _ in .failure(.unavailable("I can't find the claude command on this Mac.")) },
            copyToClipboard: { copied.append($0) },
            waitForExit: { _, done in done() })

        var answer: TutorialClaudeAsk?
        ClaudeHandoff.ask(
            "what was I reading", to: .terminal, restartingFirst: false, probe: probe
        ) { answer = $0 }
        XCTAssertEqual(answer, .commandNotFound)
        XCTAssertEqual(copied, ["what was I reading"], "and the question is somewhere to paste from")
    }

    /// The CLI branch fills no composer and must never read as one — but it did reach a Claude, so
    /// it is not one of the clipboard admissions either.
    func testTheTerminalAnswerIsAnArrivalWithoutBeingAPrefill() {
        let terminal = TutorialClaudeAsk.ranInTerminal(handler: "Ghostty")
        XCTAssertFalse(terminal.didPrefill, "nothing was typed into a prompt")
        XCTAssertTrue(terminal.didReachClaude, "but the question was handed to a real claude")
        XCTAssertFalse(TutorialClaudeAsk.commandNotFound.didReachClaude)
        XCTAssertFalse(TutorialClaudeAsk.commandNotFound.didPrefill)
    }
}
