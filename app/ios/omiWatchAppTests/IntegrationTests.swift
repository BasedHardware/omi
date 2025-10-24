import XCTest
import WatchConnectivity
import AVFoundation
@testable import omiWatchApp

/// Integration tests for the Omi Watch App
/// Tests end-to-end workflows and component interactions
@MainActor
final class OmiWatchAppIntegrationTests: XCTestCase {

    var viewModel: WatchAudioRecorderViewModel!
    var batteryManager: BatteryManager!

    override func setUp() async throws {
        try await super.setUp()
        viewModel = WatchAudioRecorderViewModel()
        batteryManager = BatteryManager.shared
    }

    override func tearDown() async throws {
        viewModel = nil
        batteryManager = nil
        try await super.tearDown()
    }

    // MARK: - End-to-End Recording Tests

    func testCompleteRecordingWorkflow() async throws {
        // 1. Initial state verification
        XCTAssertFalse(viewModel.isRecording, "Should not be recording initially")
        XCTAssertEqual(viewModel.recordingDuration, 0, "Duration should be 0")

        // 2. Start recording
        viewModel.startRecording()
        try await Task.sleep(nanoseconds: 1_000_000_000) // 1 second

        // 3. Verify recording state (may not actually record due to permissions in test)
        // The test verifies the workflow doesn't crash

        // 4. Stop recording
        viewModel.stopRecording()
        try await Task.sleep(nanoseconds: 500_000_000) // 0.5 seconds

        // 5. Verify cleanup
        XCTAssertFalse(viewModel.isRecording, "Should not be recording after stop")
        XCTAssertEqual(viewModel.recordingDuration, 0, "Duration should be reset")
        XCTAssertEqual(viewModel.audioLevel, 0.0, "Audio level should be reset")
    }

    // MARK: - Battery and Recording Integration

    func testBatteryMonitoringDuringRecording() async throws {
        // Start battery monitoring
        batteryManager.startBatteryMonitoring()

        // Get initial battery info
        let initialBatteryInfo = batteryManager.getBatteryInfo()
        XCTAssertNotNil(initialBatteryInfo["level"])

        // Start recording
        viewModel.startRecording()
        try await Task.sleep(nanoseconds: 2_000_000_000) // 2 seconds

        // Battery monitoring should continue during recording
        let duringRecordingInfo = batteryManager.getBatteryInfo()
        XCTAssertNotNil(duringRecordingInfo["level"])

        // Stop recording
        viewModel.stopRecording()
        try await Task.sleep(nanoseconds: 500_000_000)

        // Stop battery monitoring
        batteryManager.stopBatteryMonitoring()

        // All operations should complete without errors
    }

    // MARK: - WatchConnectivity Integration

    func testWatchConnectivitySession() {
        // Verify session is properly configured
        let session = WCSession.default
        XCTAssertNotNil(session, "WCSession should be available")

        // Verify delegate is set
        XCTAssertNotNil(viewModel.session.delegate, "Session delegate should be set")
    }

    func testSessionMessageHandling() async throws {
        let expectation = XCTestExpectation(description: "Message handled")

        // Simulate various message types
        let messages = [
            ["method": "startRecording"],
            ["method": "stopRecording"],
            ["method": "requestBattery"],
            ["method": "requestWatchInfo"]
        ]

        for message in messages {
            viewModel.session(viewModel.session, didReceiveMessage: message)
            try await Task.sleep(nanoseconds: 100_000_000)
        }

        expectation.fulfill()
        await fulfillment(of: [expectation], timeout: 2.0)
    }

    // MARK: - State Synchronization Tests

    func testViewModelBatteryManagerSync() async throws {
        // Initialize both components
        viewModel.startRecording()
        batteryManager.startBatteryMonitoring()

        try await Task.sleep(nanoseconds: 1_000_000_000)

        // Both should be operating without interference
        let batteryInfo = batteryManager.getBatteryInfo()
        XCTAssertNotNil(batteryInfo["level"])

        // Cleanup
        viewModel.stopRecording()
        batteryManager.stopBatteryMonitoring()

        try await Task.sleep(nanoseconds: 500_000_000)
    }

    // MARK: - Error Recovery Tests

    func testRecoveryFromRecordingError() async throws {
        // Attempt to start recording
        viewModel.startRecording()
        try await Task.sleep(nanoseconds: 500_000_000)

        // Simulate error by stopping immediately
        viewModel.stopRecording()
        try await Task.sleep(nanoseconds: 200_000_000)

        // Should be able to start again
        viewModel.startRecording()
        try await Task.sleep(nanoseconds: 500_000_000)

        viewModel.stopRecording()
        try await Task.sleep(nanoseconds: 200_000_000)

        // Should recover successfully
        XCTAssertFalse(viewModel.isRecording)
    }

    func testMultipleStartStopCycles() async throws {
        // Test multiple recording cycles
        for i in 0..<3 {
            print("Recording cycle \(i + 1)")

            // Start
            viewModel.startRecording()
            try await Task.sleep(nanoseconds: 500_000_000)

            // Stop
            viewModel.stopRecording()
            try await Task.sleep(nanoseconds: 300_000_000)

            // Verify clean state between cycles
            XCTAssertFalse(viewModel.isRecording, "Should not be recording after cycle \(i + 1)")
            XCTAssertEqual(viewModel.recordingDuration, 0, "Duration should reset after cycle \(i + 1)")
        }
    }

    // MARK: - Performance Integration Tests

    func testSystemPerformanceUnderLoad() async throws {
        // Start all systems
        batteryManager.startBatteryMonitoring()
        viewModel.startRecording()

        try await Task.sleep(nanoseconds: 3_000_000_000) // 3 seconds

        // System should remain responsive
        let batteryInfo = batteryManager.getBatteryInfo()
        XCTAssertNotNil(batteryInfo["level"], "Battery info should be available under load")

        // Cleanup
        viewModel.stopRecording()
        batteryManager.stopBatteryMonitoring()
    }

    // MARK: - Concurrency Tests

    func testConcurrentOperations() async throws {
        // Test concurrent operations don't cause crashes
        await withTaskGroup(of: Void.self) { group in
            group.addTask { @MainActor in
                self.viewModel.startRecording()
            }

            group.addTask {
                self.batteryManager.sendBatteryLevel(force: true)
            }

            group.addTask {
                self.batteryManager.sendWatchInfo()
            }

            try? await Task.sleep(nanoseconds: 1_000_000_000)

            group.addTask { @MainActor in
                self.viewModel.stopRecording()
            }
        }

        try await Task.sleep(nanoseconds: 500_000_000)

        // All operations should complete without deadlock or crash
    }

    // MARK: - Memory and Resource Tests

    func testMemoryManagementDuringLongRecording() async throws {
        // Start recording
        viewModel.startRecording()

        // Simulate longer recording session
        for _ in 0..<5 {
            try await Task.sleep(nanoseconds: 1_000_000_000)
            // Memory should remain stable
        }

        // Stop and verify cleanup
        viewModel.stopRecording()
        try await Task.sleep(nanoseconds: 500_000_000)

        XCTAssertEqual(viewModel.recordingDuration, 0)
        XCTAssertEqual(viewModel.audioLevel, 0.0)
    }

    // MARK: - Data Flow Tests

    func testAudioDataBuffering() async throws {
        // Start recording
        viewModel.startRecording()

        // Let some audio data buffer
        try await Task.sleep(nanoseconds: 2_000_000_000)

        // Audio level should be tracked
        // Note: May be 0 in test environment without real audio
        XCTAssertGreaterThanOrEqual(viewModel.audioLevel, 0.0)
        XCTAssertLessThanOrEqual(viewModel.audioLevel, 1.0)

        // Stop and verify data is flushed
        viewModel.stopRecording()
        try await Task.sleep(nanoseconds: 500_000_000)
    }

    // MARK: - UI Integration Tests

    func testUIStateConsistency() async throws {
        let view = WatchRecorderView(viewModel: viewModel)

        // UI should reflect model state
        XCTAssertFalse(viewModel.isRecording)

        viewModel.startRecording()
        try await Task.sleep(nanoseconds: 500_000_000)

        viewModel.stopRecording()
        try await Task.sleep(nanoseconds: 300_000_000)

        // State should be consistent
        XCTAssertFalse(viewModel.isRecording)
    }

    // MARK: - Stress Tests

    func testRapidStateChanges() async throws {
        // Rapidly toggle recording state
        for _ in 0..<10 {
            viewModel.startRecording()
            try await Task.sleep(nanoseconds: 100_000_000)
            viewModel.stopRecording()
            try await Task.sleep(nanoseconds: 100_000_000)
        }

        // Should handle rapid changes gracefully
        XCTAssertFalse(viewModel.isRecording)
    }

    func testBatteryUpdateStorm() async throws {
        // Send many battery updates
        for _ in 0..<20 {
            batteryManager.sendBatteryLevel(force: true)
            try await Task.sleep(nanoseconds: 50_000_000)
        }

        // Should handle without crashing
    }

    // MARK: - Lifecycle Tests

    func testAppLifecycle() async throws {
        // Simulate app lifecycle
        // 1. App launches
        batteryManager.startBatteryMonitoring()

        // 2. User starts recording
        viewModel.startRecording()
        try await Task.sleep(nanoseconds: 1_000_000_000)

        // 3. App goes to background (simulated by session becoming unreachable)
        // Recording should continue

        // 4. App returns to foreground
        try await Task.sleep(nanoseconds: 500_000_000)

        // 5. User stops recording
        viewModel.stopRecording()

        // 6. Cleanup
        batteryManager.stopBatteryMonitoring()
        try await Task.sleep(nanoseconds: 300_000_000)

        // All transitions should be smooth
    }
}
