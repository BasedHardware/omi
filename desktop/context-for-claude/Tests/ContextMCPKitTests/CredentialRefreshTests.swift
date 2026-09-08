import Foundation
import XCTest

@testable import ContextMCPKit

/// **A rejected key must not become a permanent verdict on the account.**
///
/// `context-for-claude-mcp` is spawned per Claude session and then lives for as long as someone
/// leaves Claude open, while the app rewrites
/// `~/Library/Application Support/ContextForClaude/mcp-key` underneath it whenever it re-provisions.
/// With the credential read once at construction and `.unauthorized` cached with an infinite TTL,
/// those two facts combined into the worst failure this product has: a server that took one 401 in
/// the morning told Claude "the Omi MCP API key was rejected (HTTP 401) … only this Mac's local
/// capture is searchable" for the rest of the day, over a key file that had been replaced with a
/// working one at 08:02 and answered 200 to `curl` with those exact bytes. Claude then states, with
/// confidence and no hedge, that the user has no history — which is the one thing every tool in this
/// target exists to prevent.
///
/// So the credential is a source rather than a value, and these are the assertions that keep it one.
/// Hermetic in both directions: the credential is a fake whose value changes between reads, and the
/// transport is a closure, so nothing here touches the real key file or `api.omi.me`.
final class CredentialRefreshTests: XCTestCase {

    // MARK: A rejection is repaired, once

    /// The guard test for the bug, at the call that meets it: a 401 buys one re-read of the
    /// credential and one retry, and the retry is what the caller gets back.
    ///
    /// It fails against the code as it was — a `let credential` captured in `init` has nothing to
    /// re-read, so the fresh key on disk is never presented and the call comes back `.unauthorized`
    /// with the account perfectly reachable.
    func testARejectedKeyIsReReadAndTheReplacementIsTried() {
        let keys = KeySequence(["expired-key", "fresh-key"])
        let sent = RequestLog()
        let backend = OmiBackend(
            credential: keys.source,
            isAirgapped: { false },
            transport: { request in
                sent.record(request)
                return Self.answer(request, accepting: "fresh-key")
            })

        let result = backend.conversations(since: nil, until: nil, limit: 1)

        XCTAssertNil(result.failure, "the account answered on the key that is actually on disk")
        XCTAssertEqual(result.value?.first?.title, "Standup")
        XCTAssertEqual(sent.count, 2, "one rejection, one re-read, one retry")
        XCTAssertEqual(sent.bearers, ["expired-key", "fresh-key"])
    }

    /// The other half of that ceiling. An account that rejects two keys in a row has answered, and a
    /// client that keeps minting attempts against a 300-an-hour budget is how a broken account stays
    /// broken — so the retry is one, and the second refusal is cached rather than re-asked.
    func testASecondRejectionIsTheAccountsAnswerAndNotARetryStorm() {
        // A source that would hand out a different key every single time it is asked: the ceiling
        // has to come from the client, not from running out of keys.
        let keys = KeySequence(["key-1", "key-2", "key-3", "key-4"])
        let sent = RequestLog()
        let backend = OmiBackend(
            credential: keys.source,
            isAirgapped: { false },
            transport: { request in
                sent.record(request)
                return .failure(.unauthorized)
            })

        XCTAssertEqual(backend.conversations(since: nil, until: nil, limit: 1).failure, .unauthorized)
        XCTAssertEqual(sent.count, 2, "one re-read and one retry is the whole allowance for a call")

        // And the same read again, still on the same key: the cached rejection answers it, which is
        // what keeps a revoked key from spending the hourly budget a request at a time.
        XCTAssertEqual(backend.conversations(since: nil, until: nil, limit: 1).failure, .unauthorized)
        XCTAssertEqual(sent.count, 2)
    }

    // MARK: A rewritten key file, with no rejection in between

    /// **The live failure, exactly.** The 401 arrives, is cached with no expiry, and *then* — minutes
    /// or hours later, with no further request in between — the app writes a new key. Nothing about
    /// the next call is a rejection, so nothing invalidates the credential: the cached failure would
    /// answer first and keep answering forever.
    ///
    /// The revision (`stat` on the key file) is what breaks that loop, and it is asked before the
    /// cache is consulted rather than after.
    func testALatchedRejectionEndsWhenTheKeyFileIsRewritten() {
        let file = KeyFile(key: "expired-key", revision: "08:00")
        let sent = RequestLog()
        let backend = OmiBackend(
            credential: file.source,
            isAirgapped: { false },
            transport: { request in
                sent.record(request)
                return Self.answer(request, accepting: "fresh-key")
            })

        XCTAssertEqual(
            backend.conversations(since: nil, until: nil, limit: 1).failure, .unauthorized,
            "the key really was rejected, and saying so is correct at this point")

        // The app re-provisions: same path, new bytes, new mtime. It has no way to tell this process.
        file.rewrite(key: "fresh-key", revision: "08:02")

        let recovered = backend.conversations(since: nil, until: nil, limit: 1)

        XCTAssertNil(recovered.failure, "the account is readable again and the tool must say so")
        XCTAssertEqual(recovered.value?.first?.title, "Standup")
        XCTAssertEqual(sent.bearers.last, "fresh-key")
    }

    /// What `status` renders from, over the same rewrite. `renderOmiStatus` branches on exactly this
    /// value — "Unreachable: …" against a failure, "Reachable." against `.ok` — so a stale answer
    /// here is a status page that tells Claude the account cannot be read while it is being read.
    func testStatusSeesTheAccountAsReachableAgainAfterAReprovision() {
        let file = KeyFile(key: "expired-key", revision: "08:00")
        let backend = OmiBackend(
            credential: file.source,
            isAirgapped: { false },
            transport: { Self.answer($0, accepting: "fresh-key") })

        XCTAssertEqual(backend.history().failure, .unauthorized)

        file.rewrite(key: "fresh-key", revision: "08:02")

        guard case let .ok(probe) = backend.history() else {
            return XCTFail("a readable account must not still be reported unreachable")
        }
        XCTAssertEqual(probe.newest?.title, "Standup")
    }

    /// The other direction, and the ordinary one: this process is routinely spawned before the user
    /// has signed in, so there is no key file at all when it starts. `isConfigured` and the source
    /// label are read on demand for the same reason the key is — a snapshot taken at construction
    /// makes every tool report "not configured" for the rest of a session that signed in a minute
    /// after it began.
    func testAKeyProvisionedAfterThisProcessStartedIsPickedUp() {
        let file = KeyFile(key: nil, revision: nil)
        let backend = OmiBackend(
            credential: file.source,
            isAirgapped: { false },
            transport: { Self.answer($0, accepting: "fresh-key") })

        XCTAssertFalse(backend.isConfigured)
        XCTAssertNil(backend.keySourceLabel)

        file.rewrite(key: "fresh-key", revision: "08:02")

        XCTAssertTrue(backend.isConfigured)
        XCTAssertEqual(backend.keySourceLabel, OmiKeySource.appSupportFile.label)
    }

    // MARK: Helpers

    /// One conversation for a request that carries the accepted bearer, a flat 401 for anything else
    /// — which is what `/v1/mcp/*` does with a key that has been superseded.
    private static func answer(_ request: URLRequest, accepting key: String) -> Result<Data, OmiBackendError> {
        guard request.value(forHTTPHeaderField: "Authorization") == "Bearer \(key)" else {
            return .failure(.unauthorized)
        }
        return .success(
            Data(#"[{"id":"c1","started_at":"2026-08-14T09:00:00Z","structured":{"title":"Standup"}}]"#.utf8))
    }

    /// A credential whose value changes between reads without its revision moving — the 401 path,
    /// isolated from the `stat` path.
    private final class KeySequence: @unchecked Sendable {
        private let lock = NSLock()
        private let keys: [String]
        private var reads = 0

        init(_ keys: [String]) {
            precondition(!keys.isEmpty)
            self.keys = keys
        }

        var source: OmiCredentialSource {
            OmiCredentialSource(
                read: { [self] in
                    lock.lock()
                    defer { lock.unlock() }
                    // The last key stands for "and nothing newer after that", so running out is not
                    // what stops a client that retries too much.
                    let key = keys[min(reads, keys.count - 1)]
                    reads += 1
                    return (key, .appSupportFile)
                },
                revision: { nil })
        }
    }

    /// The key file as the app leaves it: contents and a `stat` that move together, or neither.
    private final class KeyFile: @unchecked Sendable {
        private let lock = NSLock()
        private var key: String?
        private var revision: String?

        init(key: String?, revision: String?) {
            self.key = key
            self.revision = revision
        }

        func rewrite(key: String?, revision: String?) {
            lock.lock()
            self.key = key
            self.revision = revision
            lock.unlock()
        }

        var source: OmiCredentialSource {
            OmiCredentialSource(
                read: { [self] in
                    lock.lock()
                    defer { lock.unlock() }
                    return key.map { ($0, .appSupportFile) }
                },
                revision: { [self] in
                    lock.lock()
                    defer { lock.unlock() }
                    return revision
                })
        }
    }

    /// What the transport was actually asked to send. The bearers are the assertion that matters:
    /// they say which key each attempt carried, which no error value can.
    private final class RequestLog: @unchecked Sendable {
        private let lock = NSLock()
        private var requests: [URLRequest] = []

        func record(_ request: URLRequest) {
            lock.lock()
            requests.append(request)
            lock.unlock()
        }

        var count: Int {
            lock.lock()
            defer { lock.unlock() }
            return requests.count
        }

        var bearers: [String] {
            lock.lock()
            defer { lock.unlock() }
            return requests.map {
                ($0.value(forHTTPHeaderField: "Authorization") ?? "").replacingOccurrences(of: "Bearer ", with: "")
            }
        }
    }
}
