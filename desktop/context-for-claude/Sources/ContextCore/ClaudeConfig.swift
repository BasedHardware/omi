import Foundation

/// Registration of the `context-for-claude` stdio MCP server into Claude Code and Claude Desktop.
///
/// Pure document manipulation, plus the two file primitives that manipulation needs. Deciding *when*
/// to register, and reporting the outcome, belongs to `ClaudeRegistrar` in the app target.
///
/// Everything here treats the user's config as sacred. `~/.claude.json` is not a file we author: it
/// carries their whole project history, their other MCP servers, and their account, in ~120 KB of
/// keys we know nothing about. Context for Claude is a guest adding one key to one dictionary inside it. So
/// every operation is a merge that preserves unknown keys verbatim, and every write lands through a
/// fully-flushed temp file — a crash, a full disk, or a power cut must never be able to leave a
/// truncated config behind.
public enum ClaudeConfig {
    /// The key both Claude surfaces register this under. Named for what it provides rather than
    /// for the app, because this string is what a model reads first when deciding whether a
    /// connector is worth calling.
    public static let serverName = serverName(forBundle: ContextPaths.bundleIdentifier)

    /// **A development build registers under its own key.**
    ///
    /// The key *is* the registration: whoever writes `context-for-claude` owns where Claude spawns
    /// the binary from. A dev build installed beside the release would otherwise repoint the user's
    /// production connector at a locally signed binary in a build directory — silently, on launch,
    /// with no failure anywhere. Every operation below keys off this one name, so the two builds
    /// touch disjoint entries: a dev build never rewrites or removes the release's, and vice versa.
    public static func serverName(forBundle bundleIdentifier: String) -> String {
        ContextPaths.isDevelopmentBuild(bundleIdentifier)
            ? "context-for-claude-dev" : "context-for-claude"
    }

    /// Names this connector has shipped under. Registering removes them so a rename leaves one
    /// entry rather than two servers racing to answer the same question.
    static let legacyServerNames = ["earshot", "omi-ambient"]

    /// The top-level key both surfaces use.
    private static let serversKey = "mcpServers"

    // MARK: - Locations

    /// `~/.claude.json`
    ///
    /// Resolved from the home directory rather than a container-aware API because Context for Claude is not
    /// sandboxed — screen capture and the system-audio tap rule that out — and must reach the real
    /// `~`, which is where Claude Code looks.
    public static var claudeCodeConfigURL: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".claude.json")
    }

    /// `~/Library/Application Support/Claude/claude_desktop_config.json`
    public static var claudeDesktopConfigURL: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/Claude", isDirectory: true)
            .appendingPathComponent("claude_desktop_config.json")
    }

    // MARK: - Document manipulation (pure)

    /// Merges an `context-for-claude` stdio entry into an existing config document without disturbing
    /// anything else in it. Returns the new document; `existing` is never mutated and the result
    /// shares no storage with it.
    ///
    /// Every other key, at every level, survives verbatim — including the ones this code has never
    /// heard of, which is nearly all of `~/.claude.json`. Sibling MCP servers under `mcpServers`
    /// (the user's `omi-memory` HTTP entry, for one) are carried across untouched.
    ///
    /// If `mcpServers` is present but is **not** a dictionary — a string, an array, `null`, anything
    /// — the document comes back unchanged. That shape is not one we wrote and not one we
    /// understand, and replacing it would delete whatever the user or a future Claude release put
    /// there. Failing to register is recoverable: `isRegistered` reports false, the caller says so
    /// out loud, and the user can repair the file by hand. Destroying their data is not recoverable,
    /// so the tie always breaks toward doing nothing.
    ///
    /// `as` is the key to write, defaulting to this build's. Stated rather than fixed for the same
    /// reason `ContextPaths.omiDatabaseURL(inApplicationSupport:)` takes a root: the property that
    /// matters is that a build touches *only* its own entry, and that cannot be asserted while the
    /// name is a constant the test shares with the code.
    public static func merged(
        into existing: [String: Any], mcpBinaryPath: String, as serverName: String = serverName
    ) -> [String: Any] {
        var document = deepCopy(existing)

        if let present = document[serversKey], !(present is [String: Any]) {
            return document
        }

        var servers = document[serversKey] as? [String: Any] ?? [:]
        for legacy in legacyServerNames { servers.removeValue(forKey: legacy) }
        servers[serverName] = serverEntry(mcpBinaryPath: mcpBinaryPath)
        document[serversKey] = servers
        return document
    }

    /// True when `existing` already points `context-for-claude` at exactly `mcpBinaryPath`.
    ///
    /// Deliberately an exact path match, not a presence check. A leftover entry from an older
    /// install has our name but a `command` that no longer resolves to a binary; reporting that as
    /// registered would leave Claude with a server that fails to spawn forever. Reporting it as
    /// unregistered makes the caller rewrite it, which is the repair.
    public static func isRegistered(
        in existing: [String: Any], mcpBinaryPath: String, as serverName: String = serverName
    ) -> Bool {
        guard let servers = existing[serversKey] as? [String: Any],
              // A leftover entry under an old name means there is still work to do here, even when
              // the current one is already correct — otherwise two servers answer the same
              // question and the rename never finishes.
              legacyServerNames.allSatisfy({ servers[$0] == nil }),
              let entry = servers[serverName] as? [String: Any],
              let command = entry["command"] as? String
        else { return false }
        return command == mcpBinaryPath
    }

    /// Removes only the `context-for-claude` entry. Every other server, and every other key, is untouched.
    /// An `mcpServers` that is missing or not a dictionary is left exactly as found, for the same
    /// reason `merged` leaves it alone.
    public static func removed(
        from existing: [String: Any], as serverName: String = serverName
    ) -> [String: Any] {
        var document = deepCopy(existing)
        guard var servers = document[serversKey] as? [String: Any] else { return document }
        servers.removeValue(forKey: serverName)
        for legacy in legacyServerNames { servers.removeValue(forKey: legacy) }
        document[serversKey] = servers
        return document
    }

    /// The entry written into `mcpServers`, exactly:
    /// `{ "type": "stdio", "command": "<absolute path>", "args": [], "env": {} }`
    private static func serverEntry(mcpBinaryPath: String) -> [String: Any] {
        [
            "type": "stdio",
            "command": mcpBinaryPath,
            "args": [Any](),
            "env": [String: Any](),
        ]
    }

    // MARK: - File I/O

    /// Reads and parses a config document. Returns an empty document when the file is absent, and
    /// throws when it exists but is not valid JSON — silently overwriting a corrupt config would
    /// destroy the user's settings, so a parse failure has to surface as a failure instead of
    /// quietly becoming "start from scratch".
    ///
    /// The same reasoning covers read errors: only a genuinely missing file yields `[:]`. A
    /// permissions problem or an unreadable volume throws, because treating it as empty would send
    /// the caller off to write a one-key file over the top of a config that was fine.
    public static func readDocument(at url: URL) throws -> [String: Any] {
        let data: Data
        do {
            data = try Data(contentsOf: url)
        } catch {
            guard FileManager.default.fileExists(atPath: url.path) else { return [:] }
            throw ClaudeConfigError.unreadable("\(url.path): \(error.localizedDescription)")
        }

        // A zero-byte file holds nothing to preserve, so it is first-run, not corruption.
        guard !data.isEmpty else { return [:] }

        let parsed: Any
        do {
            parsed = try JSONSerialization.jsonObject(with: data)
        } catch {
            throw ClaudeConfigError.malformed("\(url.path): \(error.localizedDescription)")
        }

        guard let document = parsed as? [String: Any] else {
            throw ClaudeConfigError.notAnObject(url.path)
        }
        return document
    }

    /// Writes atomically: serialize to a sibling temp file, flush it to stable storage, then
    /// `replaceItemAt`. A crash mid-write must never leave a truncated `~/.claude.json`.
    ///
    /// The real file is never opened for writing, so it is never in a half-state; the only thing
    /// that ever touches it is a single directory-entry swap of a file that is already complete and
    /// already on disk.
    ///
    /// Output is `.prettyPrinted` + `.sortedKeys`. Sorting reorders keys, which would be rude to a
    /// file humans maintain — but nothing reads these as text. Claude Code and Claude Desktop parse
    /// them as JSON, where key order carries no meaning, which is what makes sorting safe. In
    /// exchange it is deterministic: two runs that change nothing produce identical bytes, so any
    /// diff the user sees in their config is a change we actually made.
    public static func writeDocument(_ document: [String: Any], to url: URL) throws {
        // `JSONSerialization.data` raises an Objective-C exception — uncatchable from Swift — when
        // the object graph is not serializable. Check first, so a bad document is a thrown error
        // rather than a crash inside the app.
        guard JSONSerialization.isValidJSONObject(document) else {
            throw ClaudeConfigError.notAnObject(url.path)
        }

        let data: Data
        do {
            data = try JSONSerialization.data(
                withJSONObject: document,
                // `.withoutEscapingSlashes` keeps URLs and absolute paths legible and matches how
                // Claude's own writer leaves them, so we do not churn every existing value.
                options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
            )
        } catch {
            throw ClaudeConfigError.malformed("\(url.path): \(error.localizedDescription)")
        }

        let fileManager = FileManager.default
        let directory = url.deletingLastPathComponent()
        do {
            try fileManager.createDirectory(at: directory, withIntermediateDirectories: true)
        } catch {
            throw ClaudeConfigError.unreadable("\(directory.path): \(error.localizedDescription)")
        }

        // A sibling, so the swap below is a rename inside one filesystem — a cross-device move would
        // be a copy, and a copy is exactly the truncation window this method exists to avoid. Hidden
        // and uniquely named so a temp orphaned by a crash is neither mistaken for a config nor
        // collided with by a concurrent writer.
        let tempURL = directory.appendingPathComponent(
            ".\(url.lastPathComponent).context-for-claude-\(UUID().uuidString).tmp"
        )

        // Both configs hold credentials (`~/.claude.json` carries the OAuth account). Create the
        // temp at the original's mode, defaulting to owner-only, so the content is never briefly
        // world-readable and a file we create fresh is not born at the default 0644.
        let existingMode = (try? fileManager.attributesOfItem(atPath: url.path))?[.posixPermissions] as? NSNumber
        guard fileManager.createFile(
            atPath: tempURL.path,
            contents: nil,
            attributes: [.posixPermissions: existingMode ?? NSNumber(value: 0o600)]
        ) else {
            throw ClaudeConfigError.unreadable("could not create a temporary file beside \(url.path)")
        }

        do {
            try writeFlushed(data, to: tempURL)

            // Cheap insurance against a short write — a full disk is the realistic cause. Read the
            // bytes back and confirm they still parse before letting them anywhere near the real
            // file, because the alternative is swapping a truncated document into place.
            let written = try Data(contentsOf: tempURL)
            guard written.count == data.count,
                  let reparsed = try? JSONSerialization.jsonObject(with: written),
                  reparsed is [String: Any]
            else {
                throw ClaudeConfigError.malformed("temporary write for \(url.path) did not verify")
            }

            if fileManager.fileExists(atPath: url.path) {
                // Swaps the directory entry and keeps the original's metadata and extended
                // attributes, so the path resolves to a whole file at every instant: the old one
                // until the swap, the new one after it.
                _ = try fileManager.replaceItemAt(url, withItemAt: tempURL)
            } else {
                // No original to replace; `rename(2)` is atomic on its own.
                try fileManager.moveItem(at: tempURL, to: url)
            }
        } catch {
            try? fileManager.removeItem(at: tempURL)
            throw error
        }

        // The swap itself is a directory-metadata change, and until the directory is flushed it can
        // still be sitting in the volume cache when the power goes.
        let directoryDescriptor = open(directory.path, O_RDONLY)
        if directoryDescriptor >= 0 {
            fsync(directoryDescriptor)
            close(directoryDescriptor)
        }
    }

    /// Writes `data` to an existing file and does not return until the bytes are on stable storage.
    private static func writeFlushed(_ data: Data, to url: URL) throws {
        let handle = try FileHandle(forWritingTo: url)
        do {
            try handle.write(contentsOf: data)
            // Durability, not just ordering. On macOS `fsync` only hands the bytes to the drive's
            // write cache; `F_FULLFSYNC` is what actually forces them onto the medium. It is
            // unsupported on some volumes (network mounts), where plain `fsync` is the best there
            // is — still far better than replacing a config over unflushed data.
            if fcntl(handle.fileDescriptor, F_FULLFSYNC) == -1 {
                try handle.synchronize()
            }
            try handle.close()
        } catch {
            try? handle.close()
            throw error
        }
    }

    // MARK: - Value semantics

    private static func deepCopy(_ document: [String: Any]) -> [String: Any] {
        var copy = [String: Any](minimumCapacity: document.count)
        for (key, value) in document {
            copy[key] = deepCopyValue(value)
        }
        return copy
    }

    /// Rebuilds containers as native Swift values so a merged document shares no storage with the
    /// caller's. `JSONSerialization` hands back bridged `NSDictionary`/`NSArray` objects, and a
    /// result that aliased them could observe a later mutation of the input — the kind of bug that
    /// only shows up on a user's machine, in their config.
    ///
    /// Scalars pass through untouched on purpose: an `NSNumber` remembers whether it came from a
    /// JSON `true`, an integer, or a double, and re-wrapping it as a Swift type would lose that and
    /// silently rewrite the user's booleans as `1`.
    private static func deepCopyValue(_ value: Any) -> Any {
        if let dictionary = value as? [String: Any] { return deepCopy(dictionary) }
        if let array = value as? [Any] { return array.map(deepCopyValue) }
        return value
    }
}

// MARK: - Errors

public enum ClaudeConfigError: LocalizedError {
    /// The file exists but could not be read, or a temp file could not be created beside it.
    case unreadable(String)
    /// The file exists but is not valid JSON, or a write did not verify.
    case malformed(String)
    /// Valid JSON, but not a JSON object — so there is no `mcpServers` to merge into.
    case notAnObject(String)

    public var errorDescription: String? {
        switch self {
        case .unreadable(let detail):
            return "Could not read the Claude config (\(detail))."
        case .malformed(let detail):
            return "The Claude config is not valid JSON (\(detail)). Context for Claude left it untouched."
        case .notAnObject(let detail):
            return "The Claude config at \(detail) is not a JSON object. Context for Claude left it untouched."
        }
    }
}
