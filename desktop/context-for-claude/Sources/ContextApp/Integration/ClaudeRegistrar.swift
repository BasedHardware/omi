import ContextCore
import Foundation

/// Points Claude Code and Claude Desktop at the bundled `context-for-claude-mcp` server.
///
/// `ClaudeConfig` owns every decision about the *document*; this file owns the decisions about the
/// *disk*: which binary to name, whether a surface exists on this Mac at all, and what to tell the
/// user afterwards. The two surfaces are handled independently on purpose — an unparseable
/// `~/.claude.json` must not cost the user their Claude Desktop connection, and vice versa.
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
