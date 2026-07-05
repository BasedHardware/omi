import Foundation

enum DelegationBriefValidator {
    nonisolated static func isStructurallyAcceptable(brief: String, rawIntent: String?) -> Bool {
        let normalized = brief.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !normalized.isEmpty else { return false }

        let words = normalized
            .lowercased()
            .split { !$0.isLetter && !$0.isNumber }
            .map(String.init)
        let contentWords = words.filter { !Self.stopwords.contains($0) }
        guard contentWords.count >= 3 else { return false }

        let lower = normalized.lowercased()
        if Self.unresolvedBriefPatterns.contains(where: { lower.range(of: $0, options: .regularExpression) != nil }) {
            return false
        }

        if let rawIntent {
            let raw = rawIntent.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            if raw == lower, raw.split(whereSeparator: \.isWhitespace).count <= 4 {
                return false
            }
        }
        return true
    }

    private nonisolated static let stopwords: Set<String> = [
        "a", "an", "and", "for", "in", "it", "me", "my", "of", "on", "or", "that", "the", "to", "with",
    ]

    private nonisolated static let unresolvedBriefPatterns: [String] = [
        #"^(?:do|perform|run|start|create)\s+(?:that|it|this|same thing|another one)\.?$"#,
        #"^(?:another|new|same)\s+(?:search|task|agent|one)\.?$"#,
        #"^(?:perform|run|do)\s+(?:a\s+)?(?:new\s+|another\s+)?search\s+for\s+(?:the\s+)?user\.?$"#,
        #"\b(?:that|it|same thing|previous task|last task|last one)\b$"#,
    ]
}
