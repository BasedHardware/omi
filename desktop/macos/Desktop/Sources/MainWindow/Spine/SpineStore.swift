//
//  SpineStore.swift — what the spine is made of, and when it is rebuilt.
//
//  Three stores already own this data and none of them is replaced here: conversations stay with
//  `ConversationRepository` behind `AppState`, memories stay with `MemoriesViewModel`, frames stay
//  in Rewind's database. This is a projection over the three, and it deliberately holds no
//  authority — no writes, no second cache, no third opinion about what is starred.
//
//  **The reason it is a store at all is publishing discipline.** A previous pass at this window was
//  slow because pages re-rendered whole on `@Published` churn. So this publishes exactly three
//  things — the composed days, the display list, and whether a load is in flight — and it
//  recomposes only when the *data* changed, not when a view happened to re-evaluate. Composition
//  (expensive, data-shaped) and filtering (cheap, question-shaped) are separate passes for the same
//  reason: typing must not cost a recomposition of a thousand conversations.
//

import Combine
import Foundation

@MainActor
final class SpineStore: ObservableObject {
  /// What the list renders: composed, then narrowed by the chip and the query.
  @Published private(set) var days: [SpineDay] = []
  /// True only for the first fill. A refresh behind an already-populated spine is not a spinner.
  @Published private(set) var isPreparing = true

  /// How many things survived the request. The number the panel's count line renders — one count,
  /// computed once, so the chrome and the body can never quietly disagree about what is on screen.
  @Published private(set) var matchCount = 0

  /// Which kind the shell's chips have soloed. Read by the stream to decide whether attached rows
  /// still indent.
  private(set) var kind: SpineKind = .everything

  /// The request last applied, so an identical push costs nothing.
  private var request = QueryShellRequest()

  /// Composed, unfiltered. The filter pass reads this and never mutates it.
  private var composed: [SpineDay] = []
  /// Per-day screen capture, keyed by the local start of the day.
  private var screen: [Date: SpineDayScreen] = [:]
  private var conversations: [ServerConversation] = []
  private var memories: [SpineMemory] = []

  /// Cheap change detection. Recomposing because a view re-evaluated is the whole class of waste
  /// this store exists to avoid, so ingestion compares a digest before doing any work.
  private var conversationDigest = 0
  private var memoryDigest = 0

  /// Days whose screen capture has been read, so a scroll never re-queries a day it already has.
  private var loadedScreenDays: Set<Date> = []
  private var screenLoadsInFlight: Set<Date> = []

  private let calendar: Calendar

  init(calendar: Calendar = .current) {
    self.calendar = calendar
  }

  // MARK: - Input

  /// Take the current projection of the two account-level stores.
  ///
  /// Called from the view's `onReceive`/`onChange`, which fire far more often than the data
  /// actually changes — hence the digest.
  func ingest(conversations: [ServerConversation], memories: [ServerMemory]) {
    let conversationDigest = Self.digest(conversations)
    let memoryDigest = Self.digest(memories)
    guard
      conversationDigest != self.conversationDigest || memoryDigest != self.memoryDigest
    else { return }

    self.conversationDigest = conversationDigest
    self.memoryDigest = memoryDigest
    self.conversations = conversations
    self.memories = memories.map {
      SpineMemory(
        id: $0.id,
        text: $0.content,
        timestamp: $0.capturedAt ?? $0.createdAt,
        conversationID: $0.conversationId
      )
    }
    recompose()
    loadScreenForVisibleDays()
  }

  /// The shell's request: the term, the chip, the time window. Cheap enough to call on every
  /// keystroke, because it only re-runs the filter pass.
  func apply(request: QueryShellRequest) {
    guard request != self.request else { return }
    self.request = request
    kind = Self.kind(for: request.kind)
    refilter()
  }

  private static func kind(for shellKind: QueryShellKind) -> SpineKind {
    switch shellKind {
    case .all: return .everything
    case .conversations: return .conversations
    case .memories: return .memories
    case .rewind: return .screen
    }
  }

  /// Reads the days the spine now spans, plus today, and fills in any screen capture it is missing.
  ///
  /// Today is always included even when nothing was said: a day of nothing but screen is still a
  /// day, and it is the day the user is most likely looking for.
  func loadScreenForVisibleDays() {
    var wanted: Set<Date> = [calendar.startOfDay(for: Date())]
    for conversation in conversations {
      wanted.insert(calendar.startOfDay(for: conversation.startedAt ?? conversation.createdAt))
    }
    for memory in memories {
      wanted.insert(calendar.startOfDay(for: memory.timestamp))
    }

    let missing = wanted.subtracting(loadedScreenDays).subtracting(screenLoadsInFlight)
    guard !missing.isEmpty else {
      isPreparing = false
      return
    }
    // Newest first: the day at the top of the spine is the one the user is reading.
    for day in missing.sorted(by: >) {
      screenLoadsInFlight.insert(day)
      Task { [weak self] in
        guard let self else { return }
        let result = await SpineScreenIndex.load(day: day, calendar: self.calendar)
        self.absorb(day: day, result: result)
      }
    }
  }

  private func absorb(day: Date, result: SpineDayScreen) {
    screenLoadsInFlight.remove(day)
    loadedScreenDays.insert(day)
    // A day with no capture still counts as read, so the spine does not re-query it forever.
    if result != .empty { screen[day] = result }
    if screenLoadsInFlight.isEmpty { isPreparing = false }
    guard result != .empty else { return }
    recompose()
  }

  // MARK: - Readouts

  /// The hour histogram for one day, normalised to its own busiest hour.
  ///
  /// Normalised per day rather than across the account: the rail is a picture of *that* day's
  /// shape, and scaling it against a record-breaking day months ago would flatten every ordinary
  /// day into a straight line.
  func density(for dayID: Date) -> [Double] {
    guard let counts = screen[dayID]?.hourCounts, let peak = counts.max(), peak > 0 else {
      return Array(repeating: 0, count: 24)
    }
    return counts.map { Double($0) / Double(peak) }
  }

  func momentCount(for dayID: Date) -> Int { screen[dayID]?.total ?? 0 }

  // MARK: - Composition

  private func recompose() {
    composed = SpineComposer.compose(
      conversations: conversations,
      memories: memories,
      screen: screen,
      calendar: calendar
    )
    refilter()
  }

  private func refilter() {
    let filtered = SpineComposer.filter(
      composed, kind: kind, query: request.term, earliest: request.range.earliest())
    days = filtered
    matchCount = filtered.reduce(0) { $0 + $1.matchCount }
  }

  // MARK: - Digests

  /// A conversation's identity plus the one field the spine draws that can change under it.
  private static func digest(_ conversations: [ServerConversation]) -> Int {
    var hasher = Hasher()
    hasher.combine(conversations.count)
    for conversation in conversations {
      hasher.combine(conversation.id)
      hasher.combine(conversation.starred)
      hasher.combine(conversation.structured.title)
    }
    return hasher.finalize()
  }

  private static func digest(_ memories: [ServerMemory]) -> Int {
    var hasher = Hasher()
    hasher.combine(memories.count)
    for memory in memories {
      hasher.combine(memory.id)
      hasher.combine(memory.content)
    }
    return hasher.finalize()
  }
}
