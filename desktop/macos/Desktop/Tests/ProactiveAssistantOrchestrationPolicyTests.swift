import XCTest

@testable import Omi_Computer

final class ProactiveAssistantOrchestrationPolicyTests: XCTestCase {
  func testUnavailableTargetResetsEngineFailuresWithoutHidingCaptureHealth() {
    var failures = ScreenCaptureFailureTracker()

    XCTAssertEqual(failures.recordEngineFailure(), 1)
    XCTAssertEqual(failures.recordEngineFailure(), 2)
    failures.recordTargetUnavailable()

    XCTAssertEqual(failures.consecutiveEngineFailures, 0)
    XCTAssertEqual(failures.recordEngineFailure(), 1)
    XCTAssertEqual(
      ScreenCaptureHealth.temporarilyUnavailable.statusText, "Capture paused: current window can’t be captured")
    XCTAssertEqual(ScreenCaptureHealth.temporarilyUnavailable.rewindBadgeText, "Capture paused")
    XCTAssertEqual(ScreenCaptureHealth.recovering.rewindBadgeText, "Recovering")
  }

  func testSuccessfulCaptureClearsOnlyEngineFailureState() {
    var failures = ScreenCaptureFailureTracker()

    XCTAssertEqual(failures.recordEngineFailure(), 1)
    XCTAssertEqual(failures.recordEngineFailure(), 2)
    XCTAssertEqual(failures.recordCaptureSuccess(), 2)
    XCTAssertEqual(failures.consecutiveEngineFailures, 0)
  }

  func testPermissionRecheckUsesConfiguredInterval() {
    let lastCheck = Date(timeIntervalSinceReferenceDate: 1_000)

    XCTAssertFalse(
      ProactiveAssistantOrchestrationPolicy.shouldRecheckPermission(
        now: lastCheck.addingTimeInterval(59.9),
        lastCheckTime: lastCheck,
        interval: 60
      ))
    XCTAssertTrue(
      ProactiveAssistantOrchestrationPolicy.shouldRecheckPermission(
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
    XCTAssertEqual(
      videoGate.nextDecision(isVideoCall: true, throttleFactor: 5), .skip(nextCounter: 1, didEnterCall: true))
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

  // Regression: issue #10143 — capture must pause for the whole duration of an active
  // outgoing screen share, then hold a backoff after it ends before resuming.
  func testExternalCaptureYieldPausesAcrossActiveShareThenBacksOff() {
    var yield = ProactiveExternalCaptureYield()
    let start = Date(timeIntervalSinceReferenceDate: 9_000)

    func tick(_ offset: TimeInterval, screenshotApp: Bool = false, sharing: Bool) -> Bool {
      yield.shouldYield(
        isScreenshotAppFrontmost: screenshotApp,
        isScreenShareActive: sharing,
        now: start.addingTimeInterval(offset),
        screenshotBackoffDuration: 10,
        shareBackoffDuration: 10
      )
    }

    // No external capture: proceed.
    XCTAssertFalse(tick(0, sharing: false))
    // Share starts: every tick yields for as long as the share lasts.
    XCTAssertTrue(tick(1, sharing: true))
    XCTAssertTrue(tick(2, sharing: true))
    XCTAssertTrue(tick(120, sharing: true))
    // Share ends: still yield through the backoff window...
    XCTAssertTrue(tick(121, sharing: false))
    XCTAssertTrue(tick(129, sharing: false))
    // ...and resume once the backoff has expired.
    XCTAssertFalse(tick(131, sharing: false))
  }

  func testExternalCaptureYieldScreenshotGateShortCircuitsShareCheck() {
    var yield = ProactiveExternalCaptureYield()
    let now = Date(timeIntervalSinceReferenceDate: 9_500)
    var shareChecked = false

    // While a screenshot app is frontmost, the (more expensive) share check must not run.
    XCTAssertTrue(
      yield.shouldYield(
        isScreenshotAppFrontmost: true,
        isScreenShareActive: {
          shareChecked = true
          return false
        }(),
        now: now,
        screenshotBackoffDuration: 10,
        shareBackoffDuration: 10
      )
    )
    XCTAssertFalse(shareChecked)
  }

  func testExternalCaptureYieldResetClearsBothGates() {
    var yield = ProactiveExternalCaptureYield()
    let now = Date(timeIntervalSinceReferenceDate: 9_800)

    XCTAssertTrue(
      yield.shouldYield(
        isScreenshotAppFrontmost: true,
        isScreenShareActive: true,
        now: now,
        screenshotBackoffDuration: 10,
        shareBackoffDuration: 10
      )
    )
    yield.reset()
    XCTAssertFalse(yield.screenshotGate.wasScreenshotAppFrontmost)
    XCTAssertFalse(yield.shareGate.wasScreenshotAppFrontmost)
    XCTAssertEqual(yield.screenshotGate.backoffUntil, .distantPast)
    XCTAssertEqual(yield.shareGate.backoffUntil, .distantPast)
  }

  func testVideoCallThrottleGateCarriesCounterAndResetsWhenLeavingCall() {
    var gate = ProactiveVideoCallThrottleGate()

    XCTAssertEqual(gate.nextDecision(isVideoCall: true, throttleFactor: 3), .skip(nextCounter: 1, didEnterCall: true))
    XCTAssertEqual(gate.counter, 1)
    XCTAssertEqual(gate.nextDecision(isVideoCall: true, throttleFactor: 3), .skip(nextCounter: 2, didEnterCall: false))
    XCTAssertEqual(gate.counter, 2)
    XCTAssertEqual(
      gate.nextDecision(isVideoCall: true, throttleFactor: 3), .capture(nextCounter: 0, didLeaveCall: false))
    XCTAssertEqual(gate.counter, 0)

    XCTAssertEqual(gate.nextDecision(isVideoCall: true, throttleFactor: 3), .skip(nextCounter: 1, didEnterCall: true))
    XCTAssertEqual(
      gate.nextDecision(isVideoCall: false, throttleFactor: 3), .capture(nextCounter: 0, didLeaveCall: true))
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

  // MARK: - ProactiveCaptureTrigger

  func testCaptureTriggerSkipsWhenIdle() {
    let now = Date(timeIntervalSinceReferenceDate: 5_000)
    var trigger = ProactiveCaptureTrigger(
      idleThreshold: 60, heartbeatInterval: 3, appSwitchDebounce: 0.5)

    XCTAssertEqual(
      trigger.nextDecision(
        app: "Safari", windowTitle: "Docs", idleSeconds: 60, now: now),
      .skip)
    XCTAssertEqual(
      trigger.nextDecision(
        app: "Safari", windowTitle: "Docs", idleSeconds: 61, now: now),
      .skip)
  }

  func testCaptureTriggerCapturesOnContextChange() {
    let now = Date(timeIntervalSinceReferenceDate: 6_000)
    var trigger = ProactiveCaptureTrigger(
      idleThreshold: 60, heartbeatInterval: 3, appSwitchDebounce: 0.5)

    // First call: no prior context, so capture.
    XCTAssertEqual(
      trigger.nextDecision(
        app: "Safari", windowTitle: "Docs", idleSeconds: 0, now: now),
      .capture)
    // Same context: skip until heartbeat.
    XCTAssertEqual(
      trigger.nextDecision(
        app: "Safari", windowTitle: "Docs", idleSeconds: 0, now: now.addingTimeInterval(1)),
      .skip)
    // App change: capture immediately.
    XCTAssertEqual(
      trigger.nextDecision(
        app: "Xcode", windowTitle: "Project", idleSeconds: 0, now: now.addingTimeInterval(2)),
      .capture)
    // Title change: capture immediately.
    XCTAssertEqual(
      trigger.nextDecision(
        app: "Xcode", windowTitle: "Other", idleSeconds: 0, now: now.addingTimeInterval(2.5)),
      .capture)
  }

  func testCaptureTriggerHeartbeatsOnlyWhenActive() {
    let now = Date(timeIntervalSinceReferenceDate: 7_000)
    var trigger = ProactiveCaptureTrigger(
      idleThreshold: 60, heartbeatInterval: 3, appSwitchDebounce: 0.5)

    XCTAssertEqual(
      trigger.nextDecision(app: "Safari", windowTitle: "Docs", idleSeconds: 0, now: now),
      .capture)
    XCTAssertEqual(
      trigger.nextDecision(
        app: "Safari", windowTitle: "Docs", idleSeconds: 0, now: now.addingTimeInterval(2.9)),
      .skip)
    XCTAssertEqual(
      trigger.nextDecision(
        app: "Safari", windowTitle: "Docs", idleSeconds: 0, now: now.addingTimeInterval(3)),
      .preview)
  }

  func testCaptureTriggerDebouncesAppSwitchRequests() {
    let now = Date(timeIntervalSinceReferenceDate: 8_000)
    var trigger = ProactiveCaptureTrigger(
      idleThreshold: 60, heartbeatInterval: 3, appSwitchDebounce: 0.5)

    trigger.requestAppSwitchCapture(app: "Safari", at: now)
    // Before debounce: skip (same context anyway, but request is pending).
    XCTAssertEqual(
      trigger.nextDecision(app: "Safari", windowTitle: "Docs", idleSeconds: 0, now: now.addingTimeInterval(0.1)),
      .skip)
    // After debounce: context changed from nil, so capture.
    XCTAssertEqual(
      trigger.nextDecision(app: "Safari", windowTitle: "Docs", idleSeconds: 0, now: now.addingTimeInterval(0.6)),
      .capture)
  }

  func testCaptureTriggerPreviewSimilaritySkipsUnchangedFrames() {
    let now = Date(timeIntervalSinceReferenceDate: 9_000)
    var trigger = ProactiveCaptureTrigger(
      idleThreshold: 60, heartbeatInterval: 3, appSwitchDebounce: 0.5)

    XCTAssertEqual(
      trigger.nextDecision(app: "Safari", windowTitle: "Docs", idleSeconds: 0, now: now),
      .capture)

    // First captured frame seeds the preview history.
    trigger.recordPreviewHash(0x1234)
    XCTAssertEqual(
      trigger.nextDecision(app: "Safari", windowTitle: "Docs", idleSeconds: 0, now: now.addingTimeInterval(3)),
      .preview)

    // 0x1235 is one bit away from 0x1234 -> very high similarity.
    XCTAssertEqual(trigger.previewSimilarity(to: 0x1235), 63.0 / 64.0, accuracy: 1e-9)
    XCTAssertTrue(trigger.shouldSkipPreview(0x1235, similarityThreshold: 0.92))

    // 0xFFFF is very different -> low similarity.
    XCTAssertTrue(trigger.previewSimilarity(to: 0xFFFF) < 0.9)
    XCTAssertFalse(trigger.shouldSkipPreview(0xFFFF, similarityThreshold: 0.92))

    // A cycling frame that matches any recent preview is skipped.
    trigger.recordPreviewHash(0xABCD)
    XCTAssertTrue(trigger.shouldSkipPreview(0x1234, similarityThreshold: 0.92))
  }
}
