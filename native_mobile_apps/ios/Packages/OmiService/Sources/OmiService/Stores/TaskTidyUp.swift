import Foundation
import OmiCore

/// The daily AI tidy-up of open tasks (docs/CHAT-FIRST.md): the chat agent reads a compact list
/// and answers with JSON only: what to merge, what looks done, what is no task, what matters.
/// Nothing is applied on its own; Home shows one suggestion card and the user reviews each change.
public enum TaskTidyUp {
    public struct Merge: Codable, Equatable, Sendable {
        public let keep: String
        public let drop: [String]
        public let why: String

        public init(keep: String, drop: [String], why: String) {
            self.keep = keep
            self.drop = drop
            self.why = why
        }
    }

    public struct Change: Codable, Equatable, Sendable {
        public let id: String
        public let why: String

        public init(id: String, why: String) {
            self.id = id
            self.why = why
        }
    }

    /// Task ids are the real backend ids (the prompt's short keys are mapped back by `parse`).
    public struct Proposal: Codable, Equatable, Sendable {
        public var merges: [Merge]
        public var done: [Change]
        public var notTask: [Change]
        public var important: [String]

        public init(merges: [Merge] = [], done: [Change] = [], notTask: [Change] = [], important: [String] = []) {
            self.merges = merges
            self.done = done
            self.notTask = notTask
            self.important = important
        }

        /// Nothing to change (`important` alone is only a ranking hint, never a card).
        public var isEmpty: Bool { merges.isEmpty && done.isEmpty && notTask.isEmpty }
        /// Tasks that would be merged away ("merge 6").
        public var mergedCount: Int { merges.map(\.drop.count).reduce(0, +) }

        /// Only what still applies: every task named is still open.
        public func restricted(to open: Set<String>) -> Proposal {
            Proposal(
                merges: merges.compactMap { merge in
                    let drop = merge.drop.filter(open.contains)
                    return open.contains(merge.keep) && !drop.isEmpty ? Merge(keep: merge.keep, drop: drop, why: merge.why) : nil
                },
                done: done.filter { open.contains($0.id) },
                notTask: notTask.filter { open.contains($0.id) },
                important: important.filter(open.contains)
            )
        }

        /// Each change the review sheet lists, in order: merges, done, not a task.
        public var edits: [Edit] {
            merges.flatMap { merge in merge.drop.map { Edit(taskID: $0, kind: .merge(into: merge.keep), why: merge.why) } }
                + done.map { Edit(taskID: $0.id, kind: .done, why: $0.why) }
                + notTask.map { Edit(taskID: $0.id, kind: .notTask, why: $0.why) }
        }
    }

    /// One proposed change: a PATCH once the user applies it.
    public struct Edit: Identifiable, Hashable, Sendable {
        public enum Kind: Hashable, Sendable {
            /// `superseded`, `superseded_by` the kept task.
            case merge(into: String)
            /// `completed`.
            case done
            /// `cancelled` ("Not a task").
            case notTask
        }

        public let taskID: String
        public let kind: Kind
        public let why: String

        public var id: String { taskID }

        public var status: ActionItem.Status {
            switch kind {
            case .merge: .superseded
            case .done: .completed
            case .notTask: .cancelled
            }
        }
    }

    /// At most this many tasks go into the prompt (newest first), so it stays short.
    public static let maxTasks = 60

    /// Short keys ("t1", "t2" …) for the prompt, so the model never has to copy long ids.
    public static func keys(for tasks: [ActionItem]) -> [String: String] {
        Dictionary(uniqueKeysWithValues: tasks.enumerated().map { ("t\($0.offset + 1)", $0.element.id) })
    }

    /// The question for the agent: the tasks as `id | task | due | source`, then the exact JSON shape.
    public static func prompt(
        _ tasks: [ActionItem], source: (ActionItem) -> String?, quote: (ActionItem) -> String? = { _ in nil },
        now: Date = .now, calendar: Calendar = .current
    ) -> String {
        let day = DateFormatter()
        day.calendar = calendar
        day.locale = Locale(identifier: "en_US_POSIX")
        day.timeZone = calendar.timeZone
        day.dateFormat = "yyyy-MM-dd"
        let lines = tasks.enumerated().map { offset, task in
            let text = task.description.replacingOccurrences(of: "\n", with: " ").replacingOccurrences(of: "|", with: "/")
            let due = task.dueAt.map { "due " + day.string(from: $0) } ?? "-"
            let from = source(task).map { "\"\(String($0.prefix(60)))\"" } ?? "-"
            let heard = task.createdAt.map { day.string(from: $0) } ?? "-"
            let said = quote(task).map { " | said: \"\(String($0.replacingOccurrences(of: "\n", with: " ").prefix(100)))\"" } ?? ""
            return "t\(offset + 1) | \(String(text.prefix(140))) | \(due) | \(from) \(heard)\(said)"
        }
        return """
        Tidy up my open tasks. Do not call tools and do not change anything; answer with JSON only.
        Today is \(day.string(from: now)).
        Tasks (id | task | due | source conversation, date | what was said):
        \(lines.joined(separator: "\n"))

        Answer with exactly one JSON object and nothing else:
        {"merge":[{"keep":"t1","drop":["t2"],"why":"..."}],"done":[{"id":"t3","why":"..."}],\
        "notTask":[{"id":"t4","why":"..."}],"important":["t5"]}
        Rules: merge only tasks that are the same action on the same thing (never just a similar topic), keep the \
        clearest. done only when it clearly already \
        happened or its moment has passed. notTask: a fragment, not something I have to do, someone else's job, or a \
        request I made of someone else or of an assistant ("can you …", "kannst du …") unless it is about me. \
        important: at most 5 that matter most now. "why": at most 8 words, in the task's language. \
        Leave a list empty when unsure.
        """
    }

    /// The agent's answer as a proposal, or nil when it holds no JSON object. Tolerates code fences,
    /// text around the object, numbers for keys and unknown or repeated ids (dropped): each task
    /// appears in at most one change, and a kept task is never also dropped.
    public static func parse(_ text: String, keys: [String: String]) -> Proposal? {
        guard let object = jsonObject(in: text) else { return nil }
        func id(_ value: Any?) -> String? {
            switch value {
            case let string as String:
                let key = string.trimmingCharacters(in: .whitespaces).lowercased()
                return keys[key] ?? keys["t" + key]
            case let number as NSNumber: return keys["t\(number.intValue)"]
            default: return nil
            }
        }
        func why(_ entry: [String: Any]) -> String {
            String(((entry["why"] as? String) ?? "").trimmingCharacters(in: .whitespacesAndNewlines).prefix(120))
        }
        var used = Set<String>()
        var merges: [Merge] = []
        for entry in object["merge"] as? [[String: Any]] ?? [] {
            guard let keep = id(entry["keep"]), !used.contains(keep) else { continue }
            let drops = (entry["drop"] as? [Any] ?? [entry["drop"] as Any]).compactMap(id)
            var unique: [String] = []
            for drop in drops where drop != keep && !used.contains(drop) && !unique.contains(drop) {
                unique.append(drop)
            }
            guard !unique.isEmpty else { continue }
            used.insert(keep)
            used.formUnion(unique)
            merges.append(Merge(keep: keep, drop: unique, why: why(entry)))
        }
        func changes(_ name: String...) -> [Change] {
            let entries = name.lazy.compactMap { object[$0] as? [Any] }.first ?? []
            return entries.compactMap { raw in
                let entry = raw as? [String: Any] ?? ["id": raw]
                guard let task = id(entry["id"]), used.insert(task).inserted else { return nil }
                return Change(id: task, why: why(entry))
            }
        }
        let done = changes("done")
        let notTask = changes("notTask", "not_task", "nottask")
        var seen = Set<String>()
        let important = (object["important"] as? [Any] ?? []).compactMap(id).filter { seen.insert($0).inserted }
        return Proposal(merges: merges, done: done, notTask: notTask, important: Array(important.prefix(5)))
    }

    /// The first `{` to the last `}` that parses, with Markdown code fences gone.
    static func jsonObject(in text: String) -> [String: Any]? {
        let cleaned = text.replacingOccurrences(of: "```json", with: "").replacingOccurrences(of: "```", with: "")
        guard let start = cleaned.firstIndex(of: "{") else { return nil }
        var end = cleaned.endIndex
        while let close = cleaned[start ..< end].lastIndex(of: "}") {
            let candidate = String(cleaned[start ... close])
            if let data = candidate.data(using: .utf8),
               let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            {
                return object
            }
            end = close
        }
        return nil
    }
}
