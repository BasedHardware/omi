import ContextCore
import Foundation
import XCTest

@testable import ContextMCPKit

/// Airgap Mode has to hold in *this* process, not only in the app that spawns it.
///
/// `context-for-claude-mcp` runs with its own `URLSession` and its own copy of the configuration, so
/// "the app stopped uploading" says nothing about what this binary does. These are the assertions
/// that make the Settings subtitle true of this process too — that subtitle now says the app stops
/// reaching the network, and is careful *not* to claim Claude is restricted, because the MCP tools
/// still read local capture when asked.
///
/// **Hermetic in both directions now.** Every configuration read is against a file the test wrote
/// into its own temporary directory, and `OmiBackend` takes a `transport` — so a gate that stopped
/// working fails the test on contact instead of quietly reaching `api.omi.me` and coming back
/// `.unauthorized`. That was the follow-up this file used to ask for, and it is not fastidiousness:
/// the account behind that host is rate-limited, and a suite that proves a guard by exercising it
/// spends the user's budget to learn what a tripwire says for free.
final class AirgapTests: XCTestCase {

    // MARK: The gate

    /// The guard test for the hole this file exists to close.
    ///
    /// It fails against the code as it was: with no gate in `OmiBackend.get`, a configured backend
    /// builds `GET https://api.omi.me/v1/mcp/conversations` and hands it to the transport — which is
    /// a tripwire, so the assertion is that *no request was issued* rather than an inference drawn
    /// from whichever error the network happened to return.
    func testAConfiguredAccountIsNotReadWhileAirgapModeIsOn() {
        let backend = OmiBackend(
            credential: (key: "not-a-real-key", source: .environment),
            isAirgapped: { true },
            transport: { request in
                XCTFail("Airgap Mode must not let a read reach \(request.url?.host ?? "the network")")
                return .failure(.offline("unreachable"))
            })

        let result = backend.conversations(since: nil, until: nil, limit: 5)

        XCTAssertEqual(result.failure, .airgapped)
        XCTAssertNil(result.value)
    }

    /// The control the tripwire above needs: the same read, the same client, switch off — it reaches
    /// the transport. Without it, a backend that refused everything would pass every assertion here
    /// and leave `recall` unable to see the account at all.
    func testTheSameReadReachesTheNetworkWhenAirgapModeIsOff() {
        let sent = RequestLog()
        let backend = OmiBackend(
            credential: (key: "not-a-real-key", source: .environment),
            isAirgapped: { false },
            transport: { request in
                sent.record(request)
                return .success(Data("[]".utf8))
            })

        _ = backend.conversations(since: nil, until: nil, limit: 5)

        XCTAssertEqual(sent.count, 1, "one read, one request")
        XCTAssertEqual(sent.lastMethod, "GET")
    }

    /// This process names itself to the app's audited egress list, and this is the assertion that
    /// keeps the two sides agreeing.
    ///
    /// `ContextApp` cannot link this target, so `NetworkEgress.Client.mcpOmiBackend` carries this
    /// string as its raw value rather than importing it — which means the record this process emits
    /// and the record the app would emit for it are the same line. That mattered because for a while
    /// this client was in no list at all: `AirgapEgressTests` iterated `Client.allCases` and reported
    /// a complete audit of a product whose sibling process it could not see. Its counterpart is
    /// `AirgapEgressTests.testTheMCPProcessIsInTheAuditedListUnderTheNameItReportsItselfBy`.
    func testTheMCPClientAnswersToTheNameTheAppAuditsItUnder() {
        XCTAssertEqual(OmiBackend.egressClientName, "omi-backend")
    }

    /// The switch is live in both directions, and this process is spawned per Claude session — so a
    /// person who turns Airgap Mode on (or back off) mid-session must be obeyed on the very next
    /// tool call, not on the next Claude restart.
    ///
    /// Two identical requests: the flag is consulted twice, which is only possible if the answer is
    /// neither memoised nor served from the response cache. Caching the refusal would keep refusing
    /// after the switch went off; caching the flag would keep sending after it went on.
    func testTheAirgapFlagIsReadOnEveryAttemptAndTheRefusalIsNeverCached() {
        let reads = Counter()
        let backend = OmiBackend(
            credential: (key: "not-a-real-key", source: .environment),
            isAirgapped: {
                reads.increment()
                return true
            })

        // The same URL twice: a cached refusal would answer the second one without asking again.
        _ = backend.conversations(since: nil, until: nil, limit: 5)
        _ = backend.conversations(since: nil, until: nil, limit: 5)

        XCTAssertEqual(reads.value, 2)
    }

    /// A blocked read must never come back looking like an empty account.
    ///
    /// The sentence is carried on the error itself, so every renderer — the footers, the "nothing
    /// found" prose, `status`, `transcript` — inherits it. It has to name the setting and where to
    /// change it, or the user cannot connect the silence to the switch they flipped.
    func testASuppressedReadSaysAirgapModeAndWhereToTurnItOff() {
        let reason = OmiBackendError.airgapped.reason

        XCTAssertTrue(reason.contains("Airgap Mode"), reason)
        XCTAssertTrue(reason.contains("Settings"), reason)
        // "Nothing came back" and "nothing was asked" are opposite conclusions for a reader.
        XCTAssertTrue(reason.contains("no request was sent"), reason)
        // It must not read as an account failure the user cannot do anything about.
        XCTAssertNotEqual(OmiBackendError.airgapped, OmiBackendError.offline("airgap"))
    }

    // MARK: Reading the flag

    /// The reason this reads from disk on every ask instead of trusting `ExclusionEngine.shared`'s
    /// startup snapshot: the switch is flipped in *another process*, and nothing tells this one.
    ///
    /// One engine, one file, two answers. An implementation that read `engine.current.airgapMode`
    /// without reloading passes the first assertion and fails the second — which is exactly the bug
    /// where a Claude session opened before the click keeps talking to the network until it ends.
    func testTheFlagIsRereadFromDiskWhenItChangesUnderTheProcess() throws {
        let directory = try makeTemporaryDirectory()
        let configuration = directory.appendingPathComponent("exclusions.json")
        try #"{"airgapMode": false}"#.write(to: configuration, atomically: true, encoding: .utf8)
        let engine = ExclusionEngine(configurationURL: configuration, framesRoot: directory)

        XCTAssertFalse(MCPNetworkEgress.isAirgapped(engine: engine))

        // The app, in its own process, turning the switch on.
        try #"{"airgapMode": true}"#.write(to: configuration, atomically: true, encoding: .utf8)

        XCTAssertTrue(MCPNetworkEgress.isAirgapped(engine: engine))
    }

    /// Fails closed, and inherits it rather than restating it.
    ///
    /// A configuration this build cannot parse may carry exclusions it cannot express, so the only
    /// safe reading is "assume the user asked for silence". `ExclusionSet.make` already forces
    /// `airgapMode` on for a fail-closed configuration; this asserts that the MCP process gets that
    /// behaviour rather than defaulting to `false` on a decode failure.
    func testAnUnreadableConfigurationIsTreatedAsAirgapped() throws {
        let directory = try makeTemporaryDirectory()
        let configuration = directory.appendingPathComponent("exclusions.json")
        try "this is not JSON".write(to: configuration, atomically: true, encoding: .utf8)
        let engine = ExclusionEngine(configurationURL: configuration, framesRoot: directory)

        XCTAssertTrue(MCPNetworkEgress.isAirgapped(engine: engine))
    }

    /// The legacy principal: a Mac with no `exclusions.json` at all — which is every installation
    /// that exists today, because the file is only written once someone opens Settings.
    ///
    /// That state is `.defaultsOnly`, not fail-closed, and it must stay that way. A gate that read
    /// "no file" as "airgapped" would cut every existing user off from their own Omi account on the
    /// day it shipped, without anyone having asked for it.
    func testAMacWithNoExclusionConfigurationIsNotAirgapped() throws {
        let directory = try makeTemporaryDirectory()
        let engine = ExclusionEngine(
            configurationURL: directory.appendingPathComponent("exclusions.json"),
            framesRoot: directory)

        XCTAssertFalse(MCPNetworkEgress.isAirgapped(engine: engine))
    }

    /// A configuration this build understands and that says nothing about Airgap Mode is a user who
    /// never turned it on — not an unreadable file. The two must not collapse into each other, or
    /// the fail-closed rule above would swallow every ordinary install that has opened Settings.
    func testAReadableConfigurationWithTheSwitchOffIsNotAirgapped() throws {
        let directory = try makeTemporaryDirectory()
        let configuration = directory.appendingPathComponent("exclusions.json")
        try #"{"version": 1, "excludedApps": [], "excludedDomains": []}"#
            .write(to: configuration, atomically: true, encoding: .utf8)
        let engine = ExclusionEngine(configurationURL: configuration, framesRoot: directory)

        XCTAssertFalse(MCPNetworkEgress.isAirgapped(engine: engine))
    }

    // MARK: Helpers

    private func makeTemporaryDirectory() throws -> URL {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("airgap-tests-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        addTeardownBlock { try? FileManager.default.removeItem(at: url) }
        return url
    }

    /// What the transport was asked to send. The tripwire tests assert nothing arrives here; the
    /// control asserts something does.
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

        var lastMethod: String? {
            lock.lock()
            defer { lock.unlock() }
            return requests.last?.httpMethod
        }
    }

    /// A counter a `@Sendable` closure may write to. `OmiBackend` issues its reads from the calling
    /// thread here, but the closure's type is `@Sendable`, so the box has to be too.
    private final class Counter: @unchecked Sendable {
        private let lock = NSLock()
        private var count = 0

        func increment() {
            lock.lock()
            count += 1
            lock.unlock()
        }

        var value: Int {
            lock.lock()
            defer { lock.unlock() }
            return count
        }
    }
}
