import XCTest

@testable import Omi_Computer

/// Exercises the Phase-3 narrative pass (`PeopleNarrative`) — the model-backed
/// `who` / `now` / `overall` / `facts` / `activities` / `openThreads` the profile renders and that
/// nothing in this repository used to write.
///
/// The contract under test is composition: the narrative merges *onto* the card the deterministic
/// engine produced without touching any field that engine owns, keyed strictly on the backend
/// `Person` uuid, and an ungrounded/empty field is removed rather than blanked. Plus the privacy
/// contract's device half — the request body carries no message content at all.
///
/// Hermetic: pure functions and a temp directory. No network, no Contacts, no live services.
final class PeopleNarrativeTests: XCTestCase {

  // MARK: - Fixtures

  /// A card carrying every field the deterministic engine writes, so "did the narrative clobber
  /// anything?" is checked against the real surface rather than a two-key stub.
  private func deterministicCard(uuid: String? = "pid-1") -> [String: Any] {
    var card: [String: Any] = [
      "id": "priya-shah",
      "name": "Priya Shah",
      "contactName": "Priya Shah",
      "aliases": ["Pri"],
      "relationship": "close · work",
      "closeness": 412.0,
      "channels": [["key": "imessage", "label": "iMessage", "count": 412]],
      "lastTouch": ["channel": "imessage", "date": "2026-07-20T10:00:00Z"],
      "connections": [["id": "sam-lee", "name": "Sam Lee", "weight": 1.4, "sources": ["imessage"]]],
      "circle": ["id": 2, "label": "Climbing", "size": 7],
      "groups": [["name": "Acme Team", "category": "work / venture"]],
      "affiliations": [["name": "Acme", "type": "company", "confidence": 0.8, "via": ["email: @acme.com"]]],
      "history_grounded": true,
      "photoPath": "/tmp/photos/priya-shah.jpg",
    ]
    if let uuid { card["personUUID"] = uuid }
    return card
  }

  private func dossier(
    personID: String = "pid-1",
    who: String? = "Priya is a climbing partner from Acme.",
    facts: [String] = ["Priya organizes the Thursday session."],
    openThreads: [String] = []
  ) -> PeopleNarrative.Dossier {
    PeopleNarrative.Dossier(
      personID: personID,
      who: who,
      facts: facts,
      openThreads: openThreads,
      claims: [PeopleNarrative.Claim(field: "who", text: who ?? "", evidence: ["m0"])],
      evidenceCount: 7,
      evidenceFingerprint: "fp-1")
  }

  private func makeTempDirectory() throws -> URL {
    let url = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-narrative-tests-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
    addTeardownBlock { try? FileManager.default.removeItem(at: url) }
    return url
  }

  // MARK: - Merge composes, never clobbers

  func testNarrativeMergesOntoTheCardWithoutTouchingDeterministicFields() throws {
    let before = deterministicCard()

    let merged = try XCTUnwrap(
      PeopleNarrative.merge(persons: [before], dossiers: [dossier()]).first)

    XCTAssertEqual(merged["who"] as? String, "Priya is a climbing partner from Acme.")
    XCTAssertEqual(merged["facts"] as? [String], ["Priya organizes the Thursday session."])
    XCTAssertNotNil(merged["narrative"], "provenance travels with the narrative")

    // Every field the deterministic engine owns must be byte-identical after the merge. This is
    // the whole reason the narrative is a separate pass instead of an edit to `createPeople`.
    for key in PeopleNarrative.deterministicKeys {
      XCTAssertEqual(
        String(describing: merged[key] ?? "<absent>"),
        String(describing: before[key] ?? "<absent>"),
        "`\(key)` is owned by the deterministic engine and must survive the narrative merge")
    }
  }

  func testTheTwoKeySetsDoNotOverlap() {
    let overlap = Set(PeopleNarrative.narrativeKeys)
      .intersection(PeopleNarrative.deterministicKeys)
    XCTAssertTrue(overlap.isEmpty, "narrative and deterministic ownership must be disjoint: \(overlap)")
  }

  func testProvenanceCarriesTheEvidenceBehindEachClaim() throws {
    let merged = try XCTUnwrap(
      PeopleNarrative.merge(persons: [deterministicCard()], dossiers: [dossier()]).first)

    let narrative = try XCTUnwrap(merged["narrative"] as? [String: Any])
    XCTAssertEqual(narrative["evidence_count"] as? Int, 7)
    XCTAssertEqual(narrative["evidence_fingerprint"] as? String, "fp-1")
    let claims = try XCTUnwrap(narrative["claims"] as? [[String: Any]])
    XCTAssertEqual(claims.first?["field"] as? String, "who")
    XCTAssertEqual(claims.first?["evidence"] as? [String], ["m0"])
  }

  // MARK: - Identity

  func testACardWithoutABackendPersonIDIsLeftAlone() throws {
    let card = deterministicCard(uuid: nil)

    let merged = try XCTUnwrap(
      PeopleNarrative.merge(persons: [card], dossiers: [dossier()]).first)

    for key in PeopleNarrative.narrativeKeys {
      XCTAssertNil(
        merged[key],
        "without a backend person id there is no safe match — this pass must not guess by name")
    }
  }

  func testMatchIsOnTheBackendUUIDNotTheLocalSlug() throws {
    // The dossier is keyed by the desktop slug, which must match nothing.
    let merged = try XCTUnwrap(
      PeopleNarrative.merge(persons: [deterministicCard()], dossiers: [dossier(personID: "priya-shah")]).first)

    XCTAssertNil(merged["who"], "a desktop slug is not a backend person id")
  }

  // MARK: - Absent, not blank

  func testAnEmptyFieldIsRemovedSoAStaleClaimCannotSurvive() throws {
    var card = deterministicCard()
    card["who"] = "Priya is a climbing partner from Acme."
    card["openThreads"] = ["Priya is waiting on the deposit."]
    card["narrative"] = ["evidence_count": 7]

    let refreshed = PeopleNarrative.Dossier(personID: "pid-1", who: nil, facts: [], openThreads: [])
    let merged = try XCTUnwrap(PeopleNarrative.merge(persons: [card], dossiers: [refreshed]).first)

    XCTAssertNil(merged["who"], "a field the backend could not ground must go absent, not blank")
    XCTAssertNil(merged["openThreads"])
    XCTAssertNil(merged["narrative"])
  }

  func testWhitespaceOnlyValuesCountAsAbsent() throws {
    let blank = PeopleNarrative.Dossier(
      personID: "pid-1", who: "   ", facts: ["", "  "], openThreads: [])

    let merged = try XCTUnwrap(
      PeopleNarrative.merge(persons: [deterministicCard()], dossiers: [blank]).first)

    XCTAssertNil(merged["who"])
    XCTAssertNil(merged["facts"])
  }

  func testMergeIsIdempotent() throws {
    let once = PeopleNarrative.merge(persons: [deterministicCard()], dossiers: [dossier()])
    let twice = PeopleNarrative.merge(persons: once, dossiers: [dossier()])

    XCTAssertEqual(
      String(describing: once.first?["who"] ?? ""), String(describing: twice.first?["who"] ?? ""))
    XCTAssertEqual(once.first?["facts"] as? [String], twice.first?["facts"] as? [String])
  }

  // MARK: - The request leaves no content behind

  func testRequestCarriesOnlyIDsAndFingerprints() throws {
    let items = [
      PeopleNarrative.RequestItem(person_id: "pid-1", known_fingerprint: "fp-1"),
      PeopleNarrative.RequestItem(person_id: "pid-2", known_fingerprint: nil),
    ]

    let data = try JSONEncoder().encode(items)
    let decoded = try XCTUnwrap(
      JSONSerialization.jsonObject(with: data) as? [[String: Any]])

    // The privacy contract's device half: redaction happens once, in
    // `PeopleThreadIngest.redact`, before a transcript is uploaded. This pass adds no second
    // egress path — it sends ids and hashes, so there is no message text here to redact.
    for entry in decoded {
      XCTAssertEqual(
        Set(entry.keys).subtracting(["person_id", "known_fingerprint"]), [],
        "the dossier request must never carry anything but ids and fingerprints")
    }
    let json = try XCTUnwrap(String(data: data, encoding: .utf8))
    XCTAssertFalse(json.contains("Priya"), "no names")
    XCTAssertFalse(json.contains("text"), "no message content")
  }

  // MARK: - Candidate selection

  func testGroundedPeopleGoFirstAndTheSetRotates() {
    var grounded = deterministicCard(uuid: "pid-grounded")
    grounded["history_grounded"] = true
    var ungrounded = deterministicCard(uuid: "pid-ungrounded")
    ungrounded.removeValue(forKey: "history_grounded")
    var refreshedLongAgo = deterministicCard(uuid: "pid-stale")
    refreshedLongAgo["history_grounded"] = true

    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let ledger: [String: PeopleNarrative.LedgerEntry] = [
      "pid-stale": .init(
        fingerprint: "fp-old",
        refreshedAt: now.timeIntervalSince1970 - PeopleNarrative.refreshAfter - 60)
    ]

    let picked = PeopleNarrative.candidates(
      persons: [refreshedLongAgo, ungrounded, grounded], ledger: ledger, now: now, cap: 10)

    XCTAssertEqual(
      picked.map(\.personUUID), ["pid-grounded", "pid-stale", "pid-ungrounded"],
      "never-asked grounded people first, then the stale one, then people with no known evidence")
    XCTAssertEqual(picked.first(where: { $0.personUUID == "pid-stale" })?.knownFingerprint, "fp-old")
  }

  func testARecentlyRefreshedPersonIsNotAskedAgain() {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    var card = deterministicCard()
    card["narrative"] = ["evidence_count": 7]
    let ledger: [String: PeopleNarrative.LedgerEntry] = [
      "pid-1": .init(
        fingerprint: "fp-1", refreshedAt: now.timeIntervalSince1970 - 60, producedNarrative: true)
    ]

    XCTAssertTrue(PeopleNarrative.candidates(persons: [card], ledger: ledger, now: now, cap: 10).isEmpty)
  }

  func testAPersonWhoNeverHadANarrativeIsNotReAskedEveryRun() {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    // Asked recently, answered "insufficient_evidence" — the card has no narrative and never had
    // one, so it must stay parked rather than eat the per-run budget on every sync.
    let ledger: [String: PeopleNarrative.LedgerEntry] = [
      "pid-1": .init(
        fingerprint: "fp-1", refreshedAt: now.timeIntervalSince1970 - 60, producedNarrative: false)
    ]

    XCTAssertTrue(
      PeopleNarrative.candidates(persons: [deterministicCard()], ledger: ledger, now: now, cap: 10).isEmpty)
  }

  func testALostNarrativeIsReAskedWithoutTheCachedFingerprint() throws {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    // The graph rewrote the people file from scratch and the narrative went with it. Re-asking with
    // the cached fingerprint would get `unchanged` back forever, so the fingerprint is dropped.
    let ledger: [String: PeopleNarrative.LedgerEntry] = [
      "pid-1": .init(
        fingerprint: "fp-1", refreshedAt: now.timeIntervalSince1970 - 60, producedNarrative: true)
    ]

    let picked = PeopleNarrative.candidates(
      persons: [deterministicCard()], ledger: ledger, now: now, cap: 10)

    XCTAssertEqual(picked.map(\.personUUID), ["pid-1"])
    XCTAssertNil(try XCTUnwrap(picked.first).knownFingerprint)
  }

  func testCandidateCountIsCapped() {
    let people = (0..<80).map { deterministicCard(uuid: "pid-\($0)") }

    let picked = PeopleNarrative.candidates(
      persons: people, ledger: [:], now: Date(), cap: PeopleNarrative.maxPeoplePerRun)

    XCTAssertEqual(picked.count, PeopleNarrative.maxPeoplePerRun)
  }

  // MARK: - Ledger

  func testSkippedPeopleAreStampedSoTheBudgetRotates() throws {
    let json = """
      {"dossiers": [], "skipped": [
        {"person_id": "pid-unchanged", "reason": "unchanged"},
        {"person_id": "pid-thin", "reason": "insufficient_evidence"},
        {"person_id": "pid-ghost", "reason": "unknown_person"}
      ]}
      """
    let response = try JSONDecoder().decode(
      PeopleNarrative.DossierResponse.self, from: Data(json.utf8))
    let asked = [
      PeopleNarrative.Candidate(personUUID: "pid-unchanged", knownFingerprint: "fp-1"),
      PeopleNarrative.Candidate(personUUID: "pid-thin", knownFingerprint: nil),
      PeopleNarrative.Candidate(personUUID: "pid-ghost", knownFingerprint: nil),
    ]

    let ledger = PeopleNarrative.updatedLedger(
      [:], response: response, asked: asked, now: Date(timeIntervalSince1970: 100))

    XCTAssertEqual(ledger["pid-unchanged"]?.fingerprint, "fp-1", "the cached dossier is still current")
    XCTAssertEqual(ledger["pid-thin"]?.refreshedAt, 100, "\"nothing to say\" is an answer worth remembering")
    XCTAssertNil(ledger["pid-ghost"], "an unknown person is not evidence of anything")
  }

  func testLedgerRoundTripsThroughDisk() throws {
    let dir = try makeTempDirectory()
    let entries = ["pid-1": PeopleNarrative.LedgerEntry(fingerprint: "fp-1", refreshedAt: 42)]

    PeopleNarrative.saveLedger(entries, directory: dir)

    XCTAssertEqual(PeopleNarrative.loadLedger(directory: dir), entries)
    XCTAssertEqual(PeopleNarrative.loadLedger(directory: try makeTempDirectory()), [:])
  }

  // MARK: - End-to-end write path

  func testApplyResponseWritesTheNarrativeAndKeepsUserCorrections() throws {
    let dir = try makeTempDirectory()
    let peopleURL = dir.appendingPathComponent(PeopleNarrative.peopleFileName)
    let doc: [String: Any] = ["generated_at": "2026-07-01T00:00:00Z", "people": [deterministicCard()]]
    try JSONSerialization.data(withJSONObject: doc).write(to: peopleURL)

    // The user already rejected this exact fact. A narrative refresh must not reinstate it.
    PeopleOverridesStore.save(
      PeopleOverrides(
        factEdits: [
          .init(id: "priya-shah", original: "Priya organizes the Thursday session.", corrected: "")
        ]),
      directory: dir)

    let response = try JSONDecoder().decode(
      PeopleNarrative.DossierResponse.self,
      from: Data(
        """
        {"dossiers": [{"person_id": "pid-1", "who": "Priya is a climbing partner from Acme.",
          "facts": ["Priya organizes the Thursday session.", "Priya leads the Acme design review."],
          "claims": [{"field": "who", "text": "Priya is a climbing partner from Acme.", "evidence": ["m0"]}],
          "evidence_count": 7, "evidence_fingerprint": "fp-1"}], "skipped": []}
        """.utf8))

    PeopleNarrative.applyResponse(
      response,
      asked: [PeopleNarrative.Candidate(personUUID: "pid-1", knownFingerprint: nil)],
      directory: dir,
      now: Date(timeIntervalSince1970: 500))

    let written = try XCTUnwrap(
      try JSONSerialization.jsonObject(with: Data(contentsOf: peopleURL)) as? [String: Any])
    let card = try XCTUnwrap((written["people"] as? [[String: Any]])?.first)

    XCTAssertEqual(card["who"] as? String, "Priya is a climbing partner from Acme.")
    XCTAssertEqual(
      card["facts"] as? [String], ["Priya leads the Acme design review."],
      "a fact the user rejected must stay rejected across a narrative refresh")
    XCTAssertEqual(card["relationship"] as? String, "close · work", "deterministic fields survive the write")
    XCTAssertEqual(
      PeopleNarrative.loadLedger(directory: dir)["pid-1"]?.fingerprint, "fp-1",
      "the fingerprint is cached so an unchanged person costs nothing next run")
  }

  func testApplyResponseIsANoOpWhenThereIsNoPeopleFile() throws {
    let dir = try makeTempDirectory()
    let response = try JSONDecoder().decode(
      PeopleNarrative.DossierResponse.self,
      from: Data(#"{"dossiers": [{"person_id": "pid-1", "who": "x"}], "skipped": []}"#.utf8))

    PeopleNarrative.applyResponse(response, asked: [], directory: dir, now: Date())

    XCTAssertFalse(
      FileManager.default.fileExists(
        atPath: dir.appendingPathComponent(PeopleNarrative.peopleFileName).path),
      "the narrative pass never creates the people file — the graph owns that")
  }
}
