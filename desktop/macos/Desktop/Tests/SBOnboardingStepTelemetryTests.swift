import XCTest

@testable import Omi_Computer

/// Pins the live onboarding step-exit event. A rename of the event string or a
/// step's analytics name must break this test, not the admin funnel dashboard.
@MainActor
final class SBOnboardingStepTelemetryTests: XCTestCase {
  private var captured: [(String, [String: Any])] = []
  private var retainedAppState: AppState?

  private func startCapturing() {
    captured = []
    OnboardingStepTelemetry.captureForTests = { [weak self] event, properties in
      self?.captured.append((event, properties))
    }
    addTeardownBlock {
      await MainActor.run {
        OnboardingStepTelemetry.captureForTests = nil
        OnboardingStepTelemetry.now = Date.init
      }
    }
  }

  private func makeModel() -> SBOnboardingModel {
    let appState = AppState()
    retainedAppState = appState
    return SBOnboardingModel(appState: appState, chatProvider: ChatProvider(), onComplete: nil)
  }

  func testAnalyticsNamesMatchTheLiveNineteenSteps() {
    XCTAssertEqual(
      SBOnboardingModel.Step.allCases.map(\.analyticsName),
      [
        "promise", "name", "howHeard", "language", "role",
        "mic", "systemAudio", "screen", "files", "accessibility", "automation", "notifications",
        "shortcutOpen", "shortcutTalk", "screenDemo", "agents", "context", "capture", "referral",
      ])
  }

  func testOrdinaryStepPayloadIsThePinnedEventAndPropertySet() {
    let properties = OnboardingStepTelemetry.payload(
      step: "promise",
      index: 0,
      elapsedMs: 1_250,
      skipped: false,
      exitReason: .answered,
      permission: nil,
      granted: nil)

    XCTAssertEqual(OnboardingStepTelemetry.eventName, "Onboarding Step Completed")
    XCTAssertEqual(properties["step"] as? String, "promise")
    XCTAssertEqual(properties["index"] as? Int, 0)
    XCTAssertEqual(properties["elapsed_ms"] as? Int, 1_250)
    XCTAssertEqual(properties["skipped"] as? Bool, false)
    XCTAssertEqual(properties["exit_reason"] as? String, "answered")
    XCTAssertNil(properties["permission"])
    XCTAssertNil(properties["granted"])
    XCTAssertEqual(Set(properties.keys), ["step", "index", "elapsed_ms", "skipped", "exit_reason"])
  }

  func testPermissionStepPayloadCarriesWhichPermissionAndWhetherGranted() {
    let properties = OnboardingStepTelemetry.payload(
      step: "mic",
      index: SBOnboardingModel.Step.mic.rawValue,
      elapsedMs: 400,
      skipped: true,
      exitReason: .skipped,
      permission: "microphone",
      granted: false)

    XCTAssertEqual(properties["step"] as? String, "mic")
    XCTAssertEqual(properties["index"] as? Int, SBOnboardingModel.Step.mic.rawValue)
    XCTAssertEqual(properties["elapsed_ms"] as? Int, 400)
    XCTAssertEqual(properties["skipped"] as? Bool, true)
    XCTAssertEqual(properties["exit_reason"] as? String, "skipped")
    XCTAssertEqual(properties["permission"] as? String, "microphone")
    XCTAssertEqual(properties["granted"] as? Bool, false)
    XCTAssertEqual(Set(properties.keys), OnboardingStepTelemetry.allowedKeys)
  }

  func testExitReasonIsTheClosedSet() {
    XCTAssertEqual(
      OnboardingStepTelemetry.ExitReason.allCases.map(\.rawValue),
      ["answered", "skipped", "auto_granted"])
  }

  /// Nothing an emitter passes may escape the allow-list — never a name, a role,
  /// or a page title. Covers every closed exit, including auto-granted jumps.
  func testEveryEmittedKeyIsOnTheAllowList() {
    let samples: [[String: Any]] = [
      OnboardingStepTelemetry.payload(
        step: "promise", index: 0, elapsedMs: 1, skipped: false, exitReason: .answered,
        permission: nil, granted: nil),
      OnboardingStepTelemetry.payload(
        step: "mic", index: 5, elapsedMs: 1, skipped: true, exitReason: .skipped,
        permission: "microphone", granted: false),
      OnboardingStepTelemetry.payload(
        step: "mic", index: 5, elapsedMs: 0, skipped: true, exitReason: .autoGranted,
        permission: "microphone", granted: true),
    ]
    XCTAssertFalse(samples.isEmpty)
    for properties in samples {
      for key in properties.keys {
        XCTAssertTrue(
          OnboardingStepTelemetry.allowedKeys.contains(key),
          "\(key) is not an allowed dimension of \(OnboardingStepTelemetry.eventName)")
      }
    }
  }

  func testAdvanceFromAnOrdinaryStepEmitsThePinnedEvent() {
    startCapturing()
    let model = makeModel()
    let start = Date(timeIntervalSince1970: 1_000)
    var current = start
    OnboardingStepTelemetry.now = { current }
    model.step = .promise
    model.stepStartedAt = start
    current = start.addingTimeInterval(1.5)

    model.advance(userAnswer: "Set me up", to: .name)

    XCTAssertEqual(captured.count, 1)
    XCTAssertEqual(captured[0].0, "Onboarding Step Completed")
    let properties = captured[0].1
    XCTAssertEqual(properties["step"] as? String, "promise")
    XCTAssertEqual(properties["index"] as? Int, 0)
    XCTAssertEqual(properties["elapsed_ms"] as? Int, 1_500)
    XCTAssertEqual(properties["skipped"] as? Bool, false)
    XCTAssertEqual(properties["exit_reason"] as? String, "answered")
    XCTAssertNil(properties["permission"])
    XCTAssertNil(properties["granted"])
    XCTAssertEqual(Set(properties.keys), ["step", "index", "elapsed_ms", "skipped", "exit_reason"])
    XCTAssertFalse(
      String(describing: properties).contains("Set me up"),
      "user answers must not reach analytics")
  }

  func testAdvanceFromAGrantedPermissionStepMarksGranted() {
    startCapturing()
    let model = makeModel()
    model.step = .mic
    model.micState = .on
    model.stepStartedAt = OnboardingStepTelemetry.now()

    model.answerMic()

    XCTAssertEqual(captured.count, 1)
    XCTAssertEqual(captured[0].0, "Onboarding Step Completed")
    let properties = captured[0].1
    XCTAssertEqual(properties["step"] as? String, "mic")
    XCTAssertEqual(properties["index"] as? Int, SBOnboardingModel.Step.mic.rawValue)
    XCTAssertEqual(properties["skipped"] as? Bool, false)
    XCTAssertEqual(properties["exit_reason"] as? String, "answered")
    XCTAssertEqual(properties["permission"] as? String, "microphone")
    XCTAssertEqual(properties["granted"] as? Bool, true)
    XCTAssertEqual(Set(properties.keys), OnboardingStepTelemetry.allowedKeys)
  }

  func testAdvanceFromASkippedPermissionStepMarksSkippedAndNotGranted() {
    startCapturing()
    let model = makeModel()
    model.step = .mic
    model.micState = .ask
    model.stepStartedAt = OnboardingStepTelemetry.now()

    model.answerMic()

    XCTAssertEqual(captured.count, 1)
    let properties = captured[0].1
    XCTAssertEqual(properties["step"] as? String, "mic")
    XCTAssertEqual(properties["skipped"] as? Bool, true)
    XCTAssertEqual(properties["exit_reason"] as? String, "skipped")
    XCTAssertEqual(properties["permission"] as? String, "microphone")
    XCTAssertEqual(properties["granted"] as? Bool, false)
  }

  func testScreenDemoStepUsesThePinnedAnalyticsName() {
    startCapturing()
    let model = makeModel()
    model.step = .screenDemo
    model.stepStartedAt = OnboardingStepTelemetry.now()

    model.advance(userAnswer: "Continue", to: .agents)

    XCTAssertEqual(captured.count, 1)
    XCTAssertEqual(captured[0].1["step"] as? String, "screenDemo")
    XCTAssertEqual(captured[0].1["index"] as? Int, SBOnboardingModel.Step.screenDemo.rawValue)
    XCTAssertEqual(captured[0].1["skipped"] as? Bool, false)
    XCTAssertEqual(captured[0].1["exit_reason"] as? String, "answered")
  }

  func testGoBackDoesNotEmitAStepEvent() {
    startCapturing()
    let model = makeModel()
    model.step = .language

    model.goBack()

    XCTAssertTrue(captured.isEmpty)
    XCTAssertEqual(model.step, .howHeard)
  }

  func testSkipOverrideMarksANonPermissionStepSkipped() {
    startCapturing()
    let model = makeModel()
    model.step = .screenDemo
    model.stepStartedAt = OnboardingStepTelemetry.now()

    model.recordStepExit(skipped: true)

    XCTAssertEqual(captured.count, 1)
    XCTAssertEqual(captured[0].0, "Onboarding Step Completed")
    XCTAssertEqual(captured[0].1["step"] as? String, "screenDemo")
    XCTAssertEqual(captured[0].1["skipped"] as? Bool, true)
    XCTAssertEqual(captured[0].1["exit_reason"] as? String, "skipped")
    XCTAssertNil(captured[0].1["permission"])
  }

  func testAutoJumpedPermissionStepEmitsAutoGranted() {
    startCapturing()
    let model = makeModel()

    model.recordJumpedPermissionSteps(from: .mic, to: .systemAudio)

    XCTAssertEqual(captured.count, 1)
    XCTAssertEqual(captured[0].0, "Onboarding Step Completed")
    let properties = captured[0].1
    XCTAssertEqual(properties["step"] as? String, "mic")
    XCTAssertEqual(properties["index"] as? Int, SBOnboardingModel.Step.mic.rawValue)
    XCTAssertEqual(properties["elapsed_ms"] as? Int, 0)
    XCTAssertEqual(properties["skipped"] as? Bool, true)
    XCTAssertEqual(properties["exit_reason"] as? String, "auto_granted")
    XCTAssertEqual(properties["permission"] as? String, "microphone")
    XCTAssertEqual(properties["granted"] as? Bool, true)
    XCTAssertEqual(Set(properties.keys), OnboardingStepTelemetry.allowedKeys)
  }

  func testNegativeElapsedTimeIsClampedToZero() {
    let properties = OnboardingStepTelemetry.payload(
      step: "name",
      index: 1,
      elapsedMs: -12,
      skipped: false,
      exitReason: .answered,
      permission: nil,
      granted: nil)
    XCTAssertEqual(properties["elapsed_ms"] as? Int, 0)
  }
}
