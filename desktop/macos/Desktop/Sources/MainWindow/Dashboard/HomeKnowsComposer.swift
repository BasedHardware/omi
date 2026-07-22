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

/// Builds the hub rows under the greeting as a deliberately DIVERSE set — one
/// pressing task, a tip (a real insight if there is one, otherwise a composed,
/// high-agency nudge you can hand Omi), a second task, and a prefilled ask.
/// Fixed typed slots keep it from collapsing into an all-tasks list when one
/// source (usually insights) is thin.
enum HomeKnowsListComposer {
  static let maxRows = 4

  /// How many candidates must exist beyond what's shown before the hub starts
  /// rotating — otherwise the same rows would "rotate" back onto themselves.
  static func canRotate(taskCount: Int, insightCount: Int, questionCount: Int) -> Bool {
    taskCount > 2 || insightCount > 1 || questionCount > 1
  }

  static func compose(
    tasks: [HomeKnowsTaskCandidate],
    insights: [HomeKnowsInsightCandidate],
    tip: String? = nil,
    questions: [String],
    dismissedTaskIDs: Set<String> = [],
    rotation: Int = 0
  ) -> [HomeKnowsRow] {
    let freshTasksRaw = tasks.filter { candidate in
      !dismissedTaskIDs.contains(candidate.id)
        && !candidate.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
    let cleanInsightsRaw = insights.filter {
      !$0.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
    let trimmedTip = tip?.trimmingCharacters(in: .whitespacesAndNewlines)
    let cleanTip = (trimmedTip?.isEmpty == false) ? trimmedTip : nil
    let cleanQuestionsRaw =
      questions
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty }

    // Rotate each source so the hub cycles through fresh candidates over time
    // while the diverse task · tip · task · ask structure below stays fixed.
    func rotated<T>(_ arr: [T]) -> [T] {
      guard arr.count > 1 else { return arr }
      let k = ((rotation % arr.count) + arr.count) % arr.count
      return Array(arr[k...] + arr[..<k])
    }
    let freshTasks = rotated(freshTasksRaw)
    let cleanInsights = rotated(cleanInsightsRaw)
    let cleanQuestions = rotated(cleanQuestionsRaw)
    // The ask never duplicates the composed tip.
    let ask = cleanQuestions.first { $0 != cleanTip }

    var rows: [HomeKnowsRow] = []

    // 1) The single most pressing task.
    if let task = freshTasks.first {
      rows.append(HomeKnowsRow(kind: .task(id: task.id), text: task.text))
    }

    // 2) A tip — a real server insight, else a composed nudge that prefills chat.
    if let insight = cleanInsights.first {
      rows.append(HomeKnowsRow(kind: .insight(id: insight.id), text: insight.text))
    } else if let cleanTip {
      rows.append(HomeKnowsRow(kind: .question, text: cleanTip))
    }

    // 3) A second concrete task — but only if the prefilled ask can still follow.
    if freshTasks.count > 1, ask == nil || rows.count < maxRows - 1 {
      let task = freshTasks[1]
      rows.append(HomeKnowsRow(kind: .task(id: task.id), text: task.text))
    }

    // 4) A prefilled ask, so there's always a distinct thing to hand Omi.
    if let ask, rows.count < maxRows {
      rows.append(HomeKnowsRow(kind: .question, text: ask))
    }

    return Array(rows.prefix(maxRows))
  }
}
