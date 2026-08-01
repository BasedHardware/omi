import AppKit
import ContextCore
import Foundation
import UniformTypeIdentifiers

/// Hands a query to Claude. That is the entire retrieval story.
///
/// This app ships no search engine. The bar takes a sentence and gives it to Claude, which answers it
/// with the MCP tools already registered by `ClaudeRegistrar` — so the only thing that happens here is
/// delivery, and the only thing that can go wrong is delivering it somewhere the user cannot see.
///
/// Two targets, matching the reference's "Claude target" dropdown:
///
/// - **Claude app** — a `claude://` deep link that opens Claude with the prompt already in the
///   composer. Which *surface* it lands on is `Surface`, chosen by the caller, because Claude has
///   two of them and they are not interchangeable. The prompt is **pre-filled, not sent** — the user
///   still presses Return, which is the honest thing for a shortcut that can fire by accident.
/// - **Terminal** — runs the `claude` CLI with the prompt, in whichever app owns `.command` files.
///
/// If nothing on the machine claims the `claude` scheme, delivery falls back to the clipboard and
/// says so. Nothing here ever pretends a prompt was filled in when it was not.
enum ClaudeRouter {

    // MARK: - Targets

    enum Target: String, CaseIterable, Sendable {
        case claudeApp
        case terminal

        /// The dropdown label.
        var title: String {
            switch self {
            case .claudeApp: return "Claude App"
            case .terminal: return "Terminal"
            }
        }
    }

    /// Whether a target is usable, with the sentence the row shows either way.
    enum Availability: Equatable, Sendable {
        case available(detail: String)
        case missing(detail: String)

        var isAvailable: Bool {
            if case .available = self { return true }
            return false
        }

        var detail: String {
            switch self {
            case .available(let detail), .missing(let detail): return detail
            }
        }
    }

    /// Which Claude the prompt lands in.
    ///
    /// Claude registers one scheme and routes on the host, and the two hosts are two different
    /// products: `claude.ai/new` is the ordinary chat you get from Claude's home surface, and
    /// `code/new` is the Claude Code tab. Making this a parameter rather than a constant is the fix
    /// for the bug where the tutorial — which is teaching somebody to *ask a question* — silently
    /// inherited the search bar's coding surface.
    ///
    /// Both links are documented ("Open Claude Desktop with a link", support.claude.com) and both are
    /// in the installed app's own handler, which reads `q`, caps it, and navigates: `claude.ai/new`
    /// to `/new?q=…` and `code/new` to the Claude Code route. Neither one sends the prompt.
    enum Surface: String, CaseIterable, Sendable {
        /// `claude://claude.ai/new?q=…` — a normal new chat, prompt in the composer.
        case chat
        /// `claude://code/new?q=…` — the Claude Code tab, prompt in the composer.
        case code

        /// The deep link, without the query.
        var prefillPath: String {
            switch self {
            case .chat: return "claude://claude.ai/new"
            case .code: return "claude://code/new"
            }
        }

        /// What it is called in a sentence, as the thing that got opened.
        var opened: String {
            switch self {
            case .chat: return "a new Claude chat"
            case .code: return "a Claude Code tab"
            }
        }
    }

    /// How the query actually got there. Surfaced so the UI's promise matches what happened.
    enum Mechanism: Equatable, Sendable {
        /// Claude opened on `surface`, prompt already filled in.
        ///
        /// It carries the surface rather than only the URL so the sentence below cannot name the
        /// wrong one: a note claiming a Claude Code tab after a chat opened is the same class of
        /// untruth as claiming a pre-fill after a clipboard copy.
        case prefilledTab(surface: Surface, url: URL)
        /// No handler for the scheme, so the query went on the clipboard and Claude came forward.
        case clipboard
        /// A one-shot launcher run by the user's terminal.
        case terminal(cli: String, handler: String)

        /// What the search bar says after it routes. First person, and never a claim we did not earn.
        var note: String {
            switch self {
            case .prefilledTab(let surface, _):
                return "Opened \(surface.opened) with your question in the prompt."
            case .clipboard:
                return "Nothing here answers claude:// links, so I copied your question and opened Claude — paste it in."
            case .terminal(_, let handler):
                return "Running claude in \(handler)."
            }
        }
    }

    struct Delivery: Equatable, Sendable {
        let target: Target
        let mechanism: Mechanism
        /// The prompt as delivered — truncated if the query was longer than Claude will accept.
        let deliveredCharacters: Int
        let wasTruncated: Bool
    }

    enum RouteError: Error, Equatable, Sendable {
        case emptyQuery
        case unavailable(String)
        case couldNotPrepare(String)

        var sentence: String {
            switch self {
            case .emptyQuery: return "Ask me something first."
            case .unavailable(let detail): return detail
            case .couldNotPrepare(let detail): return detail
            }
        }
    }

    // MARK: - The deep link

    /// The scheme the installed Claude registers. Every `Surface` is a host under it, so this is what
    /// LaunchServices is asked about — a machine either answers `claude://` or it does not.
    static let scheme = "claude"

    /// The URL the availability probe hands LaunchServices. Any host would resolve the same handler;
    /// this one is named so nobody reads a surface choice into it.
    private static let schemeProbePath = "claude://claude.ai/new"

    /// Claude truncates the prompt at `16 KiB − 2 KiB` characters before it ever reaches the composer,
    /// so we truncate to the same number rather than handing over a string we know it will cut.
    static let promptLimit = 16 * 1024 - 2 * 1024

    /// `<surface>?q=<query>`, or `nil` for a query with nothing in it.
    static func prefillURL(for query: String, surface: Surface) -> URL? {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        var components = URLComponents(string: surface.prefillPath)
        components?.queryItems = [URLQueryItem(name: "q", value: String(trimmed.prefix(promptLimit)))]
        return components?.url
    }

    // MARK: - Availability

    /// The one indirection tests need: what is on disk, and what LaunchServices says.
    struct Probe: Sendable {
        var handlerForClaudeScheme: @Sendable () -> URL?
        var handlerForCommandFiles: @Sendable () -> URL?
        var isExecutable: @Sendable (String) -> Bool
        var claudeCLICandidates: [String]

        static func live(home: String = NSHomeDirectory()) -> Probe {
            Probe(
                handlerForClaudeScheme: {
                    guard let url = URL(string: schemeProbePath) else { return nil }
                    return NSWorkspace.shared.urlForApplication(toOpen: url)
                },
                handlerForCommandFiles: {
                    // Asked about the *content type* rather than about Terminal.app, so a user who
                    // runs iTerm or Ghostty gets their own terminal and the row names it. `.command`
                    // is `com.apple.terminal.shell-script`.
                    commandFileType.flatMap { NSWorkspace.shared.urlForApplication(toOpen: $0) }
                        ?? NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.apple.Terminal")
                },
                isExecutable: { FileManager.default.isExecutableFile(atPath: $0) },
                claudeCLICandidates: defaultCLICandidates(home: home))
        }
    }

    /// Where `claude` actually lands. A GUI app inherits almost no `PATH`, so `which` is not an option
    /// and the list has to be explicit.
    static func defaultCLICandidates(home: String) -> [String] {
        [
            "\(home)/.local/bin/claude",
            "\(home)/.claude/local/claude",
            "\(home)/.bun/bin/claude",
            "\(home)/.npm-global/bin/claude",
            "/opt/homebrew/bin/claude",
            "/usr/local/bin/claude",
            "/usr/bin/claude",
        ]
    }

    static func claudeCLIPath(candidates: [String], isExecutable: (String) -> Bool) -> String? {
        candidates.first(where: isExecutable)
    }

    /// - Parameter surface: the surface the sentence promises, so the row cannot name one Claude
    ///   while `route` opens another. Ignored by `.terminal`.
    static func availability(of target: Target, surface: Surface, probe: Probe = .live()) -> Availability {
        switch target {
        case .claudeApp:
            guard let handler = probe.handlerForClaudeScheme() else {
                return .missing(detail: "Nothing on this Mac answers claude:// links, so I'd have to use your clipboard.")
            }
            let name = handler.deletingPathExtension().lastPathComponent
            return .available(detail: "Opens \(surface.opened) in \(name) with your question in the prompt.")
        case .terminal:
            guard let cli = claudeCLIPath(candidates: probe.claudeCLICandidates, isExecutable: probe.isExecutable) else {
                return .missing(detail: "I can't find the claude command on this Mac.")
            }
            let handler = probe.handlerForCommandFiles()?.deletingPathExtension().lastPathComponent ?? "Terminal"
            return .available(detail: "Runs \(abbreviate(cli)) in \(handler).")
        }
    }

    // MARK: - Routing

    /// - Parameter surface: which Claude the `.claudeApp` target opens. Required rather than
    ///   defaulted: the two call sites want different ones, and the last time this was implicit the
    ///   tutorial shipped pointing at Claude Code. Ignored by `.terminal`, whose CLI *is* Claude Code.
    @MainActor
    static func route(
        _ query: String, to target: Target, surface: Surface, probe: Probe = .live()
    ) -> Result<Delivery, RouteError> {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return .failure(.emptyQuery) }
        let delivered = String(trimmed.prefix(promptLimit))
        let truncated = delivered.count < trimmed.count

        switch target {
        case .claudeApp:
            return routeToApp(delivered, surface: surface, truncated: truncated, probe: probe)
        case .terminal:
            return routeToTerminal(delivered, truncated: truncated, probe: probe)
        }
    }

    @MainActor
    private static func routeToApp(
        _ query: String, surface: Surface, truncated: Bool, probe: Probe
    ) -> Result<Delivery, RouteError> {
        // Never log the query itself: it is the user's own words, and it is the single most sensitive
        // string this app handles.
        if let url = prefillURL(for: query, surface: surface), probe.handlerForClaudeScheme() != nil {
            NSWorkspace.shared.open(url)
            ContextLog.info("Routed \(query.count) characters to \(surface.opened)", logCategory)
            return .success(
                Delivery(
                    target: .claudeApp, mechanism: .prefilledTab(surface: surface, url: url),
                    deliveredCharacters: query.count, wasTruncated: truncated))
        }

        // The honest fallback. Not a fake pre-fill and not a silent failure: the query is where the
        // user can paste it, Claude is in front of them, and the note says exactly that.
        guard let claude = NSWorkspace.shared.urlForApplication(withBundleIdentifier: claudeBundleIdentifier) else {
            return .failure(.unavailable("I can't find Claude on this Mac."))
        }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(query, forType: .string)
        NSWorkspace.shared.openApplication(at: claude, configuration: NSWorkspace.OpenConfiguration())
        ContextLog.info("No claude:// handler; fell back to the clipboard", logCategory)
        return .success(
            Delivery(
                target: .claudeApp, mechanism: .clipboard,
                deliveredCharacters: query.count, wasTruncated: truncated))
    }

    @MainActor
    private static func routeToTerminal(
        _ query: String, truncated: Bool, probe: Probe
    ) -> Result<Delivery, RouteError> {
        guard let cli = claudeCLIPath(candidates: probe.claudeCLICandidates, isExecutable: probe.isExecutable) else {
            return .failure(.unavailable("I can't find the claude command on this Mac."))
        }
        do {
            let script = try writeLauncher(cli: cli, query: query)
            NSWorkspace.shared.open(script)
            let handler = probe.handlerForCommandFiles()?.deletingPathExtension().lastPathComponent ?? "Terminal"
            ContextLog.info("Routed \(query.count) characters to the claude CLI", logCategory)
            return .success(
                Delivery(
                    target: .terminal, mechanism: .terminal(cli: cli, handler: handler),
                    deliveredCharacters: query.count, wasTruncated: truncated))
        } catch {
            return .failure(.couldNotPrepare("I couldn't start Terminal: \(error.localizedDescription)"))
        }
    }

    // MARK: - The launcher

    /// A one-shot `.command` file, opened with whatever app owns that extension.
    ///
    /// A script rather than AppleScript at Terminal, on purpose: `do script` needs Automation consent,
    /// which is a fourth permission prompt for a feature that does not need one, and it hard-codes
    /// Terminal.app over the terminal the user actually chose.
    ///
    /// It deletes itself before it runs anything. The file holds the user's question, so it must not
    /// outlive the window it opens.
    static func launcherScript(cli: String, query: String) -> String {
        """
        #!/bin/sh
        # Written by Context for Claude to hand one question to the claude CLI.
        # It removes itself first: this file contains what you typed.
        rm -f -- "$0"
        cd "$HOME" || exit 1
        exec \(shellQuoted(cli)) \(shellQuoted(query))
        """
    }

    /// POSIX single-quoting. The only character that matters inside single quotes is the quote itself,
    /// and `'\''` is how you get one — this is what keeps a question containing a backtick, a `$`, or a
    /// `;` from becoming a command.
    static func shellQuoted(_ value: String) -> String {
        "'" + value.replacingOccurrences(of: "'", with: "'\\''") + "'"
    }

    private static func writeLauncher(cli: String, query: String) throws -> URL {
        let directory = try ContextPaths.ensureSupportDirectory()
            .appendingPathComponent("ask", isDirectory: true)
        try FileManager.default.createDirectory(
            at: directory, withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700])
        let url = directory.appendingPathComponent("ask-\(UUID().uuidString).command")
        let data = Data(launcherScript(cli: cli, query: query).utf8)
        // Owner-only from the moment it exists: every other user on the machine can read a 0644 file
        // in a predictable directory, and this one has the question in it.
        guard FileManager.default.createFile(
            atPath: url.path, contents: data, attributes: [.posixPermissions: 0o700])
        else {
            throw CocoaError(.fileWriteUnknown)
        }
        return url
    }

    // MARK: - The user's choice

    /// The target the search bar routes to, persisted for the Agents pane's dropdown.
    ///
    /// Defaults to the Claude app rather than the CLI: a pre-filled composer is reviewable before it
    /// runs, and a terminal window that starts talking to an agent is not.
    static var preferredTarget: Target {
        get {
            guard let raw = UserDefaults.standard.string(forKey: preferredTargetKey),
                let target = Target(rawValue: raw)
            else {
                return .claudeApp
            }
            return target
        }
        set { UserDefaults.standard.set(newValue.rawValue, forKey: preferredTargetKey) }
    }

    private static let preferredTargetKey = "context.settings.claudeTarget"

    // MARK: - Copy

    /// The reference's "Claude target" subtitle, rewritten to describe what actually happens.
    static func targetSubtitle(surface: Surface, probe: Probe = .live()) -> String {
        let app = availability(of: .claudeApp, surface: surface, probe: probe)
        let terminal = availability(of: .terminal, surface: surface, probe: probe)
        return "\(app.detail) \(terminal.detail)"
    }

    private static let claudeBundleIdentifier = "com.anthropic.claudefordesktop"
    private static let logCategory = "search"
    /// The content type a `.command` file has, which is what decides who runs it.
    private static let commandFileType = UTType("com.apple.terminal.shell-script")

    private static func abbreviate(_ path: String) -> String {
        let home = NSHomeDirectory()
        guard path.hasPrefix(home + "/") else { return path }
        return "~/" + String(path.dropFirst(home.count + 1))
    }
}
