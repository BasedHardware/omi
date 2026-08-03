import Foundation

/// Minimal seam over the backend People CRUD, so the bridge's get-or-create policy is assertable
/// without a live backend. Both members already exist on `APIClient`; this protocol only names
/// them so a test can substitute a recording double.
protocol PeopleDirectoryClient: Sendable {
  func listPeople() async throws -> [Person]
  func createPerson(name: String) async throws -> Person
}

extension APIClient: PeopleDirectoryClient {
  func listPeople() async throws -> [Person] { try await getPeople() }
}

/// Bridges an on-device person card to the backend `Person` record that segments, memories and
/// conversation subjects are keyed by.
///
/// Without this, the two id spaces are joined only by a display-name string: the on-device engine
/// speaks `slug(name)` and the backend speaks a uuid, so a segment can never say *who* is speaking
/// and `subject_entity_id` stays `unknown` for everyone. The bridge resolves one uuid per
/// identity — get-or-create against `POST /v1/users/people`, which is idempotent by name — and
/// stores it in `people_identity.json` keyed by the person's **identity keys**, not their name, so
/// the binding survives a rename exactly like the person id does.
///
/// Everything here is bounded and best-effort: gated on the same on-device-messaging consent flag
/// as the rest of the pipeline, self-throttled, capped per run, off the main thread, and a silent
/// no-op on any network/IO failure (the uuid is simply resolved on a later run).
enum PeopleIdentityBridge {
  /// Max people bridged per run. One `getPeople()` plus at most this many `createPerson` calls,
  /// so a first pass over a large contact list trickles out instead of bursting the API.
  static let maxResolutionsPerRun = 25

  /// Minimum spacing between the bridge's own runs. The graph syncs every 5 minutes; resolving
  /// uuids that often would spend request budget on a table that changes far more slowly.
  static let minResolveInterval: TimeInterval = 30 * 60

  // MARK: - Entry point (gated, throttled, off-main, silent)

  /// Called from `PeopleGraphBuilder.syncIfNeeded` after the graph has written its cards and
  /// **before** the thread ingest, so a uuid resolved this run is available to stamp onto the
  /// segments the ingest uploads moments later.
  static func resolveIfNeeded(uid: String?, force: Bool = false, client: PeopleDirectoryClient = APIClient.shared)
    async
  {
    guard UserDefaults.standard.bool(forKey: .peopleIMessageExport) else { return }
    guard
      PeopleGraphBuilder.claimRun(
        .peopleIdentityBridgeLastRun, force: force, minInterval: minResolveInterval)
    else { return }

    let plan: Plan? = await Task.detached(priority: .utility) { buildPlan(uid: uid) }.value
    guard let plan, !plan.pending.isEmpty else { return }

    let resolved = await resolve(pending: plan.pending, client: client)
    guard !resolved.isEmpty else { return }

    await Task.detached(priority: .utility) {
      commit(resolved: resolved, directory: plan.directory)
    }.value
    log("PeopleIdentityBridge: bridged \(resolved.count) person card(s) to a backend Person")
  }

  // MARK: - Planning (pure + guarded IO)

  /// One card still waiting for a backend uuid.
  struct PendingPerson: Equatable, Sendable {
    let personID: String
    let name: String
  }

  struct Plan {
    let directory: URL
    let pending: [PendingPerson]
  }

  /// The backend's `CreatePerson` contract: `name: str = Field(min_length=2, max_length=40)`
  /// (`backend/models/other.py`). Pydantic counts Unicode code points, so `unicodeScalars.count` is
  /// the matching measure — `String.count` (grapheme clusters) under-counts emoji and would let a
  /// name the server rejects through.
  ///
  /// Screening here is not a nicety. `POST /v1/users/people` answers a violation with **422**, and
  /// a 422 is permanent for that name: the same card is re-offered on every later run and refused
  /// again. That is exactly how a measured cold start bridged 12 of 102 people and then stayed at
  /// 12 forever — a 44-character `urn:biz:<uuid>` service-account label sat at position 13.
  static let minBackendNameLength = 2
  static let maxBackendNameLength = 40

  /// True when a card's label can actually become a backend `Person`. `isHumanName` alone is not
  /// enough: it accepts any label with a letter in it, including the platform tokens and long
  /// group-style names that violate the length contract above.
  static func isBridgeableName(_ name: String) -> Bool {
    let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
    guard PeopleMemoryWriter.isHumanName(trimmed) else { return false }
    let length = trimmed.unicodeScalars.count
    return length >= minBackendNameLength && length <= maxBackendNameLength
  }

  /// How a run's small budget is ranked across the cards waiting for a uuid. Higher sorts first.
  ///
  /// Never file order: even after the selection stage the population is long-tailed, so the budget
  /// has to go to people the user would actually recognize. Ordered by the strength of the evidence
  /// that there is a real relationship here.
  struct Rank: Equatable {
    /// A source asserted this person's name (`contactName`), rather than the pipeline labelling
    /// them with their own raw handle. The single strongest "you know this person" signal.
    let named: Bool
    /// Any direct message history at all. A node with none exists only because a group chat listed
    /// them — bridging it spends a backend record on someone never spoken to.
    let corresponded: Bool
    /// Whether the relationship is live: 2 within ~6 months, 1 within ~2 years, 0 older or
    /// unknown. Deliberately only three levels — recency is here to demote relationships that are
    /// *over*, not to let a two-message exchange from last week outrank a hundred-message thread
    /// from last quarter. Inside a bucket, volume decides.
    let recency: Int
    /// Direct + group message volume the graph recorded for them.
    let closeness: Int
    /// Deterministic tiebreak, so two otherwise identical cards always resolve the same way.
    let personID: String

    static func sortsBefore(_ lhs: Rank, _ rhs: Rank) -> Bool {
      if lhs.named != rhs.named { return lhs.named }
      if lhs.corresponded != rhs.corresponded { return lhs.corresponded }
      if lhs.recency != rhs.recency { return lhs.recency > rhs.recency }
      if lhs.closeness != rhs.closeness { return lhs.closeness > rhs.closeness }
      return lhs.personID < rhs.personID
    }
  }

  /// Rank one already-eligible card. Reads only fields the graph writes; every one is optional and
  /// its absence is the weakest value, so a sparse card ranks last rather than crashing or winning.
  static func rank(_ person: [String: Any], personID: String, now: Date) -> Rank {
    let contactName = (person["contactName"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
    let closeness = Int((person["closeness"] as? Double) ?? Double(person["closeness"] as? Int ?? 0))
    let lastTouch = (person["lastTouch"] as? [String: Any])?["date"] as? String
    return Rank(
      named: !(contactName?.isEmpty ?? true),
      corresponded: closeness > 0,
      recency: recencyBucket(isoDate: lastTouch, now: now),
      closeness: closeness,
      personID: personID)
  }

  /// Days-since-last-touch as a bucket. An unparseable or missing date is the *oldest* bucket, never
  /// the newest: a card with no evidence of recent contact must not outrank one that has it.
  static func recencyBucket(isoDate: String?, now: Date) -> Int {
    guard let isoDate, !isoDate.isEmpty else { return 0 }
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime]
    guard let date = formatter.date(from: isoDate) else { return 0 }
    let days = now.timeIntervalSince(date) / 86_400
    if days <= 180 { return 2 }  // a clock-skewed future date is "just now", not "unknown"
    if days <= 730 { return 1 }
    return 0
  }

  /// Cards that carry at least one identity key, have a bridgeable name, and have no `personUUID`
  /// yet — ranked, then capped.
  ///
  /// The handle requirement is deliberate: a card with no phone/handle has nothing durable to key
  /// the binding on, so creating a backend `Person` for it would just recreate the name-only
  /// identity this whole change exists to remove. The rank is applied **before** the cap, so the
  /// budget follows the strongest relationships instead of whatever order the file happens to be
  /// in.
  static func pendingPeople(
    persons: [[String: Any]], links: PeopleIdentityLinks, cap: Int, now: Date = Date()
  ) -> [PendingPerson] {
    var eligible: [(Rank, PendingPerson)] = []
    var seen = Set<String>()
    for person in persons {
      guard let id = (person["id"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines),
        !id.isEmpty, !seen.contains(id)
      else { continue }
      guard (person["personUUID"] as? String)?.isEmpty ?? true else { continue }
      guard links.personUUID(forPersonID: id) == nil else { continue }
      let hasHandle =
        !PersonIdentityKeys.from(json: person["handles"]).isEmpty || links.hasKeys(forPersonID: id)
      guard hasHandle else { continue }
      let name = (person["name"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
      // A backend Person is keyed by name; a blank, non-human, or contract-violating label either
      // creates a junk record or is refused outright.
      guard isBridgeableName(name) else { continue }
      seen.insert(id)
      eligible.append((rank(person, personID: id, now: now), PendingPerson(personID: id, name: name)))
    }
    return
      eligible
      .sorted { Rank.sortsBefore($0.0, $1.0) }
      .prefix(max(cap, 0))
      .map { $0.1 }
  }

  private static func buildPlan(uid: String?) -> Plan? {
    guard let dir = PeopleUserDirectory.resolve(uid: uid) else { return nil }
    let url = dir.appendingPathComponent("people_intelligence.json")
    guard let data = try? Data(contentsOf: url),
      let obj = try? JSONSerialization.jsonObject(with: data),
      let doc = obj as? [String: Any],
      let persons = doc["people"] as? [[String: Any]]
    else { return nil }
    let links = PeopleIdentityStore.load(directory: dir)
    let pending = pendingPeople(persons: persons, links: links, cap: maxResolutionsPerRun)
    return Plan(directory: dir, pending: pending)
  }

  // MARK: - Resolution (network, injectable)

  /// Get-or-create one backend `Person` per pending card, returning `person id → uuid`.
  ///
  /// Whether a failed create is about **this card** or about **this run**.
  ///
  /// A 4xx that is not a budget or auth answer is the backend refusing this specific name. Retrying
  /// it refuses it again, and the pending order is deterministic, so treating it as a run-level stop
  /// re-offers the same card first on every future run and wedges everyone behind it forever — the
  /// measured behavior of a bridge stuck at 12 people across every run of a day. Rate limiting
  /// (429), auth (401/403), 5xx and transport errors really are about the run, so those still stop
  /// it and leave the remaining cards for later.
  static func isCardRejection(_ error: Error) -> Bool {
    guard case APIError.httpError(let statusCode, _) = error else { return false }
    guard (400..<500).contains(statusCode) else { return false }
    return statusCode != 401 && statusCode != 403 && statusCode != 429
  }

  /// Get-or-create one backend `Person` per pending card, returning `person id → uuid`.
  ///
  /// One list call up front covers everyone the backend already knows, so the common steady state
  /// costs a single request. `POST /v1/users/people` is idempotent by name, so a create that races
  /// another client returns the same record rather than a duplicate. A card the backend refuses is
  /// skipped and the run continues (see `isCardRejection`); anything run-level stops the run and
  /// keeps whatever it already resolved, and the rest are picked up on a later throttled run.
  static func resolve(pending: [PendingPerson], client: PeopleDirectoryClient) async -> [String: String] {
    guard !pending.isEmpty else { return [:] }

    var uuidByName: [String: String] = [:]
    do {
      for person in try await client.listPeople() {
        let key = nameKey(person.name)
        guard !key.isEmpty, uuidByName[key] == nil else { continue }
        uuidByName[key] = person.id
      }
    } catch {
      // No directory means every create below would be a blind guess at duplication. Stop.
      log("PeopleIdentityBridge: people directory unavailable — \(error)")
      return [:]
    }

    var resolved: [String: String] = [:]
    var rejected = 0
    for person in pending {
      if let existing = uuidByName[nameKey(person.name)] {
        resolved[person.personID] = existing
        continue
      }
      do {
        let created = try await client.createPerson(name: person.name)
        uuidByName[nameKey(person.name)] = created.id
        resolved[person.personID] = created.id
      } catch {
        if isCardRejection(error) {
          // This card can never be created; the next one still can. Bounded by the run's cap.
          rejected += 1
          continue
        }
        log("PeopleIdentityBridge: stopped after \(resolved.count) bridged — \(error)")
        break
      }
    }
    if rejected > 0 {
      log("PeopleIdentityBridge: \(rejected) card(s) refused by the backend and skipped")
    }
    return resolved
  }

  // MARK: - Commit (guarded IO)

  /// Persist `person id → uuid` into the durable link table AND onto the already-written cards.
  ///
  /// The link table is the authority — it is keyed by identity key, so it is what survives a
  /// rename. Stamping the cards too just means the UI and the thread ingest see the uuid now
  /// instead of after the next graph rebuild.
  static func commit(resolved: [String: String], directory: URL) {
    guard !resolved.isEmpty else { return }
    var links = PeopleIdentityStore.load(directory: directory)
    for personID in resolved.keys.sorted() {
      guard let uuid = resolved[personID] else { continue }
      links.setPersonUUID(uuid, forPersonID: personID)
    }
    PeopleIdentityStore.save(links, directory: directory)
    stamp(resolved: resolved, at: directory.appendingPathComponent("people_intelligence.json"))
  }

  /// Fill `personUUID` onto matching cards without touching any other field. Fill-in only: an
  /// existing uuid always wins, so this can never repoint a card at a second backend record.
  static func stamp(resolved: [String: String], at url: URL) {
    guard let data = try? Data(contentsOf: url),
      let obj = try? JSONSerialization.jsonObject(with: data),
      var doc = obj as? [String: Any],
      var persons = doc["people"] as? [[String: Any]]
    else { return }
    var changed = false
    for index in persons.indices {
      guard let id = persons[index]["id"] as? String, let uuid = resolved[id] else { continue }
      guard (persons[index]["personUUID"] as? String)?.isEmpty ?? true else { continue }
      persons[index]["personUUID"] = uuid
      changed = true
    }
    guard changed else { return }
    doc["people"] = persons
    guard JSONSerialization.isValidJSONObject(doc) else { return }
    do {
      let out = try JSONSerialization.data(withJSONObject: doc, options: [.prettyPrinted, .sortedKeys])
      try out.write(to: url, options: .atomic)
    } catch {
      log("PeopleIdentityBridge: stamping personUUID failed: \(error)")
    }
  }

  /// Name key used to match an existing backend `Person`. Mirrors the backend's own idempotency
  /// (`get_or_create_person` matches on the stored name), normalized for whitespace and case so a
  /// trivial difference does not create a duplicate record.
  private static func nameKey(_ name: String) -> String {
    name.lowercased().split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
  }
}
