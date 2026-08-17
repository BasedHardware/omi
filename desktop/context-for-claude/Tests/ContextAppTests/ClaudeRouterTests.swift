import AppKit
import XCTest
@testable import ContextApp

/// The routing layer, asserted where it is deterministic: the URL, the truncation, the launcher
/// script, and which binary gets picked.
///
/// The parts that talk to LaunchServices are exercised through `Probe`, so the suite says nothing
/// about whether Claude happens to be installed on the machine running it.
final class ClaudeRouterTests: XCTestCase {

    // MARK: - The deep link

    /// This is the whole product claim — "opens Claude with the prompt pre-filled" — and it rests on
    /// these exact hosts, paths, and the parameter name.
    ///
    /// Both values are documented in *Open Claude Desktop with a link*
    /// (support.claude.com/en/articles/14729294): `claude://claude.ai/new?q=…` is "new chat with
    /// prefilled prompt (not sent)" and `claude://code/new?q=…` is "Claude Code with prefilled
    /// composer text". Both are also branches of the installed app's own URL handler, which reads `q`,
    /// caps it, and navigates — `claude.ai/new` to the chat surface, `code/new` to Claude Code.
    func testEachSurfaceIsTheDeepLinkClaudeActuallyRoutes() throws {
        let chat = try XCTUnwrap(ClaudeRouter.prefillURL(for: "what was I working on today?", surface: .chat))
        XCTAssertEqual(chat.scheme, "claude")
        XCTAssertEqual(chat.host, "claude.ai")
        XCTAssertEqual(chat.path, "/new")

        let code = try XCTUnwrap(ClaudeRouter.prefillURL(for: "what was I working on today?", surface: .code))
        XCTAssertEqual(code.scheme, "claude")
        XCTAssertEqual(code.host, "code")
        XCTAssertEqual(code.path, "/new")

        for url in [chat, code] {
            let components = try XCTUnwrap(URLComponents(url: url, resolvingAgainstBaseURL: false))
            XCTAssertEqual(
                components.queryItems, [URLQueryItem(name: "q", value: "what was I working on today?")],
                url.absoluteString)
        }
    }

    /// A question with a `&`, a `#`, or a `+` in it has to survive the trip intact — a fragment in
    /// particular is dropped on the far side, so an unescaped `#` would silently truncate the prompt.
    func testCharactersThatWouldBreakAURLArePercentEncoded() throws {
        let query = "ship it? A&B #1 + 2 = 3 / 100%"
        for surface in ClaudeRouter.Surface.allCases {
            let url = try XCTUnwrap(ClaudeRouter.prefillURL(for: query, surface: surface))
            XCTAssertNil(url.fragment, url.absoluteString)
            let components = try XCTUnwrap(URLComponents(url: url, resolvingAgainstBaseURL: false))
            XCTAssertEqual(components.queryItems?.first?.value, query, url.absoluteString)
        }
    }

    func testAnEmptyOrBlankQueryProducesNoURL() {
        XCTAssertNil(ClaudeRouter.prefillURL(for: "", surface: .chat))
        XCTAssertNil(ClaudeRouter.prefillURL(for: "   \n\t ", surface: .chat))
        XCTAssertNil(ClaudeRouter.prefillURL(for: "", surface: .code))
        XCTAssertNil(ClaudeRouter.prefillURL(for: "   \n\t ", surface: .code))
    }

    /// Claude cuts the prompt at 14 336 characters before it reaches the composer, so we cut it at the
    /// same number and say we did rather than handing over a string we know gets clipped.
    func testAnOverlongQueryIsTruncatedToTheLimitClaudeAccepts() throws {
        XCTAssertEqual(ClaudeRouter.promptLimit, 14_336)
        let query = String(repeating: "a", count: ClaudeRouter.promptLimit + 500)
        let url = try XCTUnwrap(ClaudeRouter.prefillURL(for: query, surface: .chat))
        let components = try XCTUnwrap(URLComponents(url: url, resolvingAgainstBaseURL: false))
        XCTAssertEqual(components.queryItems?.first?.value?.count, ClaudeRouter.promptLimit)
    }

    // MARK: - Finding the CLI

    /// A GUI app inherits almost no `PATH`, so the candidate list is the whole mechanism — and the
    /// place `claude` actually installs itself has to be on it.
    func testTheCandidateListCoversWhereClaudeInstallsItself() {
        let candidates = ClaudeRouter.defaultCLICandidates(home: "/Users/example")
        XCTAssertTrue(candidates.contains("/Users/example/.local/bin/claude"), "\(candidates)")
        XCTAssertTrue(candidates.contains("/Users/example/.claude/local/claude"), "\(candidates)")
        XCTAssertTrue(candidates.contains("/opt/homebrew/bin/claude"), "\(candidates)")
        XCTAssertTrue(candidates.contains("/usr/local/bin/claude"), "\(candidates)")
    }

    func testTheFirstExecutableCandidateWins() {
        let candidates = ["/a/claude", "/b/claude", "/c/claude"]
        XCTAssertEqual(
            ClaudeRouter.claudeCLIPath(candidates: candidates, isExecutable: { $0 != "/a/claude" }),
            "/b/claude")
        XCTAssertNil(ClaudeRouter.claudeCLIPath(candidates: candidates, isExecutable: { _ in false }))
    }

    // MARK: - Availability

    private func probe(
        claudeHandler: URL? = nil, terminalHandler: URL? = nil, executable: @escaping (String) -> Bool = { _ in false }
    ) -> ClaudeRouter.Probe {
        ClaudeRouter.Probe(
            handlerForClaudeScheme: { claudeHandler },
            handlerForCommandFiles: { terminalHandler },
            isExecutable: { executable($0) },
            claudeCLICandidates: ["/opt/fake/claude"])
    }

    /// The row names the app that will actually open, not "Claude" — if something else claimed the
    /// scheme, saying "Claude" would be a lie. And it names the *surface* it will open there, so the
    /// promise made before routing is the one `route` keeps.
    func testTheClaudeAppRowNamesTheAppAndTheSurfaceThatWillOpen() {
        let claude = probe(claudeHandler: URL(fileURLWithPath: "/Applications/Claude.app"))
        let code = ClaudeRouter.availability(of: .claudeApp, surface: .code, probe: claude)
        XCTAssertTrue(code.isAvailable)
        XCTAssertTrue(code.detail.contains("Claude"), code.detail)
        XCTAssertTrue(code.detail.contains("prompt"), code.detail)
        XCTAssertTrue(code.detail.contains("Claude Code tab"), code.detail)

        let chat = ClaudeRouter.availability(of: .claudeApp, surface: .chat, probe: claude)
        XCTAssertTrue(chat.detail.contains("new Claude chat"), chat.detail)
        XCTAssertFalse(chat.detail.contains("Claude Code"), chat.detail)
    }

    /// With no handler the row says so *and* says what would happen instead. A dropdown option that
    /// silently degrades to the clipboard is the dishonest version of this.
    func testWithNoSchemeHandlerTheRowAdmitsItWouldUseTheClipboard() {
        let availability = ClaudeRouter.availability(of: .claudeApp, surface: .code, probe: probe())
        XCTAssertFalse(availability.isAvailable)
        XCTAssertTrue(availability.detail.contains("clipboard"), availability.detail)
    }

    func testTheTerminalRowIsMissingWhenTheCLIIsNotOnDisk() {
        let availability = ClaudeRouter.availability(of: .terminal, surface: .code, probe: probe())
        XCTAssertFalse(availability.isAvailable)
        XCTAssertTrue(availability.detail.contains("claude command"), availability.detail)
    }

    /// It names the terminal the user actually chose for `.command` files, not Terminal.app by fiat.
    func testTheTerminalRowNamesWhicheverTerminalOwnsCommandFiles() {
        let availability = ClaudeRouter.availability(
            of: .terminal,
            surface: .code,
            probe: probe(
                terminalHandler: URL(fileURLWithPath: "/Applications/Ghostty.app"), executable: { _ in true }))
        XCTAssertTrue(availability.isAvailable)
        XCTAssertTrue(availability.detail.contains("Ghostty"), availability.detail)
    }

    /// The Settings row's subtitle is these two sentences, so it describes both options as they
    /// really are on the machine reading it — including the one that is not there.
    ///
    /// This is the copy `SettingsAgentsPane` shows under "Claude target". It is asked about
    /// `ClaudeHandoff.surface` because that is the surface the handoff really opens; a row promising
    /// a Claude Code tab while the handoff opens a chat would be the same mismatch, one layer up.
    func testTheTargetSubtitleDescribesBothOptionsHonestly() {
        let both = ClaudeRouter.targetSubtitle(
            surface: .chat,
            probe: probe(
                claudeHandler: URL(fileURLWithPath: "/Applications/Claude.app"),
                terminalHandler: URL(fileURLWithPath: "/Applications/Ghostty.app"),
                executable: { _ in true }))
        XCTAssertTrue(both.contains("new Claude chat"), both)
        XCTAssertTrue(both.contains("Ghostty"), both)

        // Neither absence is hidden: a row that quietly described a target this Mac cannot reach is
        // exactly the dropdown-that-lies this copy exists to prevent.
        let neither = ClaudeRouter.targetSubtitle(surface: .chat, probe: probe())
        XCTAssertTrue(neither.contains("clipboard"), neither)
        XCTAssertTrue(neither.contains("claude command"), neither)
    }

    @MainActor
    func testRoutingAnEmptyQueryFailsBeforeItTouchesAnything() {
        for surface in ClaudeRouter.Surface.allCases {
            XCTAssertEqual(
                ClaudeRouter.route("  ", to: .claudeApp, surface: surface, probe: probe()),
                .failure(.emptyQuery))
        }
    }

    @MainActor
    func testRoutingToTerminalWithoutTheCLIFailsWithAnHonestSentence() {
        let result = ClaudeRouter.route("hello", to: .terminal, surface: .code, probe: probe())
        guard case .failure(.unavailable(let sentence)) = result else {
            return XCTFail("expected an unavailable failure, got \(result)")
        }
        XCTAssertTrue(sentence.contains("claude command"), sentence)
    }

    // MARK: - The launcher

    /// The one place a query becomes something a shell will evaluate. A question containing a backtick
    /// or a `;` must stay a question.
    func testQuotingNeutralisesEverythingAShellWouldActOn() {
        XCTAssertEqual(ClaudeRouter.shellQuoted("plain"), "'plain'")
        XCTAssertEqual(ClaudeRouter.shellQuoted("it's"), "'it'\\''s'")
        XCTAssertEqual(
            ClaudeRouter.shellQuoted("`whoami`; rm -rf ~ && echo $HOME"),
            "'`whoami`; rm -rf ~ && echo $HOME'")
    }

    /// Asserted through a real shell, because "the string looks escaped" is not the property that
    /// matters — "`sh` sees exactly one argument, and it is the question" is.
    ///
    /// A single quote is the one character that can end the quoting, so every case here is built out
    /// of one. Hermetic: `/bin/sh` and nothing else.
    func testAShellSeesTheQueryAsOneArgumentWhateverIsInIt() throws {
        for query in [
            "'; touch /tmp/context-pwned; echo '",
            "what's up",
            "`whoami`",
            "$(id) ${HOME} $HOME",
            "a && b || c ; d | e > f",
            "newline\nand\ttab",
        ] {
            let quoted = ClaudeRouter.shellQuoted(query)
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/bin/sh")
            // The quoted form goes inside `-c` so the shell is the thing that parses it — passing it
            // as an argv element instead would prove nothing at all. `$#` then says it survived as one
            // argument, and `$1` says it survived unchanged.
            process.arguments = ["-c", "set -- \(quoted); printf '%s|%s' \"$#\" \"$1\""]
            let pipe = Pipe()
            process.standardOutput = pipe
            try process.run()
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            XCTAssertEqual(String(decoding: data, as: UTF8.self), "1|\(query)", "for \(query.debugDescription)")
            XCTAssertFalse(
                FileManager.default.fileExists(atPath: "/tmp/context-pwned"),
                "the quoting let a command through")
        }
    }

    /// The file holds what the user typed, so it must not outlive the window it opens.
    func testTheLauncherDeletesItselfBeforeItRunsAnything() {
        let script = ClaudeRouter.launcherScript(cli: "/bin/claude", query: "hello")
        let lines = script.split(separator: "\n").map(String.init)
        let removeIndex = try? XCTUnwrap(lines.firstIndex { $0.hasPrefix("rm -f") })
        let execIndex = try? XCTUnwrap(lines.firstIndex { $0.hasPrefix("exec ") })
        XCTAssertNotNil(removeIndex)
        XCTAssertNotNil(execIndex)
        if let removeIndex, let execIndex { XCTAssertLessThan(removeIndex, execIndex) }
        XCTAssertTrue(script.hasPrefix("#!/bin/sh"), script)
        XCTAssertTrue(script.contains("exec '/bin/claude' 'hello'"), script)
    }

    /// `claude` needs a working directory; home is the honest neutral choice, and an unset `$HOME` must
    /// not leave it running somewhere arbitrary.
    func testTheLauncherRunsFromHomeOrNotAtAll() {
        let script = ClaudeRouter.launcherScript(cli: "/bin/claude", query: "hello")
        XCTAssertTrue(script.contains(#"cd "$HOME" || exit 1"#), script)
    }

    // MARK: - The search bar's Return

    /// A launcher that records what it was asked for and answers however the case needs, so nothing
    /// here opens an application on whoever is running the suite.
    private func launcher(
        answering result: Result<ClaudeRouter.Delivery, ClaudeRouter.RouteError>,
        recording asked: @escaping (String, ClaudeRouter.Target) -> Void = { _, _ in }
    ) -> ClaudeRouter.Route {
        { query, target in
            asked(query, target)
            return result
        }
    }

    private func delivery(
        _ mechanism: ClaudeRouter.Mechanism, to target: ClaudeRouter.Target = .claudeApp
    ) -> ClaudeRouter.Delivery {
        ClaudeRouter.Delivery(
            target: target, mechanism: mechanism, deliveredCharacters: 1, wasTruncated: false)
    }

    /// The bar's two targets are one product in two shells, and this is the constant that makes that
    /// true: `.terminal` runs the `claude` CLI, which is Claude Code, so the app target opens the
    /// Claude Code tab rather than the ordinary chat. The tutorial's `.chat` is the deliberate other
    /// choice — see `ClaudeHandoff.surface` — and the two must not collapse into one.
    @MainActor
    func testTheBarOpensTheClaudeCodeTabAndTheTutorialDoesNot() throws {
        XCTAssertEqual(ClaudeRouter.searchSurface, .code)
        XCTAssertNotEqual(ClaudeRouter.searchSurface, ClaudeHandoff.surface)
        let url = try XCTUnwrap(
            ClaudeRouter.prefillURL(for: "what was that invoice site", surface: ClaudeRouter.searchSurface))
        XCTAssertEqual(url.host, "code", url.absoluteString)
    }

    /// **What the bar was asked to hand over is exactly what was typed, and it goes to the target the
    /// user picked.** Nothing is appended, nothing is inferred from the results on screen.
    @MainActor
    func testTheQuestionHandedOverIsTheQuestionInTheFieldAndNothingElse() {
        for target in ClaudeRouter.Target.allCases {
            var asked: [(String, ClaudeRouter.Target)] = []
            _ = ClaudeRouter.handOff(
                "what was that invoice site", to: target,
                using: launcher(
                    answering: .success(delivery(.terminal(cli: "/opt/homebrew/bin/claude", handler: "Ghostty"))),
                    recording: { asked.append(($0, $1)) }))
            XCTAssertEqual(asked.map(\.0), ["what was that invoice site"])
            XCTAssertEqual(asked.map(\.1), [target], "the dropdown has to decide where the question goes")
        }
    }

    /// A real delivery is the panel's cue to get out of the way, and the *only* one. Both mechanisms
    /// that put the question in front of the user count; neither says anything, because Claude coming
    /// forward with the prompt in it says it better than a note line could.
    @MainActor
    func testOnlyADeliveryTheUserCanSeeDismissesThePanel() throws {
        let url = try XCTUnwrap(ClaudeRouter.prefillURL(for: "x", surface: .code))
        for mechanism in [
            ClaudeRouter.Mechanism.prefilledTab(surface: .code, url: url),
            .terminal(cli: "/opt/homebrew/bin/claude", handler: "Ghostty"),
        ] {
            XCTAssertEqual(
                ClaudeRouter.handOff("x", to: .claudeApp, using: launcher(answering: .success(delivery(mechanism)))),
                .arrived(delivery(mechanism)))
        }
    }

    /// **The clipboard branch is not a delivery the panel may dismiss on.** It reached Claude and
    /// filled nothing in, so the one sentence that tells the user to paste has to still be on screen
    /// — dismissing here would leave somebody looking at an empty composer with no idea why.
    @MainActor
    func testTheClipboardFallbackKeepsThePanelUpAndSaysToPaste() {
        let handoff = ClaudeRouter.handOff(
            "x", to: .claudeApp, using: launcher(answering: .success(delivery(.clipboard))))
        guard case .note(let sentence) = handoff else {
            return XCTFail("a clipboard fallback dismissed the panel: \(handoff)")
        }
        XCTAssertTrue(sentence.contains("paste"), sentence)
    }

    /// **A question that goes nowhere must never go nowhere quietly.** Every failure the router can
    /// report comes back as a sentence for the note line — a Mac with no Claude, a Mac with no
    /// `claude` command — because a Return that appeared to do nothing is the failure this return
    /// type exists to make impossible.
    @MainActor
    func testAClaudeThatCannotBeReachedIsSaidOutLoud() {
        for error in [
            ClaudeRouter.RouteError.unavailable("I can't find Claude on this Mac."),
            .unavailable("I can't find the claude command on this Mac."),
            .couldNotPrepare("I couldn't start Terminal: no."),
        ] {
            XCTAssertEqual(
                ClaudeRouter.handOff("x", to: .claudeApp, using: launcher(answering: .failure(error))),
                .note(error.sentence))
        }
    }

    /// **Return on an empty bar launches nothing**, and it is decided before any launcher is reached.
    /// A window switch nobody asked for is the worst thing an accidental keypress on a summoned panel
    /// could do.
    func testReturnOnAnEmptyFieldNeverReachesClaude() {
        for empty in ["", "   ", "\n\t "] {
            XCTAssertEqual(
                SearchBarView.returnMeans(query: empty, hasSelection: false), .readAgain,
                "\(empty.debugDescription) was treated as a question")
        }
    }

    /// A selected card outranks the question: the selection exists so Return can open it, and a
    /// highlighted result that Return sent to Claude instead would be a dead end.
    func testASelectedResultStillOwnsReturn() {
        XCTAssertEqual(
            SearchBarView.returnMeans(query: "what was that invoice site", hasSelection: true),
            .openTheSelection)
        XCTAssertEqual(SearchBarView.returnMeans(query: "", hasSelection: true), .openTheSelection)
    }

    /// And with a question typed and nothing selected, Return is the handoff — trimmed, so the
    /// trailing space left by a paste is not part of what Claude is asked.
    func testATypedQuestionWithNoSelectionIsWhatGoesToClaude() {
        XCTAssertEqual(
            SearchBarView.returnMeans(query: "  what was that invoice site \n", hasSelection: false),
            .askClaude("what was that invoice site"))
    }

    // MARK: - Copy

    /// Every mechanism has a sentence, and none of them claims a pre-fill that did not happen.
    func testTheClipboardFallbackSaysWhatItActuallyDid() throws {
        XCTAssertTrue(ClaudeRouter.Mechanism.clipboard.note.contains("copied"), ClaudeRouter.Mechanism.clipboard.note)
        XCTAssertTrue(ClaudeRouter.Mechanism.clipboard.note.contains("paste"), ClaudeRouter.Mechanism.clipboard.note)
        // Every surface's sentence names *its own* surface. A note that says "Claude Code tab" after
        // a chat opened would be the same class of untruth as claiming a pre-fill after a copy.
        for surface in ClaudeRouter.Surface.allCases {
            let url = try XCTUnwrap(ClaudeRouter.prefillURL(for: "x", surface: surface))
            let prefilled = ClaudeRouter.Mechanism.prefilledTab(surface: surface, url: url)
            XCTAssertTrue(prefilled.note.contains("prompt"), prefilled.note)
            XCTAssertFalse(prefilled.note.contains("clipboard"), prefilled.note)
            XCTAssertTrue(prefilled.note.contains(surface.opened), prefilled.note)
        }
    }
}
