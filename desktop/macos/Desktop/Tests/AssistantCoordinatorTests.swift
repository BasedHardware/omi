import XCTest

@testable import Omi_Computer

final class AssistantCoordinatorTests: XCTestCase {
  /// Context switches must reach Focus, Memory and Task assistants after the
  /// context-bucket producer has been retired.
  @MainActor
  func testContextSwitchDispatchesToEveryAssistant() async {
    let spy = ContextSwitchSpyAssistant(identifier: "context-switch-spy-\(UUID().uuidString)")
    AssistantCoordinator.shared.register(spy)
    defer { AssistantCoordinator.shared.unregister(identifier: spy.spyIdentifier) }

    // register() stores the assistant from a MainActor task; yield until it is visible.
    for _ in 0..<1000 where AssistantCoordinator.shared.assistant(withIdentifier: spy.spyIdentifier) == nil {
      await Task.yield()
    }
    XCTAssertNotNil(AssistantCoordinator.shared.assistant(withIdentifier: spy.spyIdentifier))

    // First call primes the tracked context; the second is a real switch. The dispatch is
    // awaited inside checkContextSwitch, so by the time it returns the spy has heard it.
    _ = await AssistantCoordinator.shared.checkContextSwitch(
      newApp: "SpyBaselineApp", newWindowTitle: "baseline")
    _ = await AssistantCoordinator.shared.checkContextSwitch(
      newApp: "SpyTargetApp", newWindowTitle: "target")

    let apps = await spy.switchedApps()
    XCTAssertTrue(
      apps.contains("SpyTargetApp"),
      "context switches must deliver onContextSwitch to every registered assistant, got \(apps)")
  }

  @MainActor
  func testFocusCandidateRejectsExcludedAndPrivateWindows() {
    let app = "FocusLockExcluded-\(UUID().uuidString)"
    RewindSettings.shared.excludeApp(app)
    defer { RewindSettings.shared.includeApp(app) }
    AssistantCoordinator.shared.trackFrame(
      CapturedFrame(
        jpegData: Data(), appName: app, windowTitle: "Private note", frameNumber: 1))
    XCTAssertNil(AssistantCoordinator.shared.focusSourceCandidate())

    AssistantCoordinator.shared.trackFrame(
      CapturedFrame(
        jpegData: Data(), appName: "Google Chrome", windowTitle: "Incognito", frameNumber: 2))
    XCTAssertNil(AssistantCoordinator.shared.focusSourceCandidate())
  }

  @MainActor
  func testFocusCandidateRequiresLiveForegroundMatch() {
    AssistantCoordinator.shared.trackFrame(
      CapturedFrame(
        jpegData: Data(), appName: "Teams", windowTitle: "Planning", frameNumber: 3))
    XCTAssertNil(
      AssistantCoordinator.shared.focusSourceCandidate(
        liveWindow: ("Slack", "DM")))
    XCTAssertNil(
      AssistantCoordinator.shared.focusSourceCandidate(
        liveWindow: ("Teams", "Another meeting")))
    XCTAssertEqual(
      AssistantCoordinator.shared.focusSourceCandidate(
        liveWindow: ("Teams", "Planning"))?.appName, "Teams")
  }

  @MainActor
  func testFocusLockBlocksTaskAndSuggestionFramesButKeepsCapturingCurrentWindow() async throws {
    let task = ContextSwitchSpyAssistant(identifier: "task-focus-spy-\(UUID().uuidString)")
    let suggestion = ContextSwitchSpyAssistant(identifier: "suggestion-focus-spy-\(UUID().uuidString)")
    AssistantCoordinator.shared.register(task)
    AssistantCoordinator.shared.register(suggestion)
    defer {
      AssistantCoordinator.shared.unregister(identifier: task.spyIdentifier)
      AssistantCoordinator.shared.unregister(identifier: suggestion.spyIdentifier)
      _ = FocusLockController.shared.release()
    }
    for _ in 0..<1000
    where AssistantCoordinator.shared.assistant(withIdentifier: task.spyIdentifier) == nil
      || AssistantCoordinator.shared.assistant(withIdentifier: suggestion.spyIdentifier) == nil
    { await Task.yield() }
    XCTAssertNotNil(AssistantCoordinator.shared.assistant(withIdentifier: task.spyIdentifier))
    XCTAssertNotNil(AssistantCoordinator.shared.assistant(withIdentifier: suggestion.spyIdentifier))

    let source = try XCTUnwrap(FocusLockSource(appName: "Teams", windowTitle: "Planning"))
    _ = FocusLockController.shared.activate(source: source, duration: 15 * 60)
    let slack = CapturedFrame(jpegData: Data(), appName: "Slack", windowTitle: "DM", frameNumber: 1)
    AssistantCoordinator.shared.trackFrame(slack)
    AssistantCoordinator.shared.distributeFrame(slack)
    XCTAssertEqual(AssistantCoordinator.shared.focusSourceCandidate()?.appName, "Slack")
    let blockedTaskFrames = await task.analyzedApps()
    let blockedSuggestionFrames = await suggestion.analyzedApps()
    XCTAssertTrue(blockedTaskFrames.isEmpty)
    XCTAssertTrue(blockedSuggestionFrames.isEmpty)

    let teams = CapturedFrame(jpegData: Data(), appName: "Teams", windowTitle: "Planning", frameNumber: 2)
    AssistantCoordinator.shared.trackFrame(teams)
    AssistantCoordinator.shared.distributeFrame(teams)
    for _ in 0..<1000 {
      if await task.analyzedApps().count == 1, await suggestion.analyzedApps().count == 1 { break }
      await Task.yield()
    }
    let admittedTaskFrames = await task.analyzedApps()
    let admittedSuggestionFrames = await suggestion.analyzedApps()
    XCTAssertEqual(admittedTaskFrames, ["Teams"])
    XCTAssertEqual(admittedSuggestionFrames, ["Teams"])
  }
}

private actor ContextSwitchSpyAssistant: ProactiveAssistant {
  nonisolated let spyIdentifier: String
  var identifier: String { spyIdentifier }
  var displayName: String { "Context Switch Spy" }
  var isEnabled: Bool { true }
  var needsFrameDuringDelay: Bool { false }

  private var apps: [String] = []
  private var frames: [String] = []

  init(identifier: String) {
    self.spyIdentifier = identifier
  }

  func switchedApps() -> [String] { apps }
  func analyzedApps() -> [String] { frames }

  func analyze(frame: CapturedFrame) async -> AssistantResult? {
    frames.append(frame.appName)
    return nil
  }
  func handleResult(
    _ result: AssistantResult, sendEvent: @escaping @Sendable (String, [String: Any]) -> Void
  ) async {}
  func onContextSwitch(departingFrame: CapturedFrame?, newApp: String, newWindowTitle: String?) async {
    apps.append(newApp)
  }
  func clearPendingWork() async {}
  func stop() async {}
}
