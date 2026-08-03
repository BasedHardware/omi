import Contacts
import ObjectiveC
import XCTest

@testable import Omi_Computer

/// Puts this test process in the state CI is always in: **no address book**.
///
/// `PeopleGraphBuilder.build()` reaches Contacts twice — `loadContactsByPhone()` for names and
/// `PeopleContactPhotos.syncFromContacts` for thumbnails — and both are gated on
/// `CNContactStore.authorizationStatus(for: .contacts) == .authorized`. On a CI runner that is
/// always `.notDetermined`, so both return empty immediately. On a developer's Mac the *terminal*
/// holds the TCC grant, so the gate opens inside `xctest`, where the AddressBook XPC service is not
/// reachable — every enumeration then burns ~24s of CoreData retries and hundreds of error lines
/// before returning nothing useful. Measured: one cold-start test at 558s and 715 `CoreData: error`
/// lines, for data that is empty either way.
///
/// Forcing the status to `.notDetermined` makes the developer machine behave exactly like CI, so
/// the create path under test is the create path CI runs. It is done by replacing the class
/// method's implementation rather than by touching production code: `PeopleGraphBuilder` owns that
/// call site, this suite does not, and a test must not be able to change what ships.
///
/// Nothing here mocks a *result* — there is no fake address book and no injected names. The only
/// thing asserted away is the ability to read one, which is the definition of hermetic for this
/// pipeline: every name in the output must therefore have come from the synthetic export.
enum ContactsUnavailableInTests {
  /// Idempotent and thread-safe: a `static let` initializer runs exactly once, whichever test
  /// class asks for it first.
  static let install: Bool = {
    let selector = #selector(CNContactStore.authorizationStatus(for:))
    guard let method = class_getClassMethod(CNContactStore.self, selector) else { return false }
    let replacement: @convention(block) (AnyObject, CNEntityType) -> Int = { _, _ in
      CNAuthorizationStatus.notDetermined.rawValue
    }
    method_setImplementation(method, imp_implementationWithBlock(replacement))
    return CNContactStore.authorizationStatus(for: .contacts) == .notDetermined
  }()
}

/// **The contract a brand-new user's first People run must satisfy.**
///
/// This suite exists because the People tab shipped a UI for data no code in this repository
/// produced, and nothing noticed for months: the one machine it was evaluated on already had a
/// `people_intelligence.json` written out-of-tree, so `PeopleGraphBuilder.build()` took the
/// **merge** branch on every run. `createPeopleIntelligence` — the only branch a new user can ever
/// take — had never executed there. Roughly 200 existing tests passed the whole time because every
/// one of them either drove the pure sub-functions or drove the merge path.
///
/// When the create path was finally forced to run against the real export it produced:
///
///   1,825 people   (the out-of-tree file had 181, and its `stats` recorded featured 142 /
///                   dropped 121 — a selection stage this repository never had)
///   708 (38.8%)    display names that are nothing but a phone number
///   410            cards that were BOTH unnamed and never once messaged — graph nodes, not people
///   0              affiliations, 0 contact photos, 0 `history_grounded`
///   `who` / `now` / `overall` / `facts` — decoders and renderers, zero writers
///
/// So this suite drives the real create path end to end — `PeopleGraphBuilder.rebuildIfNeeded`
/// → `build` → `buildCanonicalPeople` / `buildGraph` / `buildCommunities` → `createPeople` →
/// `createPeopleIntelligence` → the on-disk `people_intelligence.json` — against a synthetic
/// export in a throwaway user directory that has **no** prior `people_intelligence.json`, and then
/// asserts the *shape of what a new user gets*. Driving `rebuildIfNeeded` (rather than reassembling
/// the stages in the test) is the whole point: `createPeopleIntelligence` is private, it is where
/// `stats` is assembled and the file is written, and a test that re-implements it would have missed
/// exactly the defect this suite is here to catch.
///
/// **Hermetic.** Synthetic exports only; no live Contacts (`loadContactsByPhone` /
/// `PeopleContactPhotos.syncFromContacts` both return empty unless Contacts is already authorized,
/// and every synthetic number is outside any real address book), no network, no sleeps, no
/// dependency on any developer's machine. The throwaway user id follows the same
/// Application-Support convention `RewindStorageTestIsolation` established, and is deleted on
/// teardown along with every UserDefaults value the run touched.
///
/// **Thresholds are contracts, not observations.** Every bound below is written against the
/// behaviour a new user is owed, with the reasoning stated at the assertion. Where a number was
/// unavoidable it is justified against both the observed failure and the reviewed reference file.
final class PeopleColdStartContractTests: XCTestCase {

  /// Prefix for this suite's throwaway user ids. Every directory it creates is deleted on teardown;
  /// the sweep below covers the case teardown never ran (a killed or crashed run), so a stale
  /// fixture can never be picked up by `resolveUserDir`'s "any users dir that has an export"
  /// fallback and turn a later run into a reader of test data.
  private static let userIDPrefix = "people-coldstart-contract-"

  override class func setUp() {
    super.setUp()
    _ = ContactsUnavailableInTests.install
    sweepStaleFixtures()
  }

  private static func sweepStaleFixtures() {
    let fm = FileManager.default
    guard let support = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask).first,
      let entries = try? fm.contentsOfDirectory(
        at: support.appendingPathComponent("Omi", isDirectory: true)
          .appendingPathComponent("users", isDirectory: true),
        includingPropertiesForKeys: nil, options: [.skipsHiddenFiles])
    else { return }
    for entry in entries where entry.lastPathComponent.hasPrefix(userIDPrefix) {
      try? fm.removeItem(at: entry)
    }
  }

  /// Wall-clock ceiling for one full cold start over this fixture. The pipeline is ~64 nodes of
  /// pure in-memory work plus a handful of small file writes — single-digit milliseconds. The
  /// budget is set at 15s only because that is comfortably below the ~24s a *single* address-book
  /// enumeration costs when it is reachable at all, so blowing it means the run left the fixture
  /// and went looking at the machine.
  private static let coldStartBudget: TimeInterval = 15

  // MARK: - What the cold-start create path owes each field the People UI decodes

  /// What a cold start must do about one JSON key that `PeopleIntelPerson`, `PersonExtrasRow`,
  /// `PersonConnectionDetail` or `PeopleExtrasFile` decodes and the People list / profile renders.
  ///
  /// This table is the machine-readable half of the rule that was violated. It is parsed by
  /// `desktop/macos/scripts/check_people_intel_field_writers.py`, which fails when a decoder gains
  /// a field that is not classified here — so a new renderer for a field nothing writes cannot land
  /// silently. See `desktop/macos/docs/people-intelligence-productization.md` → "Layer status".
  enum ColdStartExpectation: Sendable, Equatable {
    /// The create path must emit this key for at least one person on a first run.
    case produced
    /// No cold-start card may carry this key. The reason names the layer that actually owns it.
    case absentByDesign(String)
    /// Real behaviour depends on a live macOS service CI does not have, so presence is not
    /// asserted either way. Every entry here is a gap this suite deliberately cannot close.
    case notAssertableHermetically(String)
  }

  /// Person-level keys.
  static let personFieldContract: [String: ColdStartExpectation] = [
    "id": .produced,
    "name": .produced,
    "closeness": .produced,
    "channels": .produced,
    "lastTouch": .produced,
    "contactName": .produced,
    "relationship": .produced,
    "connections": .produced,
    "circle": .produced,
    "groups": .produced,
    "affiliations": .produced,
    "history_grounded": .produced,
    "handles": .produced,
    "personUUID": .produced,
    "needsConfirmation": .produced,
    "confirmReason": .produced,
    "who": .absentByDesign("Phase 3: only PeopleNarrative writes it, after a backend dossier call"),
    "now": .absentByDesign("Phase 3: only PeopleNarrative writes it, after a backend dossier call"),
    "overall": .absentByDesign(
      "Phase 3: only PeopleNarrative writes it, after a backend dossier call"),
    "facts": .absentByDesign(
      "Phase 3: only PeopleNarrative writes it, after a backend dossier call"),
    "activities": .absentByDesign(
      "Phase 3: only PeopleNarrative writes it, after a backend dossier call"),
    "openThreads": .absentByDesign(
      "Phase 3: only PeopleNarrative writes it, after a backend dossier call"),
    "role": .absentByDesign("Phase 3 model-backed; no in-repo writer at all"),
    "aliases": .absentByDesign("only a user-confirmed identity merge produces aliases"),
    "linkedin": .absentByDesign("no LinkedIn connector in-repo (Phase 2, 'next')"),
    "photoPath": .notAssertableHermetically(
      "needs an authorized macOS Contacts store holding thumbnails for the fixture's numbers"),
  ]

  /// Keys on each entry of `connections[]`.
  static let connectionFieldContract: [String: ColdStartExpectation] = [
    "id": .produced,
    "name": .produced,
    "context": .produced,
    "how": .produced,
    "type": .absentByDesign("Phase 3 relationship typing; no in-repo writer"),
    "confidence": .absentByDesign("Phase 3 relationship typing; no in-repo writer"),
  ]

  /// File-level keys.
  static let fileFieldContract: [String: ColdStartExpectation] = [
    "people": .produced,
    "community_meanings": .produced,
    "network_insights": .absentByDesign("decoded and never written by anything in this repository"),
  ]

  // MARK: - Fixture shape

  /// Group-only strangers: real identities in the graph (they are members of your group chats) who
  /// you have never messaged and whom nothing can name. 410 cards of exactly this kind reached the
  /// real cold-start file.
  private static let strangerCount = 48

  /// Synthetic, well outside any real address book, and each one's *last ten digits* differ in the
  /// leading block so no two stranger cards look like the same person.
  private static func strangerPhone(_ index: Int) -> String { "\(200 + index)5550100" }

  /// Canonical people the fixture resolves to: 16 named-or-messaged plus every stranger.
  private static let expectedCandidates = 16 + strangerCount

  /// The candidates that carry any identity-bearing signal at all — a name a human would recognise,
  /// or a message actually exchanged in either direction. A selection stage may be stricter than
  /// this (the fixture's one-way blast is messaged, unnamed, and should still not become a card);
  /// it must never be looser, because everything outside this set is a graph node, not a person.
  private static let qualifiedCandidateCeiling = 16

  /// Every human name the fixture asserts anywhere. Any other human name on a card came from the
  /// machine the test ran on, not from the export.
  private static let fixtureNames: Set<String> = [
    "Dana Kim", "Alice Chen", "Bob Ruiz", "Carol Diaz", "Carol Diez", "Frank Ito", "Grace Hall",
    "Henry Osei", "Iris Novak", "Jonas Weber", "Mira Patel", "Omar Haddad", "Priya Nair",
  ]

  /// Candidates that must never reach the People tab, and the class each one stands for.
  private static var mustNotSurviveIDs: [String: String] {
    var ids = ["12025550114": "one-way traffic from an unnamed sender — a blast, not a person"]
    for index in 0..<strangerCount {
      ids[strangerPhone(index)] = "only ever a member of somebody else's group chat"
    }
    return ids
  }

  /// Everyone the fixture messages at least 50 times. Selection that drops these has replaced one
  /// defect with a worse one, so they are asserted present by id.
  private static let mustSurviveIDs: Set<String> = [
    "dana-kim",  // 420 iMessage + 90 WhatsApp
    "alice-chen",  // 380
    "bob-ruiz",  // 260
    "mira-patel",  // 210, email identity
    "carol-diaz",  // 180
    "carol-diez",  // 140, one edit from Carol Diaz — the weak-identity case
    "omar-haddad",  // 130, email identity
    "frank-ito",  // 96
    "priya-nair",  // 88, WhatsApp-only
    "grace-hall",  // 74
    "12025550111",  // 64, deliberately unnamed: you message people who are not in Contacts
    "henry-osei",  // 58
  ]

  // MARK: - Driving the real create path

  private struct ColdStartResult: Sendable {
    /// The bytes `createPeopleIntelligence` actually wrote.
    let json: Data
    /// Canonical people the same fixture resolves to — the selection stage's input population,
    /// computed through the real `buildCanonicalPeople` rather than hardcoded.
    let candidateCount: Int
    let userDir: URL
    /// How long the whole pipeline took, so a run that reached off the fixture is visible.
    let elapsed: TimeInterval
  }

  private func runColdStart() async throws -> ColdStartResult {
    // Every run re-asserts it, because a suite that reads the developer's address book is both
    // non-hermetic and, in CI, a check that measures nothing.
    XCTAssertTrue(
      ContactsUnavailableInTests.install,
      "the cold start must run with no address book, exactly as CI does")
    XCTAssertEqual(
      CNContactStore.authorizationStatus(for: .contacts), .notDetermined,
      "Contacts must be unreachable for the duration of this suite")
    let started = Date()
    let uid = Self.userIDPrefix + UUID().uuidString
    let userDir = Self.userDirectory(for: uid)
    let fm = FileManager.default
    try fm.createDirectory(at: userDir, withIntermediateDirectories: true)
    addTeardownBlock { try? FileManager.default.removeItem(at: userDir) }

    let imessage = Self.imessageExportJSON()
    let whatsapp = Self.whatsappExportJSON()
    try XCTUnwrap(imessage.data(using: .utf8))
      .write(to: userDir.appendingPathComponent("imessage_export.json"))
    try XCTUnwrap(whatsapp.data(using: .utf8))
      .write(to: userDir.appendingPathComponent("whatsapp_export.json"))

    // A first run is not necessarily a run with nothing on disk: the deep thread ingest and the
    // backend identity bridge both write their own files, and `history_grounded` / `personUUID`
    // are read back out of them. Seeding both is what lets those two fields be asserted without a
    // network call — and both were zero in the real cold start.
    PeopleThreadIngest.appendLedger(
      directory: userDir, keys: ["synthetic-window"],
      personKeys: ["2025550101", "wa:2025550113"])
    var links = PeopleIdentityLinks()
    links.record(key: "2025550102", personID: "alice-chen", name: "Alice Chen")
    links.setPersonUUID("6f1a0d7c-6d3a-4a1e-9f2b-53c9d1e0a7b4", forPersonID: "alice-chen")
    PeopleIdentityStore.save(links, directory: userDir)

    // No `people_intelligence.json` exists, so `hasExistingPeople` is false and `build()` takes
    // the create branch. That is the only branch a new user can ever take.
    XCTAssertFalse(
      fm.fileExists(atPath: userDir.appendingPathComponent("people_intelligence.json").path),
      "the cold-start fixture must start with no people file, or the merge branch runs instead")

    let defaults = UserDefaults.standard
    let previousEnabled = defaults.object(forKey: DefaultsKey.peopleGraphBuild.rawValue) as? Bool
    let previousLastRun =
      defaults.object(forKey: DefaultsKey.peopleGraphLastRebuild.rawValue) as? Double
    addTeardownBlock {
      let defaults = UserDefaults.standard
      if let previousEnabled {
        defaults.set(previousEnabled, forKey: DefaultsKey.peopleGraphBuild.rawValue)
      } else {
        defaults.removeObject(forKey: DefaultsKey.peopleGraphBuild.rawValue)
      }
      if let previousLastRun {
        defaults.set(previousLastRun, forKey: DefaultsKey.peopleGraphLastRebuild.rawValue)
      } else {
        defaults.removeObject(forKey: DefaultsKey.peopleGraphLastRebuild.rawValue)
      }
    }
    defaults.set(true, forKey: DefaultsKey.peopleGraphBuild.rawValue)
    defaults.removeObject(forKey: DefaultsKey.peopleGraphLastRebuild.rawValue)

    await PeopleGraphBuilder.rebuildIfNeeded(uid: uid, force: true)

    let peopleURL = userDir.appendingPathComponent("people_intelligence.json")
    let json = try XCTUnwrap(
      try? Data(contentsOf: peopleURL),
      "the create path must write people_intelligence.json for a user with no backend file")

    // The selection stage's input population, through the real resolver on the same bytes.
    let root = PeopleGraphBuilder.mergedRoot(
      imessage: PeopleGraphBuilder.readExport(
        at: userDir.appendingPathComponent("imessage_export.json")),
      whatsapp: PeopleGraphBuilder.readExport(
        at: userDir.appendingPathComponent("whatsapp_export.json")))
    let candidates = PeopleGraphBuilder.buildCanonicalPeople(root: root, contactsByPhone: [:])

    let elapsed = Date().timeIntervalSince(started)
    XCTAssertLessThan(
      elapsed, Self.coldStartBudget,
      "a cold start over \(candidates.canonByID.count) synthetic nodes took \(Int(elapsed))s — "
        + "in-memory work does not cost that, so the run reached a live service")

    return ColdStartResult(
      json: json, candidateCount: candidates.canonByID.count, userDir: userDir, elapsed: elapsed)
  }

  // MARK: - The run itself is hermetic

  /// **Nothing in this file's output may have come from the machine it ran on.**
  ///
  /// The whole defect class started with a machine-specific artifact — a `people_intelligence.json`
  /// no code produced — so a guard that quietly reads the developer's address book would be the
  /// same mistake in a new costume, and it would measure nothing in CI where there is no address
  /// book at all. Every name on every card therefore has to trace back to the synthetic export:
  /// either a `contact_name` the fixture supplied, or the raw handle the pipeline falls back to.
  func testColdStartReadsNothingBeyondTheSyntheticExport() async throws {
    let result = try await runColdStart()
    let people = try Self.people(in: result.json)

    for person in people {
      let name = Self.string(person, "name")
      XCTAssertTrue(
        Self.fixtureNames.contains(name) || Self.isPhoneNumberShaped(name),
        "'\(name)' is not a name this fixture supplied and is not a handle fallback — it came from "
          + "the machine, which makes this suite non-hermetic and a no-op in CI")
      // With no address book there is no thumbnail to store, so a photo path here would mean the
      // avatar acquired a second, unclassified source.
      XCTAssertNil(
        person["photoPath"],
        "no address book was reachable, so nothing could have written a contact photo for "
          + "\(Self.string(person, "id")); if photos gained another source, reclassify photoPath")
    }
  }

  // MARK: - Population is bounded relative to the graph it came from

  /// **A graph with N nodes must not yield N person cards.**
  ///
  /// The invariant a selection stage guarantees is not a number, it is a qualification: a card is
  /// owed to somebody you can recognise or somebody you have actually talked to. A phone number
  /// sitting inside a group chat somebody else named is a node in a graph — promoting it to a
  /// person card is what turned 15 real relationships into 63 rows, and 181 into 1,825 for real.
  func testColdStartPromotesOnlyIdentifiedOrMessagedCandidatesToPeople() async throws {
    let result = try await runColdStart()
    let people = try Self.people(in: result.json)

    XCTAssertEqual(
      result.candidateCount, Self.expectedCandidates,
      "fixture drift: the graph must resolve exactly the candidate population this suite reasons about")

    XCTAssertLessThan(
      people.count, result.candidateCount,
      "a graph with \(result.candidateCount) nodes must not produce \(people.count) people — "
        + "every node became a card, which is the 1,825-person cold start")

    XCTAssertLessThanOrEqual(
      people.count, Self.qualifiedCandidateCeiling,
      "selection may be stricter than 'named or ever messaged', never looser: at most "
        + "\(Self.qualifiedCandidateCeiling) of these \(result.candidateCount) candidates carry an "
        + "identity-bearing signal")

    // The exact failure class, stated directly: 410 real cards were both unnamed and unmessaged.
    for person in people {
      let name = Self.string(person, "name")
      let closeness = (person["closeness"] as? Double) ?? 0
      XCTAssertFalse(
        Self.isPhoneNumberShaped(name) && closeness == 0,
        "\(Self.string(person, "id")) is a bare phone number you have never messaged — that is a "
          + "graph node, not a person")
    }

    let ids = Set(people.map { Self.string($0, "id") })
    for (id, why) in Self.mustNotSurviveIDs {
      XCTAssertFalse(ids.contains(id), "\(id) must not become a person card: \(why)")
    }
    for expected in Self.mustSurviveIDs {
      XCTAssertTrue(
        ids.contains(expected),
        "\(expected) exchanges 50+ messages with you — selection that drops them is a worse defect "
          + "than the one it fixes")
    }
  }

  /// **Every candidate is accounted for.** A selection stage that reports only what it kept cannot
  /// be audited: the out-of-tree file recorded `featured` and `dropped` precisely so the two sum
  /// back to what went in. The stats block in this repository reported neither, and its `people`
  /// count did not even match the array it sat next to (390 vs 181 in the reference file).
  func testColdStartStatsAccountForEveryCandidate() async throws {
    let result = try await runColdStart()
    let doc = try Self.document(in: result.json)
    let people = try Self.people(in: result.json)
    let stats = try XCTUnwrap(doc["stats"] as? [String: Any], "the create path must write stats")

    let featured = try XCTUnwrap(
      stats["featured"] as? Int,
      "stats must report how many candidates were featured; without it the selection stage is "
        + "unauditable")
    let dropped = try XCTUnwrap(
      stats["dropped"] as? Int,
      "stats must report how many candidates were dropped; without it a shrinking list is "
        + "indistinguishable from a broken one")

    XCTAssertEqual(
      featured, people.count, "stats.featured must equal the people array it describes")
    XCTAssertGreaterThanOrEqual(dropped, 0, "dropped is a count, never negative")
    XCTAssertEqual(
      featured + dropped, result.candidateCount,
      "featured + dropped must account for every canonical person the graph resolved")

    // The reference file said `people: 390` above an array of 181. A count next to the thing it
    // counts must agree with it.
    if let reported = stats["people"] as? Int {
      XCTAssertEqual(
        reported, people.count, "stats.people must equal the length of the people array")
    }
  }

  /// **A card the user cannot recognise is not intelligence.**
  ///
  /// The ceiling is 25%. Reasoning, both sides: the observed cold start was 38.8% phone-shaped
  /// names, and the reviewed 181-person reference file was 1 in 181 (0.6%). Some phone-shaped names
  /// are legitimate — you do message people who are not in your address book, and this fixture
  /// deliberately contains two of them — so the bound is not zero. 25% sits above anything a
  /// legitimate export produces here (2 of the qualified 15 = 13%) and well below the failure.
  func testColdStartUnnamedCardRatioIsBounded() async throws {
    let result = try await runColdStart()
    let people = try Self.people(in: result.json)
    XCTAssertFalse(people.isEmpty, "a cold start on a real export must produce people")

    let unnamed = people.filter { Self.isPhoneNumberShaped(Self.string($0, "name")) }
    let ratio = Double(unnamed.count) / Double(people.count)
    XCTAssertLessThanOrEqual(
      ratio, 0.25,
      "\(unnamed.count) of \(people.count) cards (\(Int(ratio * 100))%) are named by a phone "
        + "number; a large fraction of unrecognisable cards is a failure, not a warning")
  }

  // MARK: - Every field the profile renders is populated, or provably absent by design

  /// **A field the UI reads is either something the create path can produce, or an explicitly
  /// declared gap.** `who` / `now` / `overall` / `facts` had decoders and renderers and zero
  /// writers, and no test tied the two ends together. This one does: each key the People UI decodes
  /// is classified in `personFieldContract` / `connectionFieldContract` / `fileFieldContract`, and
  /// a static check refuses to let a decoder gain an unclassified field.
  func testColdStartEitherProducesEachRenderedFieldOrDeclaresItUnimplemented() async throws {
    let result = try await runColdStart()
    let doc = try Self.document(in: result.json)
    let people = try Self.people(in: result.json)
    let connections = people.flatMap { ($0["connections"] as? [[String: Any]]) ?? [] }
    XCTAssertFalse(
      connections.isEmpty, "the fixture must produce connections, or the connection table is moot")

    Self.assertContract(
      Self.personFieldContract, present: { key in people.contains { Self.isPopulated($0[key]) } },
      surface: "person card")
    Self.assertContract(
      Self.connectionFieldContract,
      present: { key in connections.contains { Self.isPopulated($0[key]) } },
      surface: "connections[] entry")
    Self.assertContract(
      Self.fileFieldContract, present: { key in Self.isPopulated(doc[key]) }, surface: "file")

    // The UI's own decoder must see what the writer wrote — a field written under a key the
    // decoder does not read is the same defect wearing the other hat.
    let context = PeopleProfileExtrasLoader.load(data: result.json)
    let dana = context.extras(for: "dana-kim")
    XCTAssertFalse(
      dana.affiliations.isEmpty, "PersonProfileExtras must decode the affiliations that were written")
    XCTAssertFalse(dana.groups.isEmpty, "PersonProfileExtras must decode the groups that were written")
    XCTAssertTrue(
      dana.historyGrounded, "PersonProfileExtras must decode history_grounded that was written")
    XCTAssertFalse(
      context.communityMeanings.isEmpty,
      "PeopleProfileContext must decode the community_meanings that were written")
  }

  // MARK: - The deterministic fields that claim to work actually appear

  /// Phase 2 is documented as **shipped** for `relationship`, `affiliations`,
  /// `community_meanings`, `connections[].how` and `history_grounded`. "Shipped" has to mean the
  /// value is on the card a new user opens; the real cold start emitted zero affiliations and zero
  /// `history_grounded` while the documentation said both were shipped.
  func testColdStartProducesTheDeterministicFieldsDocumentedAsShipped() async throws {
    let result = try await runColdStart()
    let doc = try Self.document(in: result.json)
    let people = try Self.people(in: result.json)
    let byID = Dictionary(people.map { (Self.string($0, "id"), $0) }, uniquingKeysWith: { a, _ in a })

    // --- relationship: a reach tier plus a group-chat context, never a sentence.
    let dana = try XCTUnwrap(byID["dana-kim"], "Dana is the fixture's closest contact")
    XCTAssertEqual(
      dana["relationship"] as? String, "close · work",
      "the top contact across two connectors, whose shared chats are mostly work, is 'close · work'")

    // --- affiliations: the real export carries no email addresses at all, so an organization has
    // to be derivable from group-chat evidence alone or the field is dead for every iMessage-only
    // user. Dana has no email identity anywhere in the fixture.
    let danaHandles = dana["handles"] as? [String: Any]
    XCTAssertTrue(
      ((danaHandles?["emails"] as? [String]) ?? []).isEmpty,
      "fixture drift: Dana must stay email-less, which is what makes her affiliation meaningful")
    let danaOrgs = try XCTUnwrap(
      dana["affiliations"] as? [[String: Any]],
      "a phone-only person named by two independent work chats must still get an organization; "
        + "the real cold start produced zero affiliations for every one of 1,825 people")
    XCTAssertTrue(
      danaOrgs.contains { ($0["name"] as? String) == "Northwind" },
      "two work chats naming Northwind corroborate each other")

    // --- community_meanings: written for categories that were actually inferred, and withheld for
    // the categorizer's own "we could not tell" bucket.
    let meanings = try XCTUnwrap(
      doc["community_meanings"] as? [String: String], "the file must carry a group glossary")
    let family = try XCTUnwrap(
      meanings["Kim Family"], "a family-category chat gets a plain-English gloss")
    XCTAssertTrue(
      family.lowercased().contains("family"),
      "the gloss must restate the category that was actually inferred, got: \(family)")
    // A chat the categorizer could not classify lands in its `social` fallback bucket. Whether that
    // bucket is glossed at all is the derivation layer's call; what it must never do is name a
    // category, because naming one reports an inference that never happened.
    if let unclassified = meanings["Alumni Directory 2019"] {
      let claimed = ["work", "family", "household", "friend", "trip", "event"]
        .filter { unclassified.lowercased().contains($0) }
      XCTAssertTrue(
        claimed.isEmpty,
        "the categorizer put this chat in its 'we could not tell' bucket, yet the gloss claims "
          + "\(claimed.joined(separator: "/")): \(unclassified)")
    }

    // --- connections[].how: derived from the shared groups and the connectors that carried them.
    let danaConnections = try XCTUnwrap(dana["connections"] as? [[String: Any]])
    let toCarolDiez = try XCTUnwrap(
      danaConnections.first { ($0["id"] as? String) == "carol-diez" },
      "Dana and Carol Diez share a chat on each connector")
    let how = try XCTUnwrap(toCarolDiez["how"] as? String, "every connection must explain itself")
    XCTAssertTrue(
      how.contains("Kim Family") || how.contains("Nair Family"),
      "the derivation must name a real shared group, got: \(how)")
    XCTAssertTrue(
      how.contains("iMessage") && how.contains("WhatsApp"),
      "co-occurring on two connectors is real corroboration and must be said, got: \(how)")

    // --- history_grounded: true only where the deep ingest really submitted that thread. Both
    // ledger key forms (bare phone, and the `wa:` WhatsApp form) must resolve.
    XCTAssertEqual(
      dana["history_grounded"] as? Bool, true, "Dana's thread is in the ingest ledger")
    XCTAssertEqual(
      byID["priya-nair"]?["history_grounded"] as? Bool, true,
      "a WhatsApp thread is grounded through its `wa:` ledger key")
    XCTAssertNil(
      byID["bob-ruiz"]?["history_grounded"],
      "an un-ingested person must not claim grounding — absent means 'not grounded'")

    // --- personUUID: the backend Person this card is bridged to, carried through from the durable
    // identity table rather than re-derived from a display name.
    XCTAssertEqual(
      byID["alice-chen"]?["personUUID"] as? String, "6f1a0d7c-6d3a-4a1e-9f2b-53c9d1e0a7b4",
      "a card already bridged to a backend Person must keep that binding on a fresh run")

    // --- weak identities are asked about rather than silently asserted.
    XCTAssertEqual(
      byID["carol-diaz"]?["needsConfirmation"] as? Bool, true,
      "two names one edit apart are a weak identity match and must be surfaced, not merged")
    XCTAssertFalse(
      ((doc["reviewQueue"] as? [[String: Any]]) ?? []).isEmpty,
      "the weak identity must reach the review queue the People tab renders")
  }

  // MARK: - Assertion helpers

  private static func assertContract(
    _ contract: [String: ColdStartExpectation], present: (String) -> Bool, surface: String,
    file: StaticString = #filePath, line: UInt = #line
  ) {
    for key in contract.keys.sorted() {
      switch contract[key] {
      case .produced:
        XCTAssertTrue(
          present(key),
          "\(surface) key '\(key)' is decoded and rendered but no \(surface) a new user gets "
            + "carries it — a renderer for a field the create path never writes",
          file: file, line: line)
      case .absentByDesign(let reason):
        XCTAssertFalse(
          present(key),
          "\(surface) key '\(key)' is declared not-implemented on a cold start (\(reason)); it is "
            + "now being written, so update the contract table and "
            + "desktop/macos/docs/people-intelligence-productization.md",
          file: file, line: line)
      case .notAssertableHermetically, .none:
        continue
      }
    }
  }

  /// Absent, empty and `false` all mean "we have nothing here"; the pipeline's own rule is that a
  /// key it cannot fill honestly is omitted, so an empty value must not count as produced.
  private static func isPopulated(_ value: Any?) -> Bool {
    switch value {
    case .none: return false
    case let text as String: return !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    case let flag as Bool: return flag
    case let list as [Any]: return !list.isEmpty
    case let dict as [String: Any]: return !dict.isEmpty
    case let number as NSNumber: return number != 0
    default: return true
    }
  }

  /// A display name that is nothing but a phone number.
  private static func isPhoneNumberShaped(_ name: String) -> Bool {
    let digits = name.filter(\.isNumber).count
    guard digits >= 7 else { return false }
    return name.allSatisfy { $0.isNumber || " +-().".contains($0) }
  }

  private static func string(_ person: [String: Any], _ key: String) -> String {
    (person[key] as? String) ?? ""
  }

  private static func document(in json: Data) throws -> [String: Any] {
    try XCTUnwrap(
      (try? JSONSerialization.jsonObject(with: json)) as? [String: Any],
      "people_intelligence.json must be a JSON object")
  }

  private static func people(in json: Data) throws -> [[String: Any]] {
    try XCTUnwrap(
      try document(in: json)["people"] as? [[String: Any]],
      "people_intelligence.json must carry a people array")
  }

  private static func userDirectory(for uid: String) -> URL {
    let appSupport = FileManager.default
      .urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
    return
      appSupport
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(uid, isDirectory: true)
  }

  // MARK: - Synthetic exports

  // Modeled on the field shape of the real per-user exports — `handles[] { handle, phone_last10,
  // contact_name?, message_count, last_date }` and `groups[] { display_name, member_count,
  // members[{ handle, phone_last10 }] }` — with every name, handle and number synthesized. No
  // personal content is copied into this repository.
  //
  // One shape note that carries the whole point of the fixture: the production **iMessage**
  // exporter writes no `contact_name` at all, so on a real machine those names come from the
  // Contacts framework, and CI has no Contacts. The fixture therefore supplies `contact_name` on
  // the handles a populated address book would have named, and deliberately omits it on two
  // heavily-messaged handles to model contacts macOS genuinely cannot name. The **WhatsApp**
  // exporter does write `contact_name`, so those entries mirror production exactly.

  private static func imessageExportJSON() -> String {
    // (identity key, contact name if a source could give one, sent, received, last message)
    let handles: [(key: String, name: String?, sent: Int, received: Int, last: String)] = [
      ("2025550101", "Dana Kim", 210, 210, "2026-07-30T09:00:00Z"),
      ("2025550102", "Alice Chen", 190, 190, "2026-07-28T09:00:00Z"),
      ("2025550103", "Bob Ruiz", 130, 130, "2026-07-26T09:00:00Z"),
      ("2025550104", "Carol Diaz", 90, 90, "2026-07-24T09:00:00Z"),
      ("2025550105", "Carol Diez", 70, 70, "2026-07-22T09:00:00Z"),
      ("2025550106", "Frank Ito", 48, 48, "2026-07-20T09:00:00Z"),
      ("2025550107", "Grace Hall", 37, 37, "2026-07-18T09:00:00Z"),
      ("2025550108", "Henry Osei", 29, 29, "2026-07-16T09:00:00Z"),
      ("2025550109", "Iris Novak", 16, 17, "2026-07-14T09:00:00Z"),
      ("2025550110", "Jonas Weber", 10, 11, "2026-07-12T09:00:00Z"),
      // Two people you talk with who are in neither Contacts nor any connector's name list. Their
      // cards read as phone numbers, and dropping them would be a worse defect than keeping them.
      ("2025550111", nil, 30, 34, "2026-07-10T09:00:00Z"),
      ("2025550112", nil, 12, 15, "2026-07-08T09:00:00Z"),
      // Traffic that only ever arrived: a delivery/marketing sender nothing can name.
      ("2025550114", nil, 0, 40, "2026-07-06T09:00:00Z"),
      // Two identities addressed by email rather than by phone, which is what makes the
      // email-domain half of the affiliation rule reachable at all.
      ("mira@northwind.com", "Mira Patel", 105, 105, "2026-07-29T09:00:00Z"),
      ("omar@northwind.com", "Omar Haddad", 65, 65, "2026-07-21T09:00:00Z"),
    ]
    let handleJSON = handles.map { entry -> String in
      let name = entry.name.map { "\"contact_name\": \"\($0)\", " } ?? ""
      let identity =
        entry.key.contains("@")
        ? "\"handle\": \"\(entry.key)\""
        : "\"handle\": \"+1\(entry.key)\", \"phone_last10\": \"\(entry.key)\""
      return """
        { \(identity), \(name)"message_count": \(entry.sent + entry.received), \
        "sent": \(entry.sent), "received": \(entry.received), "last_date": "\(entry.last)" }
        """
    }

    var groups: [String] = [
      group(
        "Northwind Interns",
        members: ["2025550101", "2025550102", "2025550103"],
        emails: ["mira@northwind.com", "omar@northwind.com"]),
      group(
        "Northwind Cohort 2026",
        members: ["2025550101", "2025550102", "2025550103", "2025550104"]),
      group("Northwind Board", members: ["2025550105"], emails: ["mira@northwind.com", "omar@northwind.com"]),
      group("Kim Family", members: ["2025550101", "2025550105", "2025550106"]),
      group("Tahoe Trip 2026", members: ["2025550101", "2025550102", "2025550107", "2025550108"]),
      group("725 Ashby Ave", members: ["2025550101", "2025550102", "2025550103"]),
    ]
    // Three large, generically named chats whose other members you have never messaged. This is
    // where the 48 strangers live, and it is the exact shape that inflated the real cold start.
    let noiseNames = ["Alumni Directory 2019", "Building Residents", "Conference Attendees 2025"]
    for (index, name) in noiseNames.enumerated() {
      let slice = (index * 16)..<((index + 1) * 16)
      groups.append(
        group(name, members: ["2025550101", "2025550102"] + slice.map(strangerPhone)))
    }

    return """
      { "generated_at": "2026-08-01T09:00:00Z", "total_messages": 2093,
        "handles": [\(handleJSON.joined(separator: ",\n"))],
        "groups": [\(groups.joined(separator: ",\n"))] }
      """
  }

  private static func whatsappExportJSON() -> String {
    """
    { "generated_at": "2026-08-01T09:00:00Z",
      "handles": [
        { "handle": "+12025550101", "phone_last10": "2025550101", "contact_name": "Dana Kim",
          "message_count": 90, "sent": 45, "received": 45, "last_date": "2026-07-31T09:00:00Z" },
        { "handle": "+12025550113", "phone_last10": "2025550113", "contact_name": "Priya Nair",
          "message_count": 88, "sent": 40, "received": 48, "last_date": "2026-07-27T09:00:00Z" }
      ],
      "groups": [\(group("Nair Family", members: ["2025550101", "2025550113", "2025550105"]))] }
    """
  }

  private static func group(_ name: String, members: [String], emails: [String] = []) -> String {
    let phoneMembers = members.map { "{ \"phone_last10\": \"\($0)\" }" }
    let emailMembers = emails.map { "{ \"handle\": \"\($0)\" }" }
    let all = phoneMembers + emailMembers
    return """
      { "display_name": "\(name)", "member_count": \(all.count),
        "members": [\(all.joined(separator: ", "))] }
      """
  }
}
