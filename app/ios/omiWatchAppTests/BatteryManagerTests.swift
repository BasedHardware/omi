import XCTest
import WatchKit
import WatchConnectivity
@testable import omiWatchApp

/// Unit tests for BatteryManager
/// Tests battery monitoring and reporting functionality
final class BatteryManagerTests: XCTestCase {

    var batteryManager: BatteryManager!

    override func setUp() {
        super.setUp()
        batteryManager = BatteryManager.shared
    }

    override func tearDown() {
        batteryManager = nil
        super.tearDown()
    }

    // MARK: - Initialization Tests

    func testSingletonInstance() {
        let instance1 = BatteryManager.shared
        let instance2 = BatteryManager.shared

        XCTAssertTrue(instance1 === instance2, "BatteryManager should be a singleton")
    }

    func testBatteryMonitoringEnabled() {
        XCTAssertTrue(
            WKInterfaceDevice.current().isBatteryMonitoringEnabled,
            "Battery monitoring should be enabled"
        )
    }

    // MARK: - Battery Info Tests

    func testGetBatteryInfo() {
        let info = batteryManager.getBatteryInfo()

        XCTAssertNotNil(info["level"], "Battery info should contain level")
        XCTAssertNotNil(info["state"], "Battery info should contain state")
        XCTAssertNotNil(info["isCharging"], "Battery info should contain charging status")
        XCTAssertNotNil(info["isFull"], "Battery info should contain full status")
    }

    func testBatteryLevelRange() {
        let info = batteryManager.getBatteryInfo()
        guard let level = info["level"] as? Float else {
            XCTFail("Battery level should be a Float")
            return
        }

        XCTAssertGreaterThanOrEqual(level, 0.0, "Battery level should not be negative")
        XCTAssertLessThanOrEqual(level, 100.0, "Battery level should not exceed 100")
    }

    func testBatteryStateValues() {
        let info = batteryManager.getBatteryInfo()
        guard let state = info["state"] as? Int else {
            XCTFail("Battery state should be an Int")
            return
        }

        // Battery state should be a valid WKInterfaceDeviceBatteryState raw value
        XCTAssertTrue(state >= 0 && state <= 3, "Battery state should be valid (0-3)")
    }

    // MARK: - Battery Update Tests

    func testSendBatteryLevelDoesNotCrash() {
        // Should not crash even if WCSession is not properly configured in tests
        XCTAssertNoThrow(batteryManager.sendBatteryLevel(force: true))
    }

    func testStartBatteryMonitoring() {
        XCTAssertNoThrow(batteryManager.startBatteryMonitoring())
    }

    func testStopBatteryMonitoring() {
        batteryManager.startBatteryMonitoring()
        XCTAssertNoThrow(batteryManager.stopBatteryMonitoring())
    }

    // MARK: - Watch Info Tests

    func testSendWatchInfoDoesNotCrash() {
        XCTAssertNoThrow(batteryManager.sendWatchInfo())
    }

    func testWatchInfoContainsExpectedData() {
        // This is more of an integration test
        let device = WKInterfaceDevice.current()

        XCTAssertNotNil(device.name, "Device should have a name")
        XCTAssertNotNil(device.model, "Device should have a model")
        XCTAssertNotNil(device.systemVersion, "Device should have a system version")
    }

    // MARK: - Performance Tests

    func testBatteryInfoPerformance() {
        measure {
            _ = batteryManager.getBatteryInfo()
        }
    }

    func testSendBatteryLevelPerformance() {
        measure {
            batteryManager.sendBatteryLevel(force: true)
        }
    }

    // MARK: - Concurrency Tests

    func testConcurrentBatteryAccess() async {
        await withTaskGroup(of: Void.self) { group in
            for _ in 0..<10 {
                group.addTask {
                    _ = self.batteryManager.getBatteryInfo()
                }
            }
        }
        // Test passes if no crash occurs
    }

    // MARK: - State Management Tests

    func testBatteryUpdateDeduplication() {
        // Send multiple identical updates
        batteryManager.sendBatteryLevel(force: true)
        batteryManager.sendBatteryLevel(force: false)
        batteryManager.sendBatteryLevel(force: false)

        // Should deduplicate unnecessary updates
        // This test verifies the method doesn't crash with repeated calls
    }

    func testForcedBatteryUpdate() {
        // Forced update should always send
        XCTAssertNoThrow(batteryManager.sendBatteryLevel(force: true))
    }
}
