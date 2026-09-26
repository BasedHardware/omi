import XCTest

@testable import Omi_Computer

/// Records what a probe observed from whatever thread it ran on.
private final class ProbeRecorder: @unchecked Sendable {
  private let lock = NSLock()
  private var mainThreadObservations: [Bool] = []

  func record(isMainThread: Bool) {
    lock.lock()
    mainThreadObservations.append(isMainThread)
    lock.unlock()
  }

  var ranOnMainThread: Bool {
    lock.lock()
    defer { lock.unlock() }
    return mainThreadObservations.contains(true)
  }

  var callCount: Int {
    lock.lock()
    defer { lock.unlock() }
    return mainThreadObservations.count
  }
}

/// Replays a scripted sequence of `AEDeterminePermissionToAutomateTarget` answers
/// across the actor hops a probe makes, and counts how many were consumed.
private final class StatusSequence: @unchecked Sendable {
  private let lock = NSLock()
  private var remaining: [OSStatus]
  private var consumed = 0

  init(_ statuses: [OSStatus]) { remaining = statuses }

  func next() -> OSStatus {
    lock.lock()
    defer { lock.unlock() }
    consumed += 1
    return remaining.isEmpty ? -600 : remaining.removeFirst()
  }

  var callCount: Int {
    lock.lock()
    defer { lock.unlock() }
    return consumed
  }
}

/// Holds a detached probe open while the main-actor state changes. This makes
/// the Automation -600 merge test deterministic without a wall-clock sleep.
private final class BlockingProbeGate: @unchecked Sendable {
  let release = DispatchSemaphore(value: 0)
  private let lock = NSLock()
  private var didEnter = false
  private var enteredContinuation: CheckedContinuation<Void, Never>?

  func waitUntilReleased() {
    lock.lock()
    didEnter = true
    let continuation = enteredContinuation
    enteredContinuation = nil
    lock.unlock()
    continuation?.resume()
    release.wait()
  }

  func waitUntilEntered() async {
    await withCheckedContinuation { continuation in
      lock.lock()
      if didEnter {
        lock.unlock()
        continuation.resume()
      } else {
        enteredContinuation = continuation
        lock.unlock()
      }
    }
  }
}

/// Mirrors `SBOnboardingModel.resumeStepKey`, which is main-actor isolated and so
/// unreachable from XCTest's nonisolated `setUp`/`tearDown`.
private let resumeStepDefaultsKey = "sbOnboardingResumeStep"

/// Behavioral coverage for the live (Second Brain) onboarding permission flow.
///
/// Every test drives the production API through an injected seam and asserts an
/// outcome — no source-text inspection.
@MainActor
final class SBOnboardingPermissionFlowTests: XCTestCase {
  /// `SBOnboardingModel.appState` is `unowned`, so the test has to be the owner.
  private var retainedAppState: AppState?

  private func makeModel() -> SBOnboardingModel {
    let appState = AppState()
    retainedAppState = appState
    return SBOnboardingModel(appState: appState, chatProvider: ChatProvider(), onComplete: nil)
  }

  override func setUp() {
    super.setUp()
    UserDefaults.standard.removeObject(forKey: resumeStepDefaultsKey)
  }

  override func tearDown() {
    UserDefaults.standard.removeObject(forKey: resumeStepDefaultsKey)
    super.tearDown()
  }

  // MARK: - Defect 3/4: grants this process cannot use

  func testRelaunchIsOfferedOnlyForGrantsThisProcessCannotUse() {
    XCTAssertTrue(
      SBPermissionRelaunchGate.needsRelaunch(
        key: "screen_recording", screenRecordingNeedsRelaunch: true, systemAudioTapDenied: false),
      "a screen-recording grant that arrived after launch is dead until relaunch")
    XCTAssertFalse(
      SBPermissionRelaunchGate.needsRelaunch(
        key: "screen_recording", screenRecordingNeedsRelaunch: false, systemAudioTapDenied: true),
      "a grant that was already in place at launch must never re-offer the reopen")

    XCTAssertTrue(
      SBPermissionRelaunchGate.needsRelaunch(
        key: "system_audio", screenRecordingNeedsRelaunch: true, systemAudioTapDenied: true),
      "a tap refused behind a post-launch screen-recording grant fails identically on every retry")
    XCTAssertFalse(
      SBPermissionRelaunchGate.needsRelaunch(
        key: "system_audio", screenRecordingNeedsRelaunch: true, systemAudioTapDenied: false),
      "no tap has been refused yet — asking is still the right next move")
    XCTAssertFalse(
      SBPermissionRelaunchGate.needsRelaunch(
        key: "system_audio", screenRecordingNeedsRelaunch: false, systemAudioTapDenied: true),
      "a refused tap under a launch-time screen-recording grant is a real denial, not a relaunch")

    for key in ["microphone", "full_disk_access", "accessibility", "automation"] {
      XCTAssertFalse(
        SBPermissionRelaunchGate.needsRelaunch(
          key: key, screenRecordingNeedsRelaunch: true, systemAudioTapDenied: true),
        "\(key) applies to the running process the moment it is granted")
    }
  }

  func testScreenRecordingGrantNeedingRelaunchNeverAdvancesTheFlow() {
    let model = makeModel()
    model.step = .screen
    model.scrState = .on

    model.autoAdvanceIfCurrent("screen_recording", needsRelaunch: true)
    XCTAssertEqual(
      model.step, .screen,
      "advancing on a grant this process cannot use walks the user into a dead screen demo")

    model.autoAdvanceIfCurrent("screen_recording", needsRelaunch: false)
    XCTAssertNotEqual(model.step, .screen, "a usable grant still auto-advances")
    model.streamTask?.cancel()
  }

  func testAcceptingTheRelaunchPersistsTheResumeStepBeforeRestarting() {
    let model = makeModel()
    model.step = .screen
    var persistedWhenRestartFired: Int?

    let accepted = model.acceptPermissionRelaunch("screen_recording", needsRelaunch: true) {
      persistedWhenRestartFired = UserDefaults.standard.integer(
        forKey: SBOnboardingModel.resumeStepKey)
    }

    XCTAssertTrue(accepted)
    XCTAssertEqual(
      persistedWhenRestartFired, SBOnboardingModel.Step.files.rawValue,
      "the next step must already be persisted when the process is handed over, "
        + "or the relaunched app resumes on this row and re-offers the reopen forever")
  }

  func testRelaunchIsNotAcceptedWhenTheGrantAlreadyApplies() {
    let model = makeModel()
    model.step = .screen
    var restarted = false

    let accepted = model.acceptPermissionRelaunch("screen_recording", needsRelaunch: false) {
      restarted = true
    }

    XCTAssertFalse(accepted)
    XCTAssertFalse(restarted, "a usable grant must never restart the app")
    XCTAssertEqual(
      UserDefaults.standard.integer(forKey: SBOnboardingModel.resumeStepKey), 0,
      "declining to relaunch must not rewrite the resume step")
  }

  // MARK: - Defect 2/4: what the step's button can actually do

  func testWaitingRowStaysInteractiveAndUnusableGrantsOfferTheReopen() {
    XCTAssertEqual(
      SBOnboardingModel.permissionPrimaryAction(state: .ask, needsRelaunch: false), .allow)
    XCTAssertEqual(
      SBOnboardingModel.permissionPrimaryAction(state: .waiting, needsRelaunch: false), .recheck,
      "a waiting row must offer a re-check — a grant can land long after the poll gives up")
    XCTAssertEqual(
      SBOnboardingModel.permissionPrimaryAction(state: .on, needsRelaunch: false), .proceed)

    XCTAssertEqual(
      SBOnboardingModel.permissionPrimaryAction(state: .on, needsRelaunch: true), .reopen,
      "a granted-but-unusable permission must not offer Continue")
    XCTAssertEqual(
      SBOnboardingModel.permissionPrimaryAction(state: .ask, needsRelaunch: true), .reopen,
      "a system-audio row re-armed after a refused tap must not offer an Allow that fails identically")
    XCTAssertEqual(
      SBOnboardingModel.permissionPrimaryAction(state: .waiting, needsRelaunch: true), .reopen)
  }

  // MARK: - Defect 2: a grant that lands after the poll expired

  func testReactivationAdoptsAGrantThatLandedAfterThePollExpired() async {
    let model = makeModel()
    model.step = .mic
    model.micState = .ask  // the 20s poll already gave up

    await model.recheckPermission("microphone") { _ in
      model.appState.hasMicrophonePermission = true
    }

    XCTAssertEqual(model.micState, .on)
    XCTAssertNotEqual(model.step, .mic, "the adopted grant moves the flow on")
    model.streamTask?.cancel()
  }

  func testReactivationWithoutAGrantLeavesTheStepAlone() async {
    let model = makeModel()
    model.step = .mic
    model.micState = .waiting
    model.appState.hasMicrophonePermission = false

    await model.recheckPermission("microphone") { _ in }

    XCTAssertEqual(model.micState, .waiting)
    XCTAssertEqual(model.step, .mic)
  }

  func testAProbeThatFinishesAfterTheUserMovedOnNeverYanksTheFlowForward() async {
    let model = makeModel()
    model.step = .mic

    await model.recheckPermission("microphone") { _ in
      model.appState.hasMicrophonePermission = true
      model.step = .automation  // the user pressed Skip while the probe ran
    }

    XCTAssertEqual(
      model.step, .automation, "a late answer for an abandoned step must not advance the flow")
    XCTAssertEqual(model.micState, .ask, "an abandoned step must not adopt a late row result")
  }

  func testReactivationIgnoresStepsThatGateOnNoPermission() {
    let model = makeModel()
    model.step = .promise

    model.recheckActivePermission()

    XCTAssertEqual(model.step, .promise)
  }

  // MARK: - A stopped System Events is not an answer about the grant

  func testStatusReadStartsSystemEventsWhenTheTargetIsStopped() {
    var probes: [Bool] = []
    var launches = 0

    let status = SBAutomationConsent.currentSystemEventsPermission(
      determine: { askUserIfNeeded in
        probes.append(askUserIfNeeded)
        return probes.count == 1 ? -600 : noErr
      },
      launch: { launches += 1 })

    XCTAssertEqual(
      status, noErr,
      "a granted permission must not read as missing just because the target was idle")
    XCTAssertEqual(launches, 1)
    XCTAssertEqual(probes, [false, false], "a status read must never be allowed to prompt")
  }

  func testStatusReadDoesNotStartSystemEventsWhenTheAnswerIsAlreadyDeterminate() {
    for determinate in [noErr, OSStatus(-1743), OSStatus(-1744)] {
      var launches = 0

      let status = SBAutomationConsent.currentSystemEventsPermission(
        determine: { _ in determinate },
        launch: { launches += 1 })

      XCTAssertEqual(status, determinate)
      XCTAssertEqual(launches, 0, "TCC already answered; starting the target buys nothing")
    }
  }

  func testStatusReadStillReportsProcNotFoundWhenTheTargetWillNotStart() {
    let status = SBAutomationConsent.currentSystemEventsPermission(
      determine: { _ in -600 },
      launch: {})

    XCTAssertEqual(
      status, -600,
      "an unlaunchable target stays unknown, so the caller can preserve what it knows")
  }

  // MARK: - Defect 1/5: the automation request

  func testAutomationConsentRunsOffTheMainThreadAndAdoptsItsOwnAnswer() async {
    let model = makeModel()
    model.step = .automation
    model.appState.hasAutomationPermission = false
    let recorder = ProbeRecorder()

    let request = model.beginAutomationRequest(
      consent: {
        recorder.record(isMainThread: Thread.isMainThread)
        return SBAutomationConsent.Outcome(status: noErr)
      },
      openSettings: {})

    XCTAssertEqual(
      model.autoState, .waiting,
      "the row shows progress immediately — the request must not block the click")

    await request.value

    XCTAssertEqual(recorder.callCount, 1)
    XCTAssertFalse(
      recorder.ranOnMainThread,
      "the TCC request blocks until the modal is answered; on the main actor it freezes the window")
    XCTAssertTrue(
      model.appState.hasAutomationPermission,
      "the prompt's own answer is adopted directly, not read back one probe stale")
    XCTAssertEqual(model.autoState, .on)
  }

  func testDeniedAutomationOpensSettingsInsteadOfRearmingASpentPrompt() async {
    let model = makeModel()
    model.step = .automation
    model.appState.hasAutomationPermission = false
    var openedSettings = false

    await model.beginAutomationRequest(
      consent: { SBAutomationConsent.Outcome(status: -1743) },  // errAEEventNotPermitted
      openSettings: { openedSettings = true }
    ).value

    XCTAssertFalse(model.appState.hasAutomationPermission)
    XCTAssertEqual(model.autoState, .ask)
    XCTAssertTrue(
      openedSettings,
      "macOS never re-shows a spent Automation prompt, so Settings is the only route left")
  }

  func testUndeterminedTccRequestFallsBackToTheRawAppleEventSend() async {
    let model = makeModel()
    model.step = .automation
    model.appState.hasAutomationPermission = false

    await model.beginAutomationRequest(
      consent: {
        // The documented request path determined nothing (-1744 = no prompt
        // ever reached the user), so the raw Apple Event send took over and it
        // came back granted.
        SBAutomationConsent.Outcome(status: noErr, usedAppleEventFallback: true)
      },
      openSettings: {}
    ).value

    XCTAssertTrue(model.appState.hasAutomationPermission)
    XCTAssertEqual(model.autoState, .on)
  }

  func testAutomationRequestThatNeverReachedSystemEventsPreservesTheKnownGrant() async {
    let model = makeModel()
    model.step = .automation
    model.appState.hasAutomationPermission = true
    var openedSettings = false

    await model.beginAutomationRequest(
      consent: { SBAutomationConsent.Outcome(status: -600) },  // procNotFound: System Events never started
      openSettings: { openedSettings = true }
    ).value

    XCTAssertTrue(
      model.appState.hasAutomationPermission,
      "a target that never started is not evidence the permission was revoked")
    XCTAssertEqual(model.autoState, .on)
    XCTAssertFalse(openedSettings, "nobody was asked anything, so nothing was denied")
  }

  func testAbandonedAutomationRequestCannotOpenSettingsOrWriteItsRow() async {
    let model = makeModel()
    model.step = .automation
    let gate = BlockingProbeGate()
    var openedSettings = false

    let request = model.beginAutomationRequest(
      consent: {
        gate.waitUntilReleased()
        return SBAutomationConsent.Outcome(status: -1743)
      },
      openSettings: { openedSettings = true }
    )

    await gate.waitUntilEntered()
    model.step = .shortcutOpen
    gate.release.signal()
    await request.value

    XCTAssertFalse(openedSettings, "an abandoned permission step must not steal focus with Settings")
    XCTAssertEqual(model.autoState, .waiting, "an abandoned request must not write its late row result")
  }
}

/// The permission probes `AppState` owns, exercised through their injected seams.
@MainActor
final class AppStatePermissionProbeTests: XCTestCase {
  func testAccessibilitySettingsOpenPresentsConditionalDragGuidance() {
    var openedURL: URL?
    var presentedDragGuidance = false

    let opened = PermissionDragGuidance.openAccessibilitySettings(
      open: {
        openedURL = $0
        return true
      },
      suspendForPermissionPrompt: {},
      presentDragGuidance: { presentedDragGuidance = true })

    XCTAssertTrue(opened)
    XCTAssertEqual(
      openedURL?.absoluteString,
      "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")
    XCTAssertTrue(presentedDragGuidance)
  }

  func testAccessibilitySettingsFailureDoesNotPresentDragGuidance() {
    var presentedDragGuidance = false

    let opened = PermissionDragGuidance.openAccessibilitySettings(
      open: { _ in false },
      suspendForPermissionPrompt: {},
      presentDragGuidance: { presentedDragGuidance = true })

    XCTAssertFalse(opened)
    XCTAssertFalse(presentedDragGuidance)
  }

  // MARK: - Defect 5: automation status is readable by the caller that acts on it

  func testAutomationRefreshReturnsTheFreshStatusToItsCaller() async {
    let appState = AppState()
    appState.hasAutomationPermission = false

    let granted = await appState.refreshAutomationPermission(query: { noErr })

    XCTAssertTrue(granted, "the caller must be able to act on the answer it awaited")
    XCTAssertTrue(appState.hasAutomationPermission)
    XCTAssertEqual(appState.automationPermissionError, 0)
  }

  func testAutomationRefreshPreservesTheLastKnownGrantWhenSystemEventsIsStopped() async {
    let appState = AppState()
    appState.hasAutomationPermission = true

    let granted = await appState.refreshAutomationPermission(query: { -600 })

    XCTAssertTrue(granted)
    XCTAssertTrue(appState.hasAutomationPermission)
    XCTAssertEqual(appState.automationPermissionError, -600)
  }

  func testAutomationQueryRunsOffTheMainThread() async {
    let appState = AppState()
    let recorder = ProbeRecorder()

    await appState.refreshAutomationPermission(query: {
      recorder.record(isMainThread: Thread.isMainThread)
      return noErr
    })

    XCTAssertFalse(recorder.ranOnMainThread)
  }

  /// The passive probe is launch-capable since it learned to start System
  /// Events: it can wait on LaunchServices for up to ~5s. `ChatToolExecutor`
  /// is `@MainActor`, so a synchronous call there freezes the chat window.
  /// The check-status tool must route the probe through `Task.detached`, the
  /// same rule `AppState.refreshAutomationPermission` already follows.
  func testChatPermissionStatusProbeNeverRunsOnTheMainActor() throws {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent().deletingLastPathComponent()
      .appendingPathComponent("Sources/Providers/ChatToolExecutor.swift")
    // omi-test-quality: source-inspection -- static contract: the isolation boundary is not hermetically observable
    let src = try String(contentsOf: url, encoding: .utf8)

    guard
      let fn = src.range(of: "private static func currentPermissionStatuses("),
      let end = src.range(of: "\n  }", range: fn.upperBound..<src.endIndex)?.lowerBound
    else { return XCTFail("currentPermissionStatuses must exist") }
    let body = String(src[fn.upperBound..<end])
    guard
      let detached = body.range(of: "await Task.detached(priority: .userInitiated) {")?
        .upperBound
    else {
      return XCTFail(
        "currentPermissionStatuses is @MainActor-isolated; the launch-capable probe must run via Task.detached")
    }
    XCTAssertNil(
      body.range(of: "AppState.queryAutomationPermissionStatus()", range: body.startIndex..<detached),
      "the launch-capable probe must not be called synchronously inside the @MainActor tool")
    let windowEnd = body.index(detached, offsetBy: 200, limitedBy: body.endIndex) ?? body.endIndex
    XCTAssertNotNil(
      body.range(of: "AppState.queryAutomationPermissionStatus()", range: detached..<windowEnd),
      "the automation probe must run inside the detached task")
  }

  /// The reported bug: Automation on in System Settings, "Not Granted" on the
  /// Permissions page, on every refresh, for the whole session. System Events
  /// had exited, so every probe answered `-600`, which preserves the previous
  /// value — and from a cold launch that value is the `false` default.
  func testStoppedSystemEventsThatCanBeStartedResolvesTheColdLaunchDefault() async {
    let appState = AppState()
    appState.hasAutomationPermission = false
    let statuses = StatusSequence([-600, noErr])

    let granted = await appState.refreshAutomationPermission(query: {
      SBAutomationConsent.currentSystemEventsPermission(
        determine: { _ in statuses.next() },
        launch: {})
    })

    XCTAssertTrue(granted, "a grant the user holds must not read as missing on an idle Mac")
    XCTAssertTrue(appState.hasAutomationPermission)
    XCTAssertEqual(appState.automationPermissionError, 0)
    XCTAssertEqual(statuses.callCount, 2, "the second read is the one that can answer")
  }

  func testAutomationProcNotFoundPreservesTheLatestMainActorGrantAfterAwait() async {
    let appState = AppState()
    appState.hasAutomationPermission = false
    let gate = BlockingProbeGate()

    let refresh = Task {
      await appState.refreshAutomationPermission(query: {
        gate.waitUntilReleased()
        return -600
      })
    }

    await gate.waitUntilEntered()
    appState.hasAutomationPermission = true
    gate.release.signal()

    let granted = await refresh.value
    XCTAssertTrue(granted, "-600 must merge with the current grant, not the pre-await snapshot")
    XCTAssertTrue(appState.hasAutomationPermission)
    XCTAssertEqual(appState.automationPermissionError, -600)
  }

  // MARK: - Defect 6: expensive probes leave the main actor

  func testFullDiskAccessProbeRunsOffTheMainThreadAndPublishesItsResult() async {
    let appState = AppState()
    appState.hasFullDiskAccess = false
    let recorder = ProbeRecorder()

    let granted = await appState.refreshFullDiskAccess(probe: {
      recorder.record(isMainThread: Thread.isMainThread)
      return true
    })

    XCTAssertTrue(granted)
    XCTAssertTrue(appState.hasFullDiskAccess)
    XCTAssertFalse(
      recorder.ranOnMainThread,
      "contentsOfDirectory on a TCC-protected path is a synchronous tccd round trip")
  }

  func testAccessibilityProbeRunsOffTheMainThreadAndPublishesItsProjection() async {
    let appState = AppState()
    appState.hasAccessibilityPermission = false
    appState.isAccessibilityBroken = false
    let recorder = ProbeRecorder()

    await appState.refreshAccessibilityPermission(probe: {
      recorder.record(isMainThread: Thread.isMainThread)
      return AccessibilityProbeSignals(tccTrusted: true, axProbe: .failing)
    })

    XCTAssertTrue(appState.hasAccessibilityPermission)
    XCTAssertTrue(appState.isAccessibilityBroken, "TCC says yes but real AX calls fail")
    XCTAssertFalse(
      recorder.ranOnMainThread,
      "AXUIElementCopyAttributeValue and CGEvent.tapCreate are cross-process calls")
  }

  func testAccessibilityProjectionCoversEveryProbeOutcome() {
    // TCC trusted is authoritative; only a definitively failing AX call makes it "broken".
    var projection = AppState.accessibilityProjection(
      AccessibilityProbeSignals(tccTrusted: true, axProbe: .working))
    XCTAssertTrue(projection.hasPermission)
    XCTAssertFalse(projection.isBroken)

    projection = AppState.accessibilityProjection(
      AccessibilityProbeSignals(tccTrusted: true, axProbe: .failing))
    XCTAssertTrue(projection.hasPermission)
    XCTAssertTrue(projection.isBroken, "TCC says yes and AX is refused — the stuck grant")

    // A probe that could not answer leaves the TCC verdict alone in both directions.
    projection = AppState.accessibilityProjection(
      AccessibilityProbeSignals(tccTrusted: true, axProbe: .indeterminate))
    XCTAssertTrue(projection.hasPermission)
    XCTAssertFalse(projection.isBroken, "unable to tell is not broken")

    // AXIsProcessTrusted() can be stale after an update or re-sign. A real AX call working
    // against another app is the only thing that overrides it.
    projection = AppState.accessibilityProjection(
      AccessibilityProbeSignals(tccTrusted: false, axProbe: .working))
    XCTAssertTrue(projection.hasPermission)
    XCTAssertFalse(projection.isBroken)

    projection = AppState.accessibilityProjection(
      AccessibilityProbeSignals(tccTrusted: false, axProbe: .failing))
    XCTAssertFalse(projection.hasPermission)
    XCTAssertFalse(projection.isBroken, "not granted is not the same as broken")
  }

  /// The regression this replaced. The projection used to grant the permission whenever a
  /// `CGEvent` tap could be created, and a listen-only session tap is satisfied by **Input
  /// Monitoring**, not Accessibility. On a machine with Input Monitoring granted and the
  /// Accessibility toggle visibly off, Omi displayed "Granted".
  ///
  /// There is no `eventTapWorks` signal any more, so the shape of this test is the assertion:
  /// with TCC false, nothing short of a working AX call may report a grant.
  func testUngrantedAccessibilityIsNeverReportedAsGranted() {
    for probe in [AccessibilityAXProbeResult.failing, .indeterminate] {
      let projection = AppState.accessibilityProjection(
        AccessibilityProbeSignals(tccTrusted: false, axProbe: probe))
      XCTAssertFalse(
        projection.hasPermission,
        "TCC says not trusted and AX did not work (\(probe.rawValue)) — this is not a grant")
    }
  }

  /// Probing our own process is what made the false positive flip to a clean "Granted" exactly
  /// when the user opened the Permissions page: a process can always read its own accessibility
  /// tree, permission or not, and Omi is frontmost while its own settings are on screen.
  func testProbeCandidatesNeverIncludeThisProcess() {
    let targets = AppState.accessibilityProbeTargets()
    let ownPID = ProcessInfo.processInfo.processIdentifier
    XCTAssertFalse(
      targets.candidates.contains { $0.processID == ownPID },
      "self-probe always succeeds and would manufacture a grant")
  }

  /// No candidate can answer, so the probe must not invent an answer.
  func testEmptyCandidateListIsIndeterminateNotWorking() {
    let targets = AccessibilityProbeTargets(
      candidates: [], frontmostName: "none", finderProcessID: nil)
    XCTAssertEqual(AppState.axProbeResult(targets: targets), .indeterminate)
  }

  func testFirstUnaskedScanAwaitsItsCurrentOffMainProbeBeforeSkipping() async {
    let appState = AppState()
    let model = SBOnboardingModel(appState: appState, chatProvider: ChatProvider(), onComplete: nil)
    var probedKeys: [String] = []

    let target = await model.firstUnaskedStepAwaitingCurrentProbes(from: .automation) { key in
      probedKeys.append(key)
      await Task.yield()
      // Each probe answers only its own permission, so a step is skipped only
      // after its own probe is awaited — the automation grant must not leak a
      // skip past the notifications step.
      switch key {
      case "automation": model.appState.hasAutomationPermission = true
      case "notifications": model.appState.hasNotificationPermission = true
      default: break
      }
    }

    XCTAssertEqual(probedKeys, ["automation", "notifications"])
    XCTAssertEqual(target, .shortcutOpen)
    XCTAssertEqual(model.autoState, .on)
    XCTAssertEqual(model.notifState, .on)
  }
}
