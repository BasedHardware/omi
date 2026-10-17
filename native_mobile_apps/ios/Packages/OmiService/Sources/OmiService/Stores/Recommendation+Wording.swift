import Foundation
import OmiCore

/// How a "What matters now" recommendation reads on Home: the backend's next action as a
/// question, and where it comes from. Pure (no model call), so the wording is testable.
public extension Recommendation {
    /// Where the recommendation comes from, beyond a conversation the app can name itself.
    enum Origin: Equatable, Sendable {
        /// The user wrote the task themselves.
        case addedByYou
        /// Someone or something is waiting on the user.
        case waitingOnYou
        /// The backend's own words (an LLM preview), shown as they are.
        case text(String)
    }

    /// "Send Anna the Thursday follow-up?": the next action (or the headline when the action is
    /// missing or a long sentence) without its closing period, asked.
    var question: String {
        var text = Self.plain(action)
        if text.isEmpty || text.count > 90 { text = Self.plain(headline) }
        while let last = text.last, ".!:;".contains(last) {
            text.removeLast()
        }
        text = text.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return headline }
        return text.hasSuffix("?") ? text : text + "?"
    }

    /// `whyNow` when it says something specific (a person, a place, a reason); nil for the
    /// backend's template eligibility lines ("This task is due today and has a concrete next
    /// action.", "This task is overdue by 2 days."), which only restate the due date.
    var specificWhyNow: String? {
        let text = whyNow.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return nil }
        let lowered = text.lowercased()
        let templates = [
            #"^this (task|item|commitment) (is|was) (due|overdue)\b"#,
            #"^(it is|it's|this is) (due|overdue)\b"#,
            #"^(due|overdue) (today|tomorrow|in \d+ days?|by \d+ days?)\.?$"#,
            #"concrete next action"#,
            #"^(this|the) (task|item) (was )?(recently|explicitly) created"#,
            #"^created (directly )?by you"#,
            #"^the due date (has passed|is (today|soon|near))"#,
            #"^(it|this) has a (due date|deadline)( (today|soon|coming up))?\.?$"#,
        ]
        if templates.contains(where: { lowered.range(of: $0, options: .regularExpression) != nil }) { return nil }
        return text
    }

    /// The goal or workstream, when it says more than the title (the backend often repeats it).
    var distinctGoalLabel: String? {
        guard let goalLabel = goalLabel?.trimmingCharacters(in: .whitespacesAndNewlines), !goalLabel.isEmpty else { return nil }
        let normalized = Self.normalized(goalLabel)
        return [headline, action, question].contains { Self.normalized($0) == normalized } ? nil : goalLabel
    }

    /// The evidence preview in words worth showing. The backend's canonical previews about due
    /// dates repeat `whyNow` and "Linked to 2 evidence sources" says nothing, so those are nil.
    var origin: Origin? {
        let preview = evidencePreview.trimmingCharacters(in: .whitespacesAndNewlines)
        if preview.isEmpty { return nil }
        if preview == "Created directly by you." { return .addedByYou }
        if preview == "Progress is waiting on input." { return .waitingOnYou }
        let quiet = ["Due in ", "Due date has passed", "Linked to ", "Canonical state ", "Relevant context is active"]
        if quiet.contains(where: { preview.hasPrefix($0) }) { return nil }
        return .text(preview)
    }

    /// Action texts can arrive coded as `verb:text`; the text part reads as a sentence.
    private static func plain(_ text: String) -> String {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if let colon = trimmed.firstIndex(of: ":"), trimmed[..<colon].allSatisfy({ $0.isLetter || $0 == "_" }),
           !trimmed[..<colon].contains(where: \.isUppercase), !trimmed[..<colon].isEmpty
        {
            return trimmed[trimmed.index(after: colon)...].trimmingCharacters(in: .whitespaces)
        }
        return trimmed
    }

    private static func normalized(_ text: String) -> String {
        text.lowercased().trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
    }
}
