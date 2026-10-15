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
}

private actor ContextSwitchSpyAssistant: ProactiveAssistant {
  nonisolated let spyIdentifier: String
  var identifier: String { spyIdentifier }
  var displayName: String { "Context Switch Spy" }
  var isEnabled: Bool { true }
  var needsFrameDuringDelay: Bool { false }

  private var apps: [String] = []

  init(identifier: String) {
    self.spyIdentifier = identifier
  }

  func switchedApps() -> [String] { apps }

  func analyze(frame: CapturedFrame) async -> AssistantResult? { nil }
  func handleResult(
    _ result: AssistantResult, sendEvent: @escaping @Sendable (String, [String: Any]) -> Void
  ) async {}
  func onContextSwitch(departingFrame: CapturedFrame?, newApp: String, newWindowTitle: String?) async {
    apps.append(newApp)
  }
  func clearPendingWork() async {}
  func stop() async {}
}
