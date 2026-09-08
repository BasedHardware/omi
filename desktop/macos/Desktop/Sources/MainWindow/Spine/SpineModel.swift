//
//  SpineModel.swift — the day, as one list.
//
//  A conversation, the memories and tasks it produced, and the frames that were on screen while it
//  happened are records of the same minute. The app used to file them in separate destinations, so
//  answering "what was I doing at eight?" meant visiting each one and reconciling them by eye.
//  This composes them into **one reverse-chronological stream, grouped by day** — the order they
//  actually happened in, newest first.
//
//  **Conversations stay dominant and every extracted record stays first-class.** Memories, tasks,
//  and screen moments render *close under* the conversation that produced them — tighter air, no
//  timestamp of their own — which is what keeps a conversation the thing your eye lands on. They
//  are not children of a card, though: they are rows of the same spine, and every row sits on the
//  same leading grid, so a strip of frames starts at the same left edge whether it hangs under a
//  conversation or stands on its own. Filtering to one kind is a real filter over the whole stream
//  rather than a different screen. When one kind is soloed the closeness collapses and every row
//  states its own time (see `SpineRow.isAttached` and `SpineComposer.compose`), so the spine stays
//  a clock rather than degrading into a flat list.
//
//  Everything here is a pure function of its inputs, deliberately: the composition is the part with
//  rules in it (what attaches to what, what a day header counts, where the brain map is filed), and
//  rules that can only be checked by looking at a screenshot are rules that drift.
//

import Foundation

// MARK: - Kind

/// The one axis the spine filters on.
///
/// `everything` is not a fourth kind of row — it is the absence of a filter — which is why
/// `SpineRow.kind` can never hold it.
enum SpineKind: String, CaseIterable, Identifiable, Sendable {
  case everything
  case conversations
  case memories
  case tasks
  case screen

  var id: String { rawValue }

  var title: String {
    switch self {
    case .everything: return "Everything"
    case .conversations: return "Conversations"
    case .memories: return "Memories"
    case .tasks: return "Tasks"
    case .screen: return "Screen"
    }
  }

  /// The chips, in the order they are shown.
  static let chips: [SpineKind] = [.everything, .conversations, .memories, .tasks, .screen]
}

// MARK: - Leaves

/// One frame that was on screen.
///
/// Deliberately not `Screenshot`: the spine needs seven small fields to lay a row out and decode a
/// thumbnail, and carrying the full record — OCR text, its bounding-box JSON, an embedding blob —
/// through a day of thousands of frames is the difference between a scroll and a stall.
///
/// It carries exactly the columns `RewindThumbnailLoader` needs to find the pixels, so a strip
/// never has to go back to the database for a second row per picture.
struct SpineMoment: Identifiable, Equatable, Sendable {
  let id: Int64
  let timestamp: Date
  let appName: String
  let windowTitle: String?
  let imagePath: String?
  let videoChunkPath: String?
  let frameOffset: Int?

  /// What the caption says. The window title is the specific thing; the app is the true fallback.
  var label: String {
    guard let windowTitle, !windowTitle.isEmpty else { return appName }
    return windowTitle
  }

  /// The record the thumbnail loader wants, rebuilt from what the row already holds. Every field
  /// the decoder does not read is left at its default, so this allocates nothing large.
  var screenshot: Screenshot {
    Screenshot(
      id: id,
      timestamp: timestamp,
      appName: appName,
      windowTitle: windowTitle,
      imagePath: imagePath,
      videoChunkPath: videoChunkPath,
      frameOffset: frameOffset
    )
  }
}

/// One memory, as the spine needs it.
struct SpineMemory: Identifiable, Equatable, Sendable {
  let id: String
  let text: String
  let timestamp: Date
  /// The conversation this memory came out of, when the server recorded one.
  let conversationID: String?
  let sourceConversationTitle: String?

  init(
    id: String,
    text: String,
    timestamp: Date,
    conversationID: String?,
    sourceConversationTitle: String? = nil
  ) {
    self.id = id
    self.text = text
    self.timestamp = timestamp
    self.conversationID = conversationID
    self.sourceConversationTitle = sourceConversationTitle
  }
}

/// One task in the chronology, retaining its authoritative task-store value for completion writes.
struct SpineTask: Identifiable, Equatable {
  let task: TaskActionItem
  let sourceConversationTitle: String?

  var id: String { task.id }
  var text: String { task.description }
  var timestamp: Date { task.createdAt }
  var conversationID: String? { task.conversationId }
  var sourceLabel: String {
    if let sourceConversationTitle { return "From \(sourceConversationTitle)" }
    switch task.source {
    case "screenshot": return "From screen capture"
    case "manual": return "Added manually"
    case .some(let source) where source.hasPrefix("transcription"): return "From a recording"
    default: return "Task"
    }
  }
}

/// A memory's text, split where it repeats.
///
/// Memories are generated, and generated copy runs to a template: four in a row arrive as
/// "Focused on Omi App: …", "Focused on Omi: …", "Focused on Omi App: …", "Focused on Omi Memories: …".
/// Set as one sentence in the largest reading role the spine owns, the half that is the *same* every
/// time is the loudest thing on the surface, and the half that is actually this memory is what the eye
/// gets to last.
///
/// So the repeated half is presented as a quiet label over the sentence rather than as its opening
/// words. **Nothing is hidden and nothing is truncated:** `label` and `body` together are the whole
/// text less the colon that already separated them, and a memory with no such prefix keeps its
/// sentence whole and has no label at all.
struct SpineMemoryCopy: Equatable, Sendable {
  /// The words before the colon, or nil when the text is a plain sentence.
  let label: String?
  /// The rest of it — and the whole of it when there is no label.
  let body: String
}

/// A conversation plus the two counts the row states about it.
struct SpineConversation: Identifiable, Equatable {
  let conversation: ServerConversation
  let memoryCount: Int
  let taskCount: Int
  let momentCount: Int

  var id: String { conversation.id }

  var startedAt: Date { conversation.startedAt ?? conversation.createdAt }

  /// The end of the conversation's window on the clock. `finishedAt` when the server sent one;
  /// otherwise the start, which makes the window a point and attaches nothing by accident.
  var finishedAt: Date { conversation.finishedAt ?? startedAt }

  var duration: TimeInterval { max(0, finishedAt.timeIntervalSince(startedAt)) }

  var title: String {
    let title = conversation.structured.title.trimmingCharacters(in: .whitespacesAndNewlines)
    return title.isEmpty ? "Untitled conversation" : title
  }

  /// The tile glyph. An empty emoji from the server would render as a blank circle, so the category
  /// initial is not used as a fallback — a speech mark is, because every conversation is one.
  var emoji: String {
    let emoji = conversation.structured.emoji.trimmingCharacters(in: .whitespacesAndNewlines)
    return emoji.isEmpty ? "💬" : emoji
  }

  var isStarred: Bool { conversation.starred }

  /// "8m 9s · 2 memories · 6 screen moments" — and each clause is dropped when its count is zero
  /// rather than shown as "0 memories", which reads as a defect rather than as an absence.
  var subtitle: String {
    var parts: [String] = []
    if duration >= 1 { parts.append(SpineFormat.duration(duration)) }
    if memoryCount > 0 { parts.append(SpineFormat.plural(memoryCount, "memory", "memories")) }
    if taskCount > 0 { parts.append(SpineFormat.plural(taskCount, "task", "tasks")) }
    if momentCount > 0 {
      parts.append(SpineFormat.plural(momentCount, "screen moment", "screen moments"))
    }
    if parts.isEmpty { parts.append(SpineFormat.time(startedAt)) }
    return parts.joined(separator: " · ")
  }

  /// What a typed query is matched against.
  var searchText: String {
    [title, conversation.structured.overview, conversation.structured.category]
      .joined(separator: " ")
      .lowercased()
  }
}

/// The end-of-day brain-map card's copy.
///
/// It is a summary of a day's memories and it is filed under memories — never a destination of its
/// own. Opening it routes to the surface that owns the graph.
struct SpineBrainMap: Equatable, Sendable {
  let memoryCount: Int
  let clusterCount: Int

  var headline: String { "How today's memories connect" }

  var detail: String {
    let memories = SpineFormat.plural(memoryCount, "new memory", "new memories")
    guard clusterCount > 1 else { return "\(memories) today. Open the map to see what they connect to." }
    let clusters = SpineFormat.plural(clusterCount, "cluster", "clusters")
    return "\(memories), \(clusters). Open the map to see what they connect to."
  }
}

// MARK: - Row

/// One row of the spine.
struct SpineRow: Identifiable, Equatable {
  enum Content: Equatable {
    case conversation(SpineConversation)
    case memories([SpineMemory])
    case tasks([SpineTask])
    /// The frames a strip draws, plus how many there were in the window they were sampled from —
    /// a strip that silently shows 8 of 184 is a strip that lies about the day.
    case moments(shown: [SpineMoment], total: Int)
    case brainMap(SpineBrainMap)
  }

  let id: String
  /// Where this row sits on the clock. The only thing the stream is ordered by.
  let anchor: Date
  /// Never `.everything`: a row is one kind of thing.
  let kind: SpineKind
  /// True when this row was produced by the conversation directly above it. Set close under it —
  /// on the same leading grid as every other row — while the whole spine is shown; flattened, and
  /// given its own timestamp, the moment one kind is soloed.
  let isAttached: Bool
  let content: Content

  /// What a typed query is matched against.
  let searchText: String
}

// MARK: - Day

/// Formats `SpineDay.id` (local start-of-day) as the backend's `YYYY-MM-DD` key.
///
/// Must use the same calendar the day was composed in. A UTC formatter here renders the
/// previous evening in every zone east of UTC, and every recap lookup misses.
enum SpineDayDateKey {
  static func string(from dayID: Date, calendar: Calendar) -> String? {
    let parts = calendar.dateComponents([.year, .month, .day], from: dayID)
    guard let year = parts.year, let month = parts.month, let day = parts.day else { return nil }
    return String(format: "%04d-%02d-%02d", year, month, day)
  }
}

/// One day of the spine, with the header that counts it.
struct SpineDay: Identifiable, Equatable {
  /// The local start of the day. Stable across recompositions, which is what keeps the sticky
  /// header from being rebuilt on every scroll.
  let id: Date
  let title: String
  let momentCount: Int
  let conversationCount: Int
  let taskCount: Int
  let rows: [SpineRow]

  /// How many memories the day holds. Counted off the rows rather than carried alongside them, so it
  /// cannot drift from what is actually drawn.
  var memoryCount: Int {
    rows.reduce(0) { total, row in
      if case .memories(let memories) = row.content { return total + memories.count }
      return total
    }
  }

  /// "1,204 moments · 4 conversations · 9 memories". Zero clauses are dropped for the same reason as
  /// on a row.
  ///
  /// **This line is the whole of a collapsed day.** With the rows folded away it is the only thing
  /// saying what is behind the header, so it names every kind the day holds — a day that hides nine
  /// memories and says nothing about them reads as a day that produced none.
  var subtitle: String {
    var parts: [String] = []
    if momentCount > 0 { parts.append(SpineFormat.plural(momentCount, "moment", "moments")) }
    if conversationCount > 0 {
      parts.append(SpineFormat.plural(conversationCount, "conversation", "conversations"))
    }
    if memoryCount > 0 { parts.append(SpineFormat.plural(memoryCount, "memory", "memories")) }
    if taskCount > 0 { parts.append(SpineFormat.plural(taskCount, "task", "tasks")) }
    return parts.joined(separator: " · ")
  }

  /// How many *things* this day is showing, which is not the same as how many rows it drew: one
  /// memory row can carry three memories and one strip can stand for a hundred and eighty-four
  /// frames. The panel's count line is a fraction of the corpus, so it has to count the corpus's
  /// units rather than the spine's.
  var matchCount: Int {
    rows.reduce(0) { total, row in
      switch row.content {
      case .conversation: return total + 1
      case .memories(let memories): return total + memories.count
      case .tasks(let tasks): return total + tasks.count
      case .moments(_, let count): return total + count
      case .brainMap: return total
      }
    }
  }
}

// MARK: - Folded days

/// Which days are folded shut, as a value.
///
/// **Keyed by the day's own identity, never by its position.** The spine pages older days in as you
/// scroll, so a set keyed by index folds a *different* day the moment a page lands — the day you
/// collapsed reopens and the one above it closes, which reads as the list rearranging itself.
///
/// **Session-only, deliberately.** A day found silently collapsed on the next launch is
/// indistinguishable from a day whose capture failed, and this surface is the one place a user checks
/// whether Omi recorded anything at all. Folding is a thing you do while reading, not a preference.
struct SpineDayCollapse: Equatable {
  private var folded: Set<Date> = []

  init() {}

  var isEmpty: Bool { folded.isEmpty }

  func contains(_ dayID: Date) -> Bool { folded.contains(dayID) }

  mutating func toggle(_ dayID: Date) {
    if folded.contains(dayID) {
      folded.remove(dayID)
    } else {
      folded.insert(dayID)
    }
  }
}

// MARK: - Screen moments, per day

/// What the spine knows about one day of screen capture.
///
/// The exact `total` and the exact `hourCounts` come from every row in the day; `sampled` is the
/// handful a strip can actually draw. Keeping the count separate from the sample is what lets a
/// header say 1,204 while the strip shows eight of them.
struct SpineDayScreen: Equatable, Sendable {
  var total: Int = 0
  /// 24 entries, indexed by *local* hour.
  var hourCounts: [Int] = Array(repeating: 0, count: 24)
  var sampled: [SpineMoment] = []

  static let empty = SpineDayScreen()
}

// MARK: - Composition

enum SpineComposer {
  /// How many frames a single strip draws. Eight is what fits a strip at the panel's narrowest
  /// before it starts scrolling, and a strip is a glance, not a gallery.
  static let momentsPerStrip = 8

  /// A gap this long ends a run of unattached screen moments and starts the next one. Forty-five
  /// minutes is long enough that a coffee break does not split a work session in two, and short
  /// enough that morning and evening are never one row.
  static let momentClusterGap: TimeInterval = 45 * 60

  /// Compose the whole spine, unfiltered.
  ///
  /// **Composition and filtering are deliberately two steps.** Composing is the expensive half —
  /// it groups a thousand conversations, attaches every memory and every frame, and sorts each day
  /// — and it does not depend on the chips or on what has been typed. Filtering is a scan.
  /// Recomposing on every keystroke would make the query bar feel like the list is thinking; this
  /// way the store composes when the *data* changes and filters when the *question* does.
  ///
  /// It also keeps the day header honest: `filter(_:kind:query:)` recomputes the counts from the
  /// rows it leaves on screen, so a filtered spine does not claim that hidden records are visible.
  ///
  /// - Parameters:
  ///   - conversations: the loaded page(s) of the real conversation list, any order.
  ///   - memories: the loaded memories, any order.
  ///   - screen: per-day screen capture, keyed by the local start of the day.
  static func compose(
    conversations rawConversations: [ServerConversation],
    memories rawMemories: [SpineMemory],
    tasks rawTasks: [SpineTask] = [],
    screen: [Date: SpineDayScreen],
    calendar: Calendar = .current
  ) -> [SpineDay] {
    // **Every row id below is derived from a record id, so a repeated record is a repeated
    // `SwiftUI` identity** — which in a `ForEach` is not a cosmetic duplicate but undefined
    // behaviour in the list's own diffing. The two stores upstream both page by offset against a
    // list the server keeps re-sorting, so an overlapping page is a matter of timing rather than of
    // correctness, and paging the whole account makes many more chances for it. The spine holds no
    // authority over either store, but it does own its own row identities, so it keeps the first
    // sighting of each and drops the rest here rather than rendering the same day twice.
    let conversations = uniqued(rawConversations, by: \.id)
    let memories = uniqued(rawMemories, by: \.id)
    let tasks = uniqued(rawTasks, by: \.id)

    // Memories that name a conversation we actually hold attach to it; everything else stands on
    // its own at the time it was made. A memory pointing at a conversation on a page we have not
    // loaded must not vanish — it becomes a standalone row rather than being dropped.
    let conversationIDs = Set(conversations.map(\.id))
    var attachedMemories: [String: [SpineMemory]] = [:]
    var looseMemories: [SpineMemory] = []
    for memory in memories {
      if let conversationID = memory.conversationID, conversationIDs.contains(conversationID) {
        attachedMemories[conversationID, default: []].append(memory)
      } else {
        looseMemories.append(memory)
      }
    }

    var attachedTasks: [String: [SpineTask]] = [:]
    var looseTasks: [SpineTask] = []
    for task in tasks {
      if let conversationID = task.conversationID, conversationIDs.contains(conversationID) {
        attachedTasks[conversationID, default: []].append(task)
      } else {
        looseTasks.append(task)
      }
    }

    // Group the day's conversations first, so a moment can ask which conversation's window it
    // falls inside without scanning every conversation in the account.
    var conversationsByDay: [Date: [SpineConversation]] = [:]
    for conversation in conversations {
      let started = conversation.startedAt ?? conversation.createdAt
      let day = calendar.startOfDay(for: started)
      let summary = SpineConversation(
        conversation: conversation,
        memoryCount: attachedMemories[conversation.id]?.count ?? 0,
        taskCount: attachedTasks[conversation.id]?.count ?? 0,
        momentCount: 0
      )
      conversationsByDay[day, default: []].append(summary)
    }

    var memoriesByDay: [Date: [SpineMemory]] = [:]
    for memory in looseMemories {
      memoriesByDay[calendar.startOfDay(for: memory.timestamp), default: []].append(memory)
    }
    var tasksByDay: [Date: [SpineTask]] = [:]
    for task in looseTasks {
      tasksByDay[calendar.startOfDay(for: task.timestamp), default: []].append(task)
    }

    let days = Set(conversationsByDay.keys)
      .union(memoriesByDay.keys)
      .union(tasksByDay.keys)
      .union(screen.keys)
      .sorted(by: >)

    return days.map { day in
      composeDay(
        day: day,
        conversations: conversationsByDay[day] ?? [],
        attachedMemories: attachedMemories,
        attachedTasks: attachedTasks,
        looseMemories: memoriesByDay[day] ?? [],
        looseTasks: tasksByDay[day] ?? [],
        screen: screen[day] ?? .empty,
        calendar: calendar
      )
    }
  }

  /// Narrows a composed spine to one kind, one query and one time window, in place.
  ///
  /// A day with nothing left is dropped whole — header and all — because a sticky day header over
  /// no rows is a heading for content that is not there.
  ///
  /// - Parameter query: already trimmed and case-folded by the shell (`QueryShellRequest.term`), so
  ///   there is one normalisation in the product rather than one per call site.
  static func filter(
    _ days: [SpineDay],
    kind: SpineKind,
    query: String,
    earliest: Date? = nil
  ) -> [SpineDay] {
    let needle = query
    guard kind != .everything || !needle.isEmpty || earliest != nil else { return days }

    return days.compactMap { day in
      var rows = day.rows.filter { row in
        guard kind == .everything || row.kind == kind else { return false }
        if let earliest, row.anchor < earliest { return false }
        guard !needle.isEmpty else { return true }
        return row.searchText.contains(needle)
      }
      guard !rows.isEmpty else { return nil }

      if kind != .everything {
        // Soloed: nothing is a child of anything, so every row earns its own place on the clock.
        rows = rows.map {
          SpineRow(
            id: $0.id, anchor: $0.anchor, kind: $0.kind, isAttached: false, content: $0.content,
            searchText: $0.searchText)
        }
      }

      // The day header describes the rows currently on screen. Carrying the composed day's totals
      // through a query made an empty-looking kind filter still say "1 conversation · 1 memory";
      // recompute each unit count after narrowing while keeping the timeline's row ordering intact.
      let momentCount = rows.reduce(0) { total, row in
        guard case .moments(_, let count) = row.content else { return total }
        return total + count
      }
      let conversationCount = rows.reduce(0) { total, row in
        guard case .conversation = row.content else { return total }
        return total + 1
      }
      let taskCount = rows.reduce(0) { total, row in
        guard case .tasks(let tasks) = row.content else { return total }
        return total + tasks.count
      }

      return SpineDay(
        id: day.id,
        title: day.title,
        momentCount: momentCount,
        conversationCount: conversationCount,
        taskCount: taskCount,
        rows: rows
      )
    }
  }

  private static func composeDay(
    day: Date,
    conversations: [SpineConversation],
    attachedMemories: [String: [SpineMemory]],
    attachedTasks: [String: [SpineTask]],
    looseMemories: [SpineMemory],
    looseTasks: [SpineTask],
    screen: SpineDayScreen,
    calendar: Calendar
  ) -> SpineDay {
    let ordered = conversations.sorted { $0.startedAt > $1.startedAt }

    // Attach each sampled frame to the conversation whose window contains it. Newest-first over
    // newest-first, so this is a single pass rather than a lookup per frame.
    //
    // The cursor advances only past conversations that **start after** this frame — those are in
    // the frame's future and, because both runs descend, in every later frame's future too, so
    // skipping them is permanent and safe. Advancing on `finishedAt` instead looks equivalent and
    // is not: one frame newer than the newest conversation would walk the cursor off the end and
    // every older frame after it would be orphaned.
    var momentsByConversation: [String: [SpineMoment]] = [:]
    var looseMoments: [SpineMoment] = []
    var cursor = 0
    for moment in screen.sampled.sorted(by: { $0.timestamp > $1.timestamp }) {
      while cursor < ordered.count, ordered[cursor].startedAt > moment.timestamp {
        cursor += 1
      }
      if cursor < ordered.count, moment.timestamp <= ordered[cursor].finishedAt {
        momentsByConversation[ordered[cursor].id, default: []].append(moment)
      } else {
        looseMoments.append(moment)
      }
    }

    var rows: [SpineRow] = []

    for summary in ordered {
      let memories = (attachedMemories[summary.id] ?? []).sorted { $0.timestamp > $1.timestamp }
      let moments = momentsByConversation[summary.id] ?? []
      let tasks = (attachedTasks[summary.id] ?? []).sorted { $0.timestamp > $1.timestamp }
      let counted = SpineConversation(
        conversation: summary.conversation,
        memoryCount: memories.count,
        taskCount: tasks.count,
        momentCount: moments.count
      )
      rows.append(
        SpineRow(
          id: "conv:\(summary.id)",
          anchor: summary.startedAt,
          kind: .conversations,
          isAttached: false,
          content: .conversation(counted),
          searchText: counted.searchText
        ))
      if !memories.isEmpty {
        rows.append(memoryRow(memories, id: "conv-mem:\(summary.id)", isAttached: true))
      }
      if !tasks.isEmpty {
        rows.append(taskRow(tasks, id: "conv-task:\(summary.id)", isAttached: true))
      }
      if !moments.isEmpty {
        rows.append(
          momentRow(moments, total: moments.count, id: "conv-shot:\(summary.id)", isAttached: true))
      }
    }

    for memory in looseMemories.sorted(by: { $0.timestamp > $1.timestamp }) {
      rows.append(memoryRow([memory], id: "mem:\(memory.id)", isAttached: false))
    }

    for task in looseTasks.sorted(by: { $0.timestamp > $1.timestamp }) {
      rows.append(taskRow([task], id: "task:\(task.id)", isAttached: false))
    }

    for cluster in clusters(of: looseMoments) {
      guard let first = cluster.first else { continue }
      rows.append(
        momentRow(cluster, total: cluster.count, id: "shot:\(first.id)", isAttached: false))
    }

    rows.sort { lhs, rhs in
      if lhs.anchor != rhs.anchor { return lhs.anchor > rhs.anchor }
      // A conversation's own row must stay above the rows it produced even when a memory was
      // recorded at exactly the conversation's start time.
      return lhs.kind == .conversations && rhs.kind != .conversations
    }

    // Re-seat every attached row directly under its conversation. Sorting by anchor alone would
    // interleave them with anything that happened mid-conversation, which is the exact reading
    // failure the attachment exists to prevent.
    rows = reseatAttachments(rows)

    // The brain map is filed under memories at the foot of the day, never as a destination.
    let dayMemoryCount =
      rows.reduce(0) { total, row in
        if case .memories(let memories) = row.content { return total + memories.count }
        return total
      }
    if dayMemoryCount > 0 {
      let clusters = max(1, min(dayMemoryCount, Int((Double(dayMemoryCount) / 2.5).rounded(.up))))
      rows.append(
        SpineRow(
          id: "map:\(day.timeIntervalSince1970)",
          anchor: day,
          kind: .memories,
          isAttached: false,
          content: .brainMap(SpineBrainMap(memoryCount: dayMemoryCount, clusterCount: clusters)),
          searchText: "brain map how today's memories connect"
        ))
    }

    return SpineDay(
      id: day,
      title: SpineFormat.day(day, calendar: calendar),
      momentCount: screen.total,
      conversationCount: conversations.count,
      taskCount: rows.reduce(0) { total, row in
        if case .tasks(let tasks) = row.content { return total + tasks.count }
        return total
      },
      rows: rows
    )
  }

  /// First sighting of each id wins, in the order given. Order is what the spine sorts by, so a
  /// stable filter rather than a set round-trip.
  static func uniqued<Element, Key: Hashable>(
    _ elements: [Element], by key: KeyPath<Element, Key>
  ) -> [Element] {
    var seen = Set<Key>()
    seen.reserveCapacity(elements.count)
    return elements.filter { seen.insert($0[keyPath: key]).inserted }
  }

  /// Moves each attached row to sit immediately under its own conversation.
  private static func reseatAttachments(_ rows: [SpineRow]) -> [SpineRow] {
    var attachments: [String: [SpineRow]] = [:]
    var spine: [SpineRow] = []
    for row in rows {
      guard row.isAttached else {
        spine.append(row)
        continue
      }
      // "conv-mem:<id>" / "conv-task:<id>" / "conv-shot:<id>" — owner follows the colon.
      let owner = String(row.id.drop(while: { $0 != ":" }).dropFirst())
      attachments[owner, default: []].append(row)
    }
    return spine.flatMap { row -> [SpineRow] in
      guard case .conversation(let summary) = row.content else { return [row] }
      return [row] + (attachments[summary.id] ?? [])
    }
  }

  private static func memoryRow(_ memories: [SpineMemory], id: String, isAttached: Bool) -> SpineRow {
    SpineRow(
      id: id,
      anchor: memories.map(\.timestamp).max() ?? Date(),
      kind: .memories,
      isAttached: isAttached,
      content: .memories(memories),
      searchText: memories.map(\.text).joined(separator: " ").lowercased()
    )
  }

  private static func momentRow(
    _ moments: [SpineMoment], total: Int, id: String, isAttached: Bool
  ) -> SpineRow {
    let shown = Array(moments.prefix(momentsPerStrip))
    return SpineRow(
      id: id,
      anchor: moments.map(\.timestamp).max() ?? Date(),
      kind: .screen,
      isAttached: isAttached,
      content: .moments(shown: shown, total: total),
      searchText: moments.map { "\($0.appName) \($0.windowTitle ?? "")" }
        .joined(separator: " ")
        .lowercased()
    )
  }

  private static func taskRow(_ tasks: [SpineTask], id: String, isAttached: Bool) -> SpineRow {
    SpineRow(
      id: id,
      anchor: tasks.map(\.timestamp).max() ?? Date(),
      kind: .tasks,
      isAttached: isAttached,
      content: .tasks(tasks),
      searchText: tasks.map { "\($0.text) \($0.sourceLabel)" }.joined(separator: " ").lowercased()
    )
  }

  /// Splits a newest-first run of moments wherever the gap between two of them exceeds
  /// `momentClusterGap`.
  static func clusters(of moments: [SpineMoment]) -> [[SpineMoment]] {
    let ordered = moments.sorted { $0.timestamp > $1.timestamp }
    var result: [[SpineMoment]] = []
    var current: [SpineMoment] = []
    for moment in ordered {
      if let previous = current.last,
        previous.timestamp.timeIntervalSince(moment.timestamp) > momentClusterGap
      {
        result.append(current)
        current = []
      }
      current.append(moment)
    }
    if !current.isEmpty { result.append(current) }
    return result
  }
}

// MARK: - Formatting

/// Every string the spine shows, in one place, so the phrasing is a test rather than a screenshot.
enum SpineFormat {
  static func plural(_ count: Int, _ singular: String, _ plural: String) -> String {
    "\(number(count)) \(count == 1 ? singular : plural)"
  }

  static func number(_ value: Int) -> String {
    numberFormatter.string(from: NSNumber(value: value)) ?? String(value)
  }

  /// "8m 9s", "1h 04m", "42s".
  static func duration(_ seconds: TimeInterval) -> String {
    let total = Int(seconds.rounded())
    let hours = total / 3600
    let minutes = (total % 3600) / 60
    let secs = total % 60
    if hours > 0 { return String(format: "%dh %02dm", hours, minutes) }
    if minutes > 0 { return "\(minutes)m \(secs)s" }
    return "\(secs)s"
  }

  static func time(_ date: Date) -> String { timeFormatter.string(from: date) }

  /// The longest prefix that still reads as a category rather than as the first clause of a sentence.
  /// Past this, splitting stops being a label and becomes a fold through the middle of the copy.
  static let maximumMemoryLabelCharacters = 48

  /// Splits a memory into its repeated category and the sentence that is actually about this memory.
  ///
  /// Deliberately conservative — a memory that is merely *a sentence containing a colon* keeps its
  /// sentence. Three things have to be true before the split happens, and each of them is a real
  /// memory this would otherwise mangle:
  ///
  /// - **A space after the colon.** `12:56` and `https://omi.me` both carry one and neither is a
  ///   category; a separator between a label and a sentence is always followed by a space.
  /// - **No sentence punctuation in the prefix.** "He asked Dr. Kim: …" is a sentence with a quote in
  ///   it, not a labelled one.
  /// - **A prefix under `maximumMemoryLabelCharacters`, and a body left over.** A long prefix is a
  ///   clause, and a memory that is *only* a prefix has nothing to be a label for.
  static func memoryCopy(_ text: String) -> SpineMemoryCopy {
    let whole = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard let colon = whole.firstIndex(of: ":") else { return SpineMemoryCopy(label: nil, body: whole) }
    let label = whole[whole.startIndex..<colon].trimmingCharacters(in: .whitespacesAndNewlines)
    let rest = whole[whole.index(after: colon)...]
    let body = rest.trimmingCharacters(in: .whitespacesAndNewlines)
    guard rest.first?.isWhitespace == true,
      !label.isEmpty,
      !body.isEmpty,
      label.count <= maximumMemoryLabelCharacters,
      !label.contains(where: { ".?!".contains($0) })
    else {
      return SpineMemoryCopy(label: nil, body: whole)
    }
    return SpineMemoryCopy(label: label, body: body)
  }

  /// "Wednesday 6 August" — and "Today" / "Yesterday" for the two days a date is the wrong answer
  /// for, because nobody reads their own morning as a date.
  static func day(_ date: Date, calendar: Calendar = .current, now: Date = Date()) -> String {
    if calendar.isDate(date, inSameDayAs: now) { return "Today" }
    if let yesterday = calendar.date(byAdding: .day, value: -1, to: calendar.startOfDay(for: now)),
      calendar.isDate(date, inSameDayAs: yesterday)
    {
      return "Yesterday"
    }
    let formatter =
      calendar.isDate(date, equalTo: now, toGranularity: .year) ? dayFormatter : dayYearFormatter
    return formatter.string(from: date)
  }

  /// The hour a rail label states: "6 AM", "12 PM".
  static func hourLabel(_ hour: Int) -> String {
    switch hour {
    case 0: return "12 AM"
    case 12: return "12 PM"
    case ..<12: return "\(hour) AM"
    default: return "\(hour - 12) PM"
    }
  }

  private static let numberFormatter: NumberFormatter = {
    let formatter = NumberFormatter()
    formatter.numberStyle = .decimal
    return formatter
  }()

  private static let timeFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.dateFormat = "h:mm a"
    return formatter
  }()

  private static let dayFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.dateFormat = "EEEE d MMMM"
    return formatter
  }()

  private static let dayYearFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.dateFormat = "EEEE d MMMM yyyy"
    return formatter
  }()
}
