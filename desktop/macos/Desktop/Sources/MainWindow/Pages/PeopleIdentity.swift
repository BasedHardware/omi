import Foundation

// MARK: - Durable person identity
//
// The People-Intelligence pipeline already computes a genuine cross-channel identity: the
// `phone_last10 → person` map inside `PeopleGraphBuilder.buildCanonicalPeople` is *why* one human
// on both iMessage and WhatsApp resolves to a single node. That map used to die with the function,
// which left `slug(displayName)` as the only surviving identity. Renaming a contact therefore
// silently minted a new person: `people_overrides.json` decisions, `person:<id>` memory tags
// already on the server, and `people_photos/<id>.jpg` all detached from the human they described.
//
// This file persists that identity instead. `people_identity.json` maps each **identity key** to
// the person id first assigned to it, so a display-name change is just a display-name change.

/// The identity keys one person is addressable by, exactly as the graph pipeline keys them:
/// `phone_last10` for phone-shaped handles, the lowercased raw handle for everything else (emails,
/// handle-only accounts). Persisting these costs no new computation — they are the keys
/// `People.idByPhone` / `People.idByEmail` are already built on.
///
/// The two key spaces cannot collide: a handle with ten or more digits and no `@` always becomes a
/// phone key, so an email key is never a bare 10-digit string. That is what lets one flat
/// `[key: link]` store address both.
struct PersonIdentityKeys: Codable, Equatable, Sendable {
  var phones: [String]
  var emails: [String]

  init(phones: [String] = [], emails: [String] = []) {
    self.phones = phones
    self.emails = emails
  }

  enum CodingKeys: String, CodingKey { case phones, emails }

  /// Lenient on purpose: a person card must stay readable whatever an older build wrote, so a
  /// missing or malformed side decodes to no keys rather than throwing the whole card away.
  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    phones = (try? c.decode([String].self, forKey: .phones)) ?? []
    emails = (try? c.decode([String].self, forKey: .emails)) ?? []
  }

  var isEmpty: Bool { phones.isEmpty && emails.isEmpty }

  /// Every key in a stable order — phones first, matching the lookup order the pipeline resolves in.
  var all: [String] { phones + emails }

  static let none = PersonIdentityKeys()

  /// The on-card representation written into `people_intelligence.json`.
  var json: [String: Any] { ["phones": phones, "emails": emails] }

  /// Decode the on-card representation. A missing/short shape simply yields fewer keys — never a
  /// throw, because a person card must stay readable no matter what an older build wrote.
  static func from(json: Any?) -> PersonIdentityKeys {
    guard let dict = json as? [String: Any] else { return .none }
    func strings(_ key: String) -> [String] {
      ((dict[key] as? [Any]) ?? []).compactMap { value in
        guard let text = (value as? String)?.trimmingCharacters(in: .whitespacesAndNewlines),
          !text.isEmpty
        else { return nil }
        return text
      }
    }
    return PersonIdentityKeys(phones: strings("phones"), emails: strings("emails"))
  }

  /// Union with `other`, preserving this value's order and dropping duplicates. Used by the merge
  /// path so gaining a second channel adds a key instead of replacing the first one.
  func union(_ other: PersonIdentityKeys) -> PersonIdentityKeys {
    func merged(_ lhs: [String], _ rhs: [String]) -> [String] {
      var seen = Set(lhs)
      var out = lhs
      for value in rhs where seen.insert(value).inserted { out.append(value) }
      return out
    }
    return PersonIdentityKeys(
      phones: merged(phones, other.phones), emails: merged(emails, other.emails))
  }
}

/// One durable identity record, stored under an identity key.
struct PersonIdentityLink: Codable, Equatable, Sendable {
  /// The on-device canonical person id first assigned to this identity. This is the field that
  /// makes `person:<id>` memory tags, saved override decisions and contact photos survive a
  /// rename: the display name changes, this does not.
  var personID: String
  /// The backend `Person.id` (a uuid) this identity is bridged to, once `PeopleIdentityBridge`
  /// has resolved it. Nil until then; never cleared once set.
  var personUUID: String?
  /// Display name last seen for this identity. Diagnostic only — it is deliberately **not** an
  /// identity key, which is the whole point of this file.
  var name: String?

  init(personID: String, personUUID: String? = nil, name: String? = nil) {
    self.personID = personID
    self.personUUID = personUUID
    self.name = name
  }
}

/// The whole link table, plus the two reverse indexes the pipeline reads on every person.
///
/// A value type on purpose: `PeopleGraphBuilder`'s people-building stays pure and testable, and
/// `PeopleIdentityStore` owns the only IO.
struct PeopleIdentityLinks: Equatable, Sendable {
  /// identity key → link. The persisted authority.
  private(set) var byKey: [String: PersonIdentityLink]
  /// person id → backend uuid, derived from `byKey`.
  private(set) var uuidByPersonID: [String: String] = [:]
  /// person id → its identity keys, derived from `byKey` (sorted, so output is stable).
  private(set) var keysByPersonID: [String: [String]] = [:]

  static let empty = PeopleIdentityLinks()

  init(byKey: [String: PersonIdentityLink] = [:]) {
    self.byKey = byKey
    rebuildIndexes()
  }

  var isEmpty: Bool { byKey.isEmpty }

  func personID(forKey key: String) -> String? { byKey[key]?.personID }

  func personUUID(forKey key: String) -> String? { byKey[key]?.personUUID }

  func personUUID(forPersonID id: String) -> String? { uuidByPersonID[id] }

  func hasKeys(forPersonID id: String) -> Bool { keysByPersonID[id]?.isEmpty == false }

  /// Record (or refresh) the identity key → person id binding. The `personID` of an existing link
  /// is **never** rewritten — that binding is the thing being protected — but the display name is
  /// kept current and a uuid is filled in when one arrives.
  mutating func record(key: String, personID: String, name: String? = nil) {
    insert(key: key, personID: personID, name: name)
    rebuildIndexes()
  }

  /// Batch form of `record`. The index rebuild is O(n log n), so folding a whole run's people in
  /// one key at a time would make a large contact list quadratic; this reindexes exactly once.
  mutating func record(identityKeys: [String: PersonIdentityKeys], names: [String: String]) {
    for personID in identityKeys.keys.sorted() {
      guard let keys = identityKeys[personID] else { continue }
      for key in keys.all { insert(key: key, personID: personID, name: names[personID]) }
    }
    rebuildIndexes()
  }

  private mutating func insert(key rawKey: String, personID: String, name: String?) {
    let key = rawKey.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !key.isEmpty, !personID.isEmpty else { return }
    if var existing = byKey[key] {
      if let name, !name.isEmpty { existing.name = name }
      byKey[key] = existing
    } else {
      byKey[key] = PersonIdentityLink(personID: personID, name: name)
    }
  }

  /// Bind a backend `Person` uuid to every identity key of `personID`. Fill-in only: an already
  /// recorded uuid wins, so a re-run can never repoint a person at a second backend record.
  mutating func setPersonUUID(_ uuid: String, forPersonID personID: String) {
    let uuid = uuid.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !uuid.isEmpty, !personID.isEmpty else { return }
    var changed = false
    for key in byKey.keys where byKey[key]?.personID == personID {
      guard byKey[key]?.personUUID == nil else { continue }
      byKey[key]?.personUUID = uuid
      changed = true
    }
    if changed { rebuildIndexes() }
  }

  private mutating func rebuildIndexes() {
    var uuids: [String: String] = [:]
    var keys: [String: [String]] = [:]
    for key in byKey.keys.sorted() {
      guard let link = byKey[key] else { continue }
      keys[link.personID, default: []].append(key)
      if let uuid = link.personUUID, uuids[link.personID] == nil { uuids[link.personID] = uuid }
    }
    uuidByPersonID = uuids
    keysByPersonID = keys
  }

  // MARK: - Stable id assignment (pure)

  /// Decide the canonical person id for every identity key.
  ///
  /// `nameIDByKey` is what the pipeline derives today: `identity key → slug(display name)`. A
  /// rename changes that value; the stored link does not, so a stored id always wins.
  ///
  /// Resolution runs per **name group** rather than per key: a person addressed by two handles,
  /// only one of which was seen before, must not split in half the first time they are renamed.
  /// Every key that currently slugs to the same id therefore adopts the same stored id, chosen
  /// deterministically by sorted key order so repeated runs agree.
  static func stableIDs(nameIDByKey: [String: String], links: PeopleIdentityLinks) -> [String: String] {
    guard !links.isEmpty else { return nameIDByKey }
    var storedForNameID: [String: String] = [:]
    for key in nameIDByKey.keys.sorted() {
      guard let nameID = nameIDByKey[key], let stored = links.personID(forKey: key),
        storedForNameID[nameID] == nil
      else { continue }
      storedForNameID[nameID] = stored
    }
    guard !storedForNameID.isEmpty else { return nameIDByKey }
    return nameIDByKey.mapValues { storedForNameID[$0] ?? $0 }
  }
}

// MARK: - The pipeline's identity, inverted

extension PeopleGraphBuilder.People {
  /// `person id → the identity keys that resolved to them`, inverted from `idByPhone` /
  /// `idByEmail`. Those two maps ARE the pipeline's cross-channel identity — they are what make
  /// one human on iMessage and WhatsApp a single node — so inverting them is the entire cost of
  /// persisting identity onto a person card. Nothing new is computed.
  func identityKeysByID() -> [String: PersonIdentityKeys] {
    var out: [String: PersonIdentityKeys] = [:]
    for phone in idByPhone.keys.sorted() {
      guard let id = idByPhone[phone] else { continue }
      out[id, default: .none].phones.append(phone)
    }
    for email in idByEmail.keys.sorted() {
      guard let id = idByEmail[email] else { continue }
      out[id, default: .none].emails.append(email)
    }
    return out
  }

  /// `person id → display name`, the companion of `identityKeysByID()` when recording links.
  func namesByID() -> [String: String] {
    var out: [String: String] = [:]
    for (id, canon) in canonByID { out[id] = canon.name }
    return out
  }
}

/// Reads/writes `people_identity.json`. All IO is guarded — losing this file costs identity
/// continuity for *future* renames, never the app, and it refills on the next pipeline run.
enum PeopleIdentityStore {
  static let fileName = "people_identity.json"

  private struct Document: Codable {
    var version: Int
    var links: [String: PersonIdentityLink]
  }

  static func load(directory: URL) -> PeopleIdentityLinks {
    let url = directory.appendingPathComponent(fileName)
    guard let data = try? Data(contentsOf: url),
      let doc = try? JSONDecoder().decode(Document.self, from: data)
    else { return .empty }
    return PeopleIdentityLinks(byKey: doc.links)
  }

  static func load(uid: String?) -> PeopleIdentityLinks {
    guard let dir = PeopleUserDirectory.resolve(uid: uid) else { return .empty }
    return load(directory: dir)
  }

  static func save(_ links: PeopleIdentityLinks, directory: URL) {
    let url = directory.appendingPathComponent(fileName)
    do {
      let encoder = JSONEncoder()
      encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
      let data = try encoder.encode(Document(version: 1, links: links.byKey))
      try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
      try data.write(to: url, options: .atomic)
    } catch {
      log("PeopleIdentityStore: write failed: \(error)")
    }
  }

  /// Fold this run's `identity key → person id` resolution into the stored table and persist it.
  /// Additive and idempotent: existing bindings are preserved, new identities are recorded.
  static func record(
    identityKeys: [String: PersonIdentityKeys], names: [String: String], directory: URL
  ) {
    var links = load(directory: directory)
    links.record(identityKeys: identityKeys, names: names)
    save(links, directory: directory)
  }
}
