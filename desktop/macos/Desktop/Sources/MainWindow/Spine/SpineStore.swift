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
  /// still tuck in close under their conversation.
  private(set) var kind: SpineKind = .everything

  /// The calendar the days were composed in. Recap lookups must format `SpineDay.id` with this
  /// calendar; a UTC formatter here is the class of bug that silently misses every date.
  let calendar: Calendar

  /// The request last applied, so an identical push costs nothing.
  private var request = QueryShellRequest()

  /// Composed, unfiltered. The filter pass reads this and never mutates it.
  private var composed: [SpineDay] = []
  /// Per-day screen capture, keyed by the local start of the day.
  private var screen: [Date: SpineDayScreen] = [:]
  private var conversations: [ServerConversation] = []
  private var memories: [SpineMemory] = []
  private var tasks: [SpineTask] = []

  /// Cheap change detection. Recomposing because a view re-evaluated is the whole class of waste
  /// this store exists to avoid, so ingestion compares a digest before doing any work.
  private var conversationDigest = 0
  private var memoryDigest = 0
  private var taskDigest = 0

  /// Days whose screen capture has been read, so a scroll never re-queries a day it already has.
  private var loadedScreenDays: Set<Date> = []
  /// Days waiting to be read, newest first, and the few being read right now.
  ///
  /// **A queue rather than a fan-out.** This used to spawn one `Task` per missing day the moment it
  /// heard about them, which was fine for the handful of days one page of conversations names and
  /// is not fine now the spine loads the whole account: a year of history would put hundreds of
  /// simultaneous reads on Rewind's pool, and the surface competing with them is the one the user is
  /// scrolling.
  private var screenQueue: [Date] = []
  private var queuedScreenDays: Set<Date> = []
  private var activeScreenLoads = 0
  /// Three at a time: enough that the newest days land together, few enough that Rewind's pool is
  /// never the reason a scroll stutters.
  static let maximumConcurrentScreenLoads = 3

  /// Whether the one-off walk over the capture database's own days has run.
  private var didDiscoverCapturedDays = false

  /// The coalescing window for recomposition.
  ///
  /// Composition is the expensive half of this store and its cost is the size of the corpus, not
  /// the size of the page that arrived: measured in a debug build, composing the first page (50
  /// conversations, 97 memories → 175 rows) takes 1.8 ms, and composing the whole account (995
  /// conversations, 5,849 memories → 5,917 rows) takes 74 ms. Hydration lands roughly eighty pages,
  /// so rebuilding per page would spend seconds of main-actor time behind a list the user may be
  /// scrolling. 300 ms is long enough to absorb a page or two — they arrive every few hundred
  /// milliseconds — and far too short to read as a delay on a list that is already on screen.
  private static let recomposeCoalescingWindow: Duration = .milliseconds(300)
  private var recomposeTask: Task<Void, Never>?

  init(calendar: Calendar = .current) {
    self.calendar = calendar
  }

  // MARK: - Input

  /// Take the current projection of the three account-level stores.
  ///
  /// Called from the view's `onReceive`/`onChange`, which fire far more often than the data
  /// actually changes — hence the digest.
  func ingest(
    conversations: [ServerConversation],
    memories: [ServerMemory],
    tasks: [TaskActionItem] = []
  ) {
    let conversationDigest = Self.digest(conversations)
    let memoryDigest = Self.digest(memories)
    let taskDigest = Self.digest(tasks)
    guard
      conversationDigest != self.conversationDigest || memoryDigest != self.memoryDigest
        || taskDigest != self.taskDigest
    else { return }

    self.conversationDigest = conversationDigest
    self.memoryDigest = memoryDigest
    self.taskDigest = taskDigest
    self.conversations = conversations
    let conversationTitles = Dictionary(
      lastWriteWins: conversations.map { conversation in
        let title = conversation.structured.title.trimmingCharacters(in: .whitespacesAndNewlines)
        return (conversation.id, title.isEmpty ? "Untitled conversation" : title)
      })
    self.memories = memories.map {
      SpineMemory(
        id: $0.id,
        text: $0.content,
        timestamp: $0.capturedAt ?? $0.createdAt,
        conversationID: $0.conversationId,
        sourceConversationTitle: $0.conversationId.flatMap { conversationTitles[$0] }
      )
    }
    self.tasks = tasks.filter { !$0.isRetired }.map {
      SpineTask(
        task: $0,
        sourceConversationTitle: $0.conversationId.flatMap { conversationTitles[$0] }
      )
    }
    recomposeSoon()
    discoverCapturedDays()
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
    case .tasks: return .tasks
    case .rewind: return .screen
    }
  }

  /// Fills in screen capture for every day the spine now spans, plus today.
  ///
  /// **Driven off the composed days rather than off the records.** The obvious version walked every
  /// conversation and memory asking `startOfDay` for each, which is fine for one page and is 6,800
  /// calendar conversions per page once the whole account is paging in — eighty times over. The
  /// composer has already grouped those records into at most a few hundred days, so reading its
  /// answer costs one iteration per *day* and cannot drift from what the spine actually shows.
  ///
  /// Today is always included even when nothing was said: a day of nothing but screen is still a
  /// day, and it is the day the user is most likely looking for.
  private func loadScreenForComposedDays() {
    var wanted = Set(composed.map(\.id))
    wanted.insert(calendar.startOfDay(for: Date()))
    enqueueScreen(days: wanted)
  }

  /// Asks the capture database itself which days it holds, once.
  ///
  /// Days reach the queue above only by way of a conversation or a memory, so a day spent entirely
  /// at the keyboard with nothing said and nothing learned would never be asked about at all. This
  /// is the only path that can see one.
  private func discoverCapturedDays() {
    guard !didDiscoverCapturedDays else { return }
    didDiscoverCapturedDays = true
    Task { [weak self] in
      guard let self else { return }
      let days = await SpineScreenIndex.capturedDays(calendar: self.calendar)
      self.enqueueScreen(days: Set(days))
    }
  }

  private func enqueueScreen(days: Set<Date>) {
    let missing = days.subtracting(loadedScreenDays).subtracting(queuedScreenDays)
    guard !missing.isEmpty else {
      if screenQueue.isEmpty, activeScreenLoads == 0 { isPreparing = false }
      return
    }
    queuedScreenDays.formUnion(missing)
    // Newest first: the day at the top of the spine is the one the user is reading.
    screenQueue.append(contentsOf: missing)
    screenQueue.sort(by: >)
    pumpScreenLoads()
  }

  private func pumpScreenLoads() {
    while activeScreenLoads < Self.maximumConcurrentScreenLoads, !screenQueue.isEmpty {
      let day = screenQueue.removeFirst()
      activeScreenLoads += 1
      Task { [weak self] in
        guard let self else { return }
        let result = await SpineScreenIndex.load(day: day, calendar: self.calendar)
        self.absorb(day: day, result: result)
      }
    }
  }

  private func absorb(day: Date, result: SpineDayScreen) {
    activeScreenLoads -= 1
    queuedScreenDays.remove(day)
    loadedScreenDays.insert(day)
    // A day with no capture still counts as read, so the spine does not re-query it forever.
    if result != .empty { screen[day] = result }
    if screenQueue.isEmpty, activeScreenLoads == 0 { isPreparing = false }
    if result != .empty { recomposeSoon() }
    pumpScreenLoads()
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

  /// How much screen capture a day holds — `nil` until that day has actually been read.
  ///
  /// The two absences look identical in `screen` and are not the same claim. A day whose read came
  /// back empty is deliberately not stored (so a scroll never re-queries it forever), and a day that
  /// is still sitting in `screenQueue` is not stored yet either. Collapsing both to `0` is what let
  /// the rail print a confident "0 screen moments" for a day it had not looked at. `loadedScreenDays`
  /// already knows the difference; this is it, told.
  func momentCount(for dayID: Date) -> Int? {
    guard loadedScreenDays.contains(dayID) else { return nil }
    return screen[dayID]?.total ?? 0
  }

  // MARK: - Composition

  /// Recompose, but at most once per coalescing window — unless there is nothing on screen yet.
  ///
  /// **First paint is never delayed.** An empty spine recomposes on the spot, because the whole
  /// point of the store is that the first day is on screen before anything else has finished
  /// loading. Every arrival after that is growth behind an already-readable list, and growth is
  /// worth batching: hydration lands a page every few hundred milliseconds and screen capture lands
  /// a day at a time, and rebuilding several thousand rows for each one is how a background fill
  /// turns into a scroll that stutters.
  private func recomposeSoon() {
    guard !composed.isEmpty else {
      recompose()
      return
    }
    guard recomposeTask == nil else { return }
    recomposeTask = Task { [weak self] in
      try? await Task.sleep(for: Self.recomposeCoalescingWindow)
      guard let self, !Task.isCancelled else { return }
      self.recomposeTask = nil
      self.recompose()
    }
  }

  private func recompose() {
    recomposeTask?.cancel()
    recomposeTask = nil
    composed = SpineComposer.compose(
      conversations: conversations,
      memories: memories,
      tasks: tasks,
      screen: screen,
      calendar: calendar
    )
    refilter()
    // The days the spine now spans are exactly the days its screen capture has to cover.
    loadScreenForComposedDays()
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

  private static func digest(_ tasks: [TaskActionItem]) -> Int {
    var hasher = Hasher()
    hasher.combine(tasks.count)
    for task in tasks {
      hasher.combine(task.id)
      hasher.combine(task.description)
      hasher.combine(task.completed)
      hasher.combine(task.createdAt)
      hasher.combine(task.conversationId)
      hasher.combine(task.source)
      hasher.combine(task.isRetired)
      hasher.combine(task.provenance?.count ?? 0)
      for evidence in task.provenance ?? [] {
        hasher.combine(evidence.id)
        hasher.combine(evidence.kind.rawValue)
        hasher.combine(evidence.scope.rawValue)
        hasher.combine(evidence.deviceId)
        hasher.combine(evidence.startSeconds)
        hasher.combine(evidence.endSeconds)
        hasher.combine(evidence.transcriptSegmentIds)
      }
    }
    return hasher.finalize()
  }
}
