@testable import ContextApp
import ContextCore
import Foundation
import XCTest

private final class FakeReporting: ContextSentryReporting, @unchecked Sendable {
    var reports: [ContextSentryHandledReport] = []
    var closeCount = 0
    var onClose: (() -> Void)?

    func send(_ report: ContextSentryHandledReport) { reports.append(report) }
    func close() {
        closeCount += 1
        onClose?()
    }
}

final class ContextSentryLifecycleTests: XCTestCase {
    private var support: URL!
    private var cacheRoot: URL { support.appendingPathComponent("SentryCache") }
    private var defaults: UserDefaults!
    private var defaultsName: String!
    private var queue: DispatchQueue!

    override func setUpWithError() throws {
        ContextSentryGate.resetTestSeams()
        ContextSentryGate.liveSuppression = { false }
        support = FileManager.default.temporaryDirectory
            .appendingPathComponent("cfc-sentry-lifecycle-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: support, withIntermediateDirectories: true)
        defaultsName = "cfc-sentry-tests-\(UUID().uuidString)"
        defaults = try XCTUnwrap(UserDefaults(suiteName: defaultsName))
        queue = DispatchQueue(label: "test-sentry-\(UUID().uuidString)")
    }

    override func tearDownWithError() throws {
        queue.sync {}
        ContextSentryGate.resetTestSeams()
        defaults.removePersistentDomain(forName: defaultsName)
        try FileManager.default.removeItem(at: support)
    }

    private func engine() -> ExclusionEngine {
        ExclusionEngine(
            configurationURL: support.appendingPathComponent("exclusions.json"),
            framesRoot: support.appendingPathComponent("Frames"))
    }

    private func makeSentry(
        engine: ExclusionEngine,
        dsn: String? = "https://public-key@sentry.invalid/42",
        shipping: Bool = true,
        build: @escaping (ContextSentry.StartOptions) -> ContextSentryReporting
    ) -> ContextSentry {
        ContextSentry(
            dsn: { dsn }, isShippingBundle: { shipping },
            isSuppressed: { engine.current.airgapMode },
            cacheGeneration: { engine.prepareCrashReportingGeneration() },
            cacheRoot: cacheRoot,
            retirement: ContextSentryRetirement(defaults: defaults),
            makeReporting: build,
            registerAirgapObserver: { handler in
                engine.addObserver { handler($0.airgapMode) }
            }, airgapQueue: queue)
    }

    private func write(_ text: String, in directory: URL) throws -> URL {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let file = directory.appendingPathComponent("crash-report")
        try Data(text.utf8).write(to: file)
        return file
    }

    func testDisabledLaunchesDoNotConstructSDKOrCache() {
        let engine = engine()
        for (dsn, shipping, reason) in [
            (nil, true, ContextSentry.DisabledReason.missingConfig),
            ("http://key@sentry.invalid/42", true, .missingConfig),
            ("https://key@sentry.invalid/42", false, .notShipping),
        ] {
            let sentry = makeSentry(engine: engine, dsn: dsn, shipping: shipping) { _ in
                XCTFail("disabled launches must not construct the SDK")
                return FakeReporting()
            }
            sentry.start()
            sentry.start()
            XCTAssertEqual(sentry.currentState, .disabled(reason))
        }
        XCTAssertFalse(FileManager.default.fileExists(atPath: cacheRoot.path))
        XCTAssertNil(engine.current.crashReportingGeneration)
    }

    func testHealthyCrashSurvivesRelaunchAndDuplicateStartIsNoOp() throws {
        var firstCache: URL!
        var builds = 0
        let first = makeSentry(engine: engine()) { options in
            firstCache = URL(fileURLWithPath: options.cacheRoot)
            builds += 1
            return FakeReporting()
        }
        first.start()
        first.start()
        XCTAssertEqual(builds, 1)
        let crash = try write("healthy-run crash", in: XCTUnwrap(firstCache))

        let second = makeSentry(engine: engine()) { options in
            XCTAssertEqual(options.cacheRoot, firstCache.path)
            XCTAssertEqual(try? String(contentsOf: crash, encoding: .utf8), "healthy-run crash")
            builds += 1
            return FakeReporting()
        }
        second.start()
        XCTAssertTrue(second.isStarted)
        XCTAssertEqual(builds, 2)
    }

    func testAirgapLaunchDropsCacheAndKeepsRetirementUntilAllowedRestart() throws {
        let engine = engine()
        engine.setAirgapMode(true)
        _ = try write("queued crash", in: cacheRoot)
        let sentry = makeSentry(engine: engine) { _ in
            XCTFail("Airgap launch must not construct the SDK")
            return FakeReporting()
        }
        sentry.start()
        queue.sync {}
        XCTAssertEqual(sentry.currentState, .disabled(.airgappedAtLaunch))
        XCTAssertFalse(FileManager.default.fileExists(atPath: cacheRoot.path))
        XCTAssertTrue(ContextSentryRetirement(defaults: defaults).isRetired)
    }

    func testEntryDropsLateWritesAndDoesNotRestartInSameProcess() throws {
        let engine = engine()
        let fake = FakeReporting()
        var active: URL!
        let sentry = makeSentry(engine: engine) { options in
            active = URL(fileURLWithPath: options.cacheRoot)
            return fake
        }
        sentry.start()
        fake.onClose = { _ = try? self.write("write during close", in: active) }
        engine.setAirgapMode(true)
        XCTAssertTrue(ContextSentryGate.isClosed)
        XCTAssertTrue(ContextSentryRetirement(defaults: defaults).isRetired)
        sentry.report(.init(area: .upload, outcome: .degraded, reason: .unavailable))
        queue.sync {}
        XCTAssertEqual(fake.closeCount, 1)
        XCTAssertTrue(fake.reports.isEmpty)
        XCTAssertFalse(FileManager.default.fileExists(atPath: cacheRoot.path))
        engine.setAirgapMode(false)
        sentry.start()
        XCTAssertEqual(sentry.currentState, .closedByAirgap)
    }

    func testLostRetirementRecordCannotReplayAnOldGeneration() throws {
        let firstEngine = engine()
        var oldCache: URL!
        let first = makeSentry(engine: firstEngine) { options in
            oldCache = URL(fileURLWithPath: options.cacheRoot)
            return FakeReporting()
        }
        first.start()
        firstEngine.setAirgapMode(true)
        firstEngine.setAirgapMode(false)
        queue.sync {}
        // A late SDK write after both purge passes, then loss of the secondary record.
        let stale = try write("suppressed-period crash", in: XCTUnwrap(oldCache))
        defaults.removeObject(forKey: ContextSentryRetirement.key)
        ContextSentryGate.resetTestSeams() // fresh process
        ContextSentryGate.liveSuppression = { false }
        let next = makeSentry(engine: engine()) { options in
            XCTAssertNotEqual(options.cacheRoot, oldCache.path)
            XCTAssertFalse(FileManager.default.fileExists(atPath: stale.path))
            return FakeReporting()
        }
        next.start()
        XCTAssertTrue(next.isStarted)
    }

    func testRetirementInvalidatesEvenTheCurrentGeneration() throws {
        let engine = engine()
        let generation = try XCTUnwrap(engine.prepareCrashReportingGeneration())
        let stale = try write("tainted", in: cacheRoot.appendingPathComponent(generation.uuidString))
        ContextSentryRetirement(defaults: defaults).mark()
        let sentry = makeSentry(engine: engine) { _ in
            XCTAssertFalse(FileManager.default.fileExists(atPath: stale.path))
            return FakeReporting()
        }
        sentry.start()
        XCTAssertTrue(sentry.isStarted)
        XCTAssertFalse(ContextSentryRetirement(defaults: defaults).isRetired)
    }

    func testAirgapDuringSDKConstructionClosesThePublishedReporter() {
        let engine = engine()
        let fake = FakeReporting()
        let sentry = makeSentry(engine: engine) { _ in
            // The observer fires while start() holds its lifecycle lock. It must close admission
            // immediately, then wait to uninstall the handler until the factory result is stored.
            engine.setAirgapMode(true)
            engine.setAirgapMode(false)
            XCTAssertTrue(ContextSentryGate.isClosed)
            return fake
        }
        sentry.start()
        queue.sync {}
        XCTAssertEqual(sentry.currentState, .closedByAirgap)
        XCTAssertEqual(fake.closeCount, 1)
    }

    func testCachePreparationFailureDisablesReporting() throws {
        // A regular file cannot hold the generation directory. Deterministic even as root.
        try Data("not a directory".utf8).write(to: cacheRoot)
        let sentry = makeSentry(engine: engine()) { _ in
            XCTFail("cache preparation failure must disable reporting")
            return FakeReporting()
        }
        sentry.start()
        XCTAssertEqual(sentry.currentState, .disabled(.cacheWipeFailed))
    }

    func testHandledReportUsesClosedVocabulary() {
        let fake = FakeReporting()
        let sentry = makeSentry(engine: engine()) { _ in fake }
        sentry.start()
        sentry.report(.init(area: .upload, outcome: .degraded, reason: .unavailable))
        XCTAssertEqual(fake.reports.count, 1)
        XCTAssertEqual(fake.reports.first?.tags, ["app": "context-for-claude"])
        XCTAssertEqual(fake.reports.first?.fingerprint, ["cfc-fallback", "upload", "unavailable"])
        XCTAssertEqual(fake.reports.first?.message,
                       "cfc-fallback area=upload reason=unavailable outcome=degraded")
    }
}
