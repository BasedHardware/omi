import Foundation

// MARK: - What a review row is

/// One memory the day produced, as the card addresses it.
///
/// The card renders memories, not prose. `knowledge_nuggets` is an LLM sentence about the day with
/// no identity behind it: the reader cannot tell Omi it is wrong, because there is nothing to be
/// wrong *about*. A `MemoryReviewItem` is a row in the memory store, so ✓ / ✗ / Fix are real
/// mutations on a real record and the verdict survives to the next extraction.
struct MemoryReviewItem: Identifiable, Equatable, Sendable {
  let memoryID: String
  let content: String
  let category: String

  var id: String { memoryID }

  init(memoryID: String, content: String, category: String = "") {
    self.memoryID = memoryID
    self.content = content
    self.category = category
  }

  init(_ learned: DailySummaryRecord.LearnedMemory) {
    self.init(memoryID: learned.memoryID, content: learned.content, category: learned.category)
  }

  /// The small label under the row. Bounded to the four known categories; anything else is shown
  /// as the raw backend word rather than invented, and an empty category shows no label at all.
  var categoryLabel: String? {
    let trimmed = category.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return nil }
    return MemoryCategory(rawValue: trimmed)?.displayName ?? trimmed.capitalized
  }
}

/// Where a review action happened. Bounded, and the only `source` value telemetry ever sends.
enum MemoryReviewSource: String, Sendable {
  /// The "Things I learned today" section of the daily summary card in Chat.
  case dailySummaryChat = "daily_summary_chat"
  /// The same section on the dedicated daily-recap page (the sheet the Chat pill and the
  /// Activity day open). Matches mobile's telemetry source of the same name.
  case dailySummaryDetail = "daily_summary_detail"
  /// A `memoryReviewCard` content block rendered in the Chat-first transcript.
  case chatBlock = "chat_block"
}

/// What the owner said about a memory. Derived from the memory itself, never stored by the card.
///
/// Single mutation owner: the memory API owns the verdict. Nothing here is written to defaults, to
/// the chat row, or to the summary record — a vote on the phone and a vote on the Mac read back
/// through the same field.
enum MemoryReviewVerdict: Equatable, Sendable {
  /// Not reviewed, not corrected. All three controls are live.
  case none
  /// `user_review == true`.
  case accepted
  /// `user_review == false`.
  case rejected
  /// The memory's content no longer matches what the summary captured.
  case updated
}

/// The three mutations a row can start. One value, so telemetry and the in-flight fence agree.
enum MemoryReviewAction: String, Equatable, Sendable {
  case accept
  case reject
  case edit
}

// MARK: - Row state machine

/// Everything one row shows, and nothing it does not.
///
/// `live` is what the memory says; `optimistic` is the local override held only while a request is
/// in flight. The row draws `displayed`, so a failure that clears `optimistic` puts the row back
/// exactly where it was before the click rather than somewhere new.
struct MemoryReviewRowModel: Equatable, Sendable {
  var live: MemoryReviewVerdict = .none
  var optimistic: MemoryReviewVerdict?
  var inFlight: MemoryReviewAction?
  /// Non-nil exactly while the inline single-line editor is open. Esc clears it.
  var draft: String?
  /// Honest and inline. Never a toast, never silence.
  var errorMessage: String?

  var displayed: MemoryReviewVerdict { optimistic ?? live }
  var isEditing: Bool { draft != nil }
  var isBusy: Bool { inFlight != nil }
  /// A settled row stops offering the three controls and shows what it settled on.
  var isSettled: Bool { displayed != .none }
  /// Rejection fades the row but keeps it in place until the card is refreshed: removing it here
  /// would reflow every row below the one the reader just clicked.
  var isFaded: Bool { displayed == .rejected }

  /// The one line of copy under a settled row. Each is a promise the backend actually keeps:
  /// rejection feeds bounded negative feedback into extraction, and an edit re-enters short-term
  /// as a user assertion for the consolidation job to weigh — which is "Updated.", not "Confirmed".
  var statusText: String? {
    switch displayed {
    case .none: return nil
    case .accepted: return "Confirmed. I'll act on this."
    case .rejected: return "Dropped. I'll avoid facts like this."
    case .updated: return "Updated."
    }
  }
}

/// What the reducer asks the caller to do. Values, not callbacks.
///
/// The desktop guide's synchronous state-machine rule exists because a callback invoked mid
/// transition can reduce against a half-published model. This machine cannot: `reduce` returns the
/// next model and an effect *description*, so the transition is complete before anything runs, and
/// a nested event can only arrive as another call to `reduce`.
enum MemoryReviewEffect: Equatable, Sendable {
  case none
  case review(keep: Bool)
  case edit(content: String)
  /// Re-read `user_review` / `edited` from the memory after a mutation lands, so the row shows the
  /// record's state rather than trusting the optimistic override indefinitely.
  case refreshLiveState
}

enum MemoryReviewEvent: Equatable, Sendable {
  /// A render-time or post-mutation read of the memory's own state.
  case liveStateLoaded(MemoryReviewVerdict)
  case accept
  case reject
  case beginEdit(prefill: String)
  case draftChanged(String)
  case cancelEdit
  case saveEdit
  case requestSucceeded(MemoryReviewAction)
  case requestFailed(MemoryReviewAction)
}

/// Pure transition table for one row. No I/O, no actor, no view.
enum MemoryReviewReducer {
  static let failureMessage = "Couldn't save, try again"

  static func reduce(
    _ model: MemoryReviewRowModel,
    _ event: MemoryReviewEvent
  ) -> (MemoryReviewRowModel, MemoryReviewEffect) {
    var next = model
    switch event {
    case .liveStateLoaded(let verdict):
      // A read that comes back empty must not erase a verdict this device already made: the local
      // mirror routinely lags the write it is being asked to confirm, and a row that flickered
      // back to "unreviewed" a second after the click would read as the vote not landing.
      if verdict != .none || (next.live == .none && next.optimistic == nil) {
        next.live = verdict
      }
      if !next.isBusy { next.optimistic = nil }
      return (next, .none)

    case .accept:
      guard !next.isBusy, !next.isEditing else { return (next, .none) }
      next.errorMessage = nil
      next.optimistic = .accepted
      next.inFlight = .accept
      return (next, .review(keep: true))

    case .reject:
      guard !next.isBusy, !next.isEditing else { return (next, .none) }
      next.errorMessage = nil
      next.optimistic = .rejected
      next.inFlight = .reject
      return (next, .review(keep: false))

    case .beginEdit(let prefill):
      guard !next.isBusy else { return (next, .none) }
      next.errorMessage = nil
      next.draft = prefill
      return (next, .none)

    case .draftChanged(let text):
      guard next.isEditing else { return (next, .none) }
      next.draft = text
      return (next, .none)

    case .cancelEdit:
      next.draft = nil
      return (next, .none)

    case .saveEdit:
      guard let draft = next.draft, !next.isBusy else { return (next, .none) }
      let trimmed = draft.trimmingCharacters(in: .whitespacesAndNewlines)
      // An empty correction is a cancel, not a mutation that blanks the memory.
      guard !trimmed.isEmpty else {
        next.draft = nil
        return (next, .none)
      }
      next.draft = nil
      next.errorMessage = nil
      next.optimistic = .updated
      next.inFlight = .edit
      return (next, .edit(content: trimmed))

    case .requestSucceeded(let action):
      guard next.inFlight == action else { return (next, .none) }
      next.inFlight = nil
      // The override becomes the row's own state, then the re-read confirms it against the memory.
      next.live = next.optimistic ?? next.live
      next.optimistic = nil
      next.errorMessage = nil
      return (next, .refreshLiveState)

    case .requestFailed(let action):
      guard next.inFlight == action else { return (next, .none) }
      next.inFlight = nil
      next.optimistic = nil
      next.errorMessage = failureMessage
      return (next, .none)
    }
  }
}

// MARK: - Seams

/// The mutations the card is allowed to make. Existing endpoints only — no new write path, and no
/// verdict stored anywhere but the memory.
protocol MemoryReviewMutating: Sendable {
  func review(memoryID: String, keep: Bool) async throws
  func edit(memoryID: String, content: String) async throws
}

/// The live read of `user_review` / `edited`, resolved per memory id.
///
/// Throwing rather than optional-returning: "the read failed" and "nobody has voted on any of
/// these" are different facts, and a card that cannot tell them apart shows a settled verdict as
/// unreviewed and offers the controls again.
protocol MemoryReviewStateReading: Sendable {
  func verdicts(for items: [MemoryReviewItem]) async throws -> [String: MemoryReviewVerdict]
}

struct LiveMemoryReviewMutator: MemoryReviewMutating {
  func review(memoryID: String, keep: Bool) async throws {
    try await APIClient.shared.reviewMemory(id: memoryID, keep: keep)
    // Same reason the edit path below mirrors its content. The verdict lives on the memory and the
    // backend remains its only writer; this records what that write already accepted into the local
    // mirror the desktop reads memories from, so the verdict survives the card being rebuilt
    // instead of reverting to "unreviewed" until an unrelated memory sync happens to run.
    try? await Self.mirrorVerdict(memoryID: memoryID, keep: keep)
  }

  func edit(memoryID: String, content: String) async throws {
    try await APIClient.shared.editMemory(id: memoryID, content: content)
    // Keep the local mirror in step with the write, so the re-read below confirms the edit rather
    // than reporting the text the reader just replaced.
    try? await MemoryStorage.shared.updateContentByBackendId(memoryID, content: content)
  }

  private static func mirrorVerdict(memoryID: String, keep: Bool) async throws {
    guard var record = try await MemoryStorage.shared.getMemoryByBackendId(memoryID) else { return }
    record.reviewed = true
    record.userReview = keep
    guard let mirrored = record.toServerMemory() else { return }
    try await MemoryStorage.shared.syncServerMemory(mirrored)
  }
}

/// Reads the verdict back out of the memory itself.
///
/// The desktop has no single-memory GET; `MemoryStorage` is the mirror the memory sync keeps in
/// step with the backend, and `MemoriesViewModel.refreshSelectedMemory` already treats it as
/// authoritative for one known id. `edited` is not on the desktop's `ServerMemory`, so a
/// correction is recognised the way the reader would recognise it: the stored content no longer
/// matches what the summary captured.
struct LiveMemoryReviewStateReader: MemoryReviewStateReading {
  func verdicts(for items: [MemoryReviewItem]) async throws -> [String: MemoryReviewVerdict] {
    let ids = items.map(\.memoryID).filter { !$0.isEmpty }
    guard !ids.isEmpty else { return [:] }
    let stored = try await MemoryStorage.shared.getMemories(backendIds: ids)
    var byID: [String: ServerMemory] = [:]
    for memory in stored { byID[memory.id] = memory }
    var verdicts: [String: MemoryReviewVerdict] = [:]
    for item in items {
      guard let memory = byID[item.memoryID] else { continue }
      verdicts[item.memoryID] = Self.verdict(for: item, memory: memory)
    }
    return verdicts
  }

  static func verdict(for item: MemoryReviewItem, memory: ServerMemory) -> MemoryReviewVerdict {
    if memory.userReview == false { return .rejected }
    if normalized(memory.content) != normalized(item.content) { return .updated }
    if memory.userReview == true { return .accepted }
    return .none
  }

  private static func normalized(_ text: String) -> String {
    text.trimmingCharacters(in: .whitespacesAndNewlines)
  }
}

// MARK: - Store

/// Drives one card's rows: render-time live read, the three mutations, and the re-read after each.
///
/// One store per card, so the daily-summary section and a `memoryReviewCard` block never share
/// row state. Every transition goes through `MemoryReviewReducer`; this type owns only I/O.
@MainActor
final class MemoryReviewCardStore: ObservableObject {
  @Published private(set) var rows: [String: MemoryReviewRowModel]

  let items: [MemoryReviewItem]
  let source: MemoryReviewSource

  private let mutator: MemoryReviewMutating
  private let stateReader: MemoryReviewStateReading
  /// Test seam only. `nil` means the real `AnalyticsManager`, so production has one path.
  private let analytics: (@MainActor (MemoryReviewSource, MemoryReviewAction, Bool, String) -> Void)?
  private var didLoadLiveState = false

  init(
    items: [MemoryReviewItem],
    source: MemoryReviewSource,
    mutator: MemoryReviewMutating = LiveMemoryReviewMutator(),
    stateReader: MemoryReviewStateReading = LiveMemoryReviewStateReader(),
    analytics: (@MainActor (MemoryReviewSource, MemoryReviewAction, Bool, String) -> Void)? = nil
  ) {
    self.items = items
    self.source = source
    self.mutator = mutator
    self.stateReader = stateReader
    self.analytics = analytics
    var seeded: [String: MemoryReviewRowModel] = [:]
    for item in items { seeded[item.memoryID] = MemoryReviewRowModel() }
    self.rows = seeded
  }

  func row(_ memoryID: String) -> MemoryReviewRowModel {
    rows[memoryID] ?? MemoryReviewRowModel()
  }

  /// Render-time read. Once per card mount: the section is chrome, not a poller.
  ///
  /// The attempt counts only once it has actually succeeded. Marking it up front meant a cancelled
  /// or failed read left every row reading "unreviewed" for as long as the card stayed mounted,
  /// silently and with no way back; leaving the flag down lets the next mount try again.
  func loadLiveStateIfNeeded() async {
    guard !didLoadLiveState, !items.isEmpty else { return }
    didLoadLiveState = await refreshLiveState()
  }

  /// Returns whether the memories could be read at all. A failed read sends no events: reporting
  /// every row as `.none` would be indistinguishable from a day nobody has voted on.
  @discardableResult
  func refreshLiveState() async -> Bool {
    guard let verdicts = try? await stateReader.verdicts(for: items) else { return false }
    for item in items {
      send(.liveStateLoaded(verdicts[item.memoryID] ?? .none), to: item)
    }
    return true
  }

  func send(_ event: MemoryReviewEvent, to item: MemoryReviewItem) {
    let (next, effect) = MemoryReviewReducer.reduce(row(item.memoryID), event)
    rows[item.memoryID] = next
    perform(effect, for: item)
  }

  private func perform(_ effect: MemoryReviewEffect, for item: MemoryReviewItem) {
    switch effect {
    case .none:
      return
    case .review(let keep):
      let action: MemoryReviewAction = keep ? .accept : .reject
      Task { [mutator] in
        do {
          try await mutator.review(memoryID: item.memoryID, keep: keep)
          self.complete(action, succeeded: true, for: item)
        } catch {
          self.complete(action, succeeded: false, for: item)
        }
      }
    case .edit(let content):
      Task { [mutator] in
        do {
          try await mutator.edit(memoryID: item.memoryID, content: content)
          self.complete(.edit, succeeded: true, for: item)
        } catch {
          self.complete(.edit, succeeded: false, for: item)
        }
      }
    case .refreshLiveState:
      Task { await self.refreshLiveState() }
    }
  }

  private func complete(_ action: MemoryReviewAction, succeeded: Bool, for item: MemoryReviewItem) {
    if let analytics {
      analytics(source, action, succeeded, item.category)
    } else {
      AnalyticsManager.shared.trackMemoryReviewAction(
        source: source, action: action, succeeded: succeeded, category: item.category)
    }
    send(succeeded ? .requestSucceeded(action) : .requestFailed(action), to: item)
  }
}

// MARK: - Harness handle

/// The store of the review section currently on screen, for non-production automation only.
///
/// The section owns its store as a `@StateObject` built at init, so a mounted card was reachable
/// from nowhere: an E2E flow could seed a summary and see a card render, but could not read which
/// rows it had bound or click one of them without the cursor. The bridge's `memory_review_*`
/// actions read and drive through this handle, which makes them second *callers* of the same
/// `MemoryReviewCardStore.send` the ✓ / ✗ buttons call — never a second row state machine.
///
/// `weak`, so the handle never keeps a dismissed card's rows alive, and gated: on a production
/// bundle `register` does nothing and `mounted` is always nil, so nothing here is a shipped path.
@MainActor
enum MemoryReviewCardRegistry {
  private(set) static weak var mounted: MemoryReviewCardStore?

  static func register(_ store: MemoryReviewCardStore) {
    register(store, enabled: AppBuild.isNonProduction)
  }

  /// The gate as a parameter, because `AppBuild.isNonProduction` reads `Bundle.main`, and under
  /// `swift test` that is the test runner rather than an Omi bundle — so a test asserting the
  /// production no-op would pass for the wrong reason and a test asserting the registration
  /// could not run at all.
  static func register(_ store: MemoryReviewCardStore, enabled: Bool) {
    guard enabled else { return }
    mounted = store
  }

  /// Identity-checked: two sections can overlap for a frame while the card rebuilds on new rows,
  /// and the outgoing one must not clear the handle the incoming one just took.
  static func unregister(_ store: MemoryReviewCardStore) {
    guard mounted === store else { return }
    mounted = nil
  }
}
