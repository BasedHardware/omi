import Foundation

// MARK: - "Here's what it already knows to do" rows

/// One row in the Home hub's knows-list: a concrete task, a proactive insight,
/// or a suggested question to ask.
enum HomeKnowsRowKind: Equatable {
  case task(id: String)
  case insight(id: String)
  case question

  /// Bounded analytics dimension — never carries the row's text.
  var analyticsKind: String {
    switch self {
    case .task: return "task"
    case .insight: return "insight"
    case .question: return "question"
    }
  }
}

struct HomeKnowsRow: Identifiable, Equatable {
  let kind: HomeKnowsRowKind
  let text: String
  /// Stable identity in the impression ledger. Question rows hash their text.
  var ledgerKey: String = ""
  /// Hash of the underlying object; a dismissed row returns only when it moves.
  var contentHash: String = ""
  /// How many times this row had already been shown before this composition.
  var showsBefore: Int = 0

  var id: String {
    switch kind {
    case .task(let id): return "task-\(id)"
    case .insight(let id): return "insight-\(id)"
    case .question: return "question-\(text)"
    }
  }
}

/// The four typed slots. Fixed so the list stays diverse instead of collapsing
/// into all-tasks when one source is thin.
enum HomeKnowsSlot: String, Equatable, Sendable, CaseIterable {
  case pressingTask = "pressing_task"
  case tip
  case secondTask = "second_task"
  case ask
}

/// A slot that stayed empty rather than repeating a row the reader has already
/// seen. The list is allowed to be shorter than four.
struct HomeKnowsEmptySlot: Equatable {
  let slot: HomeKnowsSlot
  let reason: HomeKnowsRotationReason
}

struct HomeKnowsComposition: Equatable {
  static let empty = HomeKnowsComposition(rows: [], emptySlots: [], canRotate: false)

  let rows: [HomeKnowsRow]
  let emptySlots: [HomeKnowsEmptySlot]
  /// True when more candidates qualify than the list shows, so the in-visit
  /// rotation cycles to genuinely different rows instead of the same set.
  let canRotate: Bool
}

struct HomeKnowsTaskCandidate: Equatable {
  let id: String
  let text: String
  var dueAt: Date?
  var updatedAt: Date?
  /// False once the task is completed, retired, or deleted.
  var isActive: Bool

  init(id: String, text: String, dueAt: Date? = nil, updatedAt: Date? = nil, isActive: Bool = true) {
    self.id = id
    self.text = text
    self.dueAt = dueAt
    self.updatedAt = updatedAt
    self.isActive = isActive
  }
}

struct HomeKnowsInsightCandidate: Equatable {
  let id: String
  let text: String
  var updatedAt: Date?

  init(id: String, text: String, updatedAt: Date? = nil) {
    self.id = id
    self.text = text
    self.updatedAt = updatedAt
  }
}

/// Builds the hub rows under the greeting as a deliberately DIVERSE set — one
/// pressing task, a tip (a real insight if there is one, otherwise a composed,
/// high-agency nudge you can hand Omi), a second task, and a prefilled ask.
/// Fixed typed slots keep it from collapsing into an all-tasks list when one
/// source (usually insights) is thin.
///
/// Every slot is gated by `HomeKnowsRotationPolicy` against the impression
/// ledger, so a thin source produces a *shorter* list rather than the same four
/// rows on every visit. An empty slot is the intended outcome, not a bug.
enum HomeKnowsListComposer {
  static let maxRows = 4

  /// Open tasks the reader has not dismissed — the count the greeting's daily
  /// brief and composed tip are phrased around.
  ///
  /// Counted through the same eligibility predicate the rows are, so the
  /// greeting cannot disagree with the list beneath it: the same duplicate ids
  /// collapse, a long-dead past-due task is out of both, and a dismissal the
  /// reader's own edit has since invalidated is back in both. Rotation state
  /// (show cap, same-day) deliberately does not count — a task you have already
  /// seen three times today still needs you.
  static func openTaskCount(
    _ tasks: [HomeKnowsTaskCandidate],
    ledger: HomeKnowsImpressionLedger = .empty,
    now: Date = Date()
  ) -> Int {
    distinctTasks(tasks).filter { candidate in
      let facts = taskFacts(candidate)
      return HomeKnowsRotationPolicy.availability(
        facts: facts, entry: ledger.entry(facts.key), now: now) == nil
    }.count
  }

  /// The task candidates a row could be built from, in the caller's own
  /// priority order. Task ids repeat across the overdue/today/no-due-date
  /// buckets the hub concatenates; a duplicate would collide as a ForEach ID
  /// and be counted twice by the greeting.
  private static func distinctTasks(_ tasks: [HomeKnowsTaskCandidate]) -> [HomeKnowsTaskCandidate] {
    var seenTaskIDs = Set<String>()
    return tasks.filter { candidate in
      !candidate.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        && seenTaskIDs.insert(candidate.id).inserted
    }
  }

  private static func taskFacts(_ candidate: HomeKnowsTaskCandidate) -> HomeKnowsCandidateFacts {
    HomeKnowsCandidateFacts(
      key: HomeKnowsRotationPolicy.taskKey(candidate.id),
      contentHash: HomeKnowsRotationPolicy.contentHash(
        text: candidate.text, updatedAt: candidate.updatedAt),
      updatedAt: candidate.updatedAt,
      dueAt: candidate.dueAt,
      isActive: candidate.isActive)
  }

  static func compose(
    tasks: [HomeKnowsTaskCandidate],
    insights: [HomeKnowsInsightCandidate],
    tip: String? = nil,
    questions: [String],
    ledger: HomeKnowsImpressionLedger = .empty,
    now: Date = Date(),
    calendar: Calendar = .current,
    rotation: Int = 0
  ) -> HomeKnowsComposition {
    // Unavailable tasks stay in the pool rather than being filtered out here:
    // `pool` is what reports *why* a slot came up empty, and a pre-filtered
    // dismissal would be indistinguishable from having no task at all.
    let taskCandidates =
      distinctTasks(tasks)
      .enumerated()
      .map { index, candidate in
        Scored(element: candidate, facts: taskFacts(candidate), order: index)
      }

    let insightCandidates =
      insights
      .filter { !$0.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
      .enumerated()
      .map { index, candidate in
        Scored(
          element: candidate,
          facts: HomeKnowsCandidateFacts(
            key: HomeKnowsRotationPolicy.insightKey(candidate.id),
            contentHash: HomeKnowsRotationPolicy.contentHash(
              text: candidate.text, updatedAt: candidate.updatedAt),
            updatedAt: candidate.updatedAt),
          order: index)
      }

    let trimmedTip = tip?.trimmingCharacters(in: .whitespacesAndNewlines)
    let cleanTip = (trimmedTip?.isEmpty == false) ? trimmedTip : nil

    // Question rows are identified by their text, so a repeated suggestion
    // would collide as a ForEach ID — keep only the first occurrence.
    var seenQuestions = Set<String>()
    let questionCandidates =
      questions
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty && seenQuestions.insert($0).inserted }
      .enumerated()
      .map { index, text in Scored(element: text, facts: questionFacts(text), order: index) }

    let taskPool = pool(taskCandidates, ledger: ledger, now: now, calendar: calendar)
    let insightPool = pool(insightCandidates, ledger: ledger, now: now, calendar: calendar)
    let questionPool = pool(questionCandidates, ledger: ledger, now: now, calendar: calendar)
    let tipPool = cleanTip.map { text in
      pool(
        [Scored(element: text, facts: questionFacts(text), order: 0)],
        ledger: ledger, now: now, calendar: calendar)
    }

    // Rotate each pool so the hub cycles through the qualifying candidates while
    // the diverse task · tip · task · ask structure below stays fixed.
    let freshTasks = rotated(taskPool.eligible, by: rotation)
    let freshInsights = rotated(insightPool.eligible, by: rotation)
    let freshQuestions = rotated(questionPool.eligible, by: rotation)
    // The ask never duplicates the composed tip.
    let ask = freshQuestions.first { $0.element != cleanTip }

    var rows: [HomeKnowsRow] = []
    var emptySlots: [HomeKnowsEmptySlot] = []

    func fill(
      _ slot: HomeKnowsSlot, with row: HomeKnowsRow?, otherwise reason: @autoclosure () -> HomeKnowsRotationReason
    ) {
      if let row {
        rows.append(row)
      } else {
        emptySlots.append(HomeKnowsEmptySlot(slot: slot, reason: reason()))
      }
    }

    // 1) The single most pressing task.
    fill(
      .pressingTask,
      with: freshTasks.first.map {
        row(kind: .task(id: $0.element.id), text: $0.element.text, facts: $0.facts, ledger: ledger)
      },
      otherwise: taskPool.emptyReason)

    // 2) A tip — a real server insight, else a composed nudge that prefills chat.
    if let insight = freshInsights.first {
      rows.append(
        row(kind: .insight(id: insight.element.id), text: insight.element.text, facts: insight.facts, ledger: ledger))
    } else if let tipPool, let tipRow = tipPool.eligible.first {
      rows.append(row(kind: .question, text: tipRow.element, facts: tipRow.facts, ledger: ledger))
    } else {
      // Report the insight source's reason when there was one; a suppressed
      // composed tip is why the slot is empty only when insights never existed.
      let reason = insightCandidates.isEmpty ? (tipPool?.emptyReason ?? .noCandidate) : insightPool.emptyReason
      emptySlots.append(HomeKnowsEmptySlot(slot: .tip, reason: reason))
    }

    // 3) A second concrete task — but only if the prefilled ask can still follow.
    // Yielding the slot to the ask is a layout choice, not a rotation outcome,
    // so it is not reported as an empty slot.
    if freshTasks.count > 1 {
      if ask == nil || rows.count < maxRows - 1 {
        let task = freshTasks[1]
        rows.append(
          row(kind: .task(id: task.element.id), text: task.element.text, facts: task.facts, ledger: ledger))
      }
    } else {
      emptySlots.append(HomeKnowsEmptySlot(slot: .secondTask, reason: taskPool.emptyReason))
    }

    // 4) A prefilled ask, so there's always a distinct thing to hand Omi.
    if let ask {
      if rows.count < maxRows {
        rows.append(row(kind: .question, text: ask.element, facts: ask.facts, ledger: ledger))
      }
    } else {
      emptySlots.append(HomeKnowsEmptySlot(slot: .ask, reason: questionPool.emptyReason))
    }

    return HomeKnowsComposition(
      rows: Array(rows.prefix(maxRows)),
      emptySlots: emptySlots,
      canRotate: canRotate(
        taskCount: taskPool.eligible.count,
        insightCount: insightPool.eligible.count,
        questionCount: questionPool.eligible.count))
  }

  /// How many candidates must qualify beyond what's shown before the hub starts
  /// rotating — otherwise the same rows would "rotate" back onto themselves.
  static func canRotate(taskCount: Int, insightCount: Int, questionCount: Int) -> Bool {
    taskCount > 2 || insightCount > 1 || questionCount > 1
  }

  // MARK: Internals

  /// A candidate paired with the facts the rotation rules read, and its
  /// position in the caller's own priority order.
  private struct Scored<Element> {
    let element: Element
    let facts: HomeKnowsCandidateFacts
    let order: Int
  }

  /// The qualifying candidates for one slot, plus why the rest were held back.
  private struct Pool<Element> {
    let eligible: [Scored<Element>]
    let emptyReason: HomeKnowsRotationReason
  }

  private static func questionFacts(_ text: String) -> HomeKnowsCandidateFacts {
    HomeKnowsCandidateFacts(
      key: HomeKnowsRotationPolicy.questionKey(text),
      contentHash: HomeKnowsRotationPolicy.contentHash(text: text))
  }

  private static func row(
    kind: HomeKnowsRowKind,
    text: String,
    facts: HomeKnowsCandidateFacts,
    ledger: HomeKnowsImpressionLedger
  ) -> HomeKnowsRow {
    HomeKnowsRow(
      kind: kind,
      text: text,
      ledgerKey: facts.key,
      contentHash: facts.contentHash,
      showsBefore: ledger.entry(facts.key)?.shows ?? 0)
  }

  /// Applies the rotation rules, then orders what survives by freshness:
  /// never-shown first, then fewest shows, then most recent underlying update.
  ///
  /// Same-day repeats are relaxed only when the strict pass leaves the slot with
  /// nothing at all — and even then the policy still requires a prior open.
  private static func pool<Element>(
    _ candidates: [Scored<Element>],
    ledger: HomeKnowsImpressionLedger,
    now: Date,
    calendar: Calendar
  ) -> Pool<Element> {
    guard !candidates.isEmpty else { return Pool(eligible: [], emptyReason: .noCandidate) }

    func pass(allowSameDayRepeat: Bool) -> ([Scored<Element>], [HomeKnowsRotationReason]) {
      var eligible: [Scored<Element>] = []
      var reasons: [HomeKnowsRotationReason] = []
      for candidate in candidates {
        if let reason = HomeKnowsRotationPolicy.suppression(
          facts: candidate.facts,
          entry: ledger.entry(candidate.facts.key),
          now: now,
          calendar: calendar,
          allowSameDayRepeat: allowSameDayRepeat)
        {
          reasons.append(reason)
        } else {
          eligible.append(candidate)
        }
      }
      return (eligible, reasons)
    }

    var (eligible, reasons) = pass(allowSameDayRepeat: false)
    if eligible.isEmpty {
      (eligible, reasons) = pass(allowSameDayRepeat: true)
    }
    // `sorted(by:)` is not stable, so the caller's order is the explicit final
    // tie-break rather than something the sort happens to preserve.
    let ordered = eligible.sorted { lhs, rhs in
      let lhsRank = HomeKnowsRotationPolicy.freshnessRank(lhs.facts, ledger: ledger)
      let rhsRank = HomeKnowsRotationPolicy.freshnessRank(rhs.facts, ledger: ledger)
      if lhsRank != rhsRank { return lhsRank < rhsRank }
      return lhs.order < rhs.order
    }
    return Pool(eligible: ordered, emptyReason: HomeKnowsRotationPolicy.dominantReason(reasons))
  }

  private static func rotated<T>(_ arr: [T], by rotation: Int) -> [T] {
    guard arr.count > 1 else { return arr }
    let k = ((rotation % arr.count) + arr.count) % arr.count
    return Array(arr[k...] + arr[..<k])
  }
}
