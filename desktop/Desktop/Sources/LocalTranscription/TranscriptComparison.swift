import Foundation

struct TranscriptComparison {
  static func normalizedWords(_ value: String) -> [String] {
    normalizedText(value).split(separator: " ").map(String.init)
  }

  static func normalizedCharacters(_ value: String) -> [Character] {
    Array(normalizedText(value).replacingOccurrences(of: " ", with: ""))
  }

  static func normalizedText(_ value: String) -> String {
    value.lowercased()
      .replacingOccurrences(
        of: #"[^a-z0-9\s]"#,
        with: " ",
        options: .regularExpression
      )
      .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
      .trimmingCharacters(in: .whitespacesAndNewlines)
  }

  static func wordErrorRate(reference: String, hypothesis: String) -> Double {
    errorRate(reference: normalizedWords(reference), hypothesis: normalizedWords(hypothesis))
  }

  static func characterErrorRate(reference: String, hypothesis: String) -> Double {
    errorRate(
      reference: normalizedCharacters(reference),
      hypothesis: normalizedCharacters(hypothesis)
    )
  }

  private static func errorRate<T: Equatable>(reference: [T], hypothesis: [T]) -> Double {
    guard !reference.isEmpty else {
      return hypothesis.isEmpty ? 0 : 1
    }
    return Double(editDistance(reference, hypothesis)) / Double(reference.count)
  }

  private static func editDistance<T: Equatable>(_ reference: [T], _ hypothesis: [T]) -> Int {
    var previous = Array(0...hypothesis.count)
    var current = Array(repeating: 0, count: hypothesis.count + 1)

    for referenceIndex in 1...reference.count {
      current[0] = referenceIndex
      for hypothesisIndex in 1...hypothesis.count {
        if reference[referenceIndex - 1] == hypothesis[hypothesisIndex - 1] {
          current[hypothesisIndex] = previous[hypothesisIndex - 1]
        } else {
          current[hypothesisIndex] =
            min(
              previous[hypothesisIndex],
              current[hypothesisIndex - 1],
              previous[hypothesisIndex - 1]
            ) + 1
        }
      }
      swap(&previous, &current)
    }

    return previous[hypothesis.count]
  }
}
