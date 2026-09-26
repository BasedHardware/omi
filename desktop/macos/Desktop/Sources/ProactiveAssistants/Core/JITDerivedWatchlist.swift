import Foundation

/// Derived, expiring standing intent compiled from knowledge the user already
/// gave Omi: open tasks, active goals, and calendar events around the observation.
///
/// Derived entries are deliberately not ledger triggers. They carry no action,
/// purchase no planned wakeup, never reach the server, and expire with their
/// source row. Their only job is to tell the ambient lane which context changes
/// carry demonstrated intent, so the bounded nano budget is spent on those
/// first instead of on the first novel contexts of the local day.
struct JITDerivedIntentEntry: Equatable, Sendable {
  enum Source: String, Equatable, Sendable {
    case task
    case goal
    case calendar
  }

  let id: String
  let source: Source
  /// Bounded, prompt-safe description of the intent. Calendar entries carry a
  /// fixed label rather than event titles so event content stays local
  /// (JIT decision 25).
  let label: String
  let keywords: [String]
}

struct JITDerivedIntentMatch: Equatable, Sendable {
  static let none = JITDerivedIntentMatch(entries: [])
  static let maxPromptEntries = 6

  let entries: [JITDerivedIntentEntry]

  var isEmpty: Bool { entries.isEmpty }
  var ids: [String] { entries.map(\.id) }

  /// Grounding section for the ambient full turn. Ordered by source so the
  /// rendered prompt is stable for identical matches.
  func promptSection() -> String? {
    guard !entries.isEmpty else { return nil }
    let lines = entries.prefix(Self.maxPromptEntries).map { entry in
      "- \(entry.source.rawValue): \(entry.label)"
    }
    return """
      == STANDING INTENT THE USER ALREADY EXPRESSED (matches this context) ==
      \(lines.joined(separator: "\n"))
      """
  }
}

enum JITDerivedWatchlistCompiler {
  static let maxEntries = 64
  static let maxKeywordsPerEntry = 6
  static let minKeywordCharacters = 4
  static let maxLabelCharacters = 160
  /// A derived entry matches only when at least this many of its keywords
  /// appear in the observation. Entries with fewer discriminating keywords are
  /// not compiled at all, so one shared token can never buy a nano call.
  static let minimumKeywordHits = 2

  static let stopwords: Set<String> = [
    "about", "after", "again", "against", "before", "being", "below", "between", "could",
    "does", "doing", "down", "during", "each", "from", "further", "have", "having", "here",
    "into", "just", "more", "most", "need", "needs", "once", "only", "other", "over", "same",
    "should", "some", "such", "than", "that", "their", "them", "then", "there", "these",
    "they", "this", "those", "through", "under", "until", "very", "were", "what", "when",
    "where", "which", "while", "will", "with", "would", "your", "make", "sure", "check",
    "follow", "send", "email", "update", "call", "task", "todo", "goal", "reminder", "remind",
    "today", "tomorrow", "week", "next", "last", "also", "like", "look", "into", "back",
    "done", "work", "working", "things", "thing", "still", "maybe", "want", "please",
    // Generic workflow verbs and nouns: they name what every task is, not which.
    "review", "pull", "request", "merge", "issue", "ticket", "meeting", "discuss", "write",
    "read", "open", "close", "create", "remove", "delete", "test", "plan", "project",
    "document", "file", "page", "link", "message", "reply", "respond", "schedule", "book",
    "order", "finish", "start", "continue", "prepare", "draft", "share", "ask", "confirm",
  ]

  /// Deterministic keyword extraction: lowercase alphanumeric tokens, at least
  /// `minKeywordCharacters` long, not a stopword, not purely numeric, first
  /// occurrence order, capped at `maxKeywordsPerEntry`.
  static func keywords(from text: String) -> [String] {
    var seen = Set<String>()
    var result: [String] = []
    for token in tokens(in: text) {
      guard token.count >= minKeywordCharacters,
        !stopwords.contains(token),
        !token.allSatisfy(\.isNumber),
        seen.insert(token).inserted
      else { continue }
      result.append(token)
      if result.count == maxKeywordsPerEntry { break }
    }
    return result
  }

  static func tokens(in text: String) -> [String] {
    text.lowercased()
      .split(whereSeparator: { !($0.isLetter || $0.isNumber) })
      .map(String.init)
  }

  static func entry(source: JITDerivedIntentEntry.Source, identity: String, text: String) -> JITDerivedIntentEntry? {
    let label = boundedLabel(text)
    guard !label.isEmpty else { return nil }
    let keywords = keywords(from: text)
    guard keywords.count >= minimumKeywordHits else { return nil }
    let normalizedIdentity = identity.trimmingCharacters(in: .whitespacesAndNewlines)
    // Identity is opaque on purpose: a task without a backend id is keyed by
    // its content through the same one-way identifier used for reservations.
    let id = JITProactivityReservation.identifier(
      "derived", source.rawValue, normalizedIdentity.isEmpty ? label : normalizedIdentity)
    return JITDerivedIntentEntry(id: id, source: source, label: label, keywords: keywords)
  }

  static func compile(
    tasks: [(identity: String, description: String)],
    goals: [(identity: String, title: String)]
  ) -> [JITDerivedIntentEntry] {
    var entries: [JITDerivedIntentEntry] = []
    var seen = Set<String>()
    for task in tasks {
      guard entries.count < maxEntries,
        let entry = entry(source: .task, identity: task.identity, text: task.description),
        seen.insert(entry.id).inserted
      else { continue }
      entries.append(entry)
    }
    for goal in goals {
      guard entries.count < maxEntries,
        let entry = entry(source: .goal, identity: goal.identity, text: goal.title),
        seen.insert(entry.id).inserted
      else { continue }
      entries.append(entry)
    }
    return entries
  }

  static func boundedLabel(_ text: String) -> String {
    let normalized = text.split(whereSeparator: \.isWhitespace).joined(separator: " ")
    return String(normalized.prefix(maxLabelCharacters))
  }
}

enum JITDerivedWatchlistMatcher {
  static let calendarLabel = "a calendar event is in progress or starting soon"

  /// Pure keyword and calendar matching over one observation. No I/O and no
  /// model; the result only influences ambient priority and prompt grounding.
  static func match(
    entries: [JITDerivedIntentEntry],
    observation: KnowledgeLedgerTriggerObservation
  ) -> JITDerivedIntentMatch {
    let corpus = [observation.text, observation.windowTitle ?? ""].joined(separator: "\n")
    let observed = Set(JITDerivedWatchlistCompiler.tokens(in: corpus))
    var matched: [JITDerivedIntentEntry] = []
    for entry in entries where entry.keywords.count >= JITDerivedWatchlistCompiler.minimumKeywordHits {
      let hits = entry.keywords.filter { observed.contains($0) }.count
      if hits >= JITDerivedWatchlistCompiler.minimumKeywordHits { matched.append(entry) }
    }
    if !observation.calendarEvents.isEmpty {
      matched.append(
        JITDerivedIntentEntry(
          id: JITProactivityReservation.identifier("derived", "calendar", "present"),
          source: .calendar,
          label: calendarLabel,
          keywords: []))
    }
    matched.sort { lhs, rhs in
      if lhs.source.rawValue != rhs.source.rawValue { return lhs.source.rawValue < rhs.source.rawValue }
      return lhs.id < rhs.id
    }
    return JITDerivedIntentMatch(entries: matched)
  }
}

/// Owner-scoped loader for derived intent with a bounded refresh interval so
/// every context visit does not re-read the task and goal tables.
actor JITDerivedWatchlistSource {
  static let shared = JITDerivedWatchlistSource()
  static let refreshInterval: TimeInterval = 600
  static let maxTasks = 40

  typealias Loader = @Sendable () async -> [JITDerivedIntentEntry]

  private let loader: Loader
  private var cache: (ownerID: String, entries: [JITDerivedIntentEntry], loadedAt: Date)?

  init(loader: @escaping Loader = JITDerivedWatchlistSource.loadLocalIntent) {
    self.loader = loader
  }

  func match(
    observation: KnowledgeLedgerTriggerObservation,
    ownerID: String,
    now: Date = Date()
  ) async -> JITDerivedIntentMatch {
    let entries = await entries(ownerID: ownerID, now: now)
    return JITDerivedWatchlistMatcher.match(entries: entries, observation: observation)
  }

  func entries(ownerID: String, now: Date = Date()) async -> [JITDerivedIntentEntry] {
    if let cache, cache.ownerID == ownerID, now.timeIntervalSince(cache.loadedAt) < Self.refreshInterval {
      return cache.entries
    }
    let loaded = await loader()
    cache = (ownerID, loaded, now)
    return loaded
  }

  func invalidate() {
    cache = nil
  }

  /// Best-effort local reads. A failing source contributes nothing rather than
  /// blocking admission; the ambient lane then paces as if no intent matched.
  static func loadLocalIntent() async -> [JITDerivedIntentEntry] {
    let tasks = (try? await ActionItemStorage.shared.getRecentActiveTasks(limit: maxTasks)) ?? []
    let goals = (try? await GoalStorage.shared.getLocalGoals(activeOnly: true)) ?? []
    return JITDerivedWatchlistCompiler.compile(
      tasks: tasks.map { (identity: $0.backendId ?? "", description: $0.description) },
      goals: goals.map { (identity: $0.id, title: $0.title) })
  }
}
