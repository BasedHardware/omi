import XCTest
import WidgetKit
@testable import omiWatchApp

final class SmartStackRelevanceStoreTests: XCTestCase {
    private var suiteName: String!
    private var defaults: UserDefaults!
    private var store: SmartStackRelevanceStore!

    override func setUp() async throws {
        try await super.setUp()
        suiteName = "SmartStackRelevanceStoreTests.\(UUID().uuidString)"
        guard let defaults = UserDefaults(suiteName: suiteName) else {
            XCTFail("Failed to create test UserDefaults suite")
            return
        }
        defaults.removePersistentDomain(forName: suiteName)
        self.defaults = defaults
        store = SmartStackRelevanceStore(userDefaults: defaults)
    }

    override func tearDown() async throws {
        if let defaults, let suiteName {
            defaults.removePersistentDomain(forName: suiteName)
        }
        store = nil
        defaults = nil
        suiteName = nil
        try await super.tearDown()
    }

    func testRecordingLifecycleUpdatesSnapshot() async throws {
        let startDate = Date()
        await store.recordingDidStart(at: startDate)

        var snapshot = await store.snapshot()
        XCTAssertTrue(snapshot.isRecording)
        XCTAssertEqual(snapshot.recordingStartDate?.timeIntervalSinceReferenceDate ?? 0,
                       startDate.timeIntervalSinceReferenceDate,
                       accuracy: 0.5)

        let stopDate = startDate.addingTimeInterval(42)
        await store.recordingDidStop(at: stopDate, duration: 42)

        snapshot = await store.snapshot()
        XCTAssertFalse(snapshot.isRecording)
        XCTAssertEqual(snapshot.lastRecordingDuration, 42, accuracy: 0.5)
        XCTAssertEqual(snapshot.lastRecordingEndDate?.timeIntervalSinceReferenceDate ?? 0,
                       stopDate.timeIntervalSinceReferenceDate,
                       accuracy: 0.5)
    }

    func testBatteryUpdatesClampLevels() async throws {
        let now = Date()
        await store.updateBattery(level: -10, at: now)

        var snapshot = await store.snapshot()
        XCTAssertEqual(snapshot.batteryLevel, 0)

        let later = now.addingTimeInterval(60)
        await store.updateBattery(level: 150, at: later)
        snapshot = await store.snapshot()
        XCTAssertEqual(snapshot.batteryLevel, 100)
        XCTAssertEqual(snapshot.batteryUpdatedAt?.timeIntervalSinceReferenceDate ?? 0,
                       later.timeIntervalSinceReferenceDate,
                       accuracy: 0.5)
    }

    func testTimelineRelevancePrefersRecording() async throws {
        let startDate = Date()
        await store.recordingDidStart(at: startDate)
        let snapshot = await store.snapshot()
        let relevance = snapshot.timelineRelevance(currentDate: startDate.addingTimeInterval(30))

        XCTAssertEqual(relevance.score, 1.0, accuracy: 0.01)
        XCTAssertGreaterThan(relevance.duration, 0)
    }

    func testWidgetRelevanceIncludesLowBatterySignal() async throws {
        let now = Date()
        await store.updateBattery(level: 15, at: now)
        let snapshot = await store.snapshot()
        let attributes = snapshot.widgetRelevanceAttributes(currentDate: now)

        XCTAssertFalse(attributes.isEmpty)
    }
}
