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
