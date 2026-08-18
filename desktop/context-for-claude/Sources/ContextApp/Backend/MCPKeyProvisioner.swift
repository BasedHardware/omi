import ContextCore
import Foundation

/// Gives `context-for-claude-mcp` a credential of its own.
///
/// The MCP server is spawned per Claude session, lives for seconds, and has nowhere to show a
/// browser, so it can only ever read a key that is already on disk. Nothing used to put one there,
/// so a Mac without a provisioned key reported the Omi account unreachable while Omi was
/// demonstrably working everywhere else in the same session.
///
/// The app is the only part of the product that can fix that. It is signed in with a real Firebase
/// ID token, so it asks the backend for an `omi_mcp_…` key of its own and writes it where the
/// resolver expects to find one — which matters because the local capture is minutes deep while the
/// account is months deep, and the account is the whole point.
///
/// The app reads that same key back. `/v1/mcp/*` is the one endpoint family a Firebase ID token
/// cannot open — `get_uid_from_mcp_api_key` looks the bearer up in `mcp_api_keys` and a token that
/// is not an `omi_mcp_…` key is a flat 401 — so the Activity surface authenticates with this
/// credential rather than with the session it is signed in as. That makes one key per Mac serve both
/// halves of the product, and makes the app the half that can repair it: see `key(replacing:)`.
///
/// Everything here is best-effort. Capture, upload and the local MCP tools do not depend on it: a
/// failure costs account history, never the app.
@MainActor
final class MCPKeyProvisioner {
    static let shared = MCPKeyProvisioner()

    private static let category = "omi-key"

    /// Must match `OmiKeyResolver.keyFileURL` in `ContextMCPKit`. The two halves of this contract
    /// live in separate targets because the MCP binary cannot link `ContextApp`.
    private static var keyFileURL: URL {
        ContextPaths.supportDirectory.appendingPathComponent("mcp-key")
    }

    /// Scoped to this Mac, and stable across renames, because one account is shared by every device
    /// the user runs Context for Claude on. It is what makes "this Mac's key" something that can be
    /// recognised on a later launch without ever matching a key a person made by hand.
    private static var keyName: String {
        "Context for Claude (\(OmiAPI.deviceIdHash.prefix(8)))"
    }

    /// One attempt at a time. `ensureKey()` is called at launch and again whenever sign-in state
    /// changes, and two concurrent runs would mint two keys for one Mac.
    private var inFlight: Task<Void, Never>?

    /// Set when a key was minted but could not be stored. Retrying would mint another key on every
    /// call and leave the account holding credentials nobody has — the failure is the disk, and it
    /// will not heal inside one launch.
    private var isBlockedForThisLaunch = false

    private var didLogSignedOut = false
    private var didLogReuse = false
    private var didLogAirgap = false

    /// How many keys a rejection has been allowed to replace this launch.
    ///
    /// **This is the loop stop.** The Activity surface polls, so a backend that rejects every key it
    /// issues would otherwise have this Mac mint one per read — filling the account's key list with
    /// credentials nobody can use and revoking each of them a moment later. Two is enough for the
    /// case this exists for (the key on disk was superseded or revoked) and far short of a storm;
    /// past it the rejection is the account's answer, not a stale file, and the surface says so.
    private var reprovisions = 0
    private static let reprovisionCeiling = 2

    private init() {}

    // MARK: - Entry point

    /// Ensures a usable MCP key exists on disk for the MCP server to read.
    /// No-op when one is already present, or while signed out.
    func ensureKey() async {
        if let existing = inFlight {
            await existing.value
            return
        }
        let task = Task { await self.provision() }
        inFlight = task
        await task.value
        inFlight = nil
    }

    func removeKey() {
        inFlight?.cancel()
        inFlight = nil
        try? Self.removeKeyFiles(at: Self.keyFileURL)
        isBlockedForThisLaunch = false
        didLogReuse = false
        reprovisions = 0
    }

    // MARK: - Reading it back

    /// The key this Mac should present to `/v1/mcp/*`, provisioning one first if there is none.
    ///
    /// `nil` is every reason there is no credential — signed out, Airgap Mode, a mint that failed —
    /// and the caller's job is to report the account unreachable rather than to render an empty one.
    func key() async -> String? {
        await ensureKey()
        return Self.storedKey(at: Self.keyFileURL)
    }

    /// Replaces a key the backend has just rejected, and answers with whatever this Mac should use
    /// now — `nil` when nothing can be.
    ///
    /// Two things keep this from becoming a mint loop. **A key that is no longer the one on disk has
    /// already been replaced**, by a sibling read that hit the same 401 a moment earlier — the three
    /// Activity sources race, so without that check the second and third rejections would each
    /// revoke the key the first one just wrote. And past `reprovisionCeiling` this stops minting
    /// entirely: a freshly issued key that is *also* rejected is the account refusing, and the only
    /// honest thing left is to say the account could not be read.
    func key(replacing rejected: String) async -> String? {
        let keyURL = Self.keyFileURL
        if let onDisk = Self.storedKey(at: keyURL), onDisk != rejected { return onDisk }

        guard reprovisions < Self.reprovisionCeiling else {
            ContextLog.error(
                "The Omi backend rejected this Mac's MCP key again; not minting another this launch",
                Self.category)
            return nil
        }
        reprovisions += 1
        ContextLog.info("The Omi backend rejected this Mac's MCP key; provisioning a new one", Self.category)

        // Removed before the mint, because `provision()` treats a key on disk as the reuse
        // mechanism and would otherwise hand the rejected one straight back.
        try? Self.removeKeyFiles(at: keyURL)
        didLogReuse = false
        await ensureKey()

        // An unchanged key means nothing was minted — signed out, Airgap Mode, or the mint failed.
        guard let fresh = Self.storedKey(at: keyURL), fresh != rejected else { return nil }
        return fresh
    }

    // MARK: - Provisioning

    private func provision() async {
        let keyURL = Self.keyFileURL

        // The file is the reuse mechanism, and deliberately the only one: the backend's list
        // endpoint returns a key's *prefix*, never its secret, so a key we did not write down at the
        // moment we minted it can never be used again — only recognised, and retired.
        let ownerURL = keyURL.appendingPathExtension("owner")
        if Self.storedKey(at: keyURL) != nil,
            let storedOwner = Self.storedOwner(at: ownerURL),
            let userId = OmiAuth.shared.userId,
            storedOwner == userId
        {
            if !didLogReuse {
                didLogReuse = true
                ContextLog.info("Reusing the Omi MCP key already on disk", Self.category)
            }
            return
        }

        if Self.storedKey(at: keyURL) != nil {
            try? Self.removeKeyFiles(at: keyURL)
            didLogReuse = false
        }

        guard !isBlockedForThisLaunch else { return }

        // Minting a key is three calls to `api.omi.me` — list, create, revoke-superseded — so Airgap
        // Mode stops it. Nothing is queued and nothing is lost: `ensureKey()` runs again on the next
        // launch and on every sign-in change, so turning Airgap Mode off provisions the key then.
        //
        // Placed *after* the reuse check, and that is a real limitation worth naming rather than
        // papering over. A key already on disk is left alone, because deleting it would be both
        // destructive and ineffective: `OmiKeyResolver` in `ContextMCPKit` falls back to any other
        // Omi key it can find in `~/.claude.json`, so removing ours would not stop the MCP binary
        // reaching the backend — it would only make it borrow someone else's credential. That binary
        // is a separate process with its own `URLSession` (`ContextMCPKit/OmiBackend.swift`), and
        // that is where that hole is closed rather than here: it re-reads the same `exclusions.json`
        // through `MCPNetworkEgress` before every request, and names itself to this app's audited
        // list as `NetworkEgress.Client.mcpOmiBackend`. So a key left on disk is a key that binary
        // will not spend while the switch is on.
        guard !NetworkEgress.isSuppressed(.mcpKeyProvisioning) else {
            if !didLogAirgap {
                didLogAirgap = true
                ContextLog.info(
                    "Airgap Mode on; not provisioning an Omi MCP key. Account-backed MCP tools stay unavailable.",
                    Self.category)
                NetworkEgress.recordSuppression(.mcpKeyProvisioning, outcome: .degraded)
            }
            return
        }
        didLogAirgap = false

        guard OmiAuth.shared.isSignedIn else {
            // Routine, not a failure: the app runs before anyone signs in, and signing in calls back
            // here. Said once, so a support log still shows why there is no key.
            if !didLogSignedOut {
                didLogSignedOut = true
                ContextLog.info("Signed out; no Omi MCP key to provision yet", Self.category)
            }
            return
        }

        let name = Self.keyName
        let superseded = await Self.keyIds(named: name)

        let created: CreatedMCPKey
        do {
            created = try await OmiAPI.shared.post(
                "v1/mcp/keys", body: CreateMCPKeyRequest(name: name), as: CreatedMCPKey.self)
        } catch {
            // Offline, rate-limited, a token that would not refresh. The resolver falls back to
            // whatever else it can find, and the tools report the account unreachable — which is true.
            ContextLog.error("Could not provision an Omi MCP key: \(error.localizedDescription)", Self.category)
            return
        }

        guard let owner = OmiAuth.shared.userId, !owner.isEmpty else { return }

        do {
            try Self.persist(created.key, owner: owner, to: keyURL)
        } catch {
            isBlockedForThisLaunch = true
            ContextLog.error(
                "Provisioned an Omi MCP key but could not store it: \(error.localizedDescription)", Self.category)
            return
        }
        ContextLog.info("Provisioned an Omi MCP key for this Mac", Self.category)

        // Only now: a mint that failed must leave the account exactly as it was.
        for id in superseded {
            await Self.retire(id)
        }
    }

    /// Ids of the keys on the account carrying `name`, so the ones this Mac can no longer read get
    /// retired instead of accumulating. A failure here is not a reason to stop — it costs tidiness,
    /// not function.
    private static func keyIds(named name: String) async -> [String] {
        do {
            let keys = try await OmiAPI.shared.get("v1/mcp/keys", as: [MCPKeyRecord].self)
            return keys.filter { $0.name == name }.map(\.id)
        } catch {
            ContextLog.error("Could not list Omi MCP keys: \(error.localizedDescription)", category)
            return []
        }
    }

    /// Revokes a key this Mac minted on an earlier install and can no longer read.
    ///
    /// Exact-name matching is what makes this safe: the name carries this Mac's device fingerprint,
    /// so it can never match `omi-memory`'s key or anything a person typed. `OmiAPI` has no DELETE
    /// verb and this is its only caller, so the request is built here from the same header set —
    /// the pattern `ScreenActivityUploader` already uses for the endpoint it owns.
    @discardableResult
    static func retire(
        _ keyId: String,
        isSuppressed: () -> Bool = { NetworkEgress.isSuppressed(.mcpKeyProvisioning) }
    ) async -> RevokeOutcome {
        // This request is built here rather than through `OmiAPI`, so it does not inherit `OmiAPI`'s
        // airgap guard and needs its own. Unreachable under Airgap Mode today — `provision()` stops
        // before the mint that produces a superseded id — but "unreachable" is a property of today's
        // call graph, and this is a DELETE to a remote host.
        //
        // **The record is not optional and this is where that was learned.** For as long as this
        // guard existed it refused and said nothing, which made it the one suppression in the app
        // that never reached telemetry — so the answer to "what did Airgap Mode actually stop?" was
        // wrong by exactly this call, and wrong in the direction that hides a client rather than
        // inventing one. A refusal nobody records is a refusal nobody can audit.
        guard !isSuppressed() else {
            NetworkEgress.recordSuppression(.mcpKeyProvisioning, outcome: .degraded)
            return .suppressedByAirgap
        }

        // Stricter than `.urlPathAllowed`, which would let a "/" in an id walk off the endpoint.
        let unreserved = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-._~"))
        guard let escaped = keyId.addingPercentEncoding(withAllowedCharacters: unreserved), !escaped.isEmpty else {
            return .unusableId
        }
        var request = URLRequest(url: OmiAPI.baseURL.appendingPathComponent("v1/mcp/keys/\(escaped)"))
        request.httpMethod = "DELETE"
        do {
            request.allHTTPHeaderFields = try await OmiAPI.shared.headers()
            let (_, response) = try await session.data(for: request)
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            // 404 counts: the key is gone, which is the whole point of the call.
            guard status == 204 || status == 200 || status == 404 else {
                ContextLog.error("Superseded Omi MCP key could not be revoked (HTTP \(status))", category)
                return .attempted
            }
            ContextLog.info("Revoked this Mac's superseded Omi MCP key", category)
        } catch {
            ContextLog.error("Superseded Omi MCP key could not be revoked: \(error.localizedDescription)", category)
        }
        return .attempted
    }

    /// What a revoke did, returned rather than swallowed so the refusal is drivable in a test.
    ///
    /// Inferring "nothing was sent" from a `Void` function means either believing the guard or
    /// issuing the DELETE to find out, and this is a live account behind a rate limit. The value is
    /// the evidence instead.
    enum RevokeOutcome: Equatable, Sendable {
        /// Airgap Mode was on. No URL was built, so nothing was sent and nothing is owed.
        case suppressedByAirgap
        /// The id could not be escaped into a path segment. Also sends nothing — and it is the
        /// control the airgap case needs, because it proves a refusal can be reached with the
        /// switch off.
        case unusableId
        /// A DELETE was issued. Whether the backend accepted it is in the log, not here: a failed
        /// revoke costs tidiness, never function.
        case attempted
    }

    private static let session: URLSession = {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 30
        configuration.timeoutIntervalForResource = 60
        return URLSession(configuration: configuration)
    }()

    // MARK: - Disk

    /// The stored key, or nil when there is nothing usable there.
    ///
    /// Any non-empty content counts, and is read exactly the way the resolver reads it. Re-minting
    /// over something a person put there by hand would be worse than trusting it.
    private static func storedKey(at url: URL) -> String? {
        guard let data = try? Data(contentsOf: url), let text = String(data: data, encoding: .utf8) else {
            return nil
        }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    private static func storedOwner(at url: URL) -> String? {
        guard let data = try? Data(contentsOf: url), let text = String(data: data, encoding: .utf8) else {
            return nil
        }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    private static func removeKeyFiles(at keyURL: URL) {
        if FileManager.default.fileExists(atPath: keyURL.path) {
            try? FileManager.default.removeItem(at: keyURL)
        }
        let ownerURL = keyURL.appendingPathExtension("owner")
        if FileManager.default.fileExists(atPath: ownerURL.path) {
            try? FileManager.default.removeItem(at: ownerURL)
        }
    }

    /// Writes the key and nothing else — no JSON envelope, no trailing newline.
    ///
    /// Created through `open(2)` with an explicit mode rather than `Data.write`, because this is a
    /// bearer credential for the user's whole account: a file that exists for even a moment at the
    /// umask's default is readable by every process running as this user for that window.
    private static func persist(_ key: String, owner: String, to url: URL) throws {
        try ContextPaths.ensureSupportDirectory()

        // Replaced rather than truncated: an existing file may already be group-readable, and
        // `O_TRUNC` would keep those bits.
        if FileManager.default.fileExists(atPath: url.path) {
            try FileManager.default.removeItem(at: url)
        }

        let descriptor = open(url.path, O_WRONLY | O_CREAT | O_EXCL, 0o600)
        guard descriptor >= 0 else {
            throw MCPKeyProvisionError.write(String(cString: strerror(errno)))
        }
        let handle = FileHandle(fileDescriptor: descriptor, closeOnDealloc: true)
        defer { try? handle.close() }
        try handle.write(contentsOf: Data(key.utf8))

        // A umask only ever clears bits, so the mode above is already an upper bound. This covers
        // the case where the file survived removal — a stale hard link, a network volume — and kept
        // its old mode: the resolver would only warn about that, and the key would stay exposed.
        try? FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)

        let ownerURL = url.appendingPathExtension("owner")
        try Data(owner.utf8).write(to: ownerURL, options: .atomic)
        try? FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: ownerURL.path)
    }
}

// MARK: - Wire shapes
//
// `OmiAPI`'s coders convert snake_case both ways. Only the fields this file acts on are declared —
// in particular no `Date`, so a timestamp shape the shared decoder dislikes can never fail the whole
// response and cost the user their account history.

private struct CreateMCPKeyRequest: Encodable {
    let name: String
}

/// `POST /v1/mcp/keys` — the one and only moment the raw key is ever returned.
private struct CreatedMCPKey: Decodable {
    let id: String
    let key: String
}

/// `GET /v1/mcp/keys` — metadata only. There is no `key` field here, by design.
private struct MCPKeyRecord: Decodable {
    let id: String
    let name: String
}

private enum MCPKeyProvisionError: LocalizedError {
    case write(String)

    var errorDescription: String? {
        switch self {
        case .write(let detail): return detail
        }
    }
}
