import XCTest

@testable import Omi_Computer

/// Exercises the on-device People-Intelligence engine's pure core (no file IO in the tested
/// path beyond decoding a synthetic export): canonical-people resolution, size-normalized edge
/// weights `1/(m-1)`, community categorization, and fresh-user people-list creation.
final class PeopleGraphBuilderTests: XCTestCase {

  /// Two 1:1 handles (Alice, Bob) plus one 3-person named group (Alice, Bob, Carol). Alice appears
  /// both as a direct handle and as a group member in a *different* phone-string format, and Carol
  /// appears only inside the group.
  private func writeSyntheticExport() throws -> URL {
    let dir = FileManager.default.temporaryDirectory
      .appendingPathComponent("PeopleGraphBuilderTests-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    let url = dir.appendingPathComponent("imessage_export.json")

    let json = """
      {
        "generated_at": "2026-07-25T10:00:00Z",
        "total_messages": 150,
        "handles": [
          {
            "handle": "+1 (555) 123-4567",
            "phone_last10": "5551234567",
            "contact_name": "Alice",
            "message_count": 100,
            "last_date": "2026-07-01T10:00:00Z"
          },
          {
            "handle": "+15559876543",
            "phone_last10": "5559876543",
            "contact_name": "Bob",
            "message_count": 50,
            "last_date": "2026-06-01T10:00:00Z"
          }
        ],
        "groups": [
          {
            "display_name": "Tahoe Trip 2024",
            "member_count": 3,
            "members": [
              { "handle": "+1-555-123-4567" },
              { "phone_last10": "5559876543" },
              { "handle": "+15550001111", "phone_last10": "5550001111" }
            ]
          }
        ]
      }
      """
    try XCTUnwrap(json.data(using: .utf8)).write(to: url)
    return url
  }

  func testFreshUserPipelineResolvesDedupesEdgesCategoriesAndCreatesPeople() throws {
    let url = try writeSyntheticExport()
    defer { try? FileManager.default.removeItem(at: url.deletingLastPathComponent()) }

    // Parse the synthetic export; everything after this is pure (no file IO).
    guard let root = PeopleGraphBuilder.readExport(at: url) else {
      return XCTFail("readExport returned nil for the synthetic export")
    }

    // Pass no contacts so the resolver never touches the Contacts store.
    let people = PeopleGraphBuilder.buildCanonicalPeople(root: root, contactsByPhone: [:])
    let graph = PeopleGraphBuilder.buildGraph(root: root, people: people)
    let communities = PeopleGraphBuilder.buildCommunities(root: root, people: people)
    let persons = PeopleGraphBuilder.createPeople(people: people, graph: graph, communities: communities)

    // --- dedup by phone: Alice (handle + group member, different string formats) and Bob collapse
    //     to one node each; Carol (group-only) is the third. Not 5 identities.
    XCTAssertEqual(people.canonByID.count, 3, "phone identities must dedupe to 3 canonical people")
    XCTAssertNotNil(people.idByPhone["5551234567"], "Alice's phone must resolve")
    XCTAssertEqual(
      people.idByPhone["5551234567"], "alice",
      "the +1 (555) 123-4567 handle and the +1-555-123-4567 group member must be the same person")

    // --- edges: a 3-person group contributes 1/(m-1) = 0.5 to every member pair (3 pairs).
    XCTAssertEqual(graph.edges.count, 3, "a 3-person group yields exactly its 3 member pairs")
    for e in graph.edges {
      XCTAssertEqual(e.weight, 0.5, accuracy: 0.0001, "each group-pair edge weight must be 1/(3-1)")
    }
    let aliceBob = graph.edges.first { Set([$0.a, $0.b]) == Set(["alice", "bob"]) }
    XCTAssertNotNil(aliceBob, "the Alice–Bob pair must have an edge")
    XCTAssertEqual(aliceBob?.weight ?? 0, 0.5, accuracy: 0.0001, "Alice–Bob edge weight is 0.5")

    // --- category: a named "Tahoe Trip" group categorizes as trip / event.
    XCTAssertEqual(communities.list.count, 1, "the named group becomes one community")
    XCTAssertEqual(
      communities.list.first?["category"] as? String, "trip / event",
      "a Tahoe/trip group must categorize as trip / event")

    // --- created people list is the *selected* people, sorted by closeness desc, with a channel.
    //     All three identities stay nodes in the graph — Carol is still an edge endpoint above —
    //     but she has never exchanged a message and no source can name her, so she is not a card.
    //     `createPeople` is a directory, not a dump of the graph (see `PeopleSelection`).
    let selection = PeopleSelection.select(people: people, graph: graph, communities: communities)
    XCTAssertEqual(persons.count, 2, "createPeople writes the selected people, not every node")
    XCTAssertEqual(
      selection.drops.map(\.reason), [.groupOnlyUnnamed],
      "the group-only, unnamed identity is dropped for exactly that reason")
    XCTAssertEqual(
      selection.candidateCount, people.canonByID.count, "every candidate is accounted for")
    XCTAssertEqual(persons.first?["name"] as? String, "Alice", "highest message_count sorts first")
    XCTAssertEqual(persons.first?["closeness"] as? Double, 100.0, "closeness proxies message_count")

    let channels = persons.first?["channels"] as? [[String: Any]]
    XCTAssertEqual(channels?.count, 1, "each created person has a single iMessage channel")
    XCTAssertEqual(channels?.first?["key"] as? String, "imessage")
    XCTAssertEqual(channels?.first?["count"] as? Int, 100)
    XCTAssertEqual(
      (persons.first?["lastTouch"] as? [String: Any])?["date"] as? String, "2026-07-01T10:00:00Z",
      "lastTouch carries the newest per-person message date")
  }

  // MARK: - Continuous-sync throttle

  /// The throttle decision that gates every continuous trigger (app-active, new conversation,
  /// connector import) so the on-device pipeline runs at most once per `minSyncInterval`.
  func testSyncThrottleDecision() {
    let now = Date()
    let interval = PeopleGraphBuilder.minSyncInterval

    // Never run before → run.
    XCTAssertTrue(
      PeopleGraphBuilder.shouldRun(lastRun: nil, now: now, force: false),
      "a first-ever sync (no recorded run) must proceed")

    // Ran just now → within the window → skip.
    XCTAssertFalse(
      PeopleGraphBuilder.shouldRun(lastRun: now, now: now, force: false),
      "a sync less than the interval ago must be throttled")
    XCTAssertFalse(
      PeopleGraphBuilder.shouldRun(
        lastRun: now.addingTimeInterval(-(interval - 1)), now: now, force: false),
      "a sync just under the interval ago must be throttled")

    // Older than the interval → run again.
    XCTAssertTrue(
      PeopleGraphBuilder.shouldRun(
        lastRun: now.addingTimeInterval(-interval), now: now, force: false),
      "a sync at exactly the interval boundary must proceed")
    XCTAssertTrue(
      PeopleGraphBuilder.shouldRun(
        lastRun: now.addingTimeInterval(-(interval + 60)), now: now, force: false),
      "a sync older than the interval must proceed")

    // Force always bypasses the throttle, even immediately after a run.
    XCTAssertTrue(
      PeopleGraphBuilder.shouldRun(lastRun: now, now: now, force: true),
      "force must bypass the throttle window")
  }

  /// The thread ingest reuses `claimRun`/`shouldRun` but with a much longer `minInterval` than the
  /// graph sync, so its from-segments submissions stay within the endpoint's rate budget. A run that
  /// clears the short graph-sync cadence must still be throttled under the ingest's own interval —
  /// otherwise the ingest would fire every graph sync and burst past the rate limit.
  func testIngestThrottleIsMoreConservativeThanGraphSync() {
    let now = Date()
    XCTAssertGreaterThan(
      PeopleThreadIngest.minIngestInterval, PeopleGraphBuilder.minSyncInterval,
      "the ingest must self-throttle more conservatively than the graph sync")

    let justPastGraphSync = now.addingTimeInterval(-(PeopleGraphBuilder.minSyncInterval + 60))
    XCTAssertTrue(
      PeopleGraphBuilder.shouldRun(lastRun: justPastGraphSync, now: now, force: false),
      "a run older than the graph-sync interval clears the default cadence")
    XCTAssertFalse(
      PeopleGraphBuilder.shouldRun(
        lastRun: justPastGraphSync, now: now, force: false,
        minInterval: PeopleThreadIngest.minIngestInterval),
      "the same run is still throttled under the ingest's longer interval, keeping submissions within budget")

    XCTAssertTrue(
      PeopleGraphBuilder.shouldRun(
        lastRun: now.addingTimeInterval(-PeopleThreadIngest.minIngestInterval), now: now, force: false,
        minInterval: PeopleThreadIngest.minIngestInterval),
      "a run older than the ingest interval proceeds")
  }
}
