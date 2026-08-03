import Foundation

// Companion decoder for per-person fields `PeopleIntelPerson` does not read:
// `role`, `history_grounded`, `affiliations`, `groups`, and the richer
// `how`/`type`/`confidence` on each connection.
//
// What actually writes them (see `docs/people-intelligence-productization.md`):
//   - `groups`, `affiliations`, `history_grounded`, `connections[].how` — the in-repo
//     on-device engine (`PeopleGraphBuilder` + `PeopleIntelDerivation`, Phase 2,
//     deterministic).
//   - `role` and `connections[].type`/`.confidence` — Phase 3, model-backed and NOT
//     implemented here; today they appear only in files produced out-of-tree.
// Every field is therefore optional and the profile page must render correctly without
// any of them. Do not treat their presence as guaranteed.

/// An organization this person is associated with, and why we believe it.
struct PersonAffiliation: Decodable, Identifiable, Equatable, Sendable {
  let name: String
  let kind: String
  let confidence: Double
  /// Human-readable evidence, e.g. "group chat: <name>".
  let via: [String]

  var id: String { "\(kind)|\(name)" }

  enum CodingKeys: String, CodingKey {
    case name
    case kind = "type"
    case confidence
    case via
  }

  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    name = (try c.decodeIfPresent(String.self, forKey: .name)) ?? ""
    kind = (try c.decodeIfPresent(String.self, forKey: .kind)) ?? ""
    confidence = (try c.decodeIfPresent(Double.self, forKey: .confidence)) ?? 0
    via = (try c.decodeIfPresent([String].self, forKey: .via)) ?? []
  }
}

/// A named group or thread this person belongs to.
struct PersonGroupRef: Decodable, Identifiable, Equatable, Sendable {
  let name: String
  let category: String

  var id: String { "\(category)|\(name)" }

  enum CodingKeys: String, CodingKey { case name, category }

  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    name = (try c.decodeIfPresent(String.self, forKey: .name)) ?? ""
    category = (try c.decodeIfPresent(String.self, forKey: .category)) ?? ""
  }
}

/// The "how do these two know each other" detail carried alongside a connection.
/// `how`, `kind`, and `confidence` are present on only some connections (153 of
/// 344 in the reference file), so all three stay optional.
struct PersonConnectionDetail: Decodable, Identifiable, Equatable, Sendable {
  let id: String
  let name: String
  /// Real shared-group names backing the edge.
  let context: [String]
  /// Plain-English derivation, e.g. "share frequent 1:1 messaging, no shared group chat".
  let how: String?
  let kind: String?
  let confidence: Double?

  enum CodingKeys: String, CodingKey {
    case id, name, context, how, confidence
    case kind = "type"
  }

  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    id = (try c.decodeIfPresent(String.self, forKey: .id)) ?? ""
    name = (try c.decodeIfPresent(String.self, forKey: .name)) ?? ""
    context = (try c.decodeIfPresent([String].self, forKey: .context)) ?? []
    how = try c.decodeIfPresent(String.self, forKey: .how)
    kind = try c.decodeIfPresent(String.self, forKey: .kind)
    confidence = try c.decodeIfPresent(Double.self, forKey: .confidence)
  }
}

/// Everything the profile page renders that `PeopleIntelPerson` drops.
struct PersonProfileExtras: Equatable, Sendable {
  let role: String?
  let historyGrounded: Bool
  let affiliations: [PersonAffiliation]
  let groups: [PersonGroupRef]
  /// Keyed by connection id so a row can be enriched without a linear scan.
  let connectionDetails: [String: PersonConnectionDetail]

  static let empty = PersonProfileExtras(
    role: nil, historyGrounded: false, affiliations: [], groups: [], connectionDetails: [:])

  var isEmpty: Bool {
    role == nil && !historyGrounded && affiliations.isEmpty && groups.isEmpty
      && connectionDetails.isEmpty
  }
}

/// Per-person extras plus the file-level context the profile page uses to explain
/// a group by name and to describe the surrounding network.
struct PeopleProfileContext: Equatable, Sendable {
  let extrasByPersonID: [String: PersonProfileExtras]
  /// Group name -> plain-English meaning.
  let communityMeanings: [String: String]
  let networkInsights: [String]

  static let empty = PeopleProfileContext(
    extrasByPersonID: [:], communityMeanings: [:], networkInsights: [])

  func extras(for personID: String) -> PersonProfileExtras {
    extrasByPersonID[personID] ?? .empty
  }

  /// The meaning of a group name, matched case-insensitively so callers can pass
  /// the label exactly as the pipeline wrote it.
  func meaning(forGroup name: String) -> String? {
    if let exact = communityMeanings[name] { return exact }
    let needle = name.lowercased()
    return communityMeanings.first { $0.key.lowercased() == needle }?.value
  }
}

// MARK: - Loading

private struct PeopleExtrasFile: Decodable {
  let people: [PersonExtrasRow]
  let communityMeanings: [String: String]
  let networkInsights: [String]

  enum CodingKeys: String, CodingKey {
    case people
    case communityMeanings = "community_meanings"
    case networkInsights = "network_insights"
  }

  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    people = (try c.decodeIfPresent([PersonExtrasRow].self, forKey: .people)) ?? []
    communityMeanings =
      (try c.decodeIfPresent([String: String].self, forKey: .communityMeanings)) ?? [:]
    networkInsights = (try c.decodeIfPresent([String].self, forKey: .networkInsights)) ?? []
  }
}

private struct PersonExtrasRow: Decodable {
  let id: String
  let role: String?
  let historyGrounded: Bool
  let affiliations: [PersonAffiliation]
  let groups: [PersonGroupRef]
  let connections: [PersonConnectionDetail]

  enum CodingKeys: String, CodingKey {
    case id, role, affiliations, groups, connections
    case historyGrounded = "history_grounded"
  }

  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    id = (try c.decodeIfPresent(String.self, forKey: .id)) ?? ""
    role = try c.decodeIfPresent(String.self, forKey: .role)
    historyGrounded = (try c.decodeIfPresent(Bool.self, forKey: .historyGrounded)) ?? false
    affiliations = (try c.decodeIfPresent([PersonAffiliation].self, forKey: .affiliations)) ?? []
    groups = (try c.decodeIfPresent([PersonGroupRef].self, forKey: .groups)) ?? []
    connections = (try c.decodeIfPresent([PersonConnectionDetail].self, forKey: .connections)) ?? []
  }
}

enum PeopleProfileExtrasLoader {
  /// Decodes the companion fields from `people_intelligence.json`.
  ///
  /// Never call this on the main actor: the reference file is ~400 KB / 181 people
  /// and the People page already reloads it on every tab visit.
  nonisolated static func load(uid: String?) -> PeopleProfileContext {
    guard let dir = PeopleUserDirectory.resolve(uid: uid) else { return .empty }
    return load(fileURL: dir.appendingPathComponent("people_intelligence.json"))
  }

  /// Seam for tests: decode a specific file rather than resolving the user directory.
  nonisolated static func load(fileURL: URL) -> PeopleProfileContext {
    guard let data = try? Data(contentsOf: fileURL) else { return .empty }
    return load(data: data)
  }

  /// Seam for tests: decode from raw bytes.
  nonisolated static func load(data: Data) -> PeopleProfileContext {
    guard let file = try? JSONDecoder().decode(PeopleExtrasFile.self, from: data) else {
      return .empty
    }
    return context(from: file)
  }

  private static func context(from file: PeopleExtrasFile) -> PeopleProfileContext {
    var byID: [String: PersonProfileExtras] = [:]
    byID.reserveCapacity(file.people.count)
    for row in file.people where !row.id.isEmpty {
      var details: [String: PersonConnectionDetail] = [:]
      for connection in row.connections where !connection.id.isEmpty {
        details[connection.id] = connection
      }
      let extras = PersonProfileExtras(
        role: (row.role?.isEmpty ?? true) ? nil : row.role,
        historyGrounded: row.historyGrounded,
        affiliations: row.affiliations.filter { !$0.name.isEmpty },
        groups: row.groups.filter { !$0.name.isEmpty },
        connectionDetails: details)
      if !extras.isEmpty { byID[row.id] = extras }
    }
    return PeopleProfileContext(
      extrasByPersonID: byID,
      communityMeanings: file.communityMeanings,
      networkInsights: file.networkInsights)
  }
}
