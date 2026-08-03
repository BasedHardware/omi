import XCTest

@testable import Omi_Computer

/// Guards the People-Intelligence identity boundary.
///
/// The failure this suite exists for: `slug(displayName)` used to BE the person's identity, so
/// renaming a contact silently minted a second person — detaching their saved override decisions,
/// their `person:<id>` memory tags already on the server, their contact photo, and any backend
/// `Person` binding. Every test here drives production functions against a real temp directory,
/// so it fails if identity ever goes back to being a display-name string.
final class PeopleIdentityTests: XCTestCase {

  // MARK: - Fixtures

  private func makeDirectory() throws -> URL {
    let dir = FileManager.default.temporaryDirectory
      .appendingPathComponent("PeopleIdentityTests-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    addTeardownBlock { try? FileManager.default.removeItem(at: dir) }
    return dir
  }

  /// One 1:1 handle plus a named group, so the person exists both as a direct handle and as a
  /// group member — the same shape the real exporter writes.
  private func writeExport(to dir: URL, phone: String = "5551234567") throws -> URL {
    let url = dir.appendingPathComponent("imessage_export.json")
    let json = """
      {
        "generated_at": "2026-07-25T10:00:00Z",
        "handles": [
          {
            "handle": "+1 (555) 123-4567",
            "phone_last10": "\(phone)",
            "message_count": 120,
            "last_date": "2026-07-01T10:00:00Z"
          },
          {
            "handle": "+15559876543",
            "phone_last10": "5559876543",
            "contact_name": "Bob Brown",
            "message_count": 40,
            "last_date": "2026-06-01T10:00:00Z"
          }
        ],
        "groups": [
          {
            "display_name": "Tahoe Trip",
            "member_count": 2,
            "members": [
              { "phone_last10": "\(phone)" },
              { "phone_last10": "5559876543" }
            ]
          }
        ]
      }
      """
    try XCTUnwrap(json.data(using: .utf8)).write(to: url)
    return url
  }

  /// One full pipeline pass, exactly as `PeopleGraphBuilder.build` sequences it: load the durable
  /// link table, resolve people through it, record what was resolved, then create the cards.
  private func runPipeline(
    exportURL: URL, directory: URL, contactsByPhone: [String: String]
  ) throws -> (people: PeopleGraphBuilder.People, cards: [[String: Any]]) {
    let root = try XCTUnwrap(PeopleGraphBuilder.readExport(at: exportURL))
    let links = PeopleIdentityStore.load(directory: directory)
    let people = PeopleGraphBuilder.buildCanonicalPeople(
      root: root, contactsByPhone: contactsByPhone, links: links)
    PeopleIdentityStore.record(
      identityKeys: people.identityKeysByID(), names: people.namesByID(), directory: directory)
    let graph = PeopleGraphBuilder.buildGraph(root: root, people: people)
    let communities = PeopleGraphBuilder.buildCommunities(root: root, people: people)
    let cards = PeopleGraphBuilder.createPeople(
      people: people, graph: graph, communities: communities,
      links: PeopleIdentityStore.load(directory: directory))
    return (people, cards)
  }

  private func card(_ cards: [[String: Any]], named name: String) throws -> [String: Any] {
    try XCTUnwrap(cards.first { ($0["name"] as? String) == name }, "no card named \(name)")
  }

  // MARK: - THE guard: a rename must not mint a new person

  /// Rename a contact between two pipeline runs and assert that everything keyed on their identity
  /// survives: the card's handles, its bridged `personUUID`, the user's saved override decision,
  /// and the `person:<id>` memory tags already written to the server.
  ///
  /// Before identity was persisted, every one of these detached the instant the user fixed a
  /// contact's name — the card's id changed, and nothing keyed on the old id could find it again.
  func testRenamingAContactKeepsItsHandlesUUIDOverridesAndMemoryTags() throws {
    let dir = try makeDirectory()
    let exportURL = try writeExport(to: dir)

    // ---- run 1: the contact is known as "Alice Anderson" ----
    let first = try runPipeline(
      exportURL: exportURL, directory: dir, contactsByPhone: ["5551234567": "Alice Anderson"])
    let before = try card(first.cards, named: "Alice Anderson")
    let originalID = try XCTUnwrap(before["id"] as? String)
    XCTAssertEqual(originalID, "alice-anderson", "the first id is still the name slug")
    XCTAssertEqual(
      PersonIdentityKeys.from(json: before["handles"]).phones, ["5551234567"],
      "the card must carry the phone identity the pipeline resolved it by")

    // The backend bridge binds this identity to a backend Person…
    PeopleIdentityBridge.commit(resolved: [originalID: "uuid-alice-1"], directory: dir)
    // …the user saves a correction against it…
    PeopleOverridesStore.save(
      PeopleOverrides(factEdits: [
        .init(id: originalID, original: "Works at Acme", corrected: "Works at Globex")
      ]),
      directory: dir)
    // …and relationship facts are already on the server tagged with the person's id.
    let tagsBefore = PeopleMemoryWriter.tags(forSubject: "person:\(originalID)")
    XCTAssertTrue(tagsBefore.contains("person:alice-anderson"))

    // ---- run 2: the user corrects the contact's name in the address book ----
    let second = try runPipeline(
      exportURL: exportURL, directory: dir, contactsByPhone: ["5551234567": "Alice Zheng"])
    let after = try card(second.cards, named: "Alice Zheng")

    // Identity survived the rename: same id, so nothing keyed on it detached.
    XCTAssertEqual(
      after["id"] as? String, originalID,
      "renaming a contact must not mint a new person — the phone identity is the same human")
    XCTAssertEqual(
      PersonIdentityKeys.from(json: after["handles"]).phones, ["5551234567"],
      "handles must survive the rename")
    XCTAssertEqual(
      after["personUUID"] as? String, "uuid-alice-1",
      "the backend Person binding must survive the rename")
    XCTAssertEqual(
      PeopleMemoryWriter.tags(forSubject: "person:\(try XCTUnwrap(after["id"] as? String))"),
      tagsBefore,
      "memory tags already on the server must still address this person")

    // The saved correction still lands on the renamed card.
    let reviewed = PeopleGraphBuilder.annotateAndReview(
      persons: [after.merging(["facts": ["Works at Acme"]]) { _, new in new }],
      overrides: PeopleOverridesStore.load(directory: dir))
    XCTAssertEqual(
      reviewed.people.first?["facts"] as? [String], ["Works at Globex"],
      "an override decision saved before the rename must still apply after it")
  }

  /// Legacy principal: a machine that has never written `people_identity.json` must resolve ids
  /// exactly the way it always did. Identity continuity is earned going forward, never applied
  /// retroactively — a first run that renumbered everyone would detach every existing memory tag.
  func testFirstRunWithNoStoredLinksAssignsNameSlugIdsExactlyAsBefore() throws {
    let dir = try makeDirectory()
    let exportURL = try writeExport(to: dir)
    let root = try XCTUnwrap(PeopleGraphBuilder.readExport(at: exportURL))

    XCTAssertFalse(
      FileManager.default.fileExists(
        atPath: dir.appendingPathComponent(PeopleIdentityStore.fileName).path),
      "precondition: no link table yet")

    let withoutLinks = PeopleGraphBuilder.buildCanonicalPeople(
      root: root, contactsByPhone: ["5551234567": "Alice Anderson"])
    let withEmptyStore = PeopleGraphBuilder.buildCanonicalPeople(
      root: root, contactsByPhone: ["5551234567": "Alice Anderson"],
      links: PeopleIdentityStore.load(directory: dir))

    XCTAssertEqual(withoutLinks.idByPhone, withEmptyStore.idByPhone)
    XCTAssertEqual(withoutLinks.idByPhone["5551234567"], "alice-anderson")
  }

  /// A person reachable on two handles, only one of which was seen before, must not split in half
  /// the first time they are renamed: the stored id has to apply to their whole name group.
  func testASecondHandleDoesNotSplitARenamedPersonInTwo() throws {
    var links = PeopleIdentityLinks.empty
    links.record(key: "5551234567", personID: "alice-anderson", name: "Alice Anderson")

    // Both handles now slug to the new name; only the first one is in the link table.
    let resolved = PeopleIdentityLinks.stableIDs(
      nameIDByKey: ["5551234567": "alice-zheng", "5550009999": "alice-zheng"], links: links)

    XCTAssertEqual(resolved["5551234567"], "alice-anderson")
    XCTAssertEqual(
      resolved["5550009999"], "alice-anderson",
      "a newly seen handle for the same person must join them, not fork a second card")
  }

  /// An unrelated person keeps their freshly-slugged id — a stored link must only ever bind the
  /// identity it was recorded for.
  func testAStoredLinkNeverCapturesAnUnrelatedPerson() throws {
    var links = PeopleIdentityLinks.empty
    links.record(key: "5551234567", personID: "alice-anderson")

    let resolved = PeopleIdentityLinks.stableIDs(
      nameIDByKey: ["5551234567": "alice-zheng", "5559876543": "bob-brown"], links: links)

    XCTAssertEqual(resolved["5551234567"], "alice-anderson")
    XCTAssertEqual(resolved["5559876543"], "bob-brown")
  }

  // MARK: - Merge path (backend-written file)

  /// The merge path must FILL identity in without clobbering: a handle a previous run recorded is
  /// kept (union, not replace) and an existing `personUUID` is never repointed.
  func testMergeFillsHandlesAndUUIDWithoutClobberingExistingValues() throws {
    let dir = try makeDirectory()
    let exportURL = try writeExport(to: dir)
    let root = try XCTUnwrap(PeopleGraphBuilder.readExport(at: exportURL))
    let people = PeopleGraphBuilder.buildCanonicalPeople(
      root: root, contactsByPhone: ["5551234567": "Alice Anderson"])
    let graph = PeopleGraphBuilder.buildGraph(root: root, people: people)
    let communities = PeopleGraphBuilder.buildCommunities(root: root, people: people)

    var links = PeopleIdentityLinks.empty
    links.record(key: "5551234567", personID: "alice-anderson")
    links.setPersonUUID("uuid-from-links", forPersonID: "alice-anderson")

    // A backend-written file that already knows a WhatsApp handle and a backend Person.
    let peopleURL = dir.appendingPathComponent("people_intelligence.json")
    let existing: [String: Any] = [
      "people": [
        [
          "id": "alice-anderson",
          "name": "Alice Anderson",
          "handles": ["phones": ["5550001111"], "emails": []],
          "personUUID": "uuid-already-bridged",
        ]
      ]
    ]
    try JSONSerialization.data(withJSONObject: existing).write(to: peopleURL)

    PeopleGraphBuilder.mergeIntoPeopleIntelligence(
      graph: graph, communities: communities, people: people, ingestedPersonKeys: [],
      links: links, at: peopleURL)

    let merged = try XCTUnwrap(
      JSONSerialization.jsonObject(with: try Data(contentsOf: peopleURL)) as? [String: Any])
    let card = try XCTUnwrap((merged["people"] as? [[String: Any]])?.first)
    XCTAssertEqual(
      Set(PersonIdentityKeys.from(json: card["handles"]).phones), ["5550001111", "5551234567"],
      "handles must union — a second channel adds a key, it does not replace the first")
    XCTAssertEqual(
      card["personUUID"] as? String, "uuid-already-bridged",
      "an existing backend binding must never be repointed at a second Person")
  }

  /// A user-confirmed "these two are the same person" must carry the absorbed card's identity
  /// across, otherwise the merge makes that handle unaddressable and the next run re-splits them.
  func testConfirmedMergeCarriesTheAbsorbedCardsIdentityAcross() throws {
    let people: [[String: Any]] = [
      [
        "id": "alice-anderson", "name": "Alice Anderson", "closeness": 100.0,
        "handles": ["phones": ["5551234567"], "emails": []],
      ],
      [
        "id": "alice-a", "name": "Alice A", "closeness": 10.0,
        "handles": ["phones": ["5550009999"], "emails": []], "personUUID": "uuid-alice",
      ],
    ]
    let result = PeopleGraphBuilder.applyOverrides(
      people: people, reviewQueue: [],
      overrides: PeopleOverrides(identity: [.init(a: "alice-anderson", b: "alice-a", same: true)]))

    let survivor = try XCTUnwrap(result.people.first)
    XCTAssertEqual(result.people.count, 1)
    XCTAssertEqual(
      Set(PersonIdentityKeys.from(json: survivor["handles"]).phones),
      ["5551234567", "5550009999"], "a confirmed merge must keep both identities addressable")
    XCTAssertEqual(survivor["personUUID"] as? String, "uuid-alice")
  }

  // MARK: - Backend bridge

  /// Recording double for the backend People CRUD.
  private actor DirectoryDouble: PeopleDirectoryClient {
    private var people: [Person]
    private(set) var created: [String] = []
    private(set) var listCalls = 0

    init(existing: [Person] = []) { people = existing }

    func listPeople() async throws -> [Person] {
      listCalls += 1
      return people
    }

    func createPerson(name: String) async throws -> Person {
      created.append(name)
      let person = Person(id: "uuid-\(created.count)", name: name)
      people.append(person)
      return person
    }
  }

  /// Backend double that refuses specific names the way `POST /v1/users/people` really does:
  /// FastAPI validates `CreatePerson.name` (`min_length=2, max_length=40`, `backend/models/other.py`)
  /// before the handler runs, so a violating name comes back **422**, every time, forever.
  private actor RejectingDirectoryDouble: PeopleDirectoryClient {
    private let rejectedStatus: Int
    private(set) var attempted: [String] = []

    init(rejectedStatus: Int = 422) { self.rejectedStatus = rejectedStatus }

    func listPeople() async throws -> [Person] { [] }

    func createPerson(name: String) async throws -> Person {
      attempted.append(name)
      guard name.unicodeScalars.count >= 2, name.unicodeScalars.count <= 40 else {
        throw APIError.httpError(statusCode: rejectedStatus, detail: nil)
      }
      return Person(id: "uuid-\(attempted.count)", name: name)
    }
  }

  /// Backend double that fails everything with one status — for separating "this card" from
  /// "this run".
  private actor AlwaysFailingDirectoryDouble: PeopleDirectoryClient {
    private let status: Int
    private(set) var attempts = 0

    init(status: Int) { self.status = status }

    func listPeople() async throws -> [Person] { [] }

    func createPerson(name: String) async throws -> Person {
      attempts += 1
      throw APIError.httpError(statusCode: status, detail: nil)
    }
  }

  /// The regression, measured on a real cold start: the bridge stamped `personUUID` on **12 of
  /// 1,825** cards and then stopped at 12 on every later run of the day. It was never the per-run
  /// cap (12 < 25). Pending card 13 was a 44-character `urn:biz:<uuid>` service-account label; the
  /// backend answered 422, and `resolve` treated that permanent per-card refusal exactly like an
  /// offline/rate-limited run and broke out of the loop. The pending order is deterministic, so the
  /// same card was re-offered first forever and everyone behind it was wedged out permanently.
  func testOneCardTheBackendRefusesDoesNotWedgeEveryCardBehindIt() async throws {
    let poison = "urn:biz:29896aa3-06a9-4b54-b544-5e113c222d08"  // 44 scalars — the real one
    XCTAssertEqual(poison.unicodeScalars.count, 44, "the label from the measured run")

    let double = RejectingDirectoryDouble()
    let resolved = await PeopleIdentityBridge.resolve(
      pending: [
        .init(personID: "alice-anderson", name: "Alice Anderson"),
        .init(personID: "urn-biz", name: poison),
        .init(personID: "bob-brown", name: "Bob Brown"),
        .init(personID: "carol-chen", name: "Carol Chen"),
      ],
      client: double)

    XCTAssertNil(resolved["urn-biz"], "a name the backend cannot accept must not be claimed")
    XCTAssertEqual(
      Set(resolved.keys), ["alice-anderson", "bob-brown", "carol-chen"],
      "the cards after the refused one must still be bridged — this is the 12-of-1,825 regression")
  }

  /// …and the poison card should not have cost a request at all: the length contract is knowable
  /// on-device, so a card that can never become a `Person` never enters the run.
  func testANameTheBackendContractForbidsNeverEntersTheRun() throws {
    let tooLong = String(repeating: "a", count: PeopleIdentityBridge.maxBackendNameLength + 1)
    let persons: [[String: Any]] = [
      ["id": "alice-anderson", "name": "Alice Anderson", "handles": ["phones": ["5551234567"]]],
      [
        "id": "urn-biz", "name": "urn:biz:29896aa3-06a9-4b54-b544-5e113c222d08",
        "handles": ["phones": ["5550001111"]],
      ],
      ["id": "too-long", "name": tooLong, "handles": ["phones": ["5550002222"]]],
      ["id": "single-letter", "name": "J", "handles": ["phones": ["5550003333"]]],
    ]
    let pending = PeopleIdentityBridge.pendingPeople(
      persons: persons, links: .empty, cap: PeopleIdentityBridge.maxResolutionsPerRun)

    XCTAssertEqual(
      pending.map(\.personID), ["alice-anderson"],
      "only a name inside the backend's 2…40 contract may be offered")
    XCTAssertTrue(PeopleIdentityBridge.isBridgeableName("Jo"))
    XCTAssertFalse(
      PeopleIdentityBridge.isBridgeableName(String(repeating: "🤟", count: 41)),
      "the contract counts Unicode scalars, as pydantic does — not grapheme clusters")
  }

  /// A refusal is only "this card" when it really is. Rate limiting, auth and server faults are
  /// about the run: those still stop it, so the remaining cards are retried later instead of
  /// burning the whole cap against a backend that is down.
  func testRunLevelFailuresStillStopTheRun() async throws {
    for status in [429, 401, 403, 500, 503] {
      let double = AlwaysFailingDirectoryDouble(status: status)
      let resolved = await PeopleIdentityBridge.resolve(
        pending: (1...5).map { .init(personID: "p\($0)", name: "Person \($0)") }, client: double)
      XCTAssertTrue(resolved.isEmpty)
      let attempts = await double.attempts
      XCTAssertEqual(attempts, 1, "HTTP \(status) is about the run, so it must stop after one try")
      XCTAssertFalse(PeopleIdentityBridge.isCardRejection(APIError.httpError(statusCode: status)))
    }
    for status in [400, 404, 409, 422] {
      XCTAssertTrue(PeopleIdentityBridge.isCardRejection(APIError.httpError(statusCode: status)))
    }
  }

  /// The cap is small and the population is long-tailed, so a run that spends its budget in file
  /// order spends it on nobody in particular. Given more candidates than the cap, the budget has to
  /// go to the people the user would recognize: named first, then people actually corresponded
  /// with, then live relationships ahead of dead ones, and volume inside that.
  func testACappedRunSpendsItsBudgetOnTheStrongestRelationshipsFirst() throws {
    let now = ISO8601DateFormatter().date(from: "2026-08-03T12:00:00Z") ?? Date()
    func card(_ id: String, _ name: String, closeness: Double, last: String?, named: Bool) -> [String: Any] {
      var person: [String: Any] = [
        "id": id, "name": name, "closeness": closeness, "handles": ["phones": ["555\(id.count)000000"]],
      ]
      if named { person["contactName"] = name }
      if let last { person["lastTouch"] = ["channel": "imessage", "date": last] }
      return person
    }
    // Deliberately in the worst possible file order: the junk is first, the real people are last.
    let persons: [[String: Any]] = [
      card("group-only", "Grace Group", closeness: 0, last: nil, named: true),
      card("loud-stranger", "Loud Stranger", closeness: 9000, last: "2026-08-01T09:00:00Z", named: false),
      card("stale-friend", "Stale Friend", closeness: 4000, last: "2021-01-04T09:00:00Z", named: true),
      card("quiet-recent", "Quiet Recent", closeness: 30, last: "2026-07-30T09:00:00Z", named: true),
      card("close-friend", "Close Friend", closeness: 2000, last: "2026-08-02T09:00:00Z", named: true),
    ]

    let pending = PeopleIdentityBridge.pendingPeople(persons: persons, links: .empty, cap: 3, now: now)
    XCTAssertEqual(
      pending.map(\.personID), ["close-friend", "quiet-recent", "stale-friend"],
      "a live relationship outranks a dead one whatever its volume (4,000 messages that stopped "
        + "five years ago lose to 30 from last week), and volume decides inside a bucket")
    XCTAssertFalse(
      pending.contains { $0.personID == "loud-stranger" },
      "9,000 messages from an unnamed handle is a service account, not a relationship")
    XCTAssertFalse(
      pending.contains { $0.personID == "group-only" },
      "a card with no direct message history has never exchanged a word with the user")

    // Ranking is a total order, so two runs over the same file always spend the budget the same way.
    XCTAssertEqual(
      PeopleIdentityBridge.pendingPeople(
        persons: persons.reversed(), links: .empty, cap: 3, now: now
      ).map(\.personID),
      pending.map(\.personID),
      "the order must come from the ranking, not from the file")
  }

  /// The bridge reuses a backend `Person` that already matches by name (the endpoint is idempotent
  /// by name, so creating one again would be a wasted round trip) and creates only what is missing.
  func testBridgeReusesAnExistingBackendPersonAndCreatesOnlyTheMissingOnes() async throws {
    let double = DirectoryDouble(existing: [Person(id: "uuid-existing", name: "Alice Anderson")])
    let resolved = await PeopleIdentityBridge.resolve(
      pending: [
        .init(personID: "alice-anderson", name: "Alice Anderson"),
        .init(personID: "bob-brown", name: "Bob Brown"),
      ],
      client: double)

    XCTAssertEqual(resolved["alice-anderson"], "uuid-existing")
    XCTAssertEqual(resolved["bob-brown"], "uuid-1")
    let created = await double.created
    XCTAssertEqual(created, ["Bob Brown"], "only the unknown person may be created")
    let listCalls = await double.listCalls
    XCTAssertEqual(listCalls, 1, "one directory read covers the whole run")
  }

  /// Only cards with a durable identity key are bridged. A handle-less card has nothing to key the
  /// binding on, so creating a backend `Person` for it would just recreate the name-only identity
  /// this change exists to remove — and a card already bridged is never resolved twice.
  func testBridgeSkipsHandlelessAlreadyBridgedAndNonHumanCards() throws {
    let persons: [[String: Any]] = [
      ["id": "alice-anderson", "name": "Alice Anderson", "handles": ["phones": ["5551234567"]]],
      ["id": "no-handles", "name": "Nora Nohandle"],
      [
        "id": "already", "name": "Already Bridged", "handles": ["phones": ["5550002222"]],
        "personUUID": "uuid-already",
      ],
      ["id": "phone-label", "name": "+15550003333", "handles": ["phones": ["5550003333"]]],
    ]
    let pending = PeopleIdentityBridge.pendingPeople(
      persons: persons, links: .empty, cap: PeopleIdentityBridge.maxResolutionsPerRun)

    XCTAssertEqual(pending.map(\.personID), ["alice-anderson"])
  }

  /// A card whose identity key is only in the link table (not yet re-written onto the card) is
  /// still bridgeable — the link table is the identity authority, the card is a projection.
  func testBridgeAcceptsAnIdentityKnownOnlyToTheLinkTable() throws {
    var links = PeopleIdentityLinks.empty
    links.record(key: "5551234567", personID: "alice-anderson")
    let pending = PeopleIdentityBridge.pendingPeople(
      persons: [["id": "alice-anderson", "name": "Alice Anderson"]], links: links, cap: 5)

    XCTAssertEqual(pending.map(\.personID), ["alice-anderson"])
  }

  /// `commit` writes the uuid to both the durable link table and the already-written cards, and
  /// the link table's binding is keyed on the identity key so it outlives the card.
  func testCommitPersistsTheUUIDToBothTheLinkTableAndTheCard() throws {
    let dir = try makeDirectory()
    var links = PeopleIdentityLinks.empty
    links.record(key: "5551234567", personID: "alice-anderson")
    PeopleIdentityStore.save(links, directory: dir)

    let peopleURL = dir.appendingPathComponent("people_intelligence.json")
    try JSONSerialization.data(withJSONObject: [
      "people": [["id": "alice-anderson", "name": "Alice Anderson"]]
    ]).write(to: peopleURL)

    PeopleIdentityBridge.commit(resolved: ["alice-anderson": "uuid-alice"], directory: dir)

    XCTAssertEqual(
      PeopleIdentityStore.load(directory: dir).personUUID(forKey: "5551234567"), "uuid-alice",
      "the binding must be keyed on the identity, not the name")
    let doc = try XCTUnwrap(
      JSONSerialization.jsonObject(with: try Data(contentsOf: peopleURL)) as? [String: Any])
    XCTAssertEqual(
      (doc["people"] as? [[String: Any]])?.first?["personUUID"] as? String, "uuid-alice")
  }

  // MARK: - Segment stamping

  /// The counterpart's backend uuid goes on the counterpart's segments only. That exact shape —
  /// one distinct non-user `person_id`, none on the user's turns — is what lets the backend
  /// attribute a 1:1 thread's memories to that person instead of leaving the subject unknown.
  func testTranscriptStampsTheCounterpartUUIDOnNonUserSegmentsOnly() throws {
    let messages = (0..<8).map { index in
      PeopleThreadIngest.RawMessage(
        fromMe: index.isMultiple(of: 2), text: "message \(index)",
        date: "2026-07-0\(index + 1)T10:00:00Z")
    }
    let built = try XCTUnwrap(
      PeopleThreadIngest.buildTranscript(
        contactName: "Alice Anderson", messages: messages, personUUID: "uuid-alice"))

    XCTAssertEqual(
      Set(built.segments.filter { !$0.is_user }.compactMap(\.person_id)), ["uuid-alice"],
      "every counterpart segment must name the same backend Person")
    XCTAssertTrue(
      built.segments.filter(\.is_user).allSatisfy { $0.person_id == nil },
      "the user's own turns must never carry a person_id")
  }

  /// Not yet bridged is not an error: the upload is simply unattributed, exactly as before.
  func testTranscriptWithoutAUUIDIsUnattributed() throws {
    let messages = (0..<8).map { index in
      PeopleThreadIngest.RawMessage(
        fromMe: index.isMultiple(of: 2), text: "message \(index)", date: "2026-07-01T10:00:00Z")
    }
    let built = try XCTUnwrap(
      PeopleThreadIngest.buildTranscript(contactName: "Alice Anderson", messages: messages))
    XCTAssertTrue(built.segments.allSatisfy { $0.person_id == nil })
  }

  /// A WhatsApp thread's per-channel person key must resolve to the same identity as the iMessage
  /// one: the channel prefix keeps the two *conversations* apart, never the two *people*.
  func testWhatsAppThreadResolvesTheSameIdentityAsIMessage() throws {
    XCTAssertEqual(PeopleThreadIngest.identityKey(personKey: "wa:5551234567"), "5551234567")
    XCTAssertEqual(PeopleThreadIngest.identityKey(personKey: "5551234567"), "5551234567")
  }

  // MARK: - Handle resolution

  /// A card that carries identity keys stays addressable after a rename — matching is on the
  /// phone, not on `slug(name)`.
  func testHandleResolutionMatchesOnIdentityNotOnTheDisplayName() throws {
    let handles = PersonHandleResolver.resolve(
      personID: "alice-anderson",
      contactName: "Alice Zheng",
      displayName: "Alice Zheng",
      identityKeys: PersonIdentityKeys(phones: ["5551234567"]),
      contacts: [
        ContactHandleRecord(
          name: "Alice Zheng", phones: ["+1 (555) 123-4567"], emails: ["alice@example.com"])
      ],
      exportFileURLs: [])

    XCTAssertEqual(handles.phones, ["+1 (555) 123-4567"])
    XCTAssertEqual(handles.emails, ["alice@example.com"])
  }

  /// Legacy principal: a card written before identity keys were persisted still resolves by name.
  func testLegacyCardWithoutIdentityKeysStillResolvesByName() throws {
    let handles = PersonHandleResolver.resolve(
      personID: "alice-anderson",
      contactName: "Alice Anderson",
      displayName: "Alice Anderson",
      contacts: [ContactHandleRecord(name: "Alice Anderson", phones: ["+15551234567"])],
      exportFileURLs: [])

    XCTAssertEqual(handles.phones, ["+15551234567"])
  }

  /// Identity keys must not widen the match: another contact's handles are never returned.
  func testIdentityMatchNeverReturnsAnotherPersonsHandles() throws {
    let handles = PersonHandleResolver.resolve(
      personID: "alice-anderson",
      contactName: nil,
      displayName: "Alice Anderson",
      identityKeys: PersonIdentityKeys(phones: ["5551234567"]),
      contacts: [ContactHandleRecord(name: "Bob Brown", phones: ["+15559876543"])],
      exportFileURLs: [])

    XCTAssertTrue(handles.isEmpty)
  }
}
