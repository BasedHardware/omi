import XCTest

@testable import Omi_Computer

/// Deterministic sleeper: parks every sleep call until the test resumes it.
private final class ManualSleeper: @unchecked Sendable {
  private var continuations: [CheckedContinuation<Void, Never>] = []
  private let lock = NSLock()

  var pendingCount: Int {
    lock.lock()
    defer { lock.unlock() }
    return continuations.count
  }

  func sleep(_: TimeInterval) async {
    await withCheckedContinuation { continuation in
      lock.lock()
      continuations.append(continuation)
      lock.unlock()
    }
  }

  func resumeAll() {
    lock.lock()
    let pending = continuations
    continuations = []
    lock.unlock()
    pending.forEach { $0.resume() }
  }
}

@MainActor
final class NotchViewModelTests: XCTestCase {
  private var defaults = UserDefaults.standard
  private var suiteName = ""

  override func setUp() async throws {
    suiteName = "NotchViewModelTests-\(UUID().uuidString)"
    defaults = UserDefaults(suiteName: suiteName) ?? .standard
  }

  override func tearDown() async throws {
    defaults.removePersistentDomain(forName: suiteName)
  }

  private func makeModel(
    now: @escaping () -> Date = { Date(timeIntervalSinceReferenceDate: 0) },
    sleep: @escaping (TimeInterval) async -> Void = { _ in }
  ) -> NotchViewModel {
    NotchViewModel(
      displayID: 1,
      screenFrame: CGRect(x: 0, y: 0, width: 1512, height: 982),
      hasPhysicalNotch: true,
      closedNotchSize: CGSize(width: 266, height: 38),
      now: now,
      sleep: sleep,
      defaults: defaults
    )
  }

  private func waitUntil(_ condition: () -> Bool) async {
    for _ in 0..<1_000 where !condition() {
      await Task.yield()
    }
  }

  // MARK: - Open / close

  func testOpenDefaultsToChatTab() {
    let model = makeModel()
    model.selectedTab = .agents
    model.open()
    XCTAssertEqual(model.state, .open)
    XCTAssertEqual(model.selectedTab, .chat)
  }

  func testOpenWithExplicitTab() {
    let model = makeModel()
    model.open(tab: .agents)
    XCTAssertEqual(model.state, .open)
    XCTAssertEqual(model.selectedTab, .agents)
  }

  func testStateChangeCallbackFiresOnOpenAndClose() {
    let model = makeModel()
    var changes = 0
    model.onStateChange = { changes += 1 }
    model.open()
    model.close()
    XCTAssertEqual(changes, 2)
    // Redundant transitions must not re-fire.
    model.close()
    XCTAssertEqual(changes, 2)
  }

  // MARK: - Hover (voice-first: hover never opens)

  func testHoverNeverSchedulesAnOpen() async {
    let sleeper = ManualSleeper()
    let model = makeModel(sleep: { await sleeper.sleep($0) })
    model.hoverEntered()
    // No dwell task is scheduled and the closed notch never expands on hover.
    for _ in 0..<50 { await Task.yield() }
    XCTAssertEqual(sleeper.pendingCount, 0)
    XCTAssertEqual(model.state, .closed)
  }

  // MARK: - Response linger

  func testResponseLingerDismissesAfterHold() async {
    let sleeper = ManualSleeper()
    let model = makeModel(sleep: { await sleeper.sleep($0) })
    model.beginResponseLinger("You have three meetings today")
    XCTAssertEqual(model.responseLinger, "You have three meetings today")
    await waitUntil { sleeper.pendingCount == 1 }
    sleeper.resumeAll()
    await waitUntil { model.responseLinger == nil }
    XCTAssertNil(model.responseLinger)
  }

  func testHoverKeepsLingerUntilResumed() async {
    let sleeper = ManualSleeper()
    let model = makeModel(sleep: { await sleeper.sleep($0) })
    model.beginResponseLinger("reply")
    await waitUntil { sleeper.pendingCount == 1 }
    // Hovering cancels the pending dismiss; the reply stays.
    model.keepLinger()
    sleeper.resumeAll()
    for _ in 0..<50 { await Task.yield() }
    XCTAssertEqual(model.responseLinger, "reply")
    // Leaving reschedules the dismiss.
    model.resumeLinger()
    await waitUntil { sleeper.pendingCount == 1 }
    sleeper.resumeAll()
    await waitUntil { model.responseLinger == nil }
    XCTAssertNil(model.responseLinger)
  }

  func testEmptyReplyNeverLingers() {
    let model = makeModel()
    model.beginResponseLinger("")
    XCTAssertNil(model.responseLinger)
  }

  // MARK: - Auto-close grace

  func testCanAutoCloseHonorsGracePeriodAndHold() {
    var currentTime = Date(timeIntervalSinceReferenceDate: 0)
    let model = makeModel(now: { currentTime })
    XCTAssertFalse(model.canAutoClose, "closed panel never auto-closes")
    model.open()
    XCTAssertFalse(model.canAutoClose, "within the 0.6s post-open grace")
    currentTime = currentTime.addingTimeInterval(0.7)
    XCTAssertTrue(model.canAutoClose)
    model.holdOpen = true
    XCTAssertFalse(model.canAutoClose)
    model.holdOpen = false
    XCTAssertTrue(model.canAutoClose)
  }

  // MARK: - Dynamic height

  func testChatHeightClampsBetweenMinAndHalfScreen() {
    let model = makeModel()
    model.chatBodyHeight = 10
    XCTAssertEqual(model.openContentSize(for: .chat).height, model.chatMinHeight)
    model.chatBodyHeight = 10_000
    XCTAssertEqual(model.openContentSize(for: .chat).height, model.chatMaxHeight)
    XCTAssertEqual(model.chatMaxHeight, 982 * 0.5)
  }

  func testChatHeightPersistsAcrossInstances() {
    let model = makeModel()
    model.open()
    model.chatBodyHeight = 333
    model.close()
    let reborn = makeModel()
    XCTAssertEqual(reborn.chatBodyHeight, 333)
  }

  func testVoiceHeightClampsBetweenMinAndThirtyPercent() {
    let model = makeModel()
    // No measurement yet -> the compact voice minimum.
    XCTAssertEqual(model.voiceExpandedSize.height, model.voiceMinHeight)
    model.voiceBodyHeight = 10
    XCTAssertEqual(model.voiceExpandedSize.height, model.voiceMinHeight)
    model.voiceBodyHeight = 10_000
    // Voice caps at 30% of the screen (verbal — it must not dominate).
    XCTAssertEqual(model.voiceExpandedSize.height, model.voiceMaxHeight)
    XCTAssertEqual(model.voiceMaxHeight, 982 * 0.3, accuracy: 0.01)
  }

  func testVoiceHeightIsTransientAndNotPersisted() {
    let model = makeModel()
    model.voiceBodyHeight = 333
    model.close()
    let reborn = makeModel()
    XCTAssertNil(reborn.voiceBodyHeight)
  }

  // MARK: - Sizing authority

  func testSizeForPresentationMapping() {
    let model = makeModel()
    XCTAssertEqual(model.size(for: .idle), model.closedNotchSize)
    XCTAssertEqual(model.size(for: .open(.chat)), model.openContentSize(for: .chat))
    XCTAssertEqual(model.size(for: .open(.agents)), model.openContentSize(for: .agents))
    XCTAssertEqual(model.size(for: .listening), model.voiceExpandedSize)
    XCTAssertEqual(model.size(for: .responding), model.voiceExpandedSize)
    XCTAssertEqual(model.size(for: .thinking), model.thinkingSize)
    XCTAssertEqual(model.size(for: .hint("too short")), model.hintSize)
    XCTAssertEqual(model.size(for: .notification(UUID())), model.notificationSize)
  }

  func testWindowSizeCoversEveryPresentationPlusTray() {
    let model = makeModel()
    model.chatBodyHeight = 10_000
    model.voiceBodyHeight = 10_000
    let window = model.windowSize
    let presentations: [NotchPresentation] = [
      .idle, .open(.chat), .open(.agents), .listening, .thinking, .responding, .hint("x"),
      .notification(UUID()),
    ]
    for presentation in presentations {
      let size = model.size(for: presentation)
      XCTAssertGreaterThanOrEqual(window.width, size.width, "\(presentation)")
      XCTAssertGreaterThanOrEqual(
        window.height, size.height + NotchMetrics.trayReserve, "\(presentation)")
    }
  }

  func testVisibleRectAndTrayRectGeometry() {
    let model = makeModel()
    let closed = model.visibleRect(open: false)
    XCTAssertEqual(closed.midX, 1512 / 2, accuracy: 0.5)
    XCTAssertEqual(closed.maxY, 982)
    XCTAssertEqual(closed.size, model.closedNotchSize)

    model.open()
    let body = model.visibleRect(open: true)
    let tray = model.trayRect(open: true)
    XCTAssertEqual(tray.maxY, body.minY - NotchMetrics.trayGap)
    XCTAssertEqual(tray.width, body.width)
    XCTAssertEqual(tray.height, NotchMetrics.trayHeight)
  }
}
