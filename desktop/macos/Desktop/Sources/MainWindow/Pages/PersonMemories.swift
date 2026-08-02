import Combine
import Foundation

/// The memories Omi holds about one person, for the person profile page.
///
/// Reads the **local** store, never the network: `GET /v3/memories` takes only
/// `limit`/`offset`/`cursor`/`device_scope`/`client_device_id` (see
/// `backend/routers/memories.py`), so the `category=` / `tags=` query parameters the Swift client
/// appends are silently dropped by FastAPI and a network path would page the user's entire memory
/// store to find a handful of rows. `MemoryStorage` already indexes tags locally, so the filter
/// happens where the data is.
///
/// Two matching paths, in priority order:
///   1. **Tag** — `person:<personID>`, written by `PeopleMemoryWriter`. Durable and exact; this is
///      the path everything written after the tagging fix takes.
///   2. **Name prefix** — a fallback for facts written *before* the fix, which carry no usable
///      provenance at all (`source` was dropped by the backend model). Those are recognised by the
///      literal shape `PeopleMemoryWriter` gives every fact.
///
/// Fallback rows are marked `isTagged: false` so the UI can tell an exact match from a heuristic
/// one, and so the fallback can be deleted once the pre-fix facts have aged out.

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

/// Read seam over the local memory store.
protocol PersonMemorySource: Sendable {
  func memories(taggedWith tag: String, limit: Int) async throws -> [PersonMemoryCandidate]
  func memories(containing text: String, limit: Int) async throws -> [PersonMemoryCandidate]
}

/// The production source: the on-device SQLite memory cache.
///
/// `MemoryStorage` is an actor, so every query below runs on its own executor — never on the main
/// actor — and the calls are additionally hopped off via `Task.detached` by the model.
struct LocalPersonMemorySource: PersonMemorySource {
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

  /// Merge the tag results and the name-prefix results into one newest-first list.
  ///
  /// A memory reached by both paths is kept once and reported as tagged — the tag is real
  /// provenance, the prefix only a guess about the same row.
  static func merge(
    personID: String,
    displayName: String,
    tagged: [PersonMemoryCandidate],
    named: [PersonMemoryCandidate]
  ) -> [PersonMemoryItem] {
    var byID: [String: PersonMemoryItem] = [:]
    byID.reserveCapacity(tagged.count + named.count)

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
  /// and must never reach the UI or a log line.
  nonisolated static let failureMessage = "Couldn't read memories from the local store."

  private let source: any PersonMemorySource
  /// Guards against an out-of-order finish when the profile switches people mid-load.
  private var loadToken = 0

  init(source: any PersonMemorySource = LocalPersonMemorySource()) {
    self.source = source
  }

  func load(personID: String, displayName: String) async {
    let id = personID.trimmingCharacters(in: .whitespacesAndNewlines)
    let name = displayName.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !id.isEmpty || !name.isEmpty else {
      memories = []
      state = .unavailable
      return
    }

    loadToken &+= 1
    let token = loadToken
    state = .loading

    let source = self.source
    let outcome = await Task.detached(priority: .utility) {
      await Self.fetch(personID: id, displayName: name, source: source)
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

  /// Off-main: both store queries plus the merge. Never touches the main actor.
  private nonisolated static func fetch(
    personID: String, displayName: String, source: any PersonMemorySource
  ) async -> PersonMemoriesOutcome {
    var tagged: [PersonMemoryCandidate] = []
    var named: [PersonMemoryCandidate] = []
    do {
      if !personID.isEmpty {
        tagged = try await source.memories(
          taggedWith: PersonMemoryMatcher.personTag(personID),
          limit: PersonMemoryMatcher.queryLimit)
      }
      if !displayName.isEmpty {
        named = try await source.memories(
          containing: displayName, limit: PersonMemoryMatcher.queryLimit)
      }
    } catch {
      return .failure(failureMessage)
    }
    return .items(
      PersonMemoryMatcher.merge(
        personID: personID, displayName: displayName, tagged: tagged, named: named))
  }
}
