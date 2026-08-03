import Combine
import Foundation

/// The real, person-attributed tasks for one person, for the person profile page.
///
/// A task now carries `assignee_person_id` / `assigner_person_id` — backend `Person` ids —
/// so "what do I owe them, what do they owe me" is data rather than prose. This model reads
/// them through `GET /v1/action-items?person_id=…`.
///
/// **Resolving the profile to a backend person is read-only on purpose.** The People page's
/// `id` is not always a backend `Person` id: for a user with no backend person cards the
/// on-device graph mints its own ids from names. So the backend id is looked up by matching
/// against the people the account already has (`GET /v1/users/people`) — id first, then name,
/// contact name, and aliases. It never calls the create endpoint: opening a profile must not
/// write a new `Person` into the user's account, and a person who does not exist in the
/// backend cannot be on any task anyway.

// MARK: - Public model types

/// Which side of a commitment a person is on, from the signed-in user's point of view.
enum PersonCommitmentDirection: String, Sendable {
  /// They are the assignee: this is on them.
  case theyOweYou
  /// They asked for it and it is not on them: this is on you.
  case youOweThem

  var label: String {
    switch self {
    case .theyOweYou: return "On them"
    case .youOweThem: return "On you"
    }
  }
}

/// One task with this person named on it.
struct PersonCommitmentItem: Identifiable, Equatable, Sendable {
  let id: String
  let description: String
  let completed: Bool
  let dueAt: Date?
  let direction: PersonCommitmentDirection
}

enum PersonCommitmentsState: Equatable, Sendable {
  case idle
  case loading
  case loaded
  /// No backend person matches this profile, so no task can name them yet.
  case notLinked
  case failed(String)
}

// MARK: - Network seam

/// Read seam over the two backend reads this needs. Keeps the matcher and the model
/// testable without standing up an HTTP stack.
protocol PersonCommitmentsSource: Sendable {
  func people() async throws -> [Person]
  func tasks(personID: String) async throws -> [TaskActionItem]
}

struct BackendPersonCommitmentsSource: PersonCommitmentsSource {
  func people() async throws -> [Person] {
    try await APIClient.shared.getPeople()
  }

  func tasks(personID: String) async throws -> [TaskActionItem] {
    try await APIClient.shared.getActionItems(limit: PersonCommitmentsModel.pageLimit, personId: personID).items
  }
}

// MARK: - Matching (pure)

/// Maps a People-page profile onto the backend `Person` that represents them, and maps that
/// person's tasks onto directed commitments. Pure and non-isolated: cheap to test, safe off
/// the main actor.
enum PersonCommitmentsMatcher {
  /// The backend person id for this profile, or nil when the account has no such person.
  ///
  /// Anchored on whole values only. A substring or prefix match would let "Sam" absorb
  /// "Samantha"'s commitments, which is the one mistake this page must never make.
  static func backendPersonID(
    profileID: String,
    displayName: String,
    contactName: String?,
    aliases: [String],
    people: [Person]
  ) -> String? {
    guard !people.isEmpty else { return nil }

    // The profile id already is a backend person id (a backend-written people file).
    let trimmedProfileID = profileID.trimmingCharacters(in: .whitespacesAndNewlines)
    if !trimmedProfileID.isEmpty, people.contains(where: { $0.id == trimmedProfileID }) {
      return trimmedProfileID
    }

    var byName: [String: String] = [:]
    for person in people {
      let key = normalized(person.name)
      guard !key.isEmpty else { continue }
      // First writer wins so the mapping is stable when two people share a name.
      if byName[key] == nil { byName[key] = person.id }
    }

    for candidate in [displayName, contactName].compactMap({ $0 }) + aliases {
      let key = normalized(candidate)
      guard !key.isEmpty, let id = byName[key] else { continue }
      return id
    }
    return nil
  }

  /// Turn this person's tasks into directed commitments, newest work first.
  ///
  /// A task where they are the assignee is on them, even if they also asked for it —
  /// whoever has to act is the more useful fact on a person's page.
  static func commitments(personID: String, tasks: [TaskActionItem]) -> [PersonCommitmentItem] {
    var seen = Set<String>()
    var items: [PersonCommitmentItem] = []
    for task in tasks where !task.isRetired {
      let direction: PersonCommitmentDirection
      if task.assigneePersonId == personID {
        direction = .theyOweYou
      } else if task.assignerPersonId == personID {
        direction = .youOweThem
      } else {
        // Defensive: the server filtered by this person, so anything else is a mismatch we
        // must not label rather than guess a direction for.
        continue
      }
      guard seen.insert(task.id).inserted else { continue }
      items.append(
        PersonCommitmentItem(
          id: task.id,
          description: task.description,
          completed: task.completed,
          dueAt: task.dueAt,
          direction: direction))
    }
    return items.sorted(by: openAndSoonestFirst)
  }

  /// Open before done, then soonest due, then undated, then stable on id.
  private static func openAndSoonestFirst(_ lhs: PersonCommitmentItem, _ rhs: PersonCommitmentItem) -> Bool {
    if lhs.completed != rhs.completed { return !lhs.completed }
    switch (lhs.dueAt, rhs.dueAt) {
    case (.some(let left), .some(let right)):
      return left == right ? lhs.id < rhs.id : left < right
    case (.some, .none):
      return true
    case (.none, .some):
      return false
    case (.none, .none):
      return lhs.id < rhs.id
    }
  }

  private static func normalized(_ value: String) -> String {
    value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
  }
}

// MARK: - Tab layout (pure)

/// What the Commitments tab shows, decided outside SwiftUI so it can be asserted.
///
/// The two kinds of content are structurally separate and can never merge: assigned tasks
/// are real, person-attributed tasks; open threads are prose the people pipeline noticed and
/// nobody is assigned to them. The page said "these are not assigned tasks" about all of it,
/// which stopped being true once a task could carry a person — so each list is now labelled
/// for what it is, and the shared empty state appears only when there is genuinely neither.
struct PersonCommitmentsTabLayout: Equatable, Sendable {
  let assigned: [PersonCommitmentItem]
  let openThreads: [String]
  let state: PersonCommitmentsState

  init(assigned: [PersonCommitmentItem], openThreads: [String], state: PersonCommitmentsState) {
    self.assigned = assigned
    self.openThreads = openThreads
    self.state = state
  }

  private var isSettled: Bool {
    switch state {
    case .idle, .loading: return false
    case .loaded, .notLinked, .failed: return true
    }
  }

  /// True while the assigned list is still being fetched.
  var showsAssignedProgress: Bool { !isSettled }

  /// Real, person-attributed task rows.
  var showsAssignedRows: Bool { state == .loaded && !assigned.isEmpty }

  /// "No tasks name them yet" — settled, nothing attributed, and not an error.
  var showsAssignedPlaceholder: Bool {
    guard isSettled else { return false }
    if case .failed = state { return false }
    return assigned.isEmpty
  }

  /// Extracted prose, always its own labelled section.
  var showsOpenThreads: Bool { !openThreads.isEmpty }

  /// The one shared empty state: only when there is nothing of either kind to show.
  var showsEmptyState: Bool { isSettled && assigned.isEmpty && openThreads.isEmpty }
}

// MARK: - Model

/// Outcome of one off-main load. Sendable by construction: the failure carries a fixed,
/// detail-free message rather than an `any Error`.
private enum PersonCommitmentsOutcome: Sendable {
  case items([PersonCommitmentItem])
  case notLinked
  case failure(String)
}

/// Drives the assigned-commitments section of a person profile page.
@MainActor
final class PersonCommitmentsModel: ObservableObject {
  @Published private(set) var commitments: [PersonCommitmentItem] = []
  @Published private(set) var state: PersonCommitmentsState = .idle

  /// A person's commitments are a handful; this only has to exceed that, not be unbounded.
  static let pageLimit = 200

  /// Deliberately detail-free: a transport error can carry a URL or a token and must never
  /// reach the UI.
  nonisolated static let failureMessage = "Couldn't load commitments right now."

  private let source: any PersonCommitmentsSource
  /// Guards against an out-of-order finish when the profile switches people mid-load.
  private var loadToken = 0

  init(source: any PersonCommitmentsSource = BackendPersonCommitmentsSource()) {
    self.source = source
  }

  func load(profileID: String, displayName: String, contactName: String?, aliases: [String]) async {
    loadToken &+= 1
    let token = loadToken
    state = .loading

    let source = self.source
    let outcome = await Task.detached(priority: .utility) {
      await Self.fetch(
        profileID: profileID,
        displayName: displayName,
        contactName: contactName,
        aliases: aliases,
        source: source)
    }.value

    // A newer load superseded this one; dropping the result keeps published state monotonic.
    guard token == loadToken else { return }
    switch outcome {
    case .items(let items):
      commitments = items
      state = .loaded
    case .notLinked:
      commitments = []
      state = .notLinked
    case .failure(let message):
      commitments = []
      state = .failed(message)
    }
  }

  func reset() {
    loadToken &+= 1
    commitments = []
    state = .idle
  }

  private nonisolated static func fetch(
    profileID: String,
    displayName: String,
    contactName: String?,
    aliases: [String],
    source: any PersonCommitmentsSource
  ) async -> PersonCommitmentsOutcome {
    do {
      let people = try await source.people()
      guard
        let personID = PersonCommitmentsMatcher.backendPersonID(
          profileID: profileID,
          displayName: displayName,
          contactName: contactName,
          aliases: aliases,
          people: people)
      else {
        return .notLinked
      }
      let tasks = try await source.tasks(personID: personID)
      return .items(PersonCommitmentsMatcher.commitments(personID: personID, tasks: tasks))
    } catch {
      return .failure(failureMessage)
    }
  }
}
