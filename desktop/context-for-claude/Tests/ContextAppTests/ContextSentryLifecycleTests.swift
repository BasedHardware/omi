@testable import ContextApp
import ContextCore
import Foundation
import XCTest

/// Records sends and can simulate SDK behavior at `close()` — the "late write" a real SDK makes
/// while its flush runs during an Airgap transition.
private final class FakeReporting: ContextSentryReporting, @unchecked Sendable {
    let received = XCTestExpectation(description: "handled report sent")
    private(set) var reports: [ContextSentryHandledReport] = []
    private(set) var closeCount = 0
    var onClose: (() -> Void)?

    func send(_ report: ContextSentryHandledReport) {
        reports.append(report)
        received.fulfill()
    }

    func close() {
        closeCount += 1
        onClose?()
    }
}

/// Hands out one `FakeReporting` per `makeReporting` call and records what it built.
private final class FakeReportingFactory {
    private(set) var created: [FakeReporting] = []
    private let lock = NSLock()

    var last: FakeReporting? { lock.withLock { created.last } }

    func next() -> FakeReporting {
        lock.lock(); defer { lock.unlock() }
        let fake = FakeReporting()
        created.append(fake)
        return fake
    }
}

/// Lifecycle: launch gates, the wipe-verify-before-start invariant, retirement outside the purged
/// subtree, and the Airgap transition's ordering.
///
/// Each test builds its own `ContextSentry` with an isolated cache root and an isolated
/// `UserDefaults` suite — the retirement record is process-wide state in production, so the tests
/// share nothing with `ContextSentry.shared`.
final class ContextSentryLifecycleTests: XCTestCase {

    private var cacheRoot: URL!
    private var support: URL!
    private var defaults: UserDefaults!
    private var defaultsName: String!
    private var observerHandler: ((Bool) -> Void)?
    private var queue: DispatchQueue!

    override func setUpWithError() throws {
        try super.setUpWithError()
        ContextSentryGate.entryOverride = false
        ContextSentryGate.liveSuppression = { false }

        support = FileManager.default.temporaryDirectory
            .appendingPathComponent("cfc-sentry-lifecycle-\(UUID().uuidString)", isDirectory: true)
        cacheRoot = support.appendingPathComponent("SentryCache", isDirectory: true)
        try FileManager.default.createDirectory(at: support, withIntermediateDirectories: true)

        defaultsName = "cfc-sentry-tests-\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: defaultsName)

        queue = DispatchQueue(label: "test-sentry-\(UUID().uuidString)")
        observerHandler = nil
    }

    override func tearDown() {
        ContextSentryGate.resetTestSeams()
        defaults?.removePersistentDomain(forName: defaultsName ?? "")
        try? FileManager.default.removeItem(at: support)
        super.tearDown()
    }

    private func makeHarness(
        dsn: String? = "https://public-key@sentry.invalid/42",
        shipping: Bool = true,
        suppressed: Bool = false,
        retirementMarked: Bool = false,
        onClose: ((URL) -> Void)? = nil
    ) -> (sentry: ContextSentry, factory: FakeReportingFactory) {
        if retirementMarked {
            ContextSentryRetirement(defaults: defaults).mark()
        }
        let factory = FakeReportingFactory()
        let sentry = ContextSentry(
            dsn: { dsn },
            isShippingBundle: { shipping },
            isSuppressed: { suppressed },
            cacheRoot: cacheRoot,
            retirement: ContextSentryRetirement(defaults: defaults),
            makeReporting: { [cacheRoot] _ in
                let fake = factory.next()
                fake.onClose = { onClose?(cacheRoot) }
                return fake
            },
            registerAirgapObserver: { [weak self] handler in
                self?.observerHandler = handler
                return UUID()
            },
            airgapQueue: queue)
        return (sentry, factory)
    }

    private func writeCacheFile(named name: String, contents: String) throws {
        try FileManager.default.createDirectory(at: cacheRoot, withIntermediateDirectories: true)
        try Data(contents.utf8).write(to: cacheRoot.appendingPathComponent(name))
    }

    func testStartGatesRefuseWithoutBuildingTheSDK() {
        // Not shipping: disabled before anything else is consulted.
        let (notShipping, notShippingFactory) = makeHarness(shipping: false)
        notShipping.start()
        XCTAssertEqual(notShipping.currentState, .disabled(.notShipping))
        XCTAssertEqual(notShippingFactory.created.count, 0)

        // Missing config: no DSN, no SDK, and no cache directory created.
        let (noDSN, noDSNFactory) = makeHarness(dsn: nil)
        noDSN.start()
        XCTAssertEqual(noDSN.currentState, .disabled(.missingConfig))
        XCTAssertEqual(noDSNFactory.created.count, 0)
        XCTAssertFalse(FileManager.default.fileExists(atPath: cacheRoot.path))
    }

    func testDuplicateStartDoesNotBuildASecondSDK() {
        let (sentry, factory) = makeHarness()
        sentry.start()
        sentry.start()
        sentry.start()
        XCTAssertEqual(factory.created.count, 1)
        XCTAssertTrue(sentry.isStarted)
    }

    func testStartWipesAndVerifiesCacheBeforeArming() throws {
        // A previous run left cached state — exactly what must never survive into a permitted
        // launch. The fake factory records whether the cache was clean at the moment the SDK was
        // built, which is the ordering the drop semantics depend on.
        var cacheStateAtBuild: Bool?
        let factory = FakeReportingFactory()
        let sentry = ContextSentry(
            dsn: { "https://public-key@sentry.invalid/42" },
            isShippingBundle: { true },
            isSuppressed: { false },
            cacheRoot: cacheRoot,
            retirement: ContextSentryRetirement(defaults: defaults),
            makeReporting: { [cacheRoot] _ in
                let fake = factory.next()
                cacheStateAtBuild = FileManager.default.fileExists(atPath: cacheRoot.path)
                return fake
            },
            registerAirgapObserver: { [weak self] handler in
                self?.observerHandler = handler
                return UUID()
            },
            airgapQueue: queue)

        try writeCacheFile(named: "queued-envelope", contents: "stale envelope")

        sentry.start()

        XCTAssertEqual(cacheStateAtBuild, false, "the SDK is built only after a verified wipe")
        XCTAssertTrue(sentry.isStarted)
        XCTAssertEqual(factory.created.count, 1)
    }

    func testAirgapAtLaunchDropsCachedStateAndRecordsIt() throws {
        let (sentry, factory) = makeHarness(suppressed: true)

        try writeCacheFile(named: "crash-envelope", contents: "crash envelope")

        let recorded = XCTestExpectation(description: "suppression recorded")
        NetworkEgress.observer = { client, outcome in
            XCTAssertEqual(client, .crashReporting)
            XCTAssertEqual(outcome, .dropped)
            recorded.fulfill()
        }
        defer { NetworkEgress.observer = nil }

        sentry.start()

        wait(for: [recorded], timeout: 5)
        XCTAssertEqual(sentry.currentState, .disabled(.airgappedAtLaunch))
        XCTAssertEqual(factory.created.count, 0, "an airgapped launch never builds the SDK")
        XCTAssertFalse(
            FileManager.default.fileExists(atPath: cacheRoot.path),
            "cached envelopes are dropped, not retained for a later launch")
    }

    func testAirgapEntryClosesGateMarksRetirementThenDropsCacheAndClosesSDK() throws {
        // The SDK-like late write: a real SDK can persist during `close()` (its flush runs before
        // the handler uninstalls). The second purge pass must catch it; the next launch's
        // wipe-verify is the backstop for anything that raced even that.
        let (sentry, factory) = makeHarness(onClose: { root in
            try? FileManager.default.createDirectory(
                at: root.appendingPathComponent("io.sentry"), withIntermediateDirectories: true)
            try? Data("envelope written during close".utf8)
                .write(to: root.appendingPathComponent("io.sentry/late-envelope"))
        })

        sentry.start()
        XCTAssertTrue(sentry.isStarted)
        XCTAssertFalse(defaults.bool(forKey: ContextSentryRetirement.key))

        observerHandler?(true)  // the ExclusionEngine observer, on its callback thread

        // Synchronous, before any queued work: no send window remains open.
        XCTAssertTrue(ContextSentryGate.isClosed)
        XCTAssertTrue(
            defaults.bool(forKey: ContextSentryRetirement.key),
            "retirement is marked durably, outside the purged subtree, before queue work starts")

        queue.sync {}  // drain the transition

        XCTAssertEqual(sentry.currentState, .closedByAirgap)
        XCTAssertEqual(factory.last?.closeCount, 1)
        XCTAssertFalse(
            FileManager.default.fileExists(atPath: cacheRoot.path),
            "the late SDK write is caught by the second purge pass")
    }

    func testReportRefusesInTheWindowBetweenEntryAndClose() {
        let (sentry, factory) = makeHarness()
        sentry.start()

        observerHandler?(true)
        XCTAssertTrue(ContextSentryGate.isClosed)

        // `reporting` is still non-nil until the queue drains — the gate is what refuses here.
        sentry.report(
            ContextSentryHandledReport(area: .upload, outcome: .degraded, reason: .unavailable))
        queue.sync {}
        XCTAssertEqual(factory.last?.reports.count, 0)
    }

    func testReportRefusesWhileSuppressed() {
        let (sentry, factory) = makeHarness(suppressed: true)
        sentry.start()
        XCTAssertEqual(sentry.currentState, .disabled(.airgappedAtLaunch))

        sentry.report(
            ContextSentryHandledReport(area: .upload, outcome: .degraded, reason: .unavailable))
        XCTAssertEqual(factory.created.count, 0)
    }

    func testReportReachesReportingOnceEveryGatePasses() throws {
        let (sentry, factory) = makeHarness()
        sentry.start()

        sentry.report(
            ContextSentryHandledReport(area: .upload, outcome: .degraded, reason: .unavailable))

        let fake = try XCTUnwrap(factory.last)
        wait(for: [fake.received], timeout: 5)
        XCTAssertEqual(fake.reports.count, 1)
        XCTAssertEqual(
            fake.reports[0].message,
            "cfc-fallback area=upload reason=unavailable outcome=degraded")
    }

    func testWipeVerificationFailureDisarmsAndKeepsRetirementSet() throws {
        // Make the cache root undeletable: its parent loses write permission, so `removeItem`
        // cannot unlink. (Skipped when running as root, which ignores directory permissions.)
        let (sentry, factory) = makeHarness(retirementMarked: true)

        try writeCacheFile(named: "stuck", contents: "cannot be deleted")
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o555], ofItemAtPath: support.path)
        let parentMadeReadOnly = !FileManager.default.isWritableFile(atPath: support.path)
        defer {
            try? FileManager.default.setAttributes(
                [.posixPermissions: 0o755], ofItemAtPath: support.path)
        }
        guard parentMadeReadOnly else {
            throw XCTSkip("running as root: directory permissions cannot simulate a stuck file")
        }

        sentry.start()

        XCTAssertEqual(sentry.currentState, .disabled(.cacheWipeFailed))
        XCTAssertEqual(factory.created.count, 0, "fail closed: the SDK never starts")
        XCTAssertTrue(
            ContextSentryRetirement(defaults: defaults).isRetired,
            "a failed wipe never clears retirement; the next launch retries the wipe")
        XCTAssertFalse(ContextSentryGate.isClosed, "wipe failure is not an Airgap entry")
    }

    func testRetirementSurvivesQueuedWritesAndShutdownAndClearsOnlyOnVerifiedFreshStart() throws {
        // (1) A permitted run, then an Airgap entry with an SDK late-write. Retirement stays set
        // through every queued SDK write and the shutdown.
        let (first, firstFactory) = makeHarness(onClose: { root in
            try? FileManager.default.createDirectory(
                at: root.appendingPathComponent("io.sentry"), withIntermediateDirectories: true)
            try? Data("x".utf8).write(to: root.appendingPathComponent("io.sentry/late"))
        })
        first.start()
        observerHandler?(true)
        queue.sync {}
        XCTAssertTrue(defaults.bool(forKey: ContextSentryRetirement.key))
        XCTAssertFalse(FileManager.default.fileExists(atPath: cacheRoot.path))
        XCTAssertEqual(firstFactory.created.count, 1)

        // (2) A *suppressed* restart: drops anything left, stays disabled, retirement remains.
        let (second, secondFactory) = makeHarness(suppressed: true)
        second.start()
        XCTAssertEqual(second.currentState, .disabled(.airgappedAtLaunch))
        XCTAssertEqual(secondFactory.created.count, 0)
        XCTAssertTrue(defaults.bool(forKey: ContextSentryRetirement.key))

        // (3) A permitted restart: verified wipe, then — and only then — the record clears, and
        // the SDK arms. This is the only code path that clears it.
        let (third, thirdFactory) = makeHarness()
        third.start()
        XCTAssertTrue(third.isStarted)
        XCTAssertEqual(thirdFactory.created.count, 1)
        XCTAssertFalse(
            defaults.bool(forKey: ContextSentryRetirement.key),
            "cleared by a fresh process, after a verified wipe, before SDK initialization")
    }

    func testLostRetirementRecordStillCannotLeadToCacheReuse() throws {
        // The failure mode the record cannot cover — its own write being lost — must still fail
        // closed for cache reuse, because *every* permitted launch wipes before arming and never
        // consults the record. Here the record is absent (as if the entry-time write was lost)
        // and a suppressed-period cache exists: the launch destroys it before the SDK exists.
        var cacheStateAtBuild: Bool?
        let factory = FakeReportingFactory()
        let sentry = ContextSentry(
            dsn: { "https://public-key@sentry.invalid/42" },
            isShippingBundle: { true },
            isSuppressed: { false },
            cacheRoot: cacheRoot,
            retirement: ContextSentryRetirement(defaults: defaults),  // nothing recorded
            makeReporting: { [cacheRoot] _ in
                let fake = factory.next()
                cacheStateAtBuild = FileManager.default.fileExists(atPath: cacheRoot.path)
                return fake
            },
            registerAirgapObserver: { [weak self] handler in
                self?.observerHandler = handler
                return UUID()
            },
            airgapQueue: queue)

        try writeCacheFile(
            named: "possibly-tainted",
            contents: "envelope from a run whose retirement write was lost")

        sentry.start()

        XCTAssertEqual(cacheStateAtBuild, false, "tainted state is wiped regardless of the record")
        XCTAssertTrue(sentry.isStarted)
    }

    func testNoRestartAfterCloseEvenIfAirgapFlipsBack() {
        let (sentry, factory) = makeHarness()
        sentry.start()
        observerHandler?(true)
        queue.sync {}
        XCTAssertEqual(sentry.currentState, .closedByAirgap)

        observerHandler?(false)  // Airgap off again: no mid-run restart
        queue.sync {}
        XCTAssertEqual(factory.created.count, 1)
        XCTAssertEqual(sentry.currentState, .closedByAirgap)

        sentry.start()  // and a second `start` is a no-op too
        XCTAssertEqual(factory.created.count, 1)
        XCTAssertEqual(sentry.currentState, .closedByAirgap)
    }
}
