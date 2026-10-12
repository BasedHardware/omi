import XCTest

@testable import Omi_Computer

/// The app-scheme item-link contract shared with mobile and web:
/// `<scheme>://items?conversation=a&task=b&memory=c` (URL order is display
/// order, max 10, unknown keys ignored) plus the singular
/// `<scheme>://<kind>/<id>` links.
final class ItemLinkRouteTests: XCTestCase {
  private func parse(_ string: String) -> ItemLinkRoute? {
    guard let url = URL(string: string) else {
      XCTFail("unparseable test URL \(string)")
      return nil
    }
    return ItemLinkParser.parse(url)
  }

  private func ref(_ kind: ItemLinkKind, _ id: String) -> ItemLinkReference {
    ItemLinkReference(kind: kind, id: id)
  }

  // MARK: - /items

  func testItemsKeepURLOrderAcrossKinds() {
    XCTAssertEqual(
      parse("omi-computer://items?task=t1&conversation=c1&memory=m1&task=t2"),
      .list([ref(.task, "t1"), ref(.conversation, "c1"), ref(.memory, "m1"), ref(.task, "t2")]))
  }

  func testItemsParseUnderEveryBundleScheme() {
    for scheme in ["omi-computer", "omi-computer-dev", "omi-omi-msg-list"] {
      XCTAssertEqual(
        parse("\(scheme)://items?conversation=c1&memory=m1"), .list([ref(.conversation, "c1"), ref(.memory, "m1")]))
    }
  }

  func testUnknownKeysAreIgnoredWithoutUsingASlot() {
    var query = (0..<10).map { "conversation=c\($0)" }
    query.insert("title=Secret", at: 0)
    query.insert("goal=g1", at: 3)
    let route = parse("omi-computer://items?" + query.joined(separator: "&"))
    XCTAssertEqual(route, .list((0..<10).map { ref(.conversation, "c\($0)") }))
  }

  func testItemsAreCappedAtTen() {
    let query = (0..<14).map { "task=t\($0)" }.joined(separator: "&")
    guard case .list(let refs) = parse("omi-computer://items?\(query)") else {
      return XCTFail("expected a list route")
    }
    XCTAssertEqual(refs.count, ItemLinkParser.maxItems)
    XCTAssertEqual(refs.first, ref(.task, "t0"))
    XCTAssertEqual(refs.last, ref(.task, "t9"))
  }

  func testDuplicateItemsCollapseToTheFirstOccurrence() {
    XCTAssertEqual(
      parse("omi-computer://items?task=t1&memory=m1&task=t1"),
      .list([ref(.task, "t1"), ref(.memory, "m1")]))
  }

  func testPercentEncodedIdsAreDecoded() {
    XCTAssertEqual(parse("omi-computer://items?memory=abc%2D123%5Fz"), .list([ref(.memory, "abc-123_z")]))
  }

  /// Ids become authenticated API path segments; an encoded separator or
  /// query must never pass as part of one.
  func testIdsThatCouldSteerAnAPIPathAreRejected() {
    for bad in ["a%2Fb", "..", "a%3Fb", "a%23b", "a%20b", "%2E%2E", "a%25b", String(repeating: "x", count: 129)] {
      XCTAssertEqual(parse("omi-computer://items?conversation=\(bad)"), .list([]), bad)
      XCTAssertNil(parse("omi-computer://conversation/\(bad)"), bad)
    }
  }

  func testEmptyOrMissingValuesAreSkipped() {
    XCTAssertEqual(parse("omi-computer://items?task=&memory&conversation=c1"), .list([ref(.conversation, "c1")]))
  }

  func testItemsWithNothingUsableIsAnEmptyList() {
    XCTAssertEqual(parse("omi-computer://items"), .list([]))
    XCTAssertEqual(parse("omi-computer://items?foo=bar"), .list([]))
    XCTAssertEqual(parse("omi-computer://items/?task=t1"), .list([ref(.task, "t1")]))
  }

  func testItemsWithAPathIsNotAnItemLink() {
    XCTAssertNil(parse("omi-computer://items/extra?task=t1"))
  }

  // MARK: - Singular links

  func testSingularLinksForEveryKind() {
    XCTAssertEqual(parse("omi-computer://conversation/c1"), .single(ref(.conversation, "c1")))
    XCTAssertEqual(parse("omi-computer://task/t1"), .single(ref(.task, "t1")))
    XCTAssertEqual(parse("omi-computer-dev://memory/m-1"), .single(ref(.memory, "m-1")))
    XCTAssertEqual(parse("omi-computer://task/t1/"), .single(ref(.task, "t1")))
  }

  func testSingularLinksNeedExactlyOneId() {
    XCTAssertNil(parse("omi-computer://conversation"))
    XCTAssertNil(parse("omi-computer://conversation/"))
    XCTAssertNil(parse("omi-computer://conversation/c1/extra"))
  }

  // MARK: - Routes that belong to someone else

  /// The auth callback and the other existing app-scheme URLs must keep
  /// reaching their own handlers.
  func testExistingAppSchemeURLsAreNotItemLinks() {
    XCTAssertNil(parse("omi-computer://auth/callback?code=abc&state=xyz"))
    XCTAssertNil(parse("omi-computer-dev://auth/callback?error=access_denied"))
    XCTAssertNil(parse("omi-computer://open"))
    XCTAssertNil(parse("omi-computer://onboarding/doors-complete"))
    XCTAssertNil(parse("omi-computer://goal/g1"))
  }
}

@MainActor
final class ItemLinkPresenterTests: XCTestCase {
  private final class Recorder {
    var openedConversations: [String] = []
    var openedTasks: [String] = []
    var openedMemories: [String] = []
    var reveals = 0
  }

  private func ref(_ kind: ItemLinkKind, _ id: String) -> ItemLinkReference {
    ItemLinkReference(kind: kind, id: id)
  }

  private func link(_ string: String) throws -> URL {
    try XCTUnwrap(URL(string: string))
  }

  private func makePresenter(
    conversations: Set<String> = [],
    tasks: Set<String> = [],
    memories: Set<String> = []
  ) -> (ItemLinkPresenter, Recorder) {
    let recorder = Recorder()
    let resolver = ItemLinkResolver(
      conversation: { id in conversations.contains(id) ? Self.conversation(id: id) : nil },
      task: { id in tasks.contains(id) ? Self.task(id: id) : nil },
      memories: { ids in ids.filter { memories.contains($0) }.map { Self.memory(id: $0) } }
    )
    let navigator = ItemLinkNavigator(
      openConversation: { recorder.openedConversations.append($0.id) },
      openTask: { recorder.openedTasks.append($0) },
      openMemory: { recorder.openedMemories.append($0) },
      revealMainWindow: { recorder.reveals += 1 }
    )
    return (ItemLinkPresenter(resolver: resolver, navigator: navigator), recorder)
  }

  func testNonItemURLsAreLeftForTheExistingHandlers() async throws {
    let (presenter, recorder) = makePresenter()
    XCTAssertFalse(try presenter.receive(link("omi-computer://auth/callback?code=abc&state=s")))
    XCTAssertEqual(presenter.pendingGeneration, 0)
    XCTAssertEqual(recorder.reveals, 0)
    await presenter.consumePending()
    XCTAssertNil(presenter.sheet)
  }

  func testListShowsRowsInURLOrderWithUnavailableRows() async throws {
    let (presenter, recorder) = makePresenter(conversations: ["c1"], tasks: ["t1"], memories: ["m1"])
    XCTAssertTrue(
      try presenter.receive(
        link("omi-computer://items?memory=m1&conversation=gone&task=t1&conversation=c1&memory=foreign")))
    XCTAssertEqual(recorder.reveals, 1)
    XCTAssertEqual(presenter.pendingGeneration, 1)

    await presenter.consumePending()

    let rows = try XCTUnwrap(presenter.sheet?.rows)
    XCTAssertEqual(
      rows.map(\.reference),
      [
        ref(.memory, "m1"), ref(.conversation, "gone"), ref(.task, "t1"), ref(.conversation, "c1"),
        ref(.memory, "foreign"),
      ])
    XCTAssertEqual(rows.map(\.isAvailable), [true, false, true, true, false])
    XCTAssertEqual(ItemLinkRowPresentation(row: rows[1]).title, "No longer available")
    XCTAssertEqual(ItemLinkRowPresentation(row: rows[1]).subtitle, "Conversation")
    XCTAssertTrue(recorder.openedConversations.isEmpty, "a list link must not open a detail on its own")
  }

  func testRowTapClosesTheSheetAndOpensTheDetail() async throws {
    let (presenter, recorder) = makePresenter(tasks: ["t1"], memories: ["m1"])
    try presenter.receive(link("omi-computer://items?task=t1&memory=m1&task=missing"))
    await presenter.consumePending()
    let rows = try XCTUnwrap(presenter.sheet?.rows)

    presenter.open(rows[2])
    XCTAssertNotNil(presenter.sheet, "an unavailable row is inert")
    XCTAssertTrue(recorder.openedTasks.isEmpty)

    presenter.open(rows[1])
    XCTAssertNil(presenter.sheet)
    XCTAssertEqual(recorder.openedMemories, ["m1"])
  }

  func testSingleAvailableItemOpensItsDetailDirectly() async throws {
    let (presenter, recorder) = makePresenter(conversations: ["c1"])
    try presenter.receive(link("omi-computer://conversation/c1"))
    await presenter.consumePending()
    XCTAssertNil(presenter.sheet)
    XCTAssertEqual(recorder.openedConversations, ["c1"])
    XCTAssertEqual(presenter.lastOpened, ref(.conversation, "c1"))
    XCTAssertEqual(presenter.settledCount, 1)
  }

  /// Automation drives links without taking focus; the URL handler always reveals.
  func testRevealIsSkippableForAutomationOnly() async throws {
    let (presenter, recorder) = makePresenter()
    try presenter.receive(link("omi-computer://task/t1"), revealsWindow: false)
    XCTAssertEqual(recorder.reveals, 0)
    try presenter.receive(link("omi-computer://task/t1"))
    XCTAssertEqual(recorder.reveals, 1)
  }

  func testOneItemListAlsoOpensDirectly() async throws {
    let (presenter, recorder) = makePresenter(tasks: ["t1"])
    try presenter.receive(link("omi-computer://items?task=t1&bogus=1"))
    await presenter.consumePending()
    XCTAssertNil(presenter.sheet)
    XCTAssertEqual(recorder.openedTasks, ["t1"])
  }

  func testSingleUnavailableItemExplainsInsteadOfOpening() async throws {
    let (presenter, recorder) = makePresenter()
    try presenter.receive(link("omi-computer://memory/m-gone"))
    await presenter.consumePending()
    let rows = try XCTUnwrap(presenter.sheet?.rows)
    XCTAssertEqual(rows.map(\.isAvailable), [false])
    XCTAssertTrue(recorder.openedMemories.isEmpty)
  }

  func testEmptyListShowsTheEmptyState() async throws {
    let (presenter, _) = makePresenter()
    try presenter.receive(link("omi-computer://items?unknown=1"))
    await presenter.consumePending()
    XCTAssertEqual(presenter.sheet?.rows?.count, 0)
  }

  func testLinkWaitsUntilTheShellConsumesIt() async throws {
    let (presenter, recorder) = makePresenter(conversations: ["c1"])
    try presenter.receive(link("omi-computer://conversation/c1"))
    XCTAssertTrue(recorder.openedConversations.isEmpty, "nothing resolves before the signed-in shell asks")
    await presenter.consumePending()
    await presenter.consumePending()
    XCTAssertEqual(recorder.openedConversations, ["c1"], "a link is consumed once")
  }

  func testNewestLinkWins() async throws {
    let (presenter, recorder) = makePresenter(tasks: ["t1", "t2"])
    try presenter.receive(link("omi-computer://task/t1"))
    try presenter.receive(link("omi-computer://task/t2"))
    XCTAssertEqual(presenter.pendingGeneration, 2)
    await presenter.consumePending()
    XCTAssertEqual(recorder.openedTasks, ["t2"])
  }

  // MARK: - Fixtures

  nonisolated private static func conversation(id: String) -> ServerConversation {
    ServerConversation(
      id: id,
      createdAt: Date(timeIntervalSince1970: 1_000),
      updatedAt: Date(timeIntervalSince1970: 1_001),
      startedAt: Date(timeIntervalSince1970: 1_000),
      finishedAt: Date(timeIntervalSince1970: 1_060),
      structured: Structured(
        title: "Meeting notes",
        overview: "Overview",
        emoji: "",
        category: "other",
        actionItems: [],
        events: []
      ),
      transcriptSegments: [],
      transcriptSegmentsIncluded: false,
      geolocation: nil,
      photos: [],
      appsResults: [],
      source: .desktop,
      language: "en",
      status: .completed,
      discarded: false,
      deleted: false,
      isLocked: false,
      starred: false,
      folderId: nil,
      inputDeviceName: nil,
      deferred: false
    )
  }

  nonisolated private static func task(id: String) -> TaskActionItem {
    TaskActionItem(
      id: id,
      description: "Follow up",
      completed: false,
      createdAt: Date(timeIntervalSince1970: 0))
  }

  nonisolated private static func memory(id: String) -> ServerMemory {
    ServerMemory(
      id: id,
      content: "Prefers morning meetings",
      category: .system,
      tier: .longTerm,
      tierIsExplicit: true,
      createdAt: Date(timeIntervalSince1970: 1),
      updatedAt: Date(timeIntervalSince1970: 1),
      conversationId: nil,
      reviewed: false,
      userReview: nil,
      visibility: "private",
      manuallyAdded: false,
      scoring: nil,
      source: "desktop",
      confidence: nil,
      sourceApp: nil,
      contextSummary: nil,
      isRead: false,
      isDismissed: false,
      tags: [],
      reasoning: nil,
      currentActivity: nil,
      inputDeviceName: nil,
      windowTitle: nil,
      headline: nil
    )
  }
}
