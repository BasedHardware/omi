import Foundation

struct FirstRunScenarioJournalEntry: Codable, Equatable, Sendable {
  enum Speaker: String, Codable, Sendable {
    case omi
    case user
    case system
  }

  let t: Date
  let who: Speaker
  let text: String
}

struct FirstRunLogEntry: Codable, Equatable, Sendable {
  let t: Date
  let text: String
  let isUser: Bool
}

struct FirstRunTranscriptSegment: Equatable, Sendable {
  let text: String
  let speaker: String
  let speakerID: Int
  let isUser: Bool
  let start: TimeInterval
  let end: TimeInterval
}

enum FirstRunSummaryComposer {
  static func decodeJournal(_ data: Data?) -> [FirstRunScenarioJournalEntry] {
    guard let data else { return [] }
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .custom { decoder in
      let value = try decoder.singleValueContainer().decode(String.self)
      let fractional = ISO8601DateFormatter()
      fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
      if let date = fractional.date(from: value) { return date }
      let standard = ISO8601DateFormatter()
      if let date = standard.date(from: value) { return date }
      throw DecodingError.dataCorruptedError(
        in: try decoder.singleValueContainer(),
        debugDescription: "Invalid first-run journal timestamp")
    }
    return (try? decoder.decode([FirstRunScenarioJournalEntry].self, from: data)) ?? []
  }

  static func compose(
    journal: [FirstRunScenarioJournalEntry],
    firstRunLog: [FirstRunLogEntry],
    sessionStart: Date,
    sessionEnd: Date
  ) -> [FirstRunTranscriptSegment] {
    struct Line {
      let date: Date
      let text: String
      let speaker: String
      let speakerID: Int
      let isUser: Bool
    }

    let journalLines = journal.compactMap { entry -> Line? in
      let text = entry.text.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !text.isEmpty else { return nil }
      switch entry.who {
      case .user:
        return Line(date: entry.t, text: text, speaker: "You", speakerID: 0, isUser: true)
      case .omi:
        return Line(date: entry.t, text: text, speaker: "Omi", speakerID: 1, isUser: false)
      case .system:
        return Line(date: entry.t, text: text, speaker: "Omi", speakerID: 1, isUser: false)
      }
    }
    let logLines = firstRunLog.compactMap { entry -> Line? in
      let text = entry.text.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !text.isEmpty else { return nil }
      return Line(
        date: entry.t,
        text: text,
        speaker: entry.isUser ? "You" : "Omi",
        speakerID: entry.isUser ? 0 : 1,
        isUser: entry.isUser)
    }
    let ordered = (journalLines + logLines).sorted {
      if $0.date == $1.date { return $0.speakerID < $1.speakerID }
      return $0.date < $1.date
    }
    guard !ordered.isEmpty else { return [] }

    var cursor: TimeInterval = 0
    return ordered.map { line in
      let measuredStart = max(0, line.date.timeIntervalSince(sessionStart))
      let start = max(cursor, measuredStart)
      let duration = max(1, min(12, Double(line.text.count) / 18))
      let end = min(max(start + duration, start + 0.1), max(sessionEnd.timeIntervalSince(sessionStart), start + 0.1))
      cursor = end
      return FirstRunTranscriptSegment(
        text: line.text,
        speaker: line.speaker,
        speakerID: line.speakerID,
        isUser: line.isUser,
        start: start,
        end: end)
    }
  }
}
