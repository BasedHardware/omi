import XCTest

@testable import Omi_Computer

/// The stage that decides who becomes a person.
///
/// A real cold start on one machine turned a 315-handle iMessage export plus a 149-handle WhatsApp
/// export into **1,825 person cards** — 988 of them unbridged WhatsApp `@lid` tokens scraped out of
/// four broadcast lists, 1,398 of them with no message ever exchanged. There was no selection stage
/// at all: every node in the social graph became a row in the People tab.
///
/// Everything here runs the real pipeline (`readExport` → `buildCanonicalPeople` → `buildGraph` →
/// `buildCommunities` → `select` / `createPeople`) over synthetic exports, so a rule that only holds
/// for hand-built `People` values cannot pass.
final class PeopleSelectionTests: XCTestCase {

  // MARK: - Fixtures

  private func decode(_ json: String) throws -> PeopleGraphBuilder.ExportRoot {
    try JSONDecoder().decode(
      PeopleGraphBuilder.ExportRoot.self, from: try XCTUnwrap(json.data(using: .utf8)))
  }

  private func run(
    _ json: String, contactsByPhone: [String: String] = [:], links: PeopleIdentityLinks = .empty
  ) throws -> (
    people: PeopleGraphBuilder.People, graph: PeopleGraphBuilder.Graph,
    communities: PeopleGraphBuilder.Communities, selection: PeopleSelection.Outcome
  ) {
    let root = try decode(json)
    let people = PeopleGraphBuilder.buildCanonicalPeople(
      root: root, contactsByPhone: contactsByPhone, links: links)
    let graph = PeopleGraphBuilder.buildGraph(root: root, people: people)
    let communities = PeopleGraphBuilder.buildCommunities(root: root, people: people)
    let selection = PeopleSelection.select(people: people, graph: graph, communities: communities)
    return (people, graph, communities, selection)
  }

  private func reason(_ outcome: PeopleSelection.Outcome, _ id: String) -> PeopleSelection.DropReason? {
    outcome.drops.first { $0.id == id }?.reason
  }

  // MARK: - The four shapes the rule exists to separate

  /// One export carrying every case at once: a named two-way correspondent, an unnamed node that is
  /// only ever a group co-member, and an unnamed node that only ever messaged inbound.
  func testNamedCorrespondentIsKeptAndUnnamedGroupOnlyNodeIsDropped() throws {
    let result = try run(
      """
      {
        "handles": [
          { "handle": "+15551110000", "phone_last10": "5551110000", "contact_name": "Dana Wu",
            "message_count": 120, "sent": 60, "received": 60, "last_date": "2026-07-01T10:00:00Z" },
          { "handle": "+15552220000", "phone_last10": "5552220000",
            "message_count": 40, "sent": 0, "received": 40, "last_date": "2026-07-01T10:00:00Z" }
        ],
        "groups": [
          { "display_name": "Tahoe Trip", "member_count": 3, "members": [
            { "phone_last10": "5551110000" },
            { "phone_last10": "5553330000" },
            { "phone_last10": "5554440000" }
          ] }
        ]
      }
      """)

    let dana = try XCTUnwrap(result.people.idByPhone["5551110000"])
    XCTAssertTrue(
      result.selection.featuredIDs.contains(dana),
      "a named person we exchange messages with is the whole point of the tab")

    // Group-only and unnamed: nothing to show and nothing to act on.
    for phone in ["5553330000", "5554440000"] {
      let id = try XCTUnwrap(result.people.idByPhone[phone])
      XCTAssertFalse(result.selection.featuredIDs.contains(id), "\(phone) must not become a person")
      XCTAssertEqual(
        reason(result.selection, id), .groupOnlyUnnamed,
        "a node that has never messaged and cannot be named is dropped for exactly that")
    }

    // Inbound-only and unnamed: the shape of a delivery notice, not of a relationship.
    let inbound = try XCTUnwrap(result.people.idByPhone["5552220000"])
    XCTAssertEqual(reason(result.selection, inbound), .oneWayUnnamed)
  }

  /// An unnamed number is still a person when the conversation was two-way — you wrote to them and
  /// they wrote back, so the thread itself is the identity even while the card reads as digits.
  /// This is the case a naive "drop everything unnamed" rule gets wrong: on the measured machine the
  /// single closest contact (11,944 messages) had no resolvable name at all.
  func testUnnamedButTwoWayCorrespondentIsKept() throws {
    let result = try run(
      """
      {
        "handles": [
          { "handle": "+15551110000", "phone_last10": "5551110000",
            "message_count": 11944, "sent": 7171, "received": 4773, "last_date": "2026-07-01T10:00:00Z" }
        ],
        "groups": []
      }
      """)
    let id = try XCTUnwrap(result.people.idByPhone["5551110000"])
    XCTAssertTrue(
      result.selection.featuredIDs.contains(id),
      "an answered conversation is evidence of a relationship even with no name")
    XCTAssertTrue(result.selection.drops.isEmpty)
  }

  /// A connector that does not report direction (WhatsApp) must not have "we never replied" inferred
  /// from its silence — the one-way reason may only fire on evidence we actually have.
  func testMissingDirectionDataIsNotTreatedAsOneWay() throws {
    let result = try run(
      """
      {
        "handles": [
          { "handle": "+15551110000", "phone_last10": "5551110000", "message_count": 12,
            "last_date": "2026-07-01T10:00:00Z" }
        ],
        "groups": []
      }
      """)
    let id = try XCTUnwrap(result.people.idByPhone["5551110000"])
    XCTAssertTrue(result.selection.featuredIDs.contains(id))
  }

  // MARK: - Broadcast lists

  /// The single biggest source of the 1,825: four WhatsApp community lists of 591 / 275 / 247 / 204
  /// members, each of which minted one person per row. Membership in a list that size is not a
  /// relationship, and the ceiling used here is the same `maxGroup` the edge builder already applies
  /// — "a real group" means one thing in this pipeline, not two.
  func testALargeBroadcastListDoesNotMintOnePersonPerMember() throws {
    var members: [String] = []
    for i in 0..<200 { members.append("{ \"phone_last10\": \"555\(String(format: "%07d", i))\" }") }
    let result = try run(
      """
      {
        "handles": [
          { "handle": "+15551110000", "phone_last10": "5551110000", "contact_name": "Dana Wu",
            "message_count": 120, "sent": 60, "received": 60, "last_date": "2026-07-01T10:00:00Z" }
        ],
        "groups": [
          { "display_name": "Cold Email Club", "member_count": 200, "members": [\(members.joined(separator: ","))] }
        ]
      }
      """)

    XCTAssertEqual(
      result.people.canonByID.count, 201, "the graph still knows every node — that is not the bug")
    XCTAssertEqual(
      result.selection.featured.count, 1,
      "a 200-member broadcast list must not produce 200 people")
    XCTAssertEqual(
      result.selection.countsByReason[PeopleSelection.DropReason.broadcastListOnly.rawValue], 200)

    let cards = PeopleGraphBuilder.createPeople(
      people: result.people, graph: result.graph, communities: result.communities)
    XCTAssertEqual(cards.count, 1, "createPeople writes the selected people, not the node dump")
  }

  /// A WhatsApp member the LID bridge could not resolve has no phone number and no address: it can
  /// never be named and can never be messaged. 988 of the measured 1,825 were exactly this.
  func testUnbridgedWhatsAppLIDTokensAreDroppedAsUnaddressable() throws {
    let result = try run(
      """
      {
        "handles": [],
        "groups": [
          { "display_name": "Founders", "member_count": 3, "members": [
            { "handle": "100056162156638@lid" },
            { "handle": "101538076848212@lid" },
            { "phone_last10": "5551110000" }
          ] }
        ]
      }
      """)
    XCTAssertEqual(result.selection.featured.count, 0)
    XCTAssertEqual(
      result.selection.countsByReason[PeopleSelection.DropReason.unaddressable.rawValue], 2,
      "an opaque platform token is not a person")
    XCTAssertTrue(PeopleSelection.isAddressable("5551110000"))
    XCTAssertTrue(PeopleSelection.isAddressable("dana@example.com"))
    XCTAssertFalse(PeopleSelection.isAddressable("100056162156638@lid"))
  }

  // MARK: - The accounting invariant

  /// Every candidate is either featured or dropped, exactly once. Without this the drop count shown
  /// to the user is a guess, and a node can vanish from both sides of the ledger.
  func testFeaturedPlusDroppedAccountsForEveryCandidate() throws {
    var members: [String] = []
    for i in 0..<80 { members.append("{ \"phone_last10\": \"555\(String(format: "%07d", i))\" }") }
    let result = try run(
      """
      {
        "handles": [
          { "handle": "+15551110000", "phone_last10": "5551110000", "contact_name": "Dana Wu",
            "message_count": 120, "sent": 60, "received": 60, "last_date": "2026-07-01T10:00:00Z" },
          { "handle": "dana.wu@example.com", "message_count": 3, "sent": 1, "received": 2 },
          { "handle": "+15559990000", "phone_last10": "5559990000", "message_count": 9,
            "sent": 0, "received": 9 }
        ],
        "groups": [
          { "display_name": "Big List", "member_count": 80, "members": [\(members.joined(separator: ","))] },
          { "display_name": "Tahoe Trip", "member_count": 2, "members": [
            { "phone_last10": "5551110000" }, { "phone_last10": "5558880000" }
          ] }
        ]
      }
      """)

    XCTAssertEqual(
      result.selection.candidateCount, result.people.canonByID.count,
      "featured + dropped must account for every canonical node")
    XCTAssertEqual(
      Set(result.selection.featured).intersection(result.selection.drops.map(\.id)), [],
      "no node may be both featured and dropped")
    XCTAssertEqual(
      Set(result.selection.featured).union(result.selection.drops.map(\.id)),
      Set(result.people.canonByID.keys))
  }

  // MARK: - Naming harder, before dropping

  /// `IMessageExporter` writes no name at all, so "unnamed" is common and therefore dangerous as a
  /// drop signal. Every source has to be tried first: the address book, the connector's own name, a
  /// name this machine resolved on an earlier run, and the address itself.
  func testNamingCascadeRescuesNodesThatWouldOtherwiseBeDropped() throws {
    let export = """
      {
        "handles": [
          { "handle": "dana.wu@example.com", "message_count": 0 }
        ],
        "groups": [
          { "display_name": "Tahoe Trip", "member_count": 3, "members": [
            { "handle": "dana.wu@example.com" },
            { "phone_last10": "5553330000" },
            { "phone_last10": "5554440000" }
          ] }
        ]
      }
      """

    // Nothing resolves the two phone-only members → both drop as group-only + unnamed.
    let bare = try run(export)
    XCTAssertEqual(bare.selection.featured.count, 1, "only the email local-part name survives")
    XCTAssertEqual(
      bare.people.canonByID[try XCTUnwrap(bare.people.idByEmail["dana.wu@example.com"])]?.name,
      "Dana Wu", "a name read off the address is still a name")

    // The address book names one of them → that one is now a person.
    let withContacts = try run(export, contactsByPhone: ["5553330000": "Kai Osei"])
    let kai = try XCTUnwrap(withContacts.people.idByPhone["5553330000"])
    XCTAssertTrue(withContacts.selection.featuredIDs.contains(kai))

    // A name an earlier run already resolved for this identity key names them again, even with no
    // address book and no connector name at all.
    var links = PeopleIdentityLinks.empty
    links.record(key: "5554440000", personID: "kim-alvarez", name: "Kim Alvarez")
    let withDurable = try run(export, links: links)
    let kim = try XCTUnwrap(withDurable.people.idByPhone["5554440000"])
    XCTAssertTrue(withDurable.selection.featuredIDs.contains(kim))
    XCTAssertEqual(withDurable.people.canonByID[kim]?.name, "Kim Alvarez")
  }

  /// The durable store records whatever the display name was, which for an unnamed person is their
  /// phone number. Reading that back as a "name" would make every unnamed node self-rescue on its
  /// second run, and the drop reason would silently stop firing.
  func testAPhoneNumberStoredAsADisplayNameIsNotTreatedAsAName() throws {
    var links = PeopleIdentityLinks.empty
    links.record(key: "5553330000", personID: "p", name: "+1 (555) 333-0000")
    XCTAssertNil(PeopleNaming.durableName(forKey: "5553330000", links: links))
    XCTAssertFalse(PeopleNaming.isHumanShaped("+1 (555) 333-0000"))
    XCTAssertFalse(PeopleNaming.isHumanShaped("100056162156638@lid"))
    XCTAssertFalse(PeopleNaming.isHumanShaped("urn:biz:6e67a89b"))
    XCTAssertTrue(PeopleNaming.isHumanShaped("Aryaveer UMN"))
  }

  /// A local part is only a name when it reads like one — a throwaway alphanumeric address must not
  /// be promoted to "R8809kwstey", because a wrong name is worse than an honest phone number.
  func testEmailLocalPartNamesOnlyWhenItReadsLikeAName() {
    XCTAssertEqual(PeopleNaming.fromEmailLocalPart("dana.wu@example.com"), "Dana Wu")
    XCTAssertEqual(PeopleNaming.fromEmailLocalPart("matt@molinar.ai"), "Matt")
    XCTAssertNil(PeopleNaming.fromEmailLocalPart("r8809kwstey@example.cn"))
    XCTAssertNil(PeopleNaming.fromEmailLocalPart("candy8106@example.com"))
    XCTAssertNil(PeopleNaming.fromEmailLocalPart("100056162156638@lid"))
  }

  /// A name read off an address is a reading, not an assertion — it must not be surfaced as a
  /// resolved contact name, which is what `contactName` means everywhere else in the app.
  func testADerivedNameNeverClaimsToBeAResolvedContactName() throws {
    let result = try run(
      """
      {
        "handles": [
          { "handle": "dana.wu@example.com", "message_count": 12, "sent": 6, "received": 6 }
        ],
        "groups": []
      }
      """)
    let id = try XCTUnwrap(result.people.idByEmail["dana.wu@example.com"])
    XCTAssertEqual(result.people.canonByID[id]?.nameSource, .emailLocalPart)
    XCTAssertFalse(try XCTUnwrap(result.people.canonByID[id]?.identified))
    let cards = PeopleGraphBuilder.createPeople(
      people: result.people, graph: result.graph, communities: result.communities)
    XCTAssertNil(try XCTUnwrap(cards.first { ($0["id"] as? String) == id })["contactName"])
  }

  // MARK: - The merge path

  /// The merge path folds this run's graph onto an existing file. It must never write a person the
  /// selection stage dropped — otherwise every hidden node reappears the moment the file exists —
  /// and it must never remove a card a previous run already showed the user.
  func testMergeNeitherResurrectsADropNorRemovesAPreviouslyFeaturedPerson() throws {
    var members: [String] = []
    for i in 0..<80 { members.append("{ \"phone_last10\": \"555\(String(format: "%07d", i))\" }") }
    let result = try run(
      """
      {
        "handles": [
          { "handle": "+15551110000", "phone_last10": "5551110000", "contact_name": "Dana Wu",
            "message_count": 120, "sent": 60, "received": 60, "last_date": "2026-07-01T10:00:00Z" }
        ],
        "groups": [
          { "display_name": "Cold Email Club", "member_count": 80, "members": [\(members.joined(separator: ","))] }
        ]
      }
      """)
    XCTAssertGreaterThan(result.selection.drops.count, 50, "the fixture must actually drop people")

    let dir = FileManager.default.temporaryDirectory
      .appendingPathComponent("PeopleSelectionTests-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: dir) }
    let url = dir.appendingPathComponent("people_intelligence.json")

    // A file a previous run wrote: one person who is not in this run's export at all.
    let existing: [String: Any] = [
      "generated_at": "2026-07-01T00:00:00Z",
      "people": [["id": "sam-lee", "name": "Sam Lee", "closeness": 9.0]],
    ]
    try JSONSerialization.data(withJSONObject: existing).write(to: url)

    PeopleGraphBuilder.mergeIntoPeopleIntelligence(
      graph: result.graph, communities: result.communities, people: result.people,
      ingestedPersonKeys: [], at: url)

    let doc = try XCTUnwrap(
      try JSONSerialization.jsonObject(with: try Data(contentsOf: url)) as? [String: Any])
    let persons = try XCTUnwrap(doc["people"] as? [[String: Any]])
    let ids = Set(persons.compactMap { $0["id"] as? String })

    XCTAssertTrue(ids.contains("sam-lee"), "a card a previous run featured is never removed")
    XCTAssertEqual(
      ids.intersection(result.selection.drops.map(\.id)), [],
      "the merge path must not resurrect a single dropped node")
    XCTAssertTrue(
      ids.contains(try XCTUnwrap(result.people.idByPhone["5551110000"])),
      "a newly selected person is appended — the list has to be able to grow after the first run")

    // The header must describe the list the user is looking at, not the run that seeded the file.
    let stats = try XCTUnwrap(doc["stats"] as? [String: Any])
    XCTAssertEqual(stats["featured"] as? Int, result.selection.featured.count)
    XCTAssertEqual(stats["dropped"] as? Int, result.selection.drops.count)
    XCTAssertEqual(stats["people"] as? Int, persons.count)
  }

  /// The drop count is only useful if the user can find out *why*. `PeopleStats` decodes the reason
  /// breakdown the engine writes, and the People tab renders it under the header.
  func testStatsCarryTheDropBreakdownThroughToTheUI() throws {
    let json = """
      {
        "stats": { "people": 315, "multichannel": 61, "channels": 2, "featured": 315,
                   "dropped": 1510, "dropped_reasons": { "unaddressable": 989, "broadcastListOnly": 282,
                   "groupOnlyUnnamed": 128, "oneWayUnnamed": 111 } },
        "people": []
      }
      """
    let file = try JSONDecoder().decode(
      PeopleIntelligenceFile.self, from: try XCTUnwrap(json.data(using: .utf8)))
    let stats = try XCTUnwrap(file.stats)
    XCTAssertEqual(stats.featured, 315)
    XCTAssertEqual(stats.dropped, 1510)
    XCTAssertEqual(stats.featured + stats.dropped, 1825)
    let summary = try XCTUnwrap(PeopleSelection.summarize(droppedReasons: stats.droppedReasons))
    XCTAssertTrue(
      summary.hasPrefix("989 \(PeopleSelection.DropReason.unaddressable.explanation)"),
      "the biggest reason leads: \(summary)")

    // A file written before the selection stage decodes to "nothing hidden", never to a wrong count.
    let legacy = try JSONDecoder().decode(
      PeopleIntelligenceFile.self,
      from: try XCTUnwrap("{\"stats\":{\"people\":9},\"people\":[]}".data(using: .utf8)))
    XCTAssertEqual(legacy.stats?.dropped, 0)
    XCTAssertNil(PeopleSelection.summarize(droppedReasons: legacy.stats?.droppedReasons ?? [:]))
  }
}
