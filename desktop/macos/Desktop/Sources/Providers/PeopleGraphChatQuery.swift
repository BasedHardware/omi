import Foundation

// MARK: - People-graph query core (pure)
//
// Reads the on-device people graph that the People tab already builds
// (`~/Library/Application Support/Omi/users/<uid>/people_intelligence.json`) so
// chat can answer "what do I know about <person>" without a backend round trip.
//
// The two existing decoders are reused verbatim — `PeopleIntelligenceFile` (People
// page) for the per-person row and `PeopleProfileExtrasLoader` (profile page) for
// the companion fields it drops (role, affiliations, groups, per-connection
// `how`/`context`, `community_meanings`, `network_insights`). There is deliberately
// no third decoder for this file.
//
// Privacy: everything here stays on-device. Nothing in this file uploads, and no
// person content is ever logged.

/// The graph as the chat tools see it: people ordered the way the People tab
/// orders them, plus the file-level context that explains groups and the network.
struct PeopleGraphSnapshot: Sendable {
  let generatedAt: String?
  /// Sorted by `closeness` descending, matching `PeopleViewModel`.
  let people: [PeopleIntelPerson]
  let context: PeopleProfileContext

  var isEmpty: Bool { people.isEmpty }

  func extras(for personID: String) -> PersonProfileExtras { context.extras(for: personID) }

  /// Plain-English meaning of a group name, from the file's `community_meanings`.
  func meaning(forGroup name: String) -> String? { context.meaning(forGroup: name) }
}

/// Distinguishes "no graph on this device" from "graph present but this person
/// isn't in it" — the tool surface must never conflate the two.
enum PeopleGraphLoadOutcome: Sendable {
  case loaded(PeopleGraphSnapshot)
  /// No `people_intelligence.json` anywhere under `Omi/users/*/`.
  case missing
  /// The file exists but could not be read or decoded.
  case unreadable(String)
}

enum PeopleGraphSnapshotLoader {
  static let fileName = "people_intelligence.json"

  /// Never call on the main actor: the reference file is ~400 KB / 181 people.
  nonisolated static func load(uid: String?) -> PeopleGraphLoadOutcome {
    guard let dir = PeopleUserDirectory.resolve(uid: uid) else { return .missing }
    return load(fileURL: dir.appendingPathComponent(fileName))
  }

  /// Seam for tests: read a specific file rather than resolving the user directory.
  nonisolated static func load(fileURL: URL) -> PeopleGraphLoadOutcome {
    guard FileManager.default.fileExists(atPath: fileURL.path) else { return .missing }
    do {
      return load(data: try Data(contentsOf: fileURL))
    } catch {
      return .unreadable(error.localizedDescription)
    }
  }

  /// Seam for tests: decode from raw bytes.
  nonisolated static func load(data: Data) -> PeopleGraphLoadOutcome {
    guard let file = try? JSONDecoder().decode(PeopleIntelligenceFile.self, from: data) else {
      return .unreadable("the people graph file is not valid JSON for this app version")
    }
    return .loaded(
      PeopleGraphSnapshot(
        generatedAt: file.generatedAt,
        people: file.people.sorted { $0.closeness > $1.closeness },
        context: PeopleProfileExtrasLoader.load(data: data)))
  }
}

// MARK: - Name matching

/// How strongly a query matched a person. Matching is **token-boundary** based on
/// purpose: a bare "Sam" resolves "Sam Altman" but must never silently resolve
/// "Samantha Lee", because fusing two people by a shared name prefix is the worst
/// failure this surface can have. Unmatched input falls through to suggestions.
enum PeopleNameMatchTier: Int, Sendable, Comparable {
  /// Final query token is a prefix of a remaining name token ("sam alt" -> "Sam Altman").
  case tokenPrefix = 1
  /// Every query token equals a name token ("altman" -> "Sam Altman").
  case tokenExact = 2
  /// Whole query equals an alias, the Contacts name, or the person id.
  case aliasExact = 3
  /// Whole query equals the display name.
  case nameExact = 4

  static func < (lhs: PeopleNameMatchTier, rhs: PeopleNameMatchTier) -> Bool {
    lhs.rawValue < rhs.rawValue
  }
}

enum PeopleNameMatcher {
  /// Case-, diacritic- and punctuation-insensitive, whitespace-collapsed.
  nonisolated static func normalized(_ raw: String) -> String {
    let folded = raw.folding(
      options: [.diacriticInsensitive, .caseInsensitive, .widthInsensitive],
      locale: Locale(identifier: "en_US_POSIX"))
    var out = ""
    var pendingSeparator = false
    for ch in folded {
      if ch.isLetter || ch.isNumber {
        if pendingSeparator && !out.isEmpty { out.append(" ") }
        pendingSeparator = false
        out.append(ch)
      } else {
        pendingSeparator = true
      }
    }
    return out
  }

  nonisolated static func tokens(_ raw: String) -> [String] {
    normalized(raw).split(separator: " ").map(String.init)
  }

  /// The names a person answers to: display name, Contacts name, and aliases.
  nonisolated static func candidateNames(for person: PeopleIntelPerson) -> [String] {
    var names = [person.name]
    if let contactName = person.contactName, !contactName.isEmpty { names.append(contactName) }
    names.append(contentsOf: person.aliases.filter { !$0.isEmpty })
    return names
  }

  nonisolated static func tier(query: String, person: PeopleIntelPerson) -> PeopleNameMatchTier? {
    let normalizedQuery = normalized(query)
    guard !normalizedQuery.isEmpty else { return nil }
    if normalized(person.name) == normalizedQuery { return .nameExact }

    let aliases = candidateNames(for: person).dropFirst()
    if aliases.contains(where: { normalized($0) == normalizedQuery }) { return .aliasExact }
    // Person ids are `slug(name)`, so a caller echoing an id from an earlier
    // result resolves without a second lookup.
    if !person.id.isEmpty, PeopleGraphBuilder.slug(query) == person.id { return .aliasExact }

    let queryTokens = tokens(query)
    guard !queryTokens.isEmpty else { return nil }
    var best: PeopleNameMatchTier?
    for candidate in candidateNames(for: person) {
      guard let tier = tokenTier(queryTokens: queryTokens, candidate: candidate) else { continue }
      best = max(best ?? tier, tier)
    }
    return best
  }

  private nonisolated static func tokenTier(
    queryTokens: [String], candidate: String
  ) -> PeopleNameMatchTier? {
    let candidateTokens = tokens(candidate)
    guard !candidateTokens.isEmpty else { return nil }
    let candidateSet = Set(candidateTokens)

    // A single token must match a whole name token. Prefix matching here is what
    // would make "Sam" swallow "Samantha", so it is not allowed.
    if queryTokens.count == 1 {
      return candidateSet.contains(queryTokens[0]) ? .tokenExact : nil
    }
    let head = queryTokens.dropLast()
    guard head.allSatisfy({ candidateSet.contains($0) }) else { return nil }
    guard let tail = queryTokens.last else { return nil }
    if candidateSet.contains(tail) { return .tokenExact }
    let remaining = candidateTokens.filter { !head.contains($0) }
    return remaining.contains { $0.hasPrefix(tail) } ? .tokenPrefix : nil
  }

  /// Everyone matching at the single best tier found, closest first. More than one
  /// result means the input is genuinely ambiguous and the caller must disambiguate
  /// rather than pick.
  nonisolated static func matches(
    query: String, in people: [PeopleIntelPerson]
  ) -> [PeopleIntelPerson] {
    var best: PeopleNameMatchTier?
    var byTier: [PeopleNameMatchTier: [PeopleIntelPerson]] = [:]
    for person in people {
      guard let tier = tier(query: query, person: person) else { continue }
      byTier[tier, default: []].append(person)
      best = max(best ?? tier, tier)
    }
    guard let best, let hits = byTier[best] else { return [] }
    return hits.sorted {
      $0.closeness != $1.closeness ? $0.closeness > $1.closeness : $0.name < $1.name
    }
  }

  /// Names to offer when nothing matched. Substring containment is safe *here*
  /// because it only ever suggests — it never resolves a person.
  nonisolated static func suggestions(
    query: String, in people: [PeopleIntelPerson], limit: Int
  ) -> [String] {
    let needle = normalized(query)
    guard !needle.isEmpty, limit > 0 else { return [] }
    var seen = Set<String>()
    var out: [String] = []
    for person in people {
      guard
        candidateNames(for: person).contains(where: {
          let name = normalized($0)
          return !name.isEmpty && (name.contains(needle) || needle.contains(name))
        })
      else { continue }
      guard !person.name.isEmpty, seen.insert(person.name).inserted else { continue }
      out.append(person.name)
      if out.count >= limit { break }
    }
    return out
  }
}

// MARK: - Listing / searching

/// Filters for "who do I know at X", "who is in <group>", "who have I not spoken
/// to in a while". All supplied filters must pass (AND).
struct PeopleGraphSearchRequest: Sendable, Equatable {
  var text: String?
  var affiliation: String?
  var group: String?
  /// Only people whose last contact is older than this many days (or who have none).
  var quietForDays: Int?
  var limit: Int

  static let defaultLimit = 10
  static let maxLimit = 25

  init(
    text: String? = nil,
    affiliation: String? = nil,
    group: String? = nil,
    quietForDays: Int? = nil,
    limit: Int = PeopleGraphSearchRequest.defaultLimit
  ) {
    self.text = PeopleGraphSearchRequest.clean(text)
    self.affiliation = PeopleGraphSearchRequest.clean(affiliation)
    self.group = PeopleGraphSearchRequest.clean(group)
    self.quietForDays = quietForDays.map { max(0, $0) }
    self.limit = min(max(1, limit), PeopleGraphSearchRequest.maxLimit)
  }

  var hasFilter: Bool {
    text != nil || affiliation != nil || group != nil || quietForDays != nil
  }

  private static func clean(_ raw: String?) -> String? {
    guard let trimmed = raw?.trimmingCharacters(in: .whitespacesAndNewlines), !trimmed.isEmpty
    else { return nil }
    return trimmed
  }
}

struct PeopleGraphSearchResult: Sendable {
  let people: [PeopleIntelPerson]
  /// How many matched before `limit` was applied.
  let totalMatched: Int
  let totalPeople: Int
}

enum PeopleGraphSearch {
  nonisolated static func run(
    _ request: PeopleGraphSearchRequest,
    snapshot: PeopleGraphSnapshot,
    now: Date
  ) -> PeopleGraphSearchResult {
    let matched = snapshot.people.filter { person in
      let extras = snapshot.extras(for: person.id)
      if let text = request.text, !contains(text, in: freeTextHaystack(person, extras)) {
        return false
      }
      if let affiliation = request.affiliation,
        !contains(affiliation, in: affiliationHaystack(person, extras))
      {
        return false
      }
      if let group = request.group, !contains(group, in: groupHaystack(person, extras)) {
        return false
      }
      if let quietDays = request.quietForDays,
        !isQuiet(person, forDays: quietDays, now: now)
      {
        return false
      }
      return true
    }

    let ordered: [PeopleIntelPerson]
    if request.quietForDays != nil {
      // Staleness questions want the coldest contacts first; "never" is coldest.
      ordered = matched.sorted { lhs, rhs in
        let l = lastTouchDate(lhs).map { $0.timeIntervalSince1970 } ?? -.greatestFiniteMagnitude
        let r = lastTouchDate(rhs).map { $0.timeIntervalSince1970 } ?? -.greatestFiniteMagnitude
        return l != r ? l < r : lhs.closeness > rhs.closeness
      }
    } else {
      ordered = matched
    }

    return PeopleGraphSearchResult(
      people: Array(ordered.prefix(request.limit)),
      totalMatched: matched.count,
      totalPeople: snapshot.people.count)
  }

  nonisolated static func lastTouchDate(_ person: PeopleIntelPerson) -> Date? {
    if let touch = person.lastTouch, let date = PeopleDateFormat.date(from: touch.date) {
      return date
    }
    return person.channels.compactMap { PeopleDateFormat.date(from: $0.last) }.max()
  }

  nonisolated static func isQuiet(
    _ person: PeopleIntelPerson, forDays days: Int, now: Date
  ) -> Bool {
    guard let last = lastTouchDate(person) else { return true }
    return now.timeIntervalSince(last) > Double(days) * 86_400
  }

  private nonisolated static func contains(_ needle: String, in haystack: [String]) -> Bool {
    let normalizedNeedle = PeopleNameMatcher.normalized(needle)
    guard !normalizedNeedle.isEmpty else { return true }
    return haystack.contains {
      PeopleNameMatcher.normalized($0).contains(normalizedNeedle)
    }
  }

  private nonisolated static func freeTextHaystack(
    _ person: PeopleIntelPerson, _ extras: PersonProfileExtras
  ) -> [String] {
    var out = PeopleNameMatcher.candidateNames(for: person)
    out.append(person.relationship)
    out.append(person.who)
    out.append(person.now)
    out.append(person.overall)
    out.append(contentsOf: person.facts)
    out.append(contentsOf: person.activities)
    out.append(contentsOf: person.openThreads)
    out.append(contentsOf: affiliationHaystack(person, extras))
    out.append(contentsOf: groupHaystack(person, extras))
    return out.filter { !$0.isEmpty }
  }

  private nonisolated static func affiliationHaystack(
    _ person: PeopleIntelPerson, _ extras: PersonProfileExtras
  ) -> [String] {
    var out = extras.affiliations.map { $0.name }
    if let role = extras.role { out.append(role) }
    if let linkedin = person.linkedin {
      if let company = linkedin.company { out.append(company) }
      if let position = linkedin.position { out.append(position) }
    }
    return out.filter { !$0.isEmpty }
  }

  private nonisolated static func groupHaystack(
    _ person: PeopleIntelPerson, _ extras: PersonProfileExtras
  ) -> [String] {
    var out = extras.groups.map { $0.name }
    if let circle = person.circle, !circle.label.isEmpty { out.append(circle.label) }
    for connection in person.connections ?? [] {
      out.append(contentsOf: connection.sources)
    }
    for detail in extras.connectionDetails.values {
      out.append(contentsOf: detail.context)
    }
    return out.filter { !$0.isEmpty }
  }
}
