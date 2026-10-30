import Foundation
import OmiCore
import OmiNetwork

/// Why Omi asks about a memory, which decides how the question is put (the words live in the
/// app: `MemoryReviewSheet`). Only the backend's own doubts and conflicts lead to a question,
/// never "is every new memory right?".
public enum MemoryReviewQuestion: Equatable, Sendable {
    /// Two versions of the same fact: which is right (or neither)? `earlier` is nil when the
    /// earlier memory is not loaded.
    case whichIsRight(earlier: String?, now: String)
    /// The backend thinks it is about someone else (`third_party_subject`).
    case aboutSomeoneElse(name: String?)
    /// It may be out of date (`stale`).
    case stillTrue
    /// Heard once and not clearly (`low_capture_signal`, with `single_source`).
    case heardOnce
    /// Not clearly heard (`low_capture_signal` from more than one source).
    case unclear
}

/// One question in the review flow.
public enum MemoryReviewItem: Identifiable, Equatable, Sendable {
    /// A memory with a doubt; `earlier` is the memory it contradicts, when there is one.
    case memory(Memory, MemoryReviewQuestion, earlier: Memory?)
    /// A conflict the backend holds back (review queue); `earlier` is the first conflicting memory.
    case conflict(MemoryConflict, earlier: Memory?)

    public var id: String {
        switch self {
        case let .memory(memory, _, _): "memory.\(memory.id)"
        case let .conflict(conflict, _): "conflict.\(conflict.id)"
        }
    }

    public var question: MemoryReviewQuestion {
        switch self {
        case let .memory(_, question, _): question
        case let .conflict(conflict, earlier): .whichIsRight(earlier: earlier?.content, now: conflict.candidate)
        }
    }
}

/// The user's answer.
public enum MemoryReviewAnswer: Equatable, Sendable {
    case yes
    case no
    case edit(String)
    /// Two versions: the earlier one, the new one, or neither.
    case keepEarlier
    case keepNew
    case neither
}

/// Which memories have a reason to be reviewed and how to ask (pure, so it is testable).
public enum MemoryReviewRule {
    /// The backend's doubts that are worth a question. `single_source` alone is nearly every
    /// memory (one conversation), so it only shapes the wording.
    static let askingReasons: Set<String> = ["contradicted_by", "third_party_subject", "stale", "low_capture_signal"]

    public static func needsReview(_ memory: Memory) -> Bool {
        guard !memory.reviewed, !memory.isLocked, !memory.isBaseline, memory.category != "manual" else { return false }
        return memory.uncertaintyReasons.contains { askingReasons.contains(reasonName($0)) }
    }

    /// The question for a memory that needs review; nil otherwise. A contradiction wins, then
    /// who it is about, then age, then how clearly it was heard.
    public static func question(for memory: Memory, among memories: [Memory]) -> (MemoryReviewQuestion, earlier: Memory?)? {
        guard needsReview(memory) else { return nil }
        let reasons = memory.uncertaintyReasons.map(reasonName)
        if reasons.contains("contradicted_by") {
            let earlier = contradictedID(memory).flatMap { id in memories.first { $0.id == id } }
            return (.whichIsRight(earlier: earlier?.content, now: memory.content), earlier)
        }
        if reasons.contains("third_party_subject") { return (.aboutSomeoneElse(name: memory.subjectName), nil) }
        if reasons.contains("stale") { return (.stillTrue, nil) }
        return (reasons.contains("single_source") ? .heardOnce : .unclear, nil)
    }

    /// `contradicted_by` may carry the other memory's id (`contradicted_by:<id>`).
    static func reasonName(_ reason: String) -> String {
        String(reason.split(separator: ":", maxSplits: 1).first ?? Substring(reason))
    }

    static func contradictedID(_ memory: Memory) -> String? {
        memory.uncertaintyReasons.lazy.compactMap { reason -> String? in
            let parts = reason.split(separator: ":", maxSplits: 1)
            return parts.count == 2 && parts[0] == "contradicted_by" ? String(parts[1]) : nil
        }.first
    }

    static func priority(_ question: MemoryReviewQuestion) -> Int {
        switch question {
        case .whichIsRight: 0
        case .aboutSomeoneElse: 1
        case .stillTrue: 2
        case .heardOnce, .unclear: 3
        }
    }
}

public extension MemoriesStore {
    /// What the review flow asks, in order: the backend's held-back conflicts, then memories with
    /// a doubt (contradictions first), newest first within each.
    var reviewQueue: [MemoryReviewItem] {
        let byID = Dictionary(memories.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        let conflicts = reviewConflicts.map { conflict in
            MemoryReviewItem.conflict(conflict, earlier: conflict.conflictsWith.lazy.compactMap { byID[$0] }.first)
        }
        let doubts = memories.compactMap { memory -> (memory: Memory, item: MemoryReviewItem)? in
            guard let (question, earlier) = MemoryReviewRule.question(for: memory, among: memories) else { return nil }
            return (memory, .memory(memory, question, earlier: earlier))
        }
        .sorted { lhs, rhs in
            let left = MemoryReviewRule.priority(lhs.item.question), right = MemoryReviewRule.priority(rhs.item.question)
            return left != right ? left < right : lhs.memory.createdAt > rhs.memory.createdAt
        }
        .map(\.item)
        return conflicts + doubts
    }

    /// How many questions wait; zero means no review entry at all.
    var reviewCount: Int {
        reviewConflicts.count + memories.count(where: MemoryReviewRule.needsReview)
    }

    /// The backend's pending conflicts. A failure leaves the last known ones.
    func loadReviewQueue() async {
        if let conflicts = try? await api.memoryReviewQueue() { reviewConflicts = conflicts }
    }

    /// Applies an answer: a memory's verdict goes to `v3/memories/{id}/review` (an edit saves
    /// the fix first), a held-back conflict to the review queue's resolve.
    func answer(_ item: MemoryReviewItem, _ answer: MemoryReviewAnswer) async {
        switch item {
        case let .memory(memory, _, earlier):
            switch answer {
            case .yes, .keepNew:
                await review(memory.id, isRight: true)
                if answer == .keepNew, let earlier { await review(earlier.id, isRight: false) }
            case .no, .keepEarlier:
                await review(memory.id, isRight: false)
            case let .edit(text):
                await edit(memory.id, content: text)
                await review(memory.id, isRight: true)
            case .neither:
                await review(memory.id, isRight: false)
                if let earlier { await review(earlier.id, isRight: false) }
            }
        case let .conflict(conflict, _):
            reviewConflicts.removeAll { $0.id == conflict.id }
            let decision: MemoryConflict.Decision = answer == .keepNew || answer == .yes ? .accept : .reject
            do {
                try await api.resolveMemoryConflict(id: conflict.id, decision: decision)
                // Neither: the earlier ones go too.
                if answer == .neither {
                    for id in conflict.conflictsWith where memories.contains(where: { $0.id == id }) {
                        await review(id, isRight: false)
                    }
                }
            } catch {
                lastError = String(describing: error)
                reviewConflicts.append(conflict)
            }
        }
    }
}
