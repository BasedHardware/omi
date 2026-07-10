import XCTest

@testable import Omi_Computer

@MainActor
final class RealtimeVoiceTurnOutboxTests: XCTestCase {
  private var defaults: UserDefaults!
  private var suiteName: String!
  private let defaultSurface = AgentSurfaceReference.mainChat(chatId: "default")

  override func setUp() {
    super.setUp()
    suiteName = "RealtimeVoiceTurnOutboxTests.\(UUID().uuidString)"
    defaults = UserDefaults(suiteName: suiteName)
    defaults.removePersistentDomain(forName: suiteName)
  }

  override func tearDown() {
    defaults.removePersistentDomain(forName: suiteName)
    defaults = nil
    suiteName = nil
    super.tearDown()
  }

  func testEntriesSurviveReloadAndLeaveOnlyAfterAcknowledgement() {
    let first = makeEntry(key: "turn-a", user: "one two three")
    let second = makeEntry(key: "turn-b", user: "A B C")
    var outbox = RealtimeVoiceTurnOutbox(defaults: defaults, storageKey: "outbox")

    outbox.enqueue(first)
    outbox.enqueue(second)
    outbox.enqueue(first)
    XCTAssertEqual(outbox.entries, [first, second])

    outbox = RealtimeVoiceTurnOutbox(defaults: defaults, storageKey: "outbox")
    XCTAssertEqual(outbox.entries, [first, second])
    outbox.acknowledge(idempotencyKey: "turn-a")
    XCTAssertEqual(outbox.entries, [second])
  }

  func testSeedContextKeepsRapidTurnsInOrderAndSpendsBudgetOnNewest() {
    let outbox = RealtimeVoiceTurnOutbox(defaults: defaults, storageKey: "seed")
    outbox.enqueue(makeEntry(key: "a", user: "OLDEST one two three"))
    outbox.enqueue(makeEntry(key: "b", user: "A B C", assistant: "partial", interrupted: true))
    outbox.enqueue(makeEntry(key: "c", user: "NEWEST R G B"))

    let full = outbox.seedContext(ownerID: "owner", surface: defaultSurface)
    XCTAssertLessThan(full.range(of: "OLDEST")!.lowerBound, full.range(of: "A B C")!.lowerBound)
    XCTAssertLessThan(full.range(of: "A B C")!.lowerBound, full.range(of: "NEWEST")!.lowerBound)
    XCTAssertTrue(full.contains("Omi (interrupted): partial"))

    let bounded = outbox.seedContext(
      ownerID: "owner", surface: defaultSurface, maxCharacters: 24)
    XCTAssertTrue(bounded.contains("NEWEST"))
    XCTAssertFalse(bounded.contains("OLDEST"))
  }

  func testOwnerSwitchQuarantinesOtherUsersEntriesAndKeepsIdenticalTurns() {
    let outbox = RealtimeVoiceTurnOutbox(defaults: defaults, storageKey: "owners")
    outbox.enqueue(makeEntry(key: "owner-a-turn", user: "private owner A text"))
    outbox.enqueue(
      .init(
        ownerID: "owner-b",
        surfaceKind: "main_chat",
        externalRefKind: "chat",
        externalRefID: "default",
        idempotencyKey: "owner-b-turn",
        userText: "owner B text",
        assistantText: "",
        interrupted: false,
        createdAtMs: 1_700_000_000_001))
    outbox.enqueue(
      .init(
        ownerID: "owner-b",
        surfaceKind: "main_chat",
        externalRefKind: "chat",
        externalRefID: "default",
        idempotencyKey: "owner-b-repeat",
        userText: "owner B text",
        assistantText: "",
        interrupted: false,
        createdAtMs: 1_700_000_000_002))

    XCTAssertEqual(
      outbox.entries(ownerID: "owner-b").map(\.idempotencyKey),
      ["owner-b-turn", "owner-b-repeat"])
    XCTAssertEqual(
      outbox.seedContext(ownerID: "owner-b", surface: defaultSurface)
        .components(separatedBy: "User: owner B text").count - 1,
      2)
    XCTAssertFalse(
      outbox.seedContext(ownerID: "owner-b", surface: defaultSurface).contains("owner A"))
  }

  func testSeedFiltersBySurfaceAndStableIdempotencyIdentity() {
    let outbox = RealtimeVoiceTurnOutbox(defaults: defaults, storageKey: "surface-identity")
    outbox.enqueue(makeEntry(key: "already-kernel", user: "same logical turn"))
    outbox.enqueue(makeEntry(key: "same-text-new-turn", user: "same logical turn"))
    outbox.enqueue(
      .init(
        ownerID: "owner",
        surfaceKind: "main_chat",
        externalRefKind: "chat",
        externalRefID: "other-chat",
        idempotencyKey: "other-surface",
        userText: "private other chat",
        assistantText: "",
        interrupted: false,
        createdAtMs: 1_700_000_000_003))

    let seed = outbox.seedContext(
      ownerID: "owner",
      surface: defaultSurface,
      excludingIdempotencyKeys: ["already-kernel"])
    XCTAssertEqual(seed, "User: same logical turn")
    XCTAssertFalse(seed.contains("private other chat"))
  }

  private func makeEntry(
    key: String,
    user: String,
    assistant: String = "",
    interrupted: Bool = false
  ) -> RealtimeVoiceTurnOutboxEntry {
    .init(
      ownerID: "owner",
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefID: "default",
      idempotencyKey: key,
      userText: user,
      assistantText: assistant,
      interrupted: interrupted,
      createdAtMs: 1_700_000_000_000)
  }
}
