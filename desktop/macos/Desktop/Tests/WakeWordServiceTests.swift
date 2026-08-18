import XCTest

@testable import Omi_Computer

@MainActor
final class WakeWordServiceTests: XCTestCase {
  private let enabledKey = "wakeWordEnabled"
  private let phraseKey = "wakeWordPhrase"
  private let cooldownKey = "wakeWordCooldown"

  private var service = WakeWordService()
  private var triggered: [String] = []
  private var clock: Double = 0

  override func setUp() {
    super.setUp()
    UserDefaults.standard.removeObject(forKey: enabledKey)
    UserDefaults.standard.removeObject(forKey: phraseKey)
    UserDefaults.standard.removeObject(forKey: cooldownKey)
    UserDefaults.standard.set(true, forKey: enabledKey)
    UserDefaults.standard.set("Omi", forKey: phraseKey)
    UserDefaults.standard.set(30.0, forKey: cooldownKey)
  }

  override func tearDown() {
    UserDefaults.standard.removeObject(forKey: enabledKey)
    UserDefaults.standard.removeObject(forKey: phraseKey)
    UserDefaults.standard.removeObject(forKey: cooldownKey)
    super.tearDown()
  }

  @MainActor
  private func configureService() {
    service = WakeWordService()
    triggered = []
    clock = 0
    service.now = { [weak self] in
      Date(timeIntervalSince1970: self?.clock ?? 0)
    }
    service.onTrigger = { [weak self] command in
      self?.triggered.append(command)
    }
  }

  private func userSegment(_ text: String, id: String? = nil) -> SpeakerSegment {
    SpeakerSegment(segmentId: id, speaker: 0, text: text, start: 0, end: 1, isUser: true)
  }

  func testDisabledSettingNeverTriggers() {
    configureService()
    UserDefaults.standard.set(false, forKey: enabledKey)
    service.observe(userSegment("Omi, let's order food", id: "a"), isConversationActive: false)
    XCTAssertTrue(triggered.isEmpty)
  }

  func testTriggersCommandWithoutWakeWord() {
    configureService()
    service.observe(userSegment("Omi, let's order food", id: "a"), isConversationActive: false)
    XCTAssertEqual(triggered, ["let's order food"])
  }

  func testBareWakeWordIgnored() {
    configureService()
    service.observe(userSegment("Omi", id: "a"), isConversationActive: false)
    XCTAssertTrue(triggered.isEmpty)
  }

  func testNonUserSegmentIgnored() {
    configureService()
    let segment = SpeakerSegment(
      segmentId: "a", speaker: 1, text: "Omi, let's order food", start: 0, end: 1, isUser: false)
    service.observe(segment, isConversationActive: false)
    XCTAssertTrue(triggered.isEmpty)
  }

  func testBusyConversationSuppresses() {
    configureService()
    service.observe(userSegment("Omi, let's order food", id: "a"), isConversationActive: true)
    XCTAssertTrue(triggered.isEmpty)
  }

  func testDeduplicatesBySegmentID() {
    configureService()
    service.observe(userSegment("Omi, let's order food", id: "a"), isConversationActive: false)
    service.observe(userSegment("Omi, let's order food", id: "a"), isConversationActive: false)
    XCTAssertEqual(triggered.count, 1)
  }

  func testCooldownSuppressesRapidRepeats() {
    configureService()
    service.observe(userSegment("Omi, let's order food", id: "a"), isConversationActive: false)
    XCTAssertEqual(triggered.count, 1)
    clock = 10
    service.observe(userSegment("Omi, let's order tea", id: "b"), isConversationActive: false)
    XCTAssertEqual(triggered.count, 1)
    clock = 31
    service.observe(userSegment("Omi, let's order tea", id: "c"), isConversationActive: false)
    XCTAssertEqual(triggered.count, 2)
  }

  func testLastTriggeredCommandRecorded() {
    configureService()
    service.observe(userSegment("Omi, order pizza", id: "a"), isConversationActive: false)
    XCTAssertEqual(service.lastTriggeredCommand, "order pizza")
  }
}
