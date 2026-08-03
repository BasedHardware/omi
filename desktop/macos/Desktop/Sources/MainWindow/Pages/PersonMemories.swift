import Combine
import Foundation

/// The memories Omi holds about one person, for the person profile page.
///
/// Three matching paths, in priority order:
///   1. **Server, by subject** — `GET /v3/memories/by-person/{person_id}`, which queries
///      `subject_entity_id` and the `person:<id>` tag in Firestore. This is the authority and the
///      only leg that works on a machine whose local cache is cold or truncated — which is the
///      normal case. The cache is filled from `GET /v3/memories`, a pagination contract that takes
///      no subject filter (the `category=` / `tags=` params the Swift client appends are silently
///      dropped by FastAPI) and orders by `scoring` before `created_at`, so a freshly written,
///      low-scoring relationship fact is not on the pages the client caches. That is why this tab
///      was empty even though the writes succeeded.
///   2. **Local tag** — `person:<personID>`, written by `PeopleMemoryWriter`. The same id string
///      the server matches on, read from SQLite, so the tab still renders offline and instantly.
///   3. **Name prefix** — a fallback for facts written *before* tagging existed, which carry no
///      usable provenance at all (`source` was dropped by the backend model). Those are recognised
///      by the literal shape `PeopleMemoryWriter` gives every fact.
///
/// Fallback rows are marked `isTagged: false` so the UI can tell an exact match from a heuristic
/// one, and so the fallback can be deleted once the pre-fix facts have aged out.
///
/// Every leg is independently fallible: an offline machine still shows its cached rows, a cold
/// machine still shows the server's. Only a total failure of all three reports `.failed`.

// MARK: - Public model types

/// One memory attributed to a person.
struct PersonMemoryItem: Identifiable, Equatable, Sendable {
  let id: String
  let content: String
  let createdAt: Date?
  /// True when matched by the durable tag rather than the name-prefix fallback.
  let isTagged: Bool
}

enum PersonMemoriesState: Equatable, Sendable {
  case idle
  case loading
  case loaded
  /// Nothing identifies this person well enough to look anything up (no id and no name).
  case unavailable
  case failed(String)
}

// MARK: - Storage seam

/// A local memory row reduced to what person-matching needs.
///
/// Keeps the matcher pure and lets tests exercise the real merge/ordering rules without standing up
/// a SQLite fixture.
struct PersonMemoryCandidate: Equatable, Sendable {
  let id: String
  let content: String
  let createdAt: Date?
  let tags: [String]
}

/// Read seam over the two stores a person's memories can come from.
protocol PersonMemorySource: Sendable {
  /// Server-side, by subject id. Default-implemented as empty so the two local legs stay
  /// independently testable and an offline-only stub does not have to fake a network.
  func serverMemories(forPerson personID: String, limit: Int) async throws -> [PersonMemoryCandidate]
  func memories(taggedWith tag: String, limit: Int) async throws -> [PersonMemoryCandidate]
  func memories(containing text: String, limit: Int) async throws -> [PersonMemoryCandidate]
}

extension PersonMemorySource {
  func serverMemories(forPerson personID: String, limit: Int) async throws -> [PersonMemoryCandidate] {
    []
  }
}

/// The production source: the server's by-subject query plus the on-device SQLite memory cache.
///
/// `MemoryStorage` is an actor, so every local query below runs on its own executor — never on the
/// main actor — and the calls are additionally hopped off via `Task.detached` by the model.
struct DefaultPersonMemorySource: PersonMemorySource {
  func serverMemories(forPerson personID: String, limit: Int) async throws -> [PersonMemoryCandidate] {
    let rows = try await APIClient.shared.getPersonMemories(personID: personID, limit: limit)
    return rows.map(PersonMemoryCandidate.init)
  }

  func memories(taggedWith tag: String, limit: Int) async throws -> [PersonMemoryCandidate] {
    let rows = try await MemoryStorage.shared.getFilteredMemories(limit: limit, matchAnyTag: [tag])
    return rows.map(PersonMemoryCandidate.init)
  }

  func memories(containing text: String, limit: Int) async throws -> [PersonMemoryCandidate] {
    let rows = try await MemoryStorage.shared.searchLocalMemories(query: text, limit: limit)
    return rows.map(PersonMemoryCandidate.init)
  }
}

extension PersonMemoryCandidate {
  init(_ memory: ServerMemory) {
    self.init(
      id: memory.id, content: memory.content, createdAt: memory.createdAt, tags: memory.tags)
  }
}

// MARK: - Matching (pure)

/// Decides which local memories belong to a person. Pure and non-isolated so it is cheap to test and
/// safe to run off the main actor.
enum PersonMemoryMatcher {
  /// Upper bound on rows pulled from either query before matching. A person's relationship facts are
  /// a handful; this only has to be larger than that, not unbounded.
  static let queryLimit = 500

  static func personTag(_ personID: String) -> String {
    PeopleMemoryWriter.personTagPrefix + personID
  }

  /// True when `content` has the literal shape `PeopleMemoryWriter` gives a fact about this person.
  ///
  /// Anchored deliberately: a person whose name is a prefix of another's ("Sam" vs "Samantha") must
  /// not absorb the other's facts, which is why every form requires the writer's own separator
  /// immediately after the name rather than a substring search.
  static func matches(content: String, displayName: String) -> Bool {
    let name = displayName.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !name.isEmpty else { return false }

    // Per-person fact: "<Name> — <role>…"
    if content.hasPrefix(name + PeopleMemoryWriter.nameSeparator) { return true }
    // Pair fact with this person first: "<Name> and <Other> both belong to your …"
    if content.hasPrefix(name + PeopleMemoryWriter.pairConjunction),
      content.contains(PeopleMemoryWriter.pairMarker)
    {
      return true
    }
    // Pair fact with this person second: "<Other> and <Name> both belong to your …"
    if content.contains(
      PeopleMemoryWriter.pairConjunction + name + PeopleMemoryWriter.pairMarker)
    {
      return true
    }
    return false
  }

  /// Merge the server, tag and name-prefix results into one newest-first list.
  ///
  /// A memory reached by more than one path is kept once and reported as tagged — server
  /// attribution and the tag are real provenance, the name prefix only a guess about the same row.
  static func merge(
    personID: String,
    displayName: String,
    server: [PersonMemoryCandidate] = [],
    tagged: [PersonMemoryCandidate],
    named: [PersonMemoryCandidate]
  ) -> [PersonMemoryItem] {
    var byID: [String: PersonMemoryItem] = [:]
    byID.reserveCapacity(server.count + tagged.count + named.count)

    func insert(_ candidate: PersonMemoryCandidate, isTagged: Bool) {
      guard !candidate.id.isEmpty else { return }
      if let existing = byID[candidate.id] {
        guard isTagged, !existing.isTagged else { return }
      }
      byID[candidate.id] = PersonMemoryItem(
        id: candidate.id,
        content: candidate.content,
        createdAt: candidate.createdAt,
        isTagged: isTagged)
    }

    // The server already answered "is this fact about this person" by querying
    // `subject_entity_id`/`tags`, and a subject-attributed fact need not carry the tag at all, so
    // re-deriving the answer here from the row's tags would drop exactly the rows this leg exists
    // to deliver.
    for candidate in server {
      insert(candidate, isTagged: true)
    }
    if !personID.isEmpty {
      // Re-check the tag in Swift: the store matches tags with a JSON `LIKE`, and this keeps the
      // contract ("tagged means the row really carries the tag") independent of that SQL.
      let tag = personTag(personID)
      for candidate in tagged where candidate.tags.contains(tag) {
        insert(candidate, isTagged: true)
      }
    }
    for candidate in named where matches(content: candidate.content, displayName: displayName) {
      insert(candidate, isTagged: false)
    }

    return byID.values.sorted(by: newestFirst)
  }

  /// Newest first; undated rows sort last, and ties break on id so the order is deterministic.
  private static func newestFirst(_ lhs: PersonMemoryItem, _ rhs: PersonMemoryItem) -> Bool {
    switch (lhs.createdAt, rhs.createdAt) {
    case (.some(let left), .some(let right)):
      return left == right ? lhs.id < rhs.id : left > right
    case (.some, .none):
      return true
    case (.none, .some):
      return false
    case (.none, .none):
      return lhs.id < rhs.id
    }
  }
}

// MARK: - Model

/// Outcome of one off-main load. Sendable-by-construction: the failure carries a fixed, PII-free
/// message rather than an `any Error`.
private enum PersonMemoriesOutcome: Sendable {
  case items([PersonMemoryItem])
  case failure(String)
}

/// Drives the memories section of a person profile page.
@MainActor
final class PersonMemoriesModel: ObservableObject {
  /// Newest first.
  @Published private(set) var memories: [PersonMemoryItem] = []
  @Published private(set) var state: PersonMemoriesState = .idle

  /// User-facing and deliberately detail-free: the underlying GRDB error can carry the database path
  /// and the URLError can carry the host, and neither may reach the UI or a log line.
  nonisolated static let failureMessage = "Couldn't read memories."

  private let source: any PersonMemorySource
  /// Guards against an out-of-order finish when the profile switches people mid-load.
  private var loadToken = 0

  init(source: any PersonMemorySource = DefaultPersonMemorySource()) {
    self.source = source
  }

  /// - Parameter backendPersonID: the backend `Person` uuid, when the identity
  ///   bridge has resolved one. Facts written before the bridge are tagged with the
  ///   on-device slug and newer ones are attributed to the uuid, so both ids are
  ///   asked for — on a cold machine the local cache holds neither.
  func load(personID: String, backendPersonID: String? = nil, displayName: String) async {
    let id = personID.trimmingCharacters(in: .whitespacesAndNewlines)
    let backendID = (backendPersonID ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    let name = displayName.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !id.isEmpty || !backendID.isEmpty || !name.isEmpty else {
      memories = []
      state = .unavailable
      return
    }

    loadToken &+= 1
    let token = loadToken
    state = .loading

    let source = self.source
    let outcome = await Task.detached(priority: .utility) {
      await Self.fetch(personID: id, backendPersonID: backendID, displayName: name, source: source)
    }.value

    // A newer load superseded this one; dropping the result keeps the published state monotonic.
    guard token == loadToken else { return }
    switch outcome {
    case .items(let items):
      memories = items
      state = .loaded
    case .failure(let message):
      memories = []
      state = .failed(message)
    }
  }

  func reset() {
    loadToken &+= 1
    memories = []
    state = .idle
  }

  /// Off-main: all three queries plus the merge. Never touches the main actor.
  ///
  /// Each leg fails independently. A cold machine has no local rows and must still show the
  /// server's; an offline machine has no server and must still show its cached rows. Only a leg
  /// that was actually attempted and threw counts as a failure, and only when *every* attempted leg
  /// threw does the tab report `.failed` — otherwise a dropped network connection would blank a
  /// profile that the local cache could have rendered.
  private nonisolated static func fetch(
    personID: String, backendPersonID: String, displayName: String, source: any PersonMemorySource
  ) async -> PersonMemoriesOutcome {
    var server: [PersonMemoryCandidate] = []
    var tagged: [PersonMemoryCandidate] = []
    var named: [PersonMemoryCandidate] = []
    var attempted = 0
    var failed = 0

    // The uuid finds subject-attributed facts; the slug finds the ones tagged before
    // the bridge existed. Neither alone is complete, so ask for each distinct id.
    var serverIDs: [String] = []
    for candidate in [backendPersonID, personID]
    where !candidate.isEmpty && !serverIDs.contains(candidate) {
      serverIDs.append(candidate)
    }
    for serverID in serverIDs {
      attempted += 1
      do {
        server += try await source.serverMemories(
          forPerson: serverID, limit: PersonMemoryMatcher.queryLimit)
      } catch {
        failed += 1
      }
    }

    if !personID.isEmpty {
      attempted += 1
      do {
        tagged = try await source.memories(
          taggedWith: PersonMemoryMatcher.personTag(personID),
          limit: PersonMemoryMatcher.queryLimit)
      } catch {
        failed += 1
      }
    }
    if !displayName.isEmpty {
      attempted += 1
      do {
        named = try await source.memories(
          containing: displayName, limit: PersonMemoryMatcher.queryLimit)
      } catch {
        failed += 1
      }
    }

    if attempted > 0, failed == attempted {
      return .failure(failureMessage)
    }
    return .items(
      PersonMemoryMatcher.merge(
        personID: personID, displayName: displayName, server: server, tagged: tagged, named: named))
  }
}
