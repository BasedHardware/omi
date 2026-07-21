import Foundation

// MARK: - "Here's what it already knows to do" rows

/// One row in the Home hub's knows-list: the live focus signal, a concrete
/// task, a proactive insight, or a suggested question to ask.
enum HomeKnowsRowKind: Equatable {
  case task(id: String)
  case insight(id: String)
  case focus
  case question
}

struct HomeKnowsRow: Identifiable, Equatable {
  let kind: HomeKnowsRowKind
  let text: String

  var id: String {
    switch kind {
    case .task(let id): return "task-\(id)"
    case .insight(let id): return "insight-\(id)"
    case .focus: return "focus"
    case .question: return "question-\(text)"
    }
  }
}

struct HomeKnowsTaskCandidate: Equatable {
  let id: String
  let text: String
}

struct HomeKnowsInsightCandidate: Equatable {
  let id: String
  let text: String
}

/// Builds the hub rows shown under the greeting — a relevant mix Omi predicts
/// from recent context: the live focus signal first, then an interleaved run of
/// tasks and insights (varied, actionable), with a suggested question reserved
/// for the last slot so the list always ends with something to ask.
enum HomeKnowsListComposer {
  static let maxRows = 5

  static func compose(
    tasks: [HomeKnowsTaskCandidate],
    insights: [HomeKnowsInsightCandidate],
    focus: String? = nil,
    questions: [String],
    dismissedTaskIDs: Set<String> = []
  ) -> [HomeKnowsRow] {
    var rows: [HomeKnowsRow] = []

    // The live focus signal leads — it's the "right now" context.
    if let focus = focus?.trimmingCharacters(in: .whitespacesAndNewlines), !focus.isEmpty {
      rows.append(HomeKnowsRow(kind: .focus, text: focus))
    }

    let freshTasks = tasks.filter { candidate in
      !dismissedTaskIDs.contains(candidate.id)
        && !candidate.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
    let cleanInsights = insights.filter {
      !$0.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
    let cleanQuestions =
      questions
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty }

    // Keep the last slot for a question whenever one exists.
    let reserve = cleanQuestions.isEmpty ? 0 : 1

    // Interleave tasks and insights so the middle reads as a varied mix rather
    // than a block of one kind.
    var taskIndex = 0
    var insightIndex = 0
    while rows.count < maxRows - reserve
      && (taskIndex < freshTasks.count || insightIndex < cleanInsights.count)
    {
      if taskIndex < freshTasks.count {
        let task = freshTasks[taskIndex]
        rows.append(HomeKnowsRow(kind: .task(id: task.id), text: task.text))
        taskIndex += 1
      }
      if rows.count >= maxRows - reserve { break }
      if insightIndex < cleanInsights.count {
        let insight = cleanInsights[insightIndex]
        rows.append(HomeKnowsRow(kind: .insight(id: insight.id), text: insight.text))
        insightIndex += 1
      }
    }

    // Questions fill the remaining slots (including the reserved one).
    for question in cleanQuestions {
      guard rows.count < maxRows else { break }
      rows.append(HomeKnowsRow(kind: .question, text: question))
    }

    return rows
  }
}
