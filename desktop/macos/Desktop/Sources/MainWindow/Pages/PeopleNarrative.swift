import Foundation

/// Phase-3 of `desktop/macos/docs/people-intelligence-productization.md`: the **model-backed**
/// per-person narrative (`who` / `now` / `overall` / `facts` / `activities` / `openThreads`).
///
/// `PersonProfilePage` has always rendered these fields and nothing in this repository ever wrote
/// them, so on every real machine those sections were permanently empty — they existed only in
/// files produced by an out-of-tree prototype. This file is the in-repo producer.
///
/// **It is a separate pass, not a change to the graph.** `PeopleGraphBuilder.createPeople` keeps
/// producing exactly the deterministic card it produced before; this runs afterwards and folds the
/// narrative onto that card. Nothing here can alter a deterministic field — `merge` writes only the
/// six narrative keys plus its own provenance blob, and `narrativeKeys` ∩ `deterministicKeys` is
/// asserted empty by the tests.
///
/// **Privacy.** The request body carries person ids and fingerprints — no message text, no names,
/// no transcripts. The narrative is synthesized on the backend from evidence that is *already on
/// the account*: memories Omi extracted from conversations the user consented to process, which for
/// messaging threads means the bounded, redacted window `PeopleThreadIngest.buildTranscript`
/// uploaded (phone numbers, emails and OTP codes stripped by `PeopleThreadIngest.redact` before
/// anything left this machine, last 40 messages only). This pass introduces no new data leaving the
/// device, and deliberately does not re-implement redaction — there is exactly one redactor.
///
/// **Bounds.** Gated on the same consent flag as the rest of the People pipeline, self-throttled to
/// `minRefreshInterval`, capped at `maxPeoplePerRun` people per run, and every person's dossier is
/// cached locally with the fingerprint of the evidence it came from — a person whose evidence has
/// not changed is reported `unchanged` by the server and costs no model call.
enum PeopleNarrative {

  // MARK: - Bounds

  /// People asked about per run. Must not exceed the server's per-request cap
  /// (`MAX_PEOPLE_PER_REQUEST`), because one run is exactly one request. A 200-person address book
  /// is therefore walked across successive runs rather than in one burst — roughly four days of
  /// normal use for a first pass, after which almost every person answers `unchanged` for free.
  static let maxPeoplePerRun = 12

  /// Minimum spacing between runs. Far longer than the graph's 5-minute sync because a narrative
  /// only changes when new memories land, which is a slow signal, and because each refreshed
  /// person costs a model call.
  static let minRefreshInterval: TimeInterval = 6 * 60 * 60

  /// How long a cached dossier is trusted without re-asking, even when its fingerprint is
  /// unchanged. Re-asking on an unchanged fingerprint is cheap (the server answers `unchanged`
  /// without a model call) but not free, so it is spaced out.
  static let refreshAfter: TimeInterval = 7 * 24 * 60 * 60

  static let ledgerFileName = "people_narrative_ledger.json"
  static let peopleFileName = "people_intelligence.json"

  /// The only keys this pass is allowed to write onto a person card.
  static let narrativeKeys = ["who", "now", "overall", "facts", "activities", "openThreads", "narrative"]

  /// Keys owned by the deterministic engine. Listed so the contract "narrative never clobbers
  /// deterministic output" is a thing a test can check rather than a thing a reviewer must notice.
  static let deterministicKeys = [
    "id", "personUUID", "name", "contactName", "aliases", "relationship", "closeness", "channels",
    "lastTouch", "connections", "circle", "groups", "affiliations", "history_grounded", "photoPath",
    "identity", "needsConfirmation", "confirmReason",
  ]

  // MARK: - Wire types

  /// Provenance for one emitted sentence or list item: which field it landed in, its exact text,
  /// and the evidence the backend cited for it. Rendered by the profile to explain a claim, and the
  /// handle a user's correction in `people_overrides.json` is correcting.
  struct Claim: Decodable, Equatable, Sendable {
    let field: String
    let text: String
    let evidence: [String]

    enum CodingKeys: String, CodingKey { case field, text, evidence }

    init(from decoder: Decoder) throws {
      let c = try decoder.container(keyedBy: CodingKeys.self)
      field = (try c.decodeIfPresent(String.self, forKey: .field)) ?? ""
      text = (try c.decodeIfPresent(String.self, forKey: .text)) ?? ""
      evidence = (try c.decodeIfPresent([String].self, forKey: .evidence)) ?? []
    }

    init(field: String, text: String, evidence: [String]) {
      self.field = field
      self.text = text
      self.evidence = evidence
    }

    var json: [String: Any] { ["field": field, "text": text, "evidence": evidence] }
  }

  /// One person's narrative as the backend returned it. Every field is optional/empty-tolerant:
  /// the backend drops anything it could not ground, so "absent" is the expected common case.
  struct Dossier: Decodable, Equatable, Sendable {
    let personID: String
    let who: String?
    let now: String?
    let overall: String?
    let facts: [String]
    let activities: [String]
    let openThreads: [String]
    let claims: [Claim]
    let evidenceCount: Int
    let evidenceFingerprint: String

    enum CodingKeys: String, CodingKey {
      case personID = "person_id"
      case who, now, overall, facts, activities, claims
      case openThreads = "open_threads"
      case evidenceCount = "evidence_count"
      case evidenceFingerprint = "evidence_fingerprint"
    }

    init(from decoder: Decoder) throws {
      let c = try decoder.container(keyedBy: CodingKeys.self)
      personID = (try c.decodeIfPresent(String.self, forKey: .personID)) ?? ""
      who = try c.decodeIfPresent(String.self, forKey: .who)
      now = try c.decodeIfPresent(String.self, forKey: .now)
      overall = try c.decodeIfPresent(String.self, forKey: .overall)
      facts = (try c.decodeIfPresent([String].self, forKey: .facts)) ?? []
      activities = (try c.decodeIfPresent([String].self, forKey: .activities)) ?? []
      openThreads = (try c.decodeIfPresent([String].self, forKey: .openThreads)) ?? []
      claims = (try c.decodeIfPresent([Claim].self, forKey: .claims)) ?? []
      evidenceCount = (try c.decodeIfPresent(Int.self, forKey: .evidenceCount)) ?? 0
      evidenceFingerprint = (try c.decodeIfPresent(String.self, forKey: .evidenceFingerprint)) ?? ""
    }

    init(
      personID: String, who: String? = nil, now: String? = nil, overall: String? = nil,
      facts: [String] = [], activities: [String] = [], openThreads: [String] = [],
      claims: [Claim] = [], evidenceCount: Int = 0, evidenceFingerprint: String = ""
    ) {
      self.personID = personID
      self.who = who
      self.now = now
      self.overall = overall
      self.facts = facts
      self.activities = activities
      self.openThreads = openThreads
      self.claims = claims
      self.evidenceCount = evidenceCount
      self.evidenceFingerprint = evidenceFingerprint
    }
  }

  struct SkippedPerson: Decodable, Equatable, Sendable {
    let personID: String
    let reason: String

    enum CodingKeys: String, CodingKey {
      case personID = "person_id"
      case reason
    }

    init(from decoder: Decoder) throws {
      let c = try decoder.container(keyedBy: CodingKeys.self)
      personID = (try c.decodeIfPresent(String.self, forKey: .personID)) ?? ""
      reason = (try c.decodeIfPresent(String.self, forKey: .reason)) ?? ""
    }
  }

  struct DossierResponse: Decodable, Sendable {
    let dossiers: [Dossier]
    let skipped: [SkippedPerson]

    enum CodingKeys: String, CodingKey { case dossiers, skipped }

    init(from decoder: Decoder) throws {
      let c = try decoder.container(keyedBy: CodingKeys.self)
      dossiers = (try c.decodeIfPresent([Dossier].self, forKey: .dossiers)) ?? []
      skipped = (try c.decodeIfPresent([SkippedPerson].self, forKey: .skipped)) ?? []
    }
  }

  /// One entry of the request body. The entire payload is ids and hashes — see the privacy note
  /// at the top of this file, and `PeopleNarrativeTests.testRequestCarriesNoMessageContent`.
  struct RequestItem: Encodable, Equatable, Sendable {
    let person_id: String
    let known_fingerprint: String?
  }

  // MARK: - Merge (pure)

  /// Fold dossiers onto person cards, keyed by the backend `Person` uuid the card carries as
  /// `personUUID`.
  ///
  /// Rules, all of which the tests pin:
  ///
  ///   - **Keyed on the backend uuid, never on a name or the desktop slug.** A card without a
  ///     `personUUID` is returned untouched: this pass has no resolver of its own and must not
  ///     invent one.
  ///   - **Deterministic fields are never written.** Only `narrativeKeys` are set.
  ///   - **Empty means absent.** A field the backend could not ground arrives null/empty and is
  ///     *removed* from the card rather than written as `""`/`[]`, so a stale narrative from an
  ///     earlier run cannot survive as a claim the current evidence no longer supports.
  ///   - **Idempotent.** Merging the same dossiers twice yields the same cards.
  ///
  /// Pure — no IO, no network, no clock.
  static func merge(persons: [[String: Any]], dossiers: [Dossier]) -> [[String: Any]] {
    guard !dossiers.isEmpty else { return persons }
    var byUUID: [String: Dossier] = [:]
    for dossier in dossiers where !dossier.personID.isEmpty {
      byUUID[dossier.personID] = dossier
    }
    guard !byUUID.isEmpty else { return persons }

    return persons.map { person in
      guard
        let uuid = (person["personUUID"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines),
        !uuid.isEmpty, let dossier = byUUID[uuid]
      else { return person }
      return apply(dossier, to: person)
    }
  }

  /// Write one dossier onto one card. Split out so the "absent, not blank" rule is stated once.
  static func apply(_ dossier: Dossier, to person: [String: Any]) -> [String: Any] {
    var out = person

    func setText(_ key: String, _ value: String?) {
      let text = (value ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
      if text.isEmpty {
        out.removeValue(forKey: key)
      } else {
        out[key] = text
      }
    }

    func setList(_ key: String, _ values: [String]) {
      let items =
        values
        .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
        .filter { !$0.isEmpty }
      if items.isEmpty {
        out.removeValue(forKey: key)
      } else {
        out[key] = items
      }
    }

    setText("who", dossier.who)
    setText("now", dossier.now)
    setText("overall", dossier.overall)
    setList("facts", dossier.facts)
    setList("activities", dossier.activities)
    setList("openThreads", dossier.openThreads)

    let claims = dossier.claims.filter { !$0.field.isEmpty && !$0.text.isEmpty }
    if claims.isEmpty {
      out.removeValue(forKey: "narrative")
    } else {
      out["narrative"] = [
        "evidence_count": dossier.evidenceCount,
        "evidence_fingerprint": dossier.evidenceFingerprint,
        "claims": claims.map(\.json),
      ]
    }
    return out
  }

  // MARK: - Candidate selection (pure)

  /// One person this run may ask about.
  struct Candidate: Equatable, Sendable {
    let personUUID: String
    let knownFingerprint: String?
  }

  /// Choose which people to refresh. Ordered so a first pass spends its budget where the answer is
  /// most likely to be non-empty and most likely to be looked at:
  ///
  ///   1. people whose 1:1 thread has actually been ingested (`history_grounded`) — the only cards
  ///      where evidence is known to exist on the account,
  ///   2. never-refreshed before already-refreshed,
  ///   3. oldest refresh first, so the set rotates instead of re-asking about the same people,
  ///   4. closeness as the final tiebreak.
  ///
  /// A card with no `personUUID` is not a candidate: the backend dossier is keyed by the backend
  /// person id and this pass does not resolve identities.
  static func candidates(
    persons: [[String: Any]], ledger: [String: LedgerEntry], now: Date, cap: Int
  ) -> [Candidate] {
    struct Row {
      let uuid: String
      let grounded: Bool
      let refreshedAt: Double?
      let closeness: Double
      let fingerprint: String?
    }

    var rows: [Row] = []
    var seen = Set<String>()
    for person in persons {
      guard
        let uuid = (person["personUUID"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines),
        !uuid.isEmpty, !seen.contains(uuid)
      else { continue }
      let entry = ledger[uuid]
      // Recently refreshed: nothing to ask about yet — unless the narrative that refresh produced
      // is no longer on the card. That happens when the graph rewrites `people_intelligence.json`
      // from scratch (a fresh-user create path after the file was lost), and without this the
      // fingerprint in the ledger would keep the server answering `unchanged` forever and the
      // profile would stay empty.
      if let entry, now.timeIntervalSince1970 - entry.refreshedAt < refreshAfter,
        !(entry.producedNarrative && person["narrative"] == nil)
      {
        continue
      }
      seen.insert(uuid)
      // A card that lost the narrative it once had must be asked *without* the cached fingerprint,
      // otherwise the server correctly answers `unchanged` and the profile never refills.
      let lostNarrative = (entry?.producedNarrative ?? false) && person["narrative"] == nil
      rows.append(
        Row(
          uuid: uuid,
          grounded: (person["history_grounded"] as? Bool) == true,
          refreshedAt: entry?.refreshedAt,
          closeness: (person["closeness"] as? Double) ?? 0,
          fingerprint: lostNarrative ? nil : entry?.fingerprint))
    }

    rows.sort { lhs, rhs in
      if lhs.grounded != rhs.grounded { return lhs.grounded }
      let lhsRefreshed = lhs.refreshedAt ?? -1
      let rhsRefreshed = rhs.refreshedAt ?? -1
      if lhsRefreshed != rhsRefreshed { return lhsRefreshed < rhsRefreshed }
      if lhs.closeness != rhs.closeness { return lhs.closeness > rhs.closeness }
      return lhs.uuid < rhs.uuid
    }

    return rows.prefix(max(cap, 0)).map {
      Candidate(personUUID: $0.uuid, knownFingerprint: $0.fingerprint)
    }
  }

  // MARK: - Ledger

  /// What we last asked about a person, and what the evidence hashed to then. The fingerprint is
  /// what makes an unchanged person free: the server compares it and answers `unchanged` without
  /// running a model.
  struct LedgerEntry: Codable, Equatable, Sendable {
    var fingerprint: String
    var refreshedAt: Double
    /// Whether that refresh actually produced a narrative. Distinguishes "we asked and there was
    /// nothing to say" from "we asked and wrote a profile", which is what lets `candidates` notice
    /// a narrative that has since been lost from the card without re-asking about every person who
    /// legitimately has none.
    var producedNarrative: Bool

    init(fingerprint: String, refreshedAt: Double, producedNarrative: Bool = false) {
      self.fingerprint = fingerprint
      self.refreshedAt = refreshedAt
      self.producedNarrative = producedNarrative
    }

    enum CodingKeys: String, CodingKey { case fingerprint, refreshedAt, producedNarrative }

    init(from decoder: Decoder) throws {
      let c = try decoder.container(keyedBy: CodingKeys.self)
      fingerprint = (try c.decodeIfPresent(String.self, forKey: .fingerprint)) ?? ""
      refreshedAt = (try c.decodeIfPresent(Double.self, forKey: .refreshedAt)) ?? 0
      // Absent in a ledger written before this field existed: reads as "no narrative", the
      // conservative direction (at worst one extra ask, which the server answers cheaply).
      producedNarrative = (try c.decodeIfPresent(Bool.self, forKey: .producedNarrative)) ?? false
    }
  }

  private struct Ledger: Codable {
    var version: Int
    var entries: [String: LedgerEntry]
  }

  /// A missing or corrupt ledger reads as empty — worst case a person is asked about again, which
  /// the server answers cheaply.
  static func loadLedger(directory: URL) -> [String: LedgerEntry] {
    let url = directory.appendingPathComponent(ledgerFileName)
    guard let data = try? Data(contentsOf: url),
      let ledger = try? JSONDecoder().decode(Ledger.self, from: data)
    else { return [:] }
    return ledger.entries
  }

  /// Merge this run's outcomes into the stored ledger. Best-effort — a write failure only means
  /// those people are re-evaluated on a later run.
  static func saveLedger(_ entries: [String: LedgerEntry], directory: URL) {
    let url = directory.appendingPathComponent(ledgerFileName)
    do {
      let encoder = JSONEncoder()
      encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
      let data = try encoder.encode(Ledger(version: 1, entries: entries))
      try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
      try data.write(to: url, options: .atomic)
    } catch {
      // Non-fatal; see loadLedger.
    }
  }

  /// Fold one response into the ledger. `unchanged` and `insufficient_evidence` both stamp a
  /// refresh time: the first because the cached answer is current, the second because "there is
  /// nothing to say" is itself an answer and re-asking every run would spend the budget on the
  /// people least likely to ever have a narrative.
  static func updatedLedger(
    _ ledger: [String: LedgerEntry], response: DossierResponse, asked: [Candidate], now: Date
  ) -> [String: LedgerEntry] {
    var out = ledger
    let stamp = now.timeIntervalSince1970
    for dossier in response.dossiers where !dossier.personID.isEmpty {
      out[dossier.personID] = LedgerEntry(
        fingerprint: dossier.evidenceFingerprint, refreshedAt: stamp, producedNarrative: true)
    }
    let askedByID = Dictionary(asked.map { ($0.personUUID, $0) }, uniquingKeysWith: { first, _ in first })
    for skipped in response.skipped where !skipped.personID.isEmpty {
      guard skipped.reason != "unknown_person" else { continue }
      let stored = out[skipped.personID]
      let previous = askedByID[skipped.personID]?.knownFingerprint ?? stored?.fingerprint ?? ""
      // `unchanged` means the cached narrative is still current, so whatever the last run produced
      // is still what the card should carry.
      out[skipped.personID] = LedgerEntry(
        fingerprint: previous,
        refreshedAt: stamp,
        producedNarrative: skipped.reason == "unchanged" && (stored?.producedNarrative ?? false))
    }
    return out
  }

  // MARK: - Entry point (gated, throttled, off-main, silent)

  /// Refresh the narrative layer for a bounded slice of the address book and cache the result into
  /// `people_intelligence.json`, which is exactly where the privacy contract says it belongs.
  ///
  /// Self-gates on the People consent flag and its own throttle, so it is cheap to call from the
  /// same continuous-sync seams the graph uses. Every failure — not signed in, offline, no people
  /// file, no card carrying a backend person id — is a silent no-op.
  static func refreshIfNeeded(uid: String?, force: Bool = false) async {
    guard UserDefaults.standard.bool(forKey: .peopleIMessageExport) else { return }
    guard
      PeopleGraphBuilder.claimRun(
        .peopleNarrativeLastRefresh, force: force, minInterval: minRefreshInterval)
    else { return }

    let now = Date()
    let plan: (directory: URL, candidates: [Candidate])? = await Task.detached(priority: .utility) {
      buildPlan(uid: uid, now: now)
    }.value
    guard let plan, !plan.candidates.isEmpty else { return }

    let items = plan.candidates.map {
      RequestItem(person_id: $0.personUUID, known_fingerprint: $0.knownFingerprint)
    }
    let response: DossierResponse
    do {
      response = try await APIClient.shared.fetchPersonDossiers(items)
    } catch {
      log("PeopleNarrative: dossier fetch failed — \(error)")
      return
    }

    let directory = plan.directory
    let asked = plan.candidates
    await Task.detached(priority: .utility) {
      applyResponse(response, asked: asked, directory: directory, now: now)
    }.value
    log(
      "PeopleNarrative: \(response.dossiers.count) narrative(s) merged, "
        + "\(response.skipped.count) skipped of \(asked.count) asked")
  }

  // MARK: - Off-main IO

  /// Resolve the user directory and pick this run's candidates from the people file on disk.
  static func buildPlan(uid: String?, now: Date) -> (directory: URL, candidates: [Candidate])? {
    guard let directory = PeopleUserDirectory.resolve(uid: uid) else { return nil }
    guard let persons = readPeople(directory: directory) else { return nil }
    let ledger = loadLedger(directory: directory)
    let picked = candidates(persons: persons, ledger: ledger, now: now, cap: maxPeoplePerRun)
    guard !picked.isEmpty else { return nil }
    return (directory, picked)
  }

  /// Merge the response into `people_intelligence.json`, re-apply the user's saved corrections, and
  /// record the ledger. Re-reads the file rather than reusing the plan's snapshot so a graph
  /// rebuild that landed while the request was in flight is not overwritten.
  static func applyResponse(
    _ response: DossierResponse, asked: [Candidate], directory: URL, now: Date
  ) {
    saveLedger(
      updatedLedger(loadLedger(directory: directory), response: response, asked: asked, now: now), directory: directory)
    guard !response.dossiers.isEmpty else { return }

    let url = directory.appendingPathComponent(peopleFileName)
    guard let data = try? Data(contentsOf: url),
      let obj = try? JSONSerialization.jsonObject(with: data),
      var doc = obj as? [String: Any],
      let persons = doc["people"] as? [[String: Any]]
    else { return }

    let merged = merge(persons: persons, dossiers: response.dossiers)
    // The narrative writes `facts`, which is exactly the field the review/override surface lets a
    // user correct. Running the same annotate+override pass the engine runs keeps user truth
    // winning over a model claim, instead of a refresh silently reinstating a rejected fact.
    let overrides = PeopleOverridesStore.load(directory: directory)
    let result = PeopleGraphBuilder.annotateAndReview(persons: merged, overrides: overrides)
    doc["people"] = result.people
    doc["reviewQueue"] = result.reviewQueue
    writeJSON(doc, to: url)
  }

  private static func readPeople(directory: URL) -> [[String: Any]]? {
    let url = directory.appendingPathComponent(peopleFileName)
    guard let data = try? Data(contentsOf: url),
      let obj = try? JSONSerialization.jsonObject(with: data),
      let doc = obj as? [String: Any],
      let persons = doc["people"] as? [[String: Any]], !persons.isEmpty
    else { return nil }
    return persons
  }

  private static func writeJSON(_ obj: Any, to url: URL) {
    guard JSONSerialization.isValidJSONObject(obj) else { return }
    do {
      let data = try JSONSerialization.data(withJSONObject: obj, options: [.prettyPrinted, .sortedKeys])
      try FileManager.default.createDirectory(
        at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
      try data.write(to: url, options: .atomic)
    } catch {
      log("PeopleNarrative: write failed: \(error)")
    }
  }
}
