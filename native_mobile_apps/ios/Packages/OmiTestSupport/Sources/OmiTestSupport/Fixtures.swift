import Foundation
import OmiCore

public enum Fixtures {
    public static let now = Date(timeIntervalSince1970: 1_791_280_800) // 2026-10-06 10:00 UTC

    public static func conversation(
        id: String,
        title: String,
        minutesAgo: Double,
        durationMinutes: Double = 25,
        emoji: String = "💬",
        actionItems: Int = 0
    ) -> Conversation {
        let start = now.addingTimeInterval(-minutesAgo * 60)
        return Conversation(
            id: id,
            title: title,
            overview: "Overview of \(title.lowercased()).",
            emoji: emoji,
            category: "business",
            createdAt: start,
            startedAt: start,
            finishedAt: start.addingTimeInterval(durationMinutes * 60),
            status: .completed,
            isStarred: false,
            actionItemCount: actionItems
        )
    }

    public static let conversations: [Conversation] = [
        conversation(id: "c1", title: "Q4 roadmap with Anna", minutesAgo: 60, emoji: "🗺️", actionItems: 3),
        conversation(id: "c2", title: "Standup", minutesAgo: 180, durationMinutes: 12, emoji: "☕️", actionItems: 1),
        conversation(id: "c3", title: "Dinner plans", minutesAgo: 60 * 26, emoji: "🍝"),
        conversation(id: "c4", title: "Investor call", minutesAgo: 60 * 50, durationMinutes: 45, emoji: "📈", actionItems: 2),
    ]

    public static func task(
        _ id: String,
        _ text: String,
        dueInDays: Double? = nil,
        owner: ActionItem.Owner = .user,
        done: Bool = false,
        conversation: String? = "c1",
        workstream: String? = nil
    ) -> ActionItem {
        ActionItem(
            id: id,
            description: text,
            isCompleted: done,
            dueAt: dueInDays.map { now.addingTimeInterval($0 * 86400) },
            conversationID: conversation,
            owner: owner,
            workstreamID: workstream,
            createdAt: now
        )
    }

    public static let tasks: [ActionItem] = [
        task("t1", "Send proof of income", dueInDays: -1),
        task("t2", "Send roadmap deck", dueInDays: 0.2),
        task("t3", "Research competitor pricing", dueInDays: 4),
        task("t4", "Look up ski chalets"),
        task("t5", "Leo unblocks firmware", dueInDays: 2, owner: .other, conversation: "c2"),
        task("t6", "Buy the book", done: true, conversation: "c3"),
    ]

    public static let memories: [Memory] = [
        Memory(id: "m1", content: "Prefers morning meetings.", headline: nil, category: "habits", createdAt: now, conversationID: nil),
        Memory(id: "m2", content: "Works on the native Omi app.", headline: nil, category: "work", createdAt: now, conversationID: "c1"),
        Memory(
            id: "m3",
            content: "Plans a ski trip in February.",
            headline: nil,
            category: "interests",
            createdAt: now,
            conversationID: "c3"
        ),
    ]
}
