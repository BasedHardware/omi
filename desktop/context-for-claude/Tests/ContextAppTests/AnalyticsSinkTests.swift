@testable import ContextApp
import Foundation
import XCTest

/// Delivery, and the four ways it is allowed to fail.
///
/// Every test here runs offline. A transport double is not a convenience — an analytics sink whose
/// retry, drop and durability rules are only ever exercised against a live endpoint is a sink whose
/// failure behaviour has never been observed at all.
final class AnalyticsSinkTests: XCTestCase {

    private var directory: URL!
    private var spoolURL: URL!

    override func setUpWithError() throws {
        directory = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("sink-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        spoolURL = directory.appendingPathComponent("analytics-spool.json")
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: directory)
    }

    private func payload(_ index: Int = 0) -> AnalyticsPayload {
        AnalyticsPayload(
            event: .onboardingStep(index: index, of: 5),
            distinctID: "cfc_0123456789abcdef",
            timestamp: Date(timeIntervalSince1970: 1_760_000_000 + Double(index)),
            superProperties: AnalyticsPayload.superProperties(
                version: "1.0.12", build: "1000012", macOSVersion: "Version 15.5.0"))
    }

    // MARK: - Delivery

    func testAFlushSendsEverythingQueued() async {
        let transport = RecordingTransport(outcome: .accept)
        let sink = AnalyticsSink(spoolURL: spoolURL, transport: transport)

        for index in 0..<3 { await sink.enqueue(payload(index)) }
        await sink.flush()

        let sent = await transport.sentNames
        XCTAssertEqual(sent.count, 3)
    }

    /// A spool that grew while offline drains over several requests rather than in one implausible
    /// burst — both for the endpoint's sake and because a single enormous POST is the request most
    /// likely to be rejected outright and retried forever.
    func testALargeSpoolDrainsInBatches() async {
        let transport = RecordingTransport(outcome: .accept)
        let sink = AnalyticsSink(spoolURL: spoolURL, transport: transport)

        for index in 0..<(AnalyticsSink.batchSize * 2 + 5) { await sink.enqueue(payload(index)) }
        await sink.flush()

        let sizes = await transport.batchSizes
        XCTAssertEqual(sizes, [AnalyticsSink.batchSize, AnalyticsSink.batchSize, 5])
    }

    // MARK: - Failure

    /// A failed flush must leave the events queued. Sending is best-effort forever, but "best
    /// effort" that discards on the first network blip is just discarding.
    func testAFailedSendKeepsTheEventsForNextTime() async {
        let transport = RecordingTransport(outcome: .fail)
        let sink = AnalyticsSink(spoolURL: spoolURL, transport: transport)

        await sink.enqueue(payload())
        await sink.flush()
        var spooled = await sink.spooledCountForTesting
        XCTAssertEqual(spooled, 1)

        await transport.set(outcome: .accept)
        await sink.flush()
        spooled = await sink.spooledCountForTesting
        XCTAssertEqual(spooled, 0)
    }

    /// **The wedge this prevents.** A 4xx that is not 429 will never succeed on retry — a malformed
    /// batch, or a revoked token. Keeping it queued would block every later event behind one that can
    /// never be sent, and the spool would never empty again. Rate limiting is the exception: it is
    /// temporary, so it must be retried rather than dropped.
    func testTheTransportRetries429AndDropsOtherClientErrors() {
        XCTAssertFalse(URLSessionAnalyticsTransport.shouldConsumeBatch(forStatus: 429))
        XCTAssertFalse(URLSessionAnalyticsTransport.shouldConsumeBatch(forStatus: 500))
        XCTAssertFalse(URLSessionAnalyticsTransport.shouldConsumeBatch(forStatus: 503))
        XCTAssertTrue(URLSessionAnalyticsTransport.shouldConsumeBatch(forStatus: 200))
        XCTAssertTrue(URLSessionAnalyticsTransport.shouldConsumeBatch(forStatus: 400))
        XCTAssertTrue(URLSessionAnalyticsTransport.shouldConsumeBatch(forStatus: 401))
    }

    // MARK: - Durability and bounds

    /// Events recorded seconds before a quit are not lost. This is most of the value of the spool: an
    /// app that is quit every evening would otherwise never deliver its rollup.
    func testTheSpoolSurvivesRelaunch() async {
        let first = AnalyticsSink(spoolURL: spoolURL, transport: RecordingTransport(outcome: .fail))
        await first.enqueue(payload(1))
        await first.enqueue(payload(2))

        let transport = RecordingTransport(outcome: .accept)
        let second = AnalyticsSink(spoolURL: spoolURL, transport: transport)
        await second.flush()

        let delivered = await transport.sentNames
        XCTAssertEqual(delivered.count, 2)
    }

    /// A spool that has overflowed has already lost the argument about completeness. Keeping the
    /// *recent* events at least keeps the series current — dropping newest-first would freeze it at
    /// whenever the machine went offline.
    func testAnOverflowingSpoolDropsItsOldestEvents() async {
        let sink = AnalyticsSink(spoolURL: spoolURL, transport: RecordingTransport(outcome: .fail))

        for index in 0..<(AnalyticsSink.spoolCapacity + 25) { await sink.enqueue(payload(index)) }

        let held = await sink.spooledCountForTesting
        XCTAssertEqual(held, AnalyticsSink.spoolCapacity)
        let oldest = await sink.oldestSpooledTimestampForTesting
        XCTAssertEqual(oldest, Date(timeIntervalSince1970: 1_760_000_000 + 25))
    }

    /// A spool is not user data: the cost of losing it is one gap in a chart, and the cost of
    /// trusting a damaged one is inventing events that never happened.
    func testADamagedSpoolIsDiscardedRatherThanRepaired() async throws {
        try Data("{ not json".utf8).write(to: spoolURL)
        let sink = AnalyticsSink(spoolURL: spoolURL, transport: RecordingTransport(outcome: .accept))
        let loaded = await sink.spooledCountForTesting
        XCTAssertEqual(loaded, 0)
    }
}

// MARK: - Doubles

private actor RecordingTransport: AnalyticsTransport {
    enum Outcome { case accept, fail }

    private(set) var sentNames: [String] = []
    private(set) var batchSizes: [Int] = []
    private var outcome: Outcome

    init(outcome: Outcome) { self.outcome = outcome }

    func set(outcome: Outcome) { self.outcome = outcome }

    func send(_ batch: [AnalyticsPayload], token: String, to endpoint: URL) async -> Bool {
        guard outcome == .accept else { return false }
        sentNames.append(contentsOf: batch.map(\.name))
        batchSizes.append(batch.count)
        return true
    }
}

/// The scheduled path — the only one production takes while the app is running.
///
/// Everything in `AnalyticsSinkTests` calls `flush()` directly, and that is exactly why 1.0.13
/// shipped delivering nothing: with no timer pending, `flush()`'s `flushTask?.cancel()` is a no-op,
/// so the direct path passed every test while the scheduled path cancelled itself on the first line
/// and threw out of `URLSession`. A suite that only exercises the caller's convenience entry point is
/// not testing the product.
final class AnalyticsScheduledFlushTests: XCTestCase {

    private var spoolURL: URL!

    override func setUpWithError() throws {
        let directory = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("sched-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        spoolURL = directory.appendingPathComponent("analytics-spool.json")
    }

    /// **The 1.0.13 regression.** Enqueue and then touch nothing: the timer alone must deliver.
    func testTheScheduledFlushActuallyDelivers() async throws {
        let transport = CancellationAwareTransport()
        let sink = AnalyticsSink(spoolURL: spoolURL, transport: transport, flushInterval: 0.1)

        await sink.enqueue(AnalyticsPayload(
            event: .appLaunched,
            distinctID: "cfc_0123456789abcdef",
            timestamp: Date(timeIntervalSince1970: 1_760_000_000),
            superProperties: AnalyticsPayload.superProperties(
                version: "1.0.14", build: "1000014", macOSVersion: "test")))

        try await Task.sleep(nanoseconds: 1_500_000_000)

        let delivered = await transport.deliveredCount
        let sawCancellation = await transport.sawCancelledTask
        let stillSpooled = await sink.spooledCountForTesting

        XCTAssertFalse(
            sawCancellation,
            "the scheduled task cancelled itself — URLSession would have thrown and the batch would never send")
        XCTAssertEqual(delivered, 1, "the timer alone must deliver; nothing else runs in production")
        XCTAssertEqual(stillSpooled, 0, "a delivered batch must leave the spool")
    }
}

/// Reports whether the task calling it had already been cancelled — which is precisely what the
/// real `URLSession.data(for:)` reacts to, and what made the shipped build silent.
private actor CancellationAwareTransport: AnalyticsTransport {
    private(set) var deliveredCount = 0
    private(set) var sawCancelledTask = false

    func send(_ batch: [AnalyticsPayload], token: String, to endpoint: URL) async -> Bool {
        if Task.isCancelled {
            sawCancelledTask = true
            return false  // exactly what URLSession does when its task is cancelled
        }
        deliveredCount += batch.count
        return true
    }
}
