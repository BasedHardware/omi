import XCTest

@testable import Omi_Computer

final class AssistantCoordinatorTests: XCTestCase {
  func testContextTransitionQueueRetainsLatestAThenBThenCTransition() {
    let destinationA = ContextTransitionRequest(app: "A", windowTitle: "Document")
    let destinationB = ContextTransitionRequest(app: "B", windowTitle: "Document")
    let destinationC = ContextTransitionRequest(app: "C", windowTitle: "Inbox")
    var queue = ContextTransitionQueue()

    XCTAssertTrue(queue.begin(destinationA))
    XCTAssertFalse(queue.begin(destinationB))
    XCTAssertFalse(queue.begin(destinationC))
    XCTAssertEqual(queue.finish(destinationA), destinationC)

    // A fresh observation can begin before the scheduled drain task runs; the
    // retained C request must join that transition rather than be dropped.
    XCTAssertTrue(queue.begin(destinationB))
    XCTAssertFalse(queue.begin(destinationC))
    XCTAssertEqual(queue.finish(destinationB), destinationC)
    XCTAssertTrue(queue.begin(destinationC))
    XCTAssertNil(queue.finish(destinationC))
  }

  func testContextTransitionQueueCoalescesDuplicateDestination() {
    let destinationA = ContextTransitionRequest(app: "A", windowTitle: nil)
    let destinationB = ContextTransitionRequest(app: "B", windowTitle: nil)
    var queue = ContextTransitionQueue()

    XCTAssertTrue(queue.begin(destinationA))
    XCTAssertFalse(queue.begin(destinationB))
    XCTAssertFalse(queue.begin(destinationB))
    XCTAssertEqual(queue.finish(destinationA), destinationB)
    XCTAssertTrue(queue.begin(destinationB))
    XCTAssertNil(queue.finish(destinationB))
  }

  func testContextTransitionQueueRejectsStaleCompletion() {
    let destinationB = ContextTransitionRequest(app: "B", windowTitle: nil)
    let destinationC = ContextTransitionRequest(app: "C", windowTitle: nil)
    var queue = ContextTransitionQueue()

    XCTAssertTrue(queue.begin(destinationB))
    XCTAssertNil(queue.finish(destinationC))
    XCTAssertEqual(queue.inFlight, destinationB)
    XCTAssertEqual(queue.finish(destinationB), nil)
  }

  /// Regression (Aug 13–14 2026): the context-buckets rollout forwarded context switches
  /// only to the task assistant, silently starving the suggestion and memory assistants —
  /// focus nudges stopped for everyone in the flag cohort with no error logged anywhere.
  /// Buckets mode changes who writes bucket exits, never who hears switches.
  @MainActor
  func testBucketsModeDispatchesContextSwitchToEveryAssistant() async {
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
      newApp: "SpyBaselineApp", newWindowTitle: "baseline", bucketsEnabled: true)
    _ = await AssistantCoordinator.shared.checkContextSwitch(
      newApp: "SpyTargetApp", newWindowTitle: "target", bucketsEnabled: true)

    let apps = await spy.switchedApps()
    XCTAssertTrue(
      apps.contains("SpyTargetApp"),
      "buckets mode must deliver onContextSwitch to every registered assistant, got \(apps)")
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
