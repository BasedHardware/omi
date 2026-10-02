import XCTest

// Operator-authorized, physical-device-only tests. They modify only the
// separate Omi Mic Probe's microphone/Bluetooth permissions and restore them
// in separate explicit steps so the host can capture denied-run evidence.
final class PermissionTests: XCTestCase {
    let probeID = "com.friend-app-with-wearable.ios12.development.micprobe"

    override func tearDown() {
        // Keep the test host foreground between operations so auto-lock does
        // not repeatedly require an operator unlock. It changes no OS setting.
        XCUIApplication(bundleIdentifier: "com.friend-app-with-wearable.ios12.development.permissionhost").activate()
        super.tearDown()
    }

    func openProbeSettings() -> XCUIApplication {
        continueAfterFailure = false
        let probe = XCUIApplication(bundleIdentifier: probeID)
        probe.launchArguments = ["--probe-open-settings"]
        probe.launch()
        let settings = XCUIApplication(bundleIdentifier: "com.apple.Preferences")
        XCTAssertTrue(settings.wait(for: .runningForeground, timeout: 15))
        return settings
    }

    func setPermission(_ name: String, enabled: Bool) {
        let settings = openProbeSettings()
        let control = settings.switches[name].firstMatch
        XCTAssertTrue(control.waitForExistence(timeout: 10), "Missing probe permission switch: \(name)")
        let wanted = enabled ? "1" : "0"
        if control.value as? String != wanted {
            // iOS Settings exposes a full-width labelled switch row. Tap its
            // trailing toggle, not the row's inert label area.
            control.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap()
        }
        let changed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == %@", wanted), object: control)
        XCTAssertEqual(XCTWaiter.wait(for: [changed], timeout: 5), .completed)
    }

    func testInspectSettings() {
        let settings = openProbeSettings()
        XCTAssertTrue(settings.switches["Microphone"].firstMatch.waitForExistence(timeout: 10))
        XCTAssertTrue(settings.switches["Bluetooth"].firstMatch.exists)
    }
    func testDenyMicrophone() { setPermission("Microphone", enabled: false) }
    func testRestoreMicrophone() { setPermission("Microphone", enabled: true) }
    func testDenyBluetooth() { setPermission("Bluetooth", enabled: false) }
    func testRestoreBluetooth() { setPermission("Bluetooth", enabled: true) }
    func testStopWearable() {
        continueAfterFailure = false
        let probe = XCUIApplication(bundleIdentifier: probeID)
        probe.activate()
        let stop = probe.buttons["Stop wearable test"]
        XCTAssertTrue(stop.waitForExistence(timeout: 10))
        stop.tap()
    }
    func testStopMicrophone() {
        continueAfterFailure = false
        let probe = XCUIApplication(bundleIdentifier: probeID)
        probe.activate()
        let stop = probe.buttons["Stop now"]
        XCTAssertTrue(stop.waitForExistence(timeout: 10))
        stop.tap()
        Thread.sleep(forTimeInterval: 3)
    }
    func testApproveCapturePrompts() {
        approveCapturePrompts(bundleID: "com.omi.capture-qualification.recovery")
    }
    func testInspectCapture() {
        let app = XCUIApplication(bundleIdentifier: "com.omi.capture-qualification.recovery")
        app.activate()
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 10))
        Thread.sleep(forTimeInterval: 2) // Allow the app-switch animation to finish before capture.
        print("CAPTURE_UI " + app.debugDescription)
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "Capture qualification app"
        screenshot.lifetime = .keepAlways
        add(screenshot)
    }
    func testApproveWearableCapturePrompts() {
        approveCapturePrompts(bundleID: "com.omi.capture-qualification.wearable")
    }
    private func approveCapturePrompts(bundleID: String) {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: bundleID)
        app.activate()
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        for _ in 0..<4 {
            let alert = springboard.alerts.firstMatch
            guard alert.waitForExistence(timeout: 5) else { continue }
            let text = alert.staticTexts.allElementsBoundByIndex.map { $0.label }.joined(separator: " ")
            XCTAssertTrue(text.contains("OmiCaptureQA"), "Unexpected app permission prompt")
            let lower = text.lowercased()
            XCTAssertTrue(lower.contains("microphone") || lower.contains("bluetooth") || lower.contains("local network"),
                          "Permission outside the capture test scope")
            if alert.buttons["Allow"].exists { alert.buttons["Allow"].tap() }
            else { XCTAssertTrue(alert.buttons["OK"].exists); alert.buttons["OK"].tap() }
        }
    }
    func testApproveInterrupterMicrophone() {
        continueAfterFailure = false
        let driver = XCUIApplication(bundleIdentifier: "com.friend-app-with-wearable.ios12.development.interruptiondriver")
        driver.launchArguments = ["--capture"]
        driver.launch()
        let alert = XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts.firstMatch
        XCTAssertTrue(alert.waitForExistence(timeout: 10))
        XCTAssertTrue(alert.staticTexts.containing(NSPredicate(format: "label CONTAINS %@", "Omi Audio Interrupter")).firstMatch.exists,
                      "Only the separate interruption driver's microphone prompt may be approved")
        let allow = alert.buttons["Allow"]
        if allow.exists { allow.tap() } else { alert.buttons["OK"].tap() }
    }
    func testSiriInterruption() {
        // Explicitly selected device experiment only, never a hermetic test.
        // The harmless arithmetic request changes no user data or settings.
        continueAfterFailure = false
        let probe = XCUIApplication(bundleIdentifier: probeID)
        probe.launchArguments = ["--probe-mode", "mic", "--probe-duration", "30"]
        probe.launch()
        Thread.sleep(forTimeInterval: 3)
        XCUIDevice.shared.siriService.activate(voiceRecognitionText: "What is two plus two?")
        Thread.sleep(forTimeInterval: 5)
        probe.activate()
        XCTAssertTrue(probe.wait(for: .runningForeground, timeout: 10))
        // The separate microphone trace/analyzer is the interruption oracle.
    }
}
