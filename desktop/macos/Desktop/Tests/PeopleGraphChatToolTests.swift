import XCTest

@testable import Omi_Computer

/// Covers the pure parts of the on-device people-graph chat tools: name matching
/// (including the "Sam must not resolve Samantha" rule that keeps two people from
/// being fused), the output byte budget the relay enforces, the search filters, and
/// the three distinguishable empty outcomes (graph missing / unreadable / no match).
final class PeopleGraphChatToolTests: XCTestCase {

  // MARK: - Fixtures

  /// A graph shaped like the real export: snake_case file-level keys, camelCase
  /// per-person keys, `community_meanings` explaining group names.
  private func fixtureJSON(people: [[String: Any]]) -> Data {
    let file: [String: Any] = [
      "generated_at": "2026-08-02T04:48:00Z",
      "stats": ["people": people.count, "featured": 1, "multichannel": 1, "channels": 3, "dropped": 0],
      "people": people,
      "community_meanings": [
        "Tahoe Trip 2024": "weekend ski crew — mostly SF friends you travel with once a year"
      ],
      "network_insights": ["Most of your messaging volume sits in two clusters."],
    ]
    return try! JSONSerialization.data(withJSONObject: file)
  }

  private func person(
    id: String,
    name: String,
    aliases: [String] = [],
    contactName: String? = nil,
    relationship: String = "friend",
    role: String? = nil,
    closeness: Double = 100,
    lastTouchDate: String? = "2026-07-30T10:00:00Z",
    affiliations: [[String: Any]] = [],
    groups: [[String: Any]] = [],
    connections: [[String: Any]] = [],
    facts: [String] = [],
    openThreads: [String] = [],
    activities: [String] = [],
    who: String = "",
    now: String = "",
    overall: String = ""
  ) -> [String: Any] {
    // The channel's `last` tracks `lastTouchDate` because the staleness filter
    // falls back to channel dates when `lastTouch` is absent.
    var channel: [String: Any] = ["key": "imessage", "label": "iMessage", "count": 412]
    if let lastTouchDate { channel["last"] = lastTouchDate }
    var row: [String: Any] = [
      "id": id,
      "name": name,
      "relationship": relationship,
      "who": who,
      "now": now,
      "overall": overall,
      "closeness": closeness,
      "aliases": aliases,
      "channels": [channel],
      "facts": facts,
      "openThreads": openThreads,
      "activities": activities,
      "affiliations": affiliations,
      "groups": groups,
      "connections": connections,
      "history_grounded": true,
    ]
    if let contactName { row["contactName"] = contactName }
    if let role { row["role"] = role }
    if let lastTouchDate {
      row["lastTouch"] = ["channel": "iMessage", "date": lastTouchDate]
    }
    return row
  }

  private func loadSnapshot(_ data: Data) throws -> PeopleGraphSnapshot {
    guard case .loaded(let snapshot) = PeopleGraphSnapshotLoader.load(data: data) else {
      throw XCTSkip("fixture did not decode")
    }
    return snapshot
  }

  /// Sam Altman (dense), Samantha Lee (the near-miss), and two Priyas (ambiguous).
  private func standardSnapshot() throws -> PeopleGraphSnapshot {
    try loadSnapshot(
      fixtureJSON(people: [
        person(
          id: "sam-altman",
          name: "Sam Altman",
          aliases: ["sama"],
          contactName: "Sam A (work)",
          relationship: "colleague",
          role: "product lead at Figma",
          closeness: 900,
          affiliations: [["name": "Figma", "type": "company", "confidence": 0.9, "via": ["group chat: Figma Design"]]],
          groups: [["name": "Tahoe Trip 2024", "category": "group chat"]],
          connections: [
            [
              "id": "priya-raman", "name": "Priya Raman", "weight": 3.5,
              "sources": ["Tahoe Trip 2024"],
              "context": ["Tahoe Trip 2024"],
              "how": "share frequent 1:1 messaging plus one group chat",
              "type": "strong",
            ]
          ],
          facts: ["Runs the design review on Thursdays."],
          openThreads: ["Owes you the Q3 roadmap doc."],
          who: "Product lead you met through the Figma design community."),
        person(id: "samantha-lee", name: "Samantha Lee", closeness: 500),
        person(id: "priya-raman", name: "Priya Raman", closeness: 400),
        person(id: "priya-nair", name: "Priya Nair", closeness: 300),
      ]))
  }

  // MARK: - Name matching

  func testMatchesExactFullNameCaseInsensitivelyAndByAliasContactNameAndID() throws {
    let snapshot = try standardSnapshot()
    let people = snapshot.people

    for query in ["Sam Altman", "sam altman", "  SAM   ALTMAN ", "sama", "Sam A (work)", "sam-altman"] {
      let hits = PeopleNameMatcher.matches(query: query, in: people)
      XCTAssertEqual(hits.map(\.id), ["sam-altman"], "query \"\(query)\" should resolve Sam Altman")
    }
  }

  func testMatchesFirstNameAndPartialTrailingToken() throws {
    let people = try standardSnapshot().people
    XCTAssertEqual(PeopleNameMatcher.matches(query: "Sam", in: people).map(\.id), ["sam-altman"])
    XCTAssertEqual(PeopleNameMatcher.matches(query: "Altman", in: people).map(\.id), ["sam-altman"])
    XCTAssertEqual(PeopleNameMatcher.matches(query: "sam alt", in: people).map(\.id), ["sam-altman"])
    XCTAssertEqual(
      PeopleNameMatcher.tier(query: "sam alt", person: people[0]), .tokenPrefix,
      "a partial trailing token is the weakest accepted tier")
  }

  /// The rule that keeps two different people from being fused by a shared prefix.
  func testShortFirstNameDoesNotMatchALongerName() throws {
    let people = try standardSnapshot().people
    let samantha = try XCTUnwrap(people.first { $0.id == "samantha-lee" })
    XCTAssertNil(PeopleNameMatcher.tier(query: "Sam", person: samantha))
    XCTAssertFalse(
      PeopleNameMatcher.matches(query: "Sam", in: people).contains { $0.id == "samantha-lee" })
    // The full name still resolves her.
    XCTAssertEqual(
      PeopleNameMatcher.matches(query: "Samantha", in: people).map(\.id), ["samantha-lee"])
  }

  func testAmbiguousFirstNameReturnsEveryEqualMatchAndTheToolRefusesToPick() throws {
    let snapshot = try standardSnapshot()
    let hits = PeopleNameMatcher.matches(query: "Priya", in: snapshot.people)
    XCTAssertEqual(hits.map(\.id), ["priya-raman", "priya-nair"], "closest first")

    let rendered = PeopleGraphChatTool.renderPerson(
      name: "Priya", snapshot: snapshot, now: Date(timeIntervalSince1970: 1_785_000_000))
    XCTAssertTrue(rendered.hasPrefix("AMBIGUOUS"))
    XCTAssertTrue(rendered.contains("Priya Raman"))
    XCTAssertTrue(rendered.contains("Priya Nair"))
  }

  func testDiacriticsAndPunctuationAreIgnored() throws {
    let snapshot = try loadSnapshot(
      fixtureJSON(people: [person(id: "jose-garcia", name: "José García")]))
    XCTAssertEqual(
      PeopleNameMatcher.matches(query: "jose garcia", in: snapshot.people).map(\.id),
      ["jose-garcia"])
  }

  // MARK: - Substance of the answer

  func testPersonAnswerCarriesRelationshipRoleGroupsAffiliationsAndConnectionReasons() throws {
    let snapshot = try standardSnapshot()
    let rendered = PeopleGraphChatTool.renderPerson(
      name: "Sam Altman", snapshot: snapshot, now: Date(timeIntervalSince1970: 1_785_000_000))

    XCTAssertTrue(rendered.contains("Sam Altman — colleague · product lead at Figma"))
    XCTAssertTrue(rendered.contains("id=sam-altman"))
    XCTAssertTrue(rendered.contains("iMessage"))
    XCTAssertTrue(rendered.contains("Runs the design review on Thursdays."))
    XCTAssertTrue(rendered.contains("Owes you the Q3 roadmap doc."))
    XCTAssertTrue(rendered.contains("Figma (company)"))
    // The group is explained in plain English from community_meanings.
    XCTAssertTrue(rendered.contains("Tahoe Trip 2024 (group chat) — weekend ski crew"))
    // The connection carries the reason for the edge, not just the name.
    XCTAssertTrue(
      rendered.contains("Priya Raman — share frequent 1:1 messaging plus one group chat"))
    XCTAssertTrue(rendered.contains("[via Tahoe Trip 2024]"))
  }

  // MARK: - Output budget

  /// The densest person the real graph can produce must still fit the relay's
  /// 8 KiB cap *after* JSON wrapping, because oversize results are discarded.
  func testDensePersonStaysInsideTheRelayByteBudget() throws {
    let filler = { (count: Int, seed: String) -> String in
      String(String(repeating: "\(seed) detail ", count: count / 8 + 1).prefix(count))
    }
    let dense = person(
      id: "dense-person",
      name: "Dense Person",
      aliases: (0..<8).map { "alias\($0)" },
      contactName: "Dense Person (mobile)",
      relationship: "close friend and former colleague",
      role: filler(60, "role"),
      closeness: 999,
      affiliations: (0..<6).map {
        ["name": "Org \($0)", "type": "company", "confidence": 0.8, "via": [filler(62, "via")]]
      },
      groups: (0..<8).map { ["name": "Group number \($0)", "category": "group chat"] },
      connections: (0..<6).map {
        [
          "id": "peer-\($0)", "name": "Peer Number \($0)", "weight": 2.0,
          "sources": [filler(37, "src"), filler(37, "src2")],
          "context": [filler(37, "ctx"), filler(37, "ctx2")],
          "how": filler(134, "how"),
          "type": "strong",
        ]
      },
      facts: (0..<7).map { filler(350, "fact\($0)") },
      openThreads: (0..<6).map { filler(179, "thread\($0)") },
      activities: (0..<5).map { filler(116, "activity\($0)") },
      who: filler(284, "who"),
      now: filler(436, "now"),
      overall: filler(617, "overall"))

    let snapshot = try loadSnapshot(fixtureJSON(people: [dense]))
    let rendered = PeopleGraphChatTool.renderPerson(
      name: "Dense Person", snapshot: snapshot, now: Date(timeIntervalSince1970: 1_785_000_000))

    XCTAssertLessThanOrEqual(
      rendered.utf8.count, PeopleGraphOutputBudget.defaultBytes,
      "person output must stay inside its own budget")

    // Model the relay envelope `agent/src/runtime/relay-tool-result.ts` wraps
    // results in; anything over MAX_RELAY_TOOL_RESULT_BYTES (8 KiB) is dropped.
    let wrapped = try JSONSerialization.data(
      withJSONObject: [
        "text": rendered,
        "ok": true,
        "toolResultEnvelope": [
          "status": "succeeded",
          "truncated": false,
          "originalBytes": rendered.utf8.count,
          "projectedBytes": rendered.utf8.count,
          "fullOutputRef": NSNull(),
          "provenance": [
            "invocationId": UUID().uuidString,
            "runId": UUID().uuidString,
            "attemptId": UUID().uuidString,
            "toolName": "get_person",
          ],
        ],
      ])
    XCTAssertLessThanOrEqual(wrapped.count, 8 * 1024, "JSON-wrapped result must survive the relay")
  }

  func testSearchOutputStaysInsideTheBudgetAtTheMaximumLimit() throws {
    let many = (0..<PeopleGraphSearchRequest.maxLimit + 10).map {
      person(
        id: "person-\($0)", name: "Person Number \($0)",
        relationship: "long-standing professional acquaintance",
        role: "senior staff engineer, platform infrastructure",
        closeness: Double(1000 - $0))
    }
    let snapshot = try loadSnapshot(fixtureJSON(people: many))
    let rendered = PeopleGraphChatTool.renderSearch(
      request: PeopleGraphSearchRequest(limit: 999),
      snapshot: snapshot,
      now: Date(timeIntervalSince1970: 1_785_000_000))

    XCTAssertTrue(rendered.contains("showing 25 of 35"), "limit is clamped to maxLimit")
    XCTAssertLessThanOrEqual(rendered.utf8.count, PeopleGraphOutputBudget.defaultBytes)
  }

  func testBudgetDropsTrailingSectionsAndSaysSoInsteadOfOverflowing() throws {
    let snapshot = try standardSnapshot()
    let tiny = PeopleGraphChatTool.renderPerson(
      name: "Sam Altman", snapshot: snapshot,
      now: Date(timeIntervalSince1970: 1_785_000_000), budgetBytes: 400)
    XCTAssertLessThanOrEqual(tiny.utf8.count, 400)
    XCTAssertTrue(tiny.contains("omitted to stay inside the tool output budget"))
    XCTAssertTrue(tiny.hasPrefix("Sam Altman"), "the headline always survives")
  }

  // MARK: - Honest emptiness

  func testMissingUnreadableAndNotFoundAreDistinguishable() throws {
    let absent = FileManager.default.temporaryDirectory
      .appendingPathComponent("PeopleGraphChatToolTests-\(UUID().uuidString)")
      .appendingPathComponent("people_intelligence.json")
    guard case .missing = PeopleGraphSnapshotLoader.load(fileURL: absent) else {
      return XCTFail("an absent file must report .missing")
    }
    guard case .unreadable = PeopleGraphSnapshotLoader.load(data: Data("not json".utf8)) else {
      return XCTFail("undecodable bytes must report .unreadable, not .missing")
    }

    let snapshot = try standardSnapshot()
    let notFound = PeopleGraphChatTool.renderPerson(
      name: "Nobody Here", snapshot: snapshot, now: Date(timeIntervalSince1970: 1_785_000_000))

    XCTAssertTrue(notFound.hasPrefix("NO PERSON NAMED"))
    XCTAssertTrue(notFound.contains("4 people"), "a miss still reports the graph size")
    XCTAssertTrue(PeopleGraphChatTool.graphMissingMessage.contains("NOT BUILT"))
    XCTAssertNotEqual(notFound, PeopleGraphChatTool.graphMissingMessage)
    XCTAssertFalse(
      notFound.contains("NOT BUILT"), "a miss must never read as an unbuilt graph")
  }

  func testNotFoundOffersCloseNamesWithoutResolvingThem() throws {
    let snapshot = try standardSnapshot()
    let rendered = PeopleGraphChatTool.renderPerson(
      name: "Saman", snapshot: snapshot, now: Date(timeIntervalSince1970: 1_785_000_000))
    XCTAssertTrue(rendered.hasPrefix("NO PERSON NAMED"))
    XCTAssertTrue(rendered.contains("Samantha Lee"), "suggested, not resolved")
  }

  func testEmptyGraphIsReportedSeparatelyFromAMissingOne() throws {
    let snapshot = try loadSnapshot(fixtureJSON(people: []))
    let rendered = PeopleGraphChatTool.renderPerson(
      name: "Anyone", snapshot: snapshot, now: Date(timeIntervalSince1970: 1_785_000_000))
    XCTAssertTrue(rendered.hasPrefix("PEOPLE GRAPH EMPTY"))
    XCTAssertNotEqual(rendered, PeopleGraphChatTool.graphMissingMessage)
  }

  // MARK: - Listing / searching

  func testAffiliationFilterFindsWhoTheUserKnowsAtACompany() throws {
    let snapshot = try standardSnapshot()
    let result = PeopleGraphSearch.run(
      PeopleGraphSearchRequest(affiliation: "figma"),
      snapshot: snapshot,
      now: Date(timeIntervalSince1970: 1_785_000_000))
    XCTAssertEqual(result.people.map(\.id), ["sam-altman"])
    XCTAssertEqual(result.totalPeople, 4)
  }

  func testQuietForDaysFindsStaleContactsColdestFirst() throws {
    let snapshot = try loadSnapshot(
      fixtureJSON(people: [
        person(id: "recent", name: "Recent Person", closeness: 900, lastTouchDate: "2026-07-30T10:00:00Z"),
        person(id: "stale", name: "Stale Person", closeness: 800, lastTouchDate: "2025-09-01T10:00:00Z"),
        person(id: "never", name: "Never Person", closeness: 700, lastTouchDate: nil),
      ]))
    // 2026-08-02T00:00:00Z
    let now = Date(timeIntervalSince1970: 1_785_628_800)
    let result = PeopleGraphSearch.run(
      PeopleGraphSearchRequest(quietForDays: 90), snapshot: snapshot, now: now)
    XCTAssertEqual(result.people.map(\.id), ["never", "stale"], "no contact at all is coldest")
    XCTAssertFalse(result.people.contains { $0.id == "recent" })
  }

  func testGroupFilterMatchesSharedGroupNames() throws {
    let snapshot = try standardSnapshot()
    let result = PeopleGraphSearch.run(
      PeopleGraphSearchRequest(group: "tahoe"), snapshot: snapshot, now: Date())
    XCTAssertEqual(result.people.map(\.id), ["sam-altman"])
  }

  func testSearchWithNoFilterListsClosestFirstAndNoMatchIsNotAnEmptyGraph() throws {
    let snapshot = try standardSnapshot()
    let all = PeopleGraphSearch.run(
      PeopleGraphSearchRequest(limit: 2), snapshot: snapshot, now: Date())
    XCTAssertEqual(all.people.map(\.id), ["sam-altman", "samantha-lee"])
    XCTAssertEqual(all.totalMatched, 4)

    let miss = PeopleGraphChatTool.renderSearch(
      request: PeopleGraphSearchRequest(affiliation: "no-such-company"),
      snapshot: snapshot,
      now: Date())
    XCTAssertTrue(miss.hasPrefix("NO PEOPLE MATCH"))
    XCTAssertTrue(miss.contains("The graph itself is fine"))
  }

  // MARK: - Argument coercion

  func testNumericArgumentsAreAcceptedAsIntDoubleOrString() {
    XCTAssertEqual(PeopleGraphChatTool.intArgument(7), 7)
    XCTAssertEqual(PeopleGraphChatTool.intArgument(7.0), 7)
    XCTAssertEqual(PeopleGraphChatTool.intArgument("7"), 7)
    XCTAssertNil(PeopleGraphChatTool.intArgument("seven"))
    XCTAssertNil(PeopleGraphChatTool.intArgument(nil))
  }

  func testSearchRequestClampsLimitAndDropsBlankFilters() {
    XCTAssertEqual(PeopleGraphSearchRequest(limit: 0).limit, 1)
    XCTAssertEqual(PeopleGraphSearchRequest(limit: 1_000).limit, PeopleGraphSearchRequest.maxLimit)
    XCTAssertNil(PeopleGraphSearchRequest(text: "   ").text)
    XCTAssertFalse(PeopleGraphSearchRequest().hasFilter)
  }
}
