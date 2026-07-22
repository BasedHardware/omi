import Foundation

// MARK: - "Here's what it already knows to do" rows

/// One row in the Home hub's knows-list: a concrete task, a proactive
/// insight, or a suggested question to ask.
enum HomeKnowsRowKind: Equatable {
  case task(id: String)
  case insight(id: String)
  case question
}

struct HomeKnowsRow: Identifiable, Equatable {
  let kind: HomeKnowsRowKind
  let text: String

  var id: String {
    switch kind {
    case .task(let id): return "task-\(id)"
    case .insight(let id): return "insight-\(id)"
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

/// Builds the three hub rows shown under "Here's what it already knows to
/// do:" — at most one task, then insights, with the last slot reserved for a
/// suggested question whenever one is available.
enum HomeKnowsListComposer {
  static let maxRows = 3

  static func compose(
    tasks: [HomeKnowsTaskCandidate],
    insights: [HomeKnowsInsightCandidate],
    questions: [String],
    dismissedTaskIDs: Set<String> = []
  ) -> [HomeKnowsRow] {
    var rows: [HomeKnowsRow] = []

    if let task = tasks.first(where: { candidate in
      !dismissedTaskIDs.contains(candidate.id)
        && !candidate.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }) {
      rows.append(HomeKnowsRow(kind: .task(id: task.id), text: task.text))
    }

    // Question rows are identified by their text, so a repeated suggestion
    // would collide as a ForEach ID — keep only the first occurrence.
    var seenQuestions = Set<String>()
    let cleanQuestions =
      questions
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty && seenQuestions.insert($0).inserted }

    // Insights fill the middle; one slot stays reserved for a question so the
    // list always ends with something the user can ask.
    let insightBudget = cleanQuestions.isEmpty ? maxRows - rows.count : maxRows - rows.count - 1
    for insight in insights.prefix(max(0, insightBudget)) {
      let text = insight.text.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !text.isEmpty else { continue }
      rows.append(HomeKnowsRow(kind: .insight(id: insight.id), text: text))
    }

    for question in cleanQuestions {
      guard rows.count < maxRows else { break }
      rows.append(HomeKnowsRow(kind: .question, text: question))
    }

    return rows
  }
}
