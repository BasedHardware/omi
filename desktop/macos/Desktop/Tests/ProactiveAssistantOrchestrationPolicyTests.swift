import XCTest
@testable import Omi_Computer

final class ProactiveAssistantOrchestrationPolicyTests: XCTestCase {
    func testPermissionRecheckUsesConfiguredInterval() {
        let lastCheck = Date(timeIntervalSinceReferenceDate: 1_000)

        XCTAssertFalse(ProactiveAssistantOrchestrationPolicy.shouldRecheckPermission(
            now: lastCheck.addingTimeInterval(59.9),
            lastCheckTime: lastCheck,
            interval: 60
        ))
        XCTAssertTrue(ProactiveAssistantOrchestrationPolicy.shouldRecheckPermission(
            now: lastCheck.addingTimeInterval(60),
            lastCheckTime: lastCheck,
            interval: 60
        ))
    }

    func testScreenshotAppPausesAndExtendsBackoffWhileFrontmost() {
        let now = Date(timeIntervalSinceReferenceDate: 2_000)

        XCTAssertEqual(
            ProactiveAssistantOrchestrationPolicy.screenshotAppDecision(
                isScreenshotAppFrontmost: true,
                wasScreenshotAppFrontmost: false,
                backoffUntil: .distantPast,
                now: now,
                backoffDuration: 10
            ),
            .pause(backoffUntil: now.addingTimeInterval(10))
        )
    }

    func testScreenshotAppTransitionContinuesBackoffThenCapturesAfterExpiry() {
        let now = Date(timeIntervalSinceReferenceDate: 3_000)

        XCTAssertEqual(
            ProactiveAssistantOrchestrationPolicy.screenshotAppDecision(
                isScreenshotAppFrontmost: false,
                wasScreenshotAppFrontmost: true,
                backoffUntil: now.addingTimeInterval(4),
                now: now,
                backoffDuration: 10
            ),
            .resumeIntoBackoff
        )
        XCTAssertEqual(
            ProactiveAssistantOrchestrationPolicy.screenshotAppDecision(
                isScreenshotAppFrontmost: false,
                wasScreenshotAppFrontmost: false,
                backoffUntil: now.addingTimeInterval(4),
                now: now,
                backoffDuration: 10
            ),
            .continueBackoff
        )
        XCTAssertEqual(
            ProactiveAssistantOrchestrationPolicy.screenshotAppDecision(
                isScreenshotAppFrontmost: false,
                wasScreenshotAppFrontmost: false,
                backoffUntil: now.addingTimeInterval(-0.1),
                now: now,
                backoffDuration: 10
            ),
            .capture
        )
    }

    func testScreenshotAppTransitionCapturesImmediatelyWhenBackoffExpired() {
        let now = Date(timeIntervalSinceReferenceDate: 3_500)

        XCTAssertEqual(
            ProactiveAssistantOrchestrationPolicy.screenshotAppDecision(
                isScreenshotAppFrontmost: false,
                wasScreenshotAppFrontmost: true,
                backoffUntil: now.addingTimeInterval(-0.1),
                now: now,
                backoffDuration: 10
            ),
            .resumeAndCapture
        )
    }

    func testScreenshotAndVideoGatesResetStaleState() {
        var screenshotGate = ProactiveScreenshotCaptureGate()
        let now = Date(timeIntervalSinceReferenceDate: 3_750)
        XCTAssertEqual(
            screenshotGate.nextDecision(isScreenshotAppFrontmost: true, now: now, backoffDuration: 10),
            .pause(backoffUntil: now.addingTimeInterval(10))
        )

        screenshotGate.reset()
        XCTAssertFalse(screenshotGate.wasScreenshotAppFrontmost)
        XCTAssertEqual(screenshotGate.backoffUntil, .distantPast)

        var videoGate = ProactiveVideoCallThrottleGate()
        XCTAssertEqual(videoGate.nextDecision(isVideoCall: true, throttleFactor: 5), .skip(nextCounter: 1, didEnterCall: true))
        videoGate.reset()
        XCTAssertEqual(videoGate.counter, 0)
    }

    func testVideoCallThrottleCapturesOneOutOfEveryNFrames() {
        let factor = 5

        XCTAssertEqual(
            ProactiveAssistantOrchestrationPolicy.videoCallThrottleDecision(
                isVideoCall: true,
                currentCounter: 0,
                throttleFactor: factor
            ),
            .skip(nextCounter: 1, didEnterCall: true)
        )
        XCTAssertEqual(
            ProactiveAssistantOrchestrationPolicy.videoCallThrottleDecision(
                isVideoCall: true,
                currentCounter: 4,
                throttleFactor: factor
            ),
            .capture(nextCounter: 0, didLeaveCall: false)
        )
        XCTAssertEqual(
            ProactiveAssistantOrchestrationPolicy.videoCallThrottleDecision(
                isVideoCall: false,
                currentCounter: 2,
                throttleFactor: factor
            ),
            .capture(nextCounter: 0, didLeaveCall: true)
        )
    }

    func testDistributionFlushesFirstFrameAndDebouncesContextChange() {
        let now = Date(timeIntervalSinceReferenceDate: 4_000)

        XCTAssertEqual(
            distributionDecision(
                lastApp: nil,
                lastTitle: nil,
                frameApp: "Xcode",
                frameTitle: "Project",
                lastDistributionTime: .distantPast,
                now: now
            ),
            .flushNow
        )
        XCTAssertEqual(
            distributionDecision(
                lastApp: "Xcode",
                lastTitle: "Project",
                frameApp: "Safari",
                frameTitle: "Docs",
                lastDistributionTime: now,
                now: now
            ),
            .debounce
        )
    }

    func testDistributionFallbackUsesDefaultAndMessagingCadence() {
        let now = Date(timeIntervalSinceReferenceDate: 5_000)

        XCTAssertEqual(
            distributionDecision(
                lastApp: "Xcode",
                lastTitle: "Project",
                frameApp: "Xcode",
                frameTitle: "Project",
                lastDistributionTime: now.addingTimeInterval(-59),
                now: now
            ),
            .skip
        )
        XCTAssertEqual(
            distributionDecision(
                lastApp: "Xcode",
                lastTitle: "Project",
                frameApp: "Xcode",
                frameTitle: "Project",
                lastDistributionTime: now.addingTimeInterval(-60),
                now: now
            ),
            .flushNow
        )
        XCTAssertEqual(
            distributionDecision(
                lastApp: "Slack",
                lastTitle: "Team",
                frameApp: "Slack",
                frameTitle: "Team",
                lastDistributionTime: now.addingTimeInterval(-15),
                now: now
            ),
            .flushNow
        )
    }

    func testScreenshotGateMutatesBackoffStateAcrossPauseResumeAndExpiry() {
        var gate = ProactiveScreenshotCaptureGate()
        let now = Date(timeIntervalSinceReferenceDate: 6_000)

        XCTAssertEqual(
            gate.nextDecision(isScreenshotAppFrontmost: true, now: now, backoffDuration: 10),
            .pause(backoffUntil: now.addingTimeInterval(10))
        )
        XCTAssertTrue(gate.wasScreenshotAppFrontmost)
        XCTAssertEqual(gate.backoffUntil, now.addingTimeInterval(10))

        XCTAssertEqual(
            gate.nextDecision(isScreenshotAppFrontmost: false, now: now.addingTimeInterval(2), backoffDuration: 10),
            .resumeIntoBackoff
        )
        XCTAssertFalse(gate.wasScreenshotAppFrontmost)
        XCTAssertEqual(gate.backoffUntil, now.addingTimeInterval(10))

        XCTAssertEqual(
            gate.nextDecision(isScreenshotAppFrontmost: false, now: now.addingTimeInterval(9), backoffDuration: 10),
            .continueBackoff
        )
        XCTAssertEqual(
            gate.nextDecision(isScreenshotAppFrontmost: false, now: now.addingTimeInterval(10), backoffDuration: 10),
            .capture
        )
    }

    func testVideoCallThrottleGateCarriesCounterAndResetsWhenLeavingCall() {
        var gate = ProactiveVideoCallThrottleGate()

        XCTAssertEqual(gate.nextDecision(isVideoCall: true, throttleFactor: 3), .skip(nextCounter: 1, didEnterCall: true))
        XCTAssertEqual(gate.counter, 1)
        XCTAssertEqual(gate.nextDecision(isVideoCall: true, throttleFactor: 3), .skip(nextCounter: 2, didEnterCall: false))
        XCTAssertEqual(gate.counter, 2)
        XCTAssertEqual(gate.nextDecision(isVideoCall: true, throttleFactor: 3), .capture(nextCounter: 0, didLeaveCall: false))
        XCTAssertEqual(gate.counter, 0)

        XCTAssertEqual(gate.nextDecision(isVideoCall: true, throttleFactor: 3), .skip(nextCounter: 1, didEnterCall: true))
        XCTAssertEqual(gate.nextDecision(isVideoCall: false, throttleFactor: 3), .capture(nextCounter: 0, didLeaveCall: true))
        XCTAssertEqual(gate.counter, 0)
    }

    func testDistributionGateTracksPendingContextAndFlushTime() {
        var gate = ProactiveFrameDistributionGate()
        let now = Date(timeIntervalSinceReferenceDate: 7_000)

        XCTAssertEqual(
            gate.nextAction(
                frameApp: "Xcode",
                frameWindowTitle: "Project",
                now: now,
                defaultFallbackInterval: 60,
                messagingFallbackInterval: 15,
                messagingFastPathApps: ["Slack"]
            ),
            .flushNow
        )
        XCTAssertNil(gate.lastDistributedApp)

        gate.markFlushed(frameApp: "Xcode", frameWindowTitle: "Project", at: now)
        XCTAssertEqual(gate.lastDistributedApp, "Xcode")
        XCTAssertEqual(gate.lastDistributedWindowTitle, "Project")
        XCTAssertEqual(gate.lastDistributionTime, now)

        XCTAssertEqual(
            gate.nextAction(
                frameApp: "Safari",
                frameWindowTitle: "Docs",
                now: now.addingTimeInterval(1),
                defaultFallbackInterval: 60,
                messagingFallbackInterval: 15,
                messagingFastPathApps: ["Slack"]
            ),
            .scheduleDebounce
        )
        XCTAssertEqual(gate.lastDistributedApp, "Safari")
        XCTAssertEqual(gate.lastDistributedWindowTitle, "Docs")
        XCTAssertEqual(gate.lastDistributionTime, now)

        XCTAssertEqual(
            gate.nextAction(
                frameApp: "Safari",
                frameWindowTitle: "Docs",
                now: now.addingTimeInterval(2),
                defaultFallbackInterval: 60,
                messagingFallbackInterval: 15,
                messagingFastPathApps: ["Slack"]
            ),
            .skip
        )

        let flushTime = now.addingTimeInterval(4)
        gate.markFlushed(frameApp: "Safari", frameWindowTitle: "Docs", at: flushTime)
        XCTAssertEqual(gate.lastDistributionTime, flushTime)
    }

    private func distributionDecision(
        lastApp: String?,
        lastTitle: String?,
        frameApp: String,
        frameTitle: String?,
        lastDistributionTime: Date,
        now: Date
    ) -> ProactiveAssistantOrchestrationPolicy.DistributionDecision {
        ProactiveAssistantOrchestrationPolicy.distributionDecision(
            lastDistributedApp: lastApp,
            lastDistributedWindowTitle: lastTitle,
            frameApp: frameApp,
            frameWindowTitle: frameTitle,
            lastDistributionTime: lastDistributionTime,
            now: now,
            defaultFallbackInterval: 60,
            messagingFallbackInterval: 15,
            messagingFastPathApps: ["Slack", "Messages"]
        )
    }
}
