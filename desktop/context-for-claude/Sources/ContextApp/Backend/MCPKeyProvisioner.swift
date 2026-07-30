import ContextCore
import Combine
import Foundation

/// Gives `context-for-claude-mcp` a credential of its own.
///
/// The MCP server is spawned per Claude session, lives for seconds, and has nowhere to show a
/// browser, so it can only ever read a key that is already on disk. Nothing used to put one there:
/// the resolver's last resort is the `omi-memory` entry in `~/.claude.json`, which belongs to a
/// *different* MCP server, so a Mac that never configured one reported the Omi account unreachable
/// while Omi was demonstrably working everywhere else in the same session. Reading someone else's
/// credential is not a design; it is a coincidence that happened to hold on the author's machine.
///
/// The app is the only part of the product that can fix that. It is signed in with a real Firebase
/// ID token, so it asks the backend for an `omi_mcp_…` key of its own and writes it where the
/// resolver expects to find one — which matters because the local capture is minutes deep while the
/// account is months deep, and the account is the whole point.
///
/// Everything here is best-effort. Capture, upload and the local MCP tools do not depend on it: a
/// failure costs account history, never the app.
@MainActor
final class MCPKeyProvisioner: ObservableObject {
    static let shared = MCPKeyProvisioner()

    private static let category = "omi-key"

    enum Status: Equatable {
        case unknown
        case signedOut
        case ready
        case missing
        case failed(String)
    }

    @Published private(set) var status: Status = .unknown

    /// Must match `OmiKeyResolver.keyFileURL` in `ContextMCPKit`. The two halves of this contract
    /// live in separate targets because the MCP binary cannot link `ContextApp`.
    private static var keyFileURL: URL {
        ContextPaths.supportDirectory.appendingPathComponent("mcp-key")
    }

    /// Sidecar so MCP PostHog can stamp a uid-scoped distinct_id (not a shared blob).
    private static var uidFileURL: URL {
        ContextPaths.supportDirectory.appendingPathComponent("mcp-uid")
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
    private(set) var isBlockedForThisLaunch = false

    /// False when disk storage failed permanently this launch — retry would only mint more keys.
    var canRetry: Bool { !isBlockedForThisLaunch }

    private var didLogSignedOut = false
    private var didLogReuse = false

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

    /// Deletes the on-disk MCP credential so Claude cannot keep reading a signed-out account.
    func clearKeyForSignOut() {
        inFlight?.cancel()
        inFlight = nil
        try? FileManager.default.removeItem(at: Self.keyFileURL)
        try? FileManager.default.removeItem(at: Self.uidFileURL)
        didLogReuse = false
        didLogSignedOut = false
        status = .signedOut
        ContextLog.info("Cleared Omi MCP key on sign-out", Self.category)
    }

    // MARK: - Provisioning

    private func provision() async {
        let url = Self.keyFileURL

        // The file is the reuse mechanism, and deliberately the only one: the backend's list
        // endpoint returns a key's *prefix*, never its secret, so a key we did not write down at the
        // moment we minted it can never be used again — only recognised, and retired.
        if let existing = Self.storedKey(at: url) {
            _ = existing
            if let storedUid = Self.storedUid(),
               let currentUid = OmiAuth.shared.userId,
               !currentUid.isEmpty,
               storedUid != currentUid
            {
                ContextLog.info(
                    "Stored MCP key belongs to a different uid; re-provisioning", Self.category)
                try? FileManager.default.removeItem(at: url)
                try? FileManager.default.removeItem(at: Self.uidFileURL)
                didLogReuse = false
            } else {
                if !didLogReuse {
                    didLogReuse = true
                    ContextLog.info("Reusing the Omi MCP key already on disk", Self.category)
                }
                status = .ready
                Self.persistUidIfNeeded()
                return
            }
        }

        guard !isBlockedForThisLaunch else {
            status = .failed("Could not store the Omi MCP key on disk")
            return
        }

        guard OmiAuth.shared.isSignedIn else {
            // Routine, not a failure: the app runs before anyone signs in, and signing in calls back
            // here. Said once, so a support log still shows why there is no key.
            if !didLogSignedOut {
                didLogSignedOut = true
                ContextLog.info("Signed out; no Omi MCP key to provision yet", Self.category)
            }
            status = .signedOut
            return
        }

        status = .missing

        let name = Self.keyName
        let superseded = await Self.keyIds(named: name)

        let created: CreatedMCPKey
        do {
            created = try await OmiAPI.shared.post(
                "v1/mcp/keys",
                body: CreateMCPKeyRequest(name: name, product: OmiAPI.appProduct),
                as: CreatedMCPKey.self)
        } catch {
            // Offline, rate-limited, a token that would not refresh. The resolver falls back to
            // whatever else it can find, and the tools report the account unreachable — which is true.
            ContextLog.error("Could not provision an Omi MCP key: \(error.localizedDescription)", Self.category)
            status = .failed(error.localizedDescription)
            ContextAnalytics.capture(
                "mcp_key_provision_failed",
                properties: ["reason": String(error.localizedDescription.prefix(120))])
            return
        }

        do {
            try Self.persist(created.key, to: url)
            Self.persistUidIfNeeded()
        } catch {
            isBlockedForThisLaunch = true
            ContextLog.error(
                "Provisioned an Omi MCP key but could not store it: \(error.localizedDescription)", Self.category)
            status = .failed(error.localizedDescription)
            ContextAnalytics.capture(
                "mcp_key_provision_failed",
                properties: ["reason": "store_failed"])
            return
        }
        ContextLog.info("Provisioned an Omi MCP key for this Mac", Self.category)
        status = .ready
        ContextAnalytics.capture("mcp_key_provision_succeeded")

        // Only now: a mint that failed must leave the account exactly as it was.
        for id in superseded {
            await Self.retire(id)
        }
    }

    private static func persistUidIfNeeded() {
        guard let uid = OmiAuth.shared.userId, !uid.isEmpty else { return }
        try? uid.data(using: .utf8)?.write(to: uidFileURL, options: .atomic)
    }

    private static func storedUid() -> String? {
        guard let data = try? Data(contentsOf: uidFileURL),
              let text = String(data: data, encoding: .utf8)
        else { return nil }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
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
    private static func retire(_ keyId: String) async {
        // Stricter than `.urlPathAllowed`, which would let a "/" in an id walk off the endpoint.
        let unreserved = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-._~"))
        guard let escaped = keyId.addingPercentEncoding(withAllowedCharacters: unreserved), !escaped.isEmpty else {
            return
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
                return
            }
            ContextLog.info("Revoked this Mac's superseded Omi MCP key", category)
        } catch {
            ContextLog.error("Superseded Omi MCP key could not be revoked: \(error.localizedDescription)", category)
        }
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

    /// Writes the key and nothing else — no JSON envelope, no trailing newline.
    ///
    /// Created through `open(2)` with an explicit mode rather than `Data.write`, because this is a
    /// bearer credential for the user's whole account: a file that exists for even a moment at the
    /// umask's default is readable by every process running as this user for that window.
    private static func persist(_ key: String, to url: URL) throws {
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
    }
}

// MARK: - Wire shapes
//
// `OmiAPI`'s coders convert snake_case both ways. Only the fields this file acts on are declared —
// in particular no `Date`, so a timestamp shape the shared decoder dislikes can never fail the whole
// response and cost the user their account history.

private struct CreateMCPKeyRequest: Encodable {
    let name: String
    let product: String
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
