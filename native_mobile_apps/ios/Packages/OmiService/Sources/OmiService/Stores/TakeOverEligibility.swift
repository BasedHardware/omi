import Foundation
import OmiCore

/// Whether "Omi takes over" makes sense for a task: only the user's own tasks (the backend's
/// `owner`), and only ones Omi can plausibly do on a screen: write, send, research, book,
/// schedule, order, remind, summarize. Not a climb, a workout or a market visit, and not what
/// Leo promised to do. Conservative on purpose: a missing button costs less than a run that
/// cannot work. English and German.
public enum TakeOverEligibility {
    public static func canTakeOver(_ task: ActionItem) -> Bool {
        guard !task.isCompleted, task.owner != .other else { return false }
        let text = normalized(task.description)
        guard !text.isEmpty, !looksLikeSomeoneElses(task.description) else { return false }
        if physicalMarkers.contains(where: { contains(text, $0) }) { return false }
        let words = text.split(separator: " ").map(String.init)
        guard let first = words.first else { return false }
        // The task starts with something Omi can do ("Draft the memo", "Schreib Anna").
        if digitalVerbs.contains(first) { return true }
        // Or names a digital thing to act on anywhere ("Follow up with Anna by email").
        return digitalPhrases.contains { contains(text, $0) }
    }

    /// "Leo unblocks the firmware release", "Northwind sends the term sheet": a name, then a
    /// verb in the third person, is another person's commitment even when the owner is unknown.
    static func looksLikeSomeoneElses(_ description: String) -> Bool {
        let words = description.split(separator: " ").map(String.init)
        guard words.count >= 2, let initial = words[0].first, initial.isUppercase else { return false }
        let first = words[0].lowercased(), second = words[1].lowercased()
        if digitalVerbs.contains(first) || otherImperatives.contains(first) { return false }
        let thirdPerson = second.count > 3 && second.hasSuffix("s") && !second.hasSuffix("ss")
        let germanThirdPerson = second.count > 3 && second.hasSuffix("t") && !digitalVerbs.contains(second)
        return thirdPerson || (germanThirdPerson && germanSubjects(words[0]) && looksGerman(description))
    }

    /// "Anna schickt das Angebot", not "Renew passport": the "-t" ending only reads as a German
    /// verb in a German sentence (an article, a preposition or an umlaut).
    private static func looksGerman(_ text: String) -> Bool {
        let lowered = text.lowercased()
        if lowered.contains(where: { "äöüß".contains($0) }) { return true }
        let markers: Set<String> = [
            "der", "die", "das", "den", "dem", "ein", "eine", "einen", "und", "mit", "für", "von", "zu", "auf", "noch", "bis",
        ]
        return lowered.split(separator: " ").contains { markers.contains(String($0)) }
    }

    private static func germanSubjects(_ word: String) -> Bool {
        // A capitalized first word that is not a German imperative ("Ziehe", "Buche") is a name.
        !word.lowercased().hasSuffix("e")
    }

    private static func normalized(_ text: String) -> String {
        text.lowercased()
            .replacingOccurrences(of: "e-mail", with: "email")
            .components(separatedBy: CharacterSet.alphanumerics.inverted.subtracting(CharacterSet(charactersIn: "'")))
            .filter { !$0.isEmpty }
            .joined(separator: " ")
    }

    private static func contains(_ text: String, _ phrase: String) -> Bool {
        " \(text) ".contains(" \(phrase) ")
    }

    /// Imperatives Omi can carry out with its tools (drafts it leaves for the user to send).
    static let digitalVerbs: Set<String> = [
        // English
        "email", "mail", "message", "text", "send", "draft", "write", "reply", "respond", "answer", "ask", "invite",
        "research", "look", "find", "search", "compare", "summarize", "summarise", "book", "schedule", "reschedule",
        "order", "reserve", "remind", "plan", "follow", "share", "forward", "compile", "outline", "translate",
        // German
        "schreib", "schreibe", "schreiben", "schick", "schicke", "schicken", "sende", "senden", "antworte", "antworten",
        "frag", "frage", "fragen", "lade", "recherchiere", "recherchieren", "such", "suche", "suchen", "finde", "finden",
        "vergleiche", "vergleichen", "fasse", "buche", "buchen", "plane", "planen", "bestelle", "bestellen", "reserviere",
        "reservieren", "erinnere", "erinnern", "entwirf", "entwerfen", "vereinbare", "vereinbaren", "übersetze",
    ]

    /// Digital objects or channels that make a task doable even without a leading verb.
    static let digitalPhrases: [String] = [
        "email", "mail", "message", "text", "invite", "calendar", "meeting", "appointment", "reservation", "flight", "hotel",
        "ticket", "online", "draft", "memo", "summary", "doc", "document", "slack", "whatsapp", "follow up", "look up",
        "termin", "nachricht", "einladung", "kalender", "zusammenfassung", "flug", "entwurf",
    ]

    /// Things done in person or with the body: Omi cannot do these, whatever the verb.
    static let physicalMarkers: [String] = [
        "climb", "climbing", "run", "jog", "walk", "hike", "gym", "workout", "work out", "exercise", "stretch", "swim",
        "yoga", "cook", "clean", "tidy", "wash", "laundry", "groceries", "pick up", "drop off", "drive", "go to", "visit",
        "at a market", "at the market", "in person", "sleep", "eat", "drink", "water the", "rocks",
        "klettern", "laufen", "joggen", "wandern", "sport", "trainieren", "kochen", "putzen", "aufräumen", "waschen",
        "einkaufen", "abholen", "fahren", "besuchen", "schlafen", "essen", "auf dem markt",
    ]

    /// Imperatives that are clearly the user's own but not doable by Omi (kept out of the
    /// third-person check so "Maximize …" is not read as a name).
    static let otherImperatives: Set<String> = [
        "maximize", "implement", "improve", "measure", "copy", "choose", "purchase", "buy", "make", "build", "fix", "test",
        "integrate", "optimize", "utilize", "develop", "provide", "introduce", "explain", "clarify", "remove", "archive",
        "check", "create", "update", "review", "figure", "prepare", "set", "add", "collect", "gather", "confirm", "cancel",
        "ziehe", "kaufe", "baue", "teste", "verbessere",
    ]
}

public extension AgentStore {
    /// "Omi takes over" is offered for this task (the For you pill and the task row): the user's
    /// own, digital tasks only. A task Omi already worked on keeps its status either way.
    func canTakeOver(_ task: ActionItem) -> Bool {
        TakeOverEligibility.canTakeOver(task)
    }
}
