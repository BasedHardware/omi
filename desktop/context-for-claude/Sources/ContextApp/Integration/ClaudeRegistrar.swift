import ContextCore
import Darwin
import Foundation

/// Points Claude Code and Claude Desktop at the bundled `context-for-claude-mcp` server.
///
/// `ClaudeConfig` owns every decision about the *document*; this file owns the decisions about the
/// *disk*: which binary to name, whether a surface exists on this Mac at all, and what to tell the
/// user afterwards. The two surfaces are handled independently on purpose — an unparseable
/// `~/.claude.json` must not cost the user their Claude Desktop connection, and vice versa.
///
/// **The connector's icon is not declared here, and there is no key for it.** Both configs describe
/// a stdio entry as `type`/`command`/`args`/`env` and nothing else. Claude Code does carry an
/// `iconUrl`, but only on its `claudeai-proxy` server type — the remote connectors claude.ai
/// provisions from its own directory — and it never reads one off a local entry; Claude Desktop's
/// other icon route is the `icon`/`icons` field of a `.mcpb` Desktop Extension manifest, which is a
/// packaging format this app does not ship as. So the icon rides on the `initialize` result instead
/// (``ServerIcon``, `Sources/ContextMCPKit/`), which is where MCP puts it. Adding an icon key here
/// would be inert at best, and a key the client's schema does not know at worst.
enum ClaudeRegistrar {
    struct Result {
        /// Whether the surface ended in the state the call was after: connected after `register()`,
        /// disconnected after `unregister()`.
        let claudeCode: Bool
        let claudeDesktop: Bool
        /// One to three plain sentences, shown verbatim in onboarding.
        let message: String
    }

    private static let logCategory = "claude"

    private struct RegistrationError: Error {
        let message: String
    }

    // MARK: - The binary Claude will spawn

    private static let binaryName = "context-for-claude-mcp"

    /// Absolute path to the MCP server Claude should launch.
    ///
    /// The canonical answer is `Context for Claude.app/Contents/MacOS/context-for-claude-mcp`, which is what a signed
    /// build ships. The fallbacks matter because this is first exercised from a raw `swift build`,
    /// where there is no bundle at all and both executables are siblings in `.build/<config>` — a
    /// registrar that only works inside an assembled bundle could not be tested until the very end.
    static var mcpBinaryPath: String {
        let candidates = binaryCandidates
        return candidates.first { FileManager.default.isExecutableFile(atPath: $0) } ?? candidates[0]
    }

    private static var binaryCandidates: [String] {
        var candidates = [Bundle.main.bundleURL.appendingPathComponent("Contents/MacOS/\(binaryName)").path]
        if let executableDirectory = Bundle.main.executableURL?.resolvingSymlinksInPath().deletingLastPathComponent() {
            candidates.append(executableDirectory.appendingPathComponent(binaryName).path)
        }
        candidates.append(Bundle.main.bundleURL.appendingPathComponent(binaryName).path)
        return candidates.reduce(into: [String]()) { unique, path in
            if !unique.contains(path) { unique.append(path) }
        }
    }

    // MARK: - When we were written

    /// When Claude Desktop's copy of our MCP registration was last written to disk.
    ///
    /// Evidence for exactly one question, and it is asked before something destructive: a Claude
    /// Desktop process launched *after* this already read us at startup, so quitting it would
    /// accomplish nothing except taking the user's open conversation with it.
    ///
    /// Deliberately this file and **not** `~/.claude.json`. That one is Claude Code's own state
    /// store and is rewritten constantly for reasons that have nothing to do with us, so its
    /// modification date is no evidence of when *we* wrote — reading it would have us quitting
    /// sessions on the strength of somebody else's write, which is the wrong direction to be wrong
    /// in. This file is the one read at startup by the process a restart would restart.
    ///
    /// Nil when there is no registration on disk at all. That is a different fact, and it is not a
    /// reason to restart either: a Claude with no entry for us does not gain one by relaunching.
    static var claudeDesktopRegisteredAt: Date? {
        let path = ClaudeConfig.claudeDesktopConfigURL.path
        guard let attributes = try? FileManager.default.attributesOfItem(atPath: path) else {
            return nil
        }
        return attributes[.modificationDate] as? Date
    }

    // MARK: - Register / unregister

    static func register() -> Result {
        let binary = mcpBinaryPath
        // Writing a command that isn't on disk would hand Claude a server that fails to spawn, and
        // the user would meet that failure inside Claude — far from anything that can explain it.
        guard FileManager.default.isExecutableFile(atPath: binary) else {
            ContextLog.error(
                "No \(binaryName) found at \(binaryCandidates.map { displayPath($0) }.joined(separator: ", "))",
                logCategory)
            return Result(
                claudeCode: false,
                claudeDesktop: false,
                message: "I couldn't find my MCP server at \(displayPath(binary)), so I haven't changed anything. "
                    + "Reinstall Context for Claude and connect again.")
        }

        let code = connect(.claudeCode, binary: binary)
        let desktop = connect(.claudeDesktop, binary: binary)
        installSkill()
        installMemory()
        let message = registerMessage([(.claudeCode, code), (.claudeDesktop, desktop)])
        ContextLog.info(message, logCategory)
        return Result(
            claudeCode: isConnected(after: code),
            claudeDesktop: isConnected(after: desktop),
            message: message)
    }

    /// The exact inverse, for when the user wants Context for Claude out of Claude again. Removes the entry
    /// wherever it points, not only when it points at this build.
    static func unregister() -> Result {
        let code = disconnect(.claudeCode)
        let desktop = disconnect(.claudeDesktop)
        removeSkill()
        removeMemory()
        let message = unregisterMessage([(.claudeCode, code), (.claudeDesktop, desktop)])
        ContextLog.info(message, logCategory)
        return Result(
            claudeCode: isDisconnected(after: code),
            claudeDesktop: isDisconnected(after: desktop),
            message: message)
    }

    static func status() -> (claudeCode: Bool, claudeDesktop: Bool) {
        let binary = mcpBinaryPath
        return (isRegistered(.claudeCode, binary: binary), isRegistered(.claudeDesktop, binary: binary))
    }

    // MARK: - The skill

    /// Installs the Claude Code skill beside the MCP registration, and never fails the connection
    /// over it.
    ///
    /// Deliberately not part of the `Result`, and deliberately not a surface. The connection is the
    /// contract — with the server registered, every tool works whether or not this file exists; the
    /// skill only changes how readily an agent reaches for them, and most of all how readily a
    /// subagent does. Turning a `~/.claude/skills` permission problem into "I couldn't connect to
    /// Claude Code" would trade a working connector for an accurate error message.
    private static func installSkill() {
        do {
            if try ClaudeSkill.install() {
                ContextLog.info("Installed the Claude Code skill at \(displayPath(ClaudeSkill.documentURL.path))", logCategory)
            }
        } catch {
            ContextLog.error("Could not install the Claude Code skill: \(error.localizedDescription)", logCategory)
        }
    }

    private static func removeSkill() {
        do {
            if try ClaudeSkill.remove() {
                ContextLog.info("Removed the Claude Code skill", logCategory)
            }
        } catch {
            ContextLog.error("Could not remove the Claude Code skill: \(error.localizedDescription)", logCategory)
        }
    }

    // MARK: - The standing instruction

    /// Writes the "check this Mac's context first" block into the user's global `CLAUDE.md`,
    /// alongside the skill, and never fails the connection over it — same reasoning as the skill,
    /// one step stronger. The connection is what makes the tools *available*; ``ClaudeMemory`` is
    /// what makes an agent reach for them without being asked. A permissions problem in
    /// `~/.claude` must not be reported to the user as "I couldn't connect to Claude Code".
    private static func installMemory() {
        do {
            if try ClaudeMemory.install() {
                ContextLog.info(
                    "Wrote the standing instruction into \(displayPath(ClaudeMemory.documentURL.path))",
                    logCategory)
            }
        } catch {
            ContextLog.error(
                "Could not write the standing instruction: \(error.localizedDescription)", logCategory)
        }
    }

    private static func removeMemory() {
        do {
            if try ClaudeMemory.remove() {
                ContextLog.info("Removed the standing instruction from the global CLAUDE.md", logCategory)
            }
        } catch {
            ContextLog.error(
                "Could not remove the standing instruction: \(error.localizedDescription)", logCategory)
        }
    }

    // MARK: - One surface at a time

    private enum Outcome: Equatable {
        /// The config was rewritten.
        case changed
        /// Already in the state the caller wanted; the file was not touched.
        case unchanged
        /// That Claude surface is not on this Mac.
        case absent
        /// A complete, user-facing sentence explaining why this surface was skipped.
        case failed(String)
    }

    private static func connect(_ surface: Surface, binary: String) -> Outcome {
        modify(surface) { existing in
            guard !ClaudeConfig.isRegistered(in: existing, mcpBinaryPath: binary) else { return nil }
            if let mcpServers = existing["mcpServers"], !(mcpServers is [String: Any]) {
                throw RegistrationError(
                    message: "I couldn’t update \(surface.name) — the `mcpServers` key in \(displayPath(surface.configURL)) isn’t a dictionary. I left it exactly as it was.")
            }
            return ClaudeConfig.merged(into: existing, mcpBinaryPath: binary)
        }
    }

    private static func disconnect(_ surface: Surface) -> Outcome {
        modify(surface) { existing in
            let stripped = ClaudeConfig.removed(from: existing)
            // `removed` is a no-op when the entry was never there; comparing is how we tell the
            // user "disconnected" apart from "there was nothing to disconnect".
            return NSDictionary(dictionary: stripped).isEqual(to: existing) ? nil : stripped
        }
    }

    /// Reads a surface's config, applies `transform`, and writes the result back. `transform`
    /// returning nil means "already correct" — that is the difference between `.changed` and
    /// `.unchanged`, which is the difference the user reads in the message.
    private static func modify(_ surface: Surface, _ transform: ([String: Any]) throws -> [String: Any]?) -> Outcome {
        guard surface.isInstalled else { return .absent }
        let url = surface.configURL
        do {
            let existing = try currentDocument(at: url)
            guard let updated = try transform(existing) else { return .unchanged }
            // Only ever reached once `isInstalled` has confirmed the surface is really here, so
            // this creates a directory for an app the user has, never for one they don't.
            try FileManager.default.createDirectory(
                at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
            try ClaudeConfig.writeDocument(updated, to: url)
            ContextLog.info("Rewrote \(ClaudeConfig.serverName) in \(displayPath(url))", logCategory)
            return .changed
        } catch {
            return .failed(failureSentence(surface, error))
        }
    }

    private static func isRegistered(_ surface: Surface, binary: String) -> Bool {
        guard let existing = try? currentDocument(at: surface.configURL) else { return false }
        return ClaudeConfig.isRegistered(in: existing, mcpBinaryPath: binary)
    }

    private static func currentDocument(at url: URL) throws -> [String: Any] {
        let fileManager = FileManager.default
        guard fileManager.fileExists(atPath: url.path) else { return [:] }
        // A zero-byte config is "nothing written yet", not a document we would be destroying, so it
        // must not read as corruption and block the user forever.
        if let size = (try? fileManager.attributesOfItem(atPath: url.path))?[.size] as? NSNumber, size.intValue == 0 {
            return [:]
        }
        return try ClaudeConfig.readDocument(at: url)
    }

    private static func isConnected(after outcome: Outcome) -> Bool {
        switch outcome {
        case .changed, .unchanged: return true
        case .absent, .failed: return false
        }
    }

    private static func isDisconnected(after outcome: Outcome) -> Bool {
        switch outcome {
        case .changed, .unchanged, .absent: return true
        case .failed: return false
        }
    }

    // MARK: - What the user is told

    private static func registerMessage(_ outcomes: [(Surface, Outcome)]) -> String {
        var sentences: [String] = []
        let connected = names(outcomes, .changed)
        let already = names(outcomes, .unchanged)
        let absent = names(outcomes, .absent)

        if !connected.isEmpty {
            sentences.append("Connected to \(list(connected)).")
        }
        if !already.isEmpty {
            sentences.append(
                connected.isEmpty
                    ? "Already connected to \(list(already))."
                    : "\(list(already)) \(already.count == 1 ? "was" : "were") already connected.")
        }
        if absent.count == Surface.allCases.count {
            sentences.append(
                "I don't see \(list(absent, conjunction: "or")) on this Mac yet — I'll be there when you install one.")
        } else {
            sentences.append(contentsOf: absent.map { "\($0) isn't installed yet — I'll be there when it is." })
        }
        sentences.append(contentsOf: failureSentences(outcomes))
        return sentences.joined(separator: " ")
    }

    private static func unregisterMessage(_ outcomes: [(Surface, Outcome)]) -> String {
        var sentences: [String] = []
        let removed = names(outcomes, .changed)
        // "Wasn't connected" and "isn't installed" are the same fact to someone disconnecting.
        let untouched = names(outcomes, in: [.unchanged, .absent])

        if !removed.isEmpty {
            sentences.append("Disconnected from \(list(removed)).")
        }
        if !untouched.isEmpty {
            sentences.append("\(list(untouched)) \(untouched.count == 1 ? "wasn't" : "weren't") connected.")
        }
        sentences.append(contentsOf: failureSentences(outcomes))
        return sentences.joined(separator: " ")
    }

    private static func failureSentence(_ surface: Surface, _ error: Error) -> String {
        let path = displayPath(surface.configURL)
        // The error's detail string is deliberately never logged: it comes from parsing the user's
        // own config, and `~/.claude.json` carries their whole project history.
        if let registrationError = error as? RegistrationError {
            ContextLog.error(registrationError.message, logCategory)
            return registrationError.message
        }
        if let configError = error as? ClaudeConfigError {
            switch configError {
            case .unreadable:
                ContextLog.error("Could not open \(path)", logCategory)
                return "I couldn't update \(surface.name) — \(path) wouldn't open. I left it exactly as it was."
            case .malformed, .notAnObject:
                ContextLog.error("Could not parse \(path)", logCategory)
                return "I couldn't update \(surface.name) — \(path) isn't valid JSON. I left it exactly as it was."
            }
        }
        ContextLog.error("Could not write \(path): \(error.localizedDescription)", logCategory)
        let detail = terminated(error.localizedDescription)
        return "I couldn't update \(surface.name) — writing \(path) failed\(detail.isEmpty ? "." : ": \(detail)")"
    }

    private static func names(_ outcomes: [(Surface, Outcome)], _ outcome: Outcome) -> [String] {
        names(outcomes, in: [outcome])
    }

    /// Keeps the surfaces in `Surface.allCases` order, so a sentence never reads "Claude Desktop and
    /// Claude Code" only because of which outcome each one happened to land in.
    private static func names(_ outcomes: [(Surface, Outcome)], in wanted: [Outcome]) -> [String] {
        outcomes.filter { wanted.contains($0.1) }.map { $0.0.name }
    }

    private static func failureSentences(_ outcomes: [(Surface, Outcome)]) -> [String] {
        outcomes.compactMap { pair -> String? in
            guard case .failed(let sentence) = pair.1 else { return nil }
            return sentence
        }
    }

    private static func list(_ names: [String], conjunction: String = "and") -> String {
        guard names.count > 1 else { return names.first ?? "" }
        return names.dropLast().joined(separator: ", ") + " \(conjunction) " + (names.last ?? "")
    }

    /// Error descriptions arrive with and without a full stop; the sentence has to read as prose
    /// either way.
    private static func terminated(_ text: String) -> String {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let last = trimmed.last else { return "" }
        return ".!?".contains(last) ? trimmed : trimmed + "."
    }

    // MARK: - Surfaces

    private enum Surface: CaseIterable {
        case claudeCode
        case claudeDesktop

        var name: String {
            switch self {
            case .claudeCode: return "Claude Code"
            case .claudeDesktop: return "Claude Desktop"
            }
        }

        var configURL: URL {
            switch self {
            case .claudeCode: return ClaudeConfig.claudeCodeConfigURL
            case .claudeDesktop: return ClaudeConfig.claudeDesktopConfigURL
            }
        }

        /// Evidence the user actually has this surface, without launching anything. Conjuring a
        /// config for an app that isn't installed leaves a file the user never asked for and can
        /// never see the effect of, so absence is reported rather than papered over.
        var isInstalled: Bool {
            if FileManager.default.fileExists(atPath: configURL.path) { return true }
            switch self {
            case .claudeCode:
                // Claude Code creates `~/.claude` on its first run, before it has anything to put
                // in `~/.claude.json`.
                return directoryExists(
                    at: ClaudeRegistrar.homeDirectory.appendingPathComponent(".claude", isDirectory: true))
            case .claudeDesktop:
                // `~/Library/Application Support/Claude` appears the first time the app runs.
                return directoryExists(at: configURL.deletingLastPathComponent())
            }
        }

        private func directoryExists(at url: URL) -> Bool {
            var isDirectory: ObjCBool = false
            let exists = FileManager.default.fileExists(atPath: url.path, isDirectory: &isDirectory)
            return exists && isDirectory.boolValue
        }
    }

    // MARK: - Paths

    /// Derived from `ClaudeConfig` rather than `FileManager` so both halves of the registrar always
    /// agree on where home is.
    private static var homeDirectory: URL {
        ClaudeConfig.claudeCodeConfigURL.deletingLastPathComponent()
    }

    private static func displayPath(_ url: URL) -> String {
        displayPath(url.standardizedFileURL.path)
    }

    /// `~`-relative, so neither a log line nor an onboarding sentence carries the user's name.
    private static func displayPath(_ path: String) -> String {
        let home = homeDirectory.standardizedFileURL.path
        let standardized = URL(fileURLWithPath: path).standardizedFileURL.path
        guard standardized.hasPrefix(home + "/") else { return standardized }
        return "~/" + String(standardized.dropFirst(home.count + 1))
    }
}

// MARK: - Is a server actually running?

/// Whether Claude Desktop has a **live** `context-for-claude-mcp` process right now.
///
/// `ClaudeRegistrar` above answers "is the registration on disk". This answers the question that
/// actually decides whether Claude can call our tools — "is one of our servers running" — and the two
/// come apart in a way that is not theoretical.
///
/// Claude spawns a stdio MCP server **once, when it launches, and does not respawn it if it dies.**
/// Replacing the app bundle kills the running one: the kernel invalidates a process whose executable
/// has been rewritten underneath it, so every update, reinstall and rebuild takes out the server
/// inside whatever Claude was already open. From that moment the user has a registration, no tools,
/// and nothing anywhere that says so — until they restart Claude. This Mac's own MCP log records it
/// twice, as a four-minute outage and as one that lasted three days.
///
/// That gap is what handed the tutorial's payoff question to a Claude which then told the user it had
/// no access to what they had been reading. It is invisible to every disk-based check: Claude had
/// launched *after* we registered, so the config was correct, the entry was there, and the date
/// comparison in `ClaudeHandoff.restartIsNeeded` said everything was fine.
enum ClaudeServerLiveness {

    /// What could be established, kept as three cases because they are three different amounts of
    /// evidence — and only one of them may be used to ask the user to quit Claude.
    enum State: Equatable {
        /// At least one live server built from the binary we registered descends from a running
        /// Claude Desktop, so that Claude can reach our tools.
        case servingClaudeDesktop
        /// The process list was read and no such server exists. Evidence of absence rather than
        /// absence of evidence, and the only state that justifies offering a restart.
        case notServingClaudeDesktop
        /// Nothing could be established. Never acted on: callers fall back to what they knew before.
        case unknown
    }

    /// `PROC_PIDPATHINFO_MAXSIZE`, which the C macro does not export to Swift ("structure not
    /// supported"), so its value is restated rather than a smaller buffer invented — `proc_pidpath`
    /// fails outright on a buffer below it.
    private static let executablePathCapacity = 4 * 1_024

    /// How far up a process tree to look for Claude. The chains are short — two hops to Claude
    /// Desktop (`context-for-claude-mcp` → `Claude.app/Contents/Helpers/disclaimer` → `Claude`), one
    /// to a Claude Code that is running inside it; the bound is what stops a cyclic or corrupted
    /// parent chain from spinning this loop forever.
    private static let maximumAncestorHops = 8

    /// - Parameter claudeDesktopPIDs: the running Claude Desktop processes, passed in rather than
    ///   read here so this file stays free of AppKit and the whole decision stays testable.
    static func state(
        binary: String = ClaudeRegistrar.mcpBinaryPath,
        claudeDesktopPIDs: Set<pid_t>
    ) -> State {
        // No Claude Desktop means the question is moot, not answered: there is nothing for a server
        // to be serving, and reporting an absence here would read as a fault.
        guard !claudeDesktopPIDs.isEmpty else { return .unknown }
        guard let servers = liveProcesses(matching: binary) else { return .unknown }
        guard !servers.isEmpty else { return .notServingClaudeDesktop }

        // Attribution matters because Claude Code spawns this same binary, and one of *its* servers
        // must never be read as proof that Claude Desktop has one.
        let servesClaude = servers.contains { server in
            switch owner(
                of: server,
                claudeDesktopPIDs: claudeDesktopPIDs,
                parent: parentPID(of:),
                executablePath: executablePath(of:))
            {
            // A chain that cannot be resolved counts as Claude's, because the cost of being wrong is
            // asymmetric in both directions this state is read: it gates an offer to quit somebody's
            // Claude, and it gates a status line that would otherwise nag. Guessing "not Claude's"
            // on a parent lookup that failed would do both on no evidence at all.
            case .claudeDesktop, .unknown: return true
            case .claudeCode, .none: return false
            }
        }
        return servesClaude ? .servingClaudeDesktop : .notServingClaudeDesktop
    }

    /// Who a server belongs to, decided by the **nearest** owner above it rather than by whether
    /// Claude Desktop appears anywhere on the chain.
    ///
    /// **The distinction is the whole of it, because Claude Code now runs inside Claude Desktop.**
    /// A Claude Code session opened in the desktop app has this ancestry, read off this Mac:
    ///
    /// ```
    /// context-for-claude-mcp
    ///   → …/Application Support/Claude/claude-code/2.1.229/claude.app/Contents/MacOS/claude
    ///     → /Applications/Claude.app/Contents/Helpers/disclaimer
    ///       → /Applications/Claude.app/Contents/MacOS/Claude     ← a Claude Desktop PID
    /// ```
    ///
    /// A walk that only asks "is a Claude Desktop PID an ancestor" answers yes for every one of
    /// those, so on any Mac where the user has a Claude Code session open in the desktop app, one of
    /// *Claude Code's* servers is read as proof that Claude Desktop has one. Measured on the Mac
    /// whose Claude Desktop connector had been failing to spawn for three days: every disk check
    /// said connected, and this probe — the one thing that could have contradicted them — agreed,
    /// because fifteen Claude Code servers were descendants of the same process.
    ///
    /// So the first owner met wins. A `claude-code` process between the server and Claude Desktop
    /// means the server is Claude Code's, and Claude Desktop's own spawn is not on this chain at all.
    ///
    /// Pure, with the process table passed in as two lookups, because the tree it has to reason about
    /// cannot be built inside a test — the real one needs a running Claude Desktop, a running Claude
    /// Code inside it, and a server under each.
    enum Owner: Equatable {
        /// A Claude Code process sits between the server and anything else.
        case claudeCode
        /// A running Claude Desktop was reached first.
        case claudeDesktop
        /// The walk finished at launchd having met neither.
        case none
        /// The walk ran out of parents it could read. Not an answer, and never acted on.
        case unknown
    }

    /// Claude Code's own install directory, which every copy of it the desktop app runs sits inside:
    /// `~/Library/Application Support/Claude/claude-code/<version>/claude.app/…`.
    ///
    /// A path marker rather than an executable name because both binaries are called some case of
    /// "claude", and a case-insensitive name test would classify Claude Desktop itself as Claude
    /// Code. A Claude Code installed elsewhere — a CLI on `PATH`, say — is not matched and does not
    /// need to be: it is not a descendant of Claude Desktop, so it was never a false positive here.
    static let claudeCodePathMarker = "/claude-code/"

    static func owner(
        of pid: pid_t,
        claudeDesktopPIDs: Set<pid_t>,
        parent: (pid_t) -> pid_t?,
        executablePath: (pid_t) -> String?
    ) -> Owner {
        var current = pid
        for _ in 0..<maximumAncestorHops {
            guard let ancestor = parent(current) else { return .unknown }
            // **The line the old walk did not have.** Without it the loop below is the shipped
            // behaviour — "is a Claude Desktop PID anywhere above this server" — and every Claude
            // Code session inside the desktop app answers yes. Order between the two tests is
            // immaterial (no process is both); presence of this one is the whole fix.
            if executablePath(ancestor)?.contains(claudeCodePathMarker) == true { return .claudeCode }
            if claudeDesktopPIDs.contains(ancestor) { return .claudeDesktop }
            // launchd (1) and the kernel (0) top every tree: the walk finished, and neither owner
            // was anywhere on it.
            if ancestor <= 1 { return .none }
            current = ancestor
        }
        return .unknown
    }

    /// Every live process whose executable is exactly `binary`, or nil when the process list could
    /// not be read at all.
    ///
    /// Exact match, not a name match: a server left behind by a previous install lives at a
    /// different path, is not the binary we just registered, and is not evidence that *this* build
    /// is reachable.
    private static func liveProcesses(matching binary: String) -> [pid_t]? {
        let capacity = proc_listallpids(nil, 0)
        guard capacity > 0 else { return nil }
        // Headroom, because processes can be created between sizing the buffer and filling it.
        var pids = [pid_t](repeating: 0, count: Int(capacity) + 64)
        let byteCount = Int32(pids.count * MemoryLayout<pid_t>.size)
        let written = pids.withUnsafeMutableBufferPointer {
            proc_listallpids($0.baseAddress, byteCount)
        }
        guard written > 0 else { return nil }
        return pids.prefix(Int(written)).filter { $0 > 0 && executablePath(of: $0) == binary }
    }

    private static func executablePath(of pid: pid_t) -> String? {
        var buffer = [CChar](repeating: 0, count: executablePathCapacity)
        // A process that exited between the listing and this call, or one this user may not inspect,
        // answers nothing — which is not the path we are looking for either way.
        guard proc_pidpath(pid, &buffer, UInt32(executablePathCapacity)) > 0 else { return nil }
        return String(cString: buffer)
    }

    private static func parentPID(of pid: pid_t) -> pid_t? {
        var info = proc_bsdinfo()
        let size = Int32(MemoryLayout<proc_bsdinfo>.size)
        guard proc_pidinfo(pid, PROC_PIDTBSDINFO, 0, &info, size) == size else { return nil }
        return pid_t(info.pbi_ppid)
    }
}
