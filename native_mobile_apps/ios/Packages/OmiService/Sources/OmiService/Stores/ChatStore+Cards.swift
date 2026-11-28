import Foundation
import OmiCore

/// A card the app draws under an answer, from what the agent did (never from model markup, so a
/// web page or an answer cannot fake one): a missing connection, a task Omi added or ticked off.
public enum ChatCard: Hashable, Sendable, Identifiable {
    /// The answer failed on a connection that is missing (`google_calendar`, `gmail`, `apple_health`).
    case connect(String)
    case taskAdded(id: String, title: String)
    case taskCompleted(id: String, title: String)

    public var id: String {
        switch self {
        case let .connect(integration): "connect:\(integration)"
        case let .taskAdded(id, _): "added:\(id)"
        case let .taskCompleted(id, _): "done:\(id)"
        }
    }
}

/// Reading cards out of a finished turn. Pure, so the rules are tested on the backend's own texts.
public enum ChatCardDetector {
    /// The connections the backend names when a tool cannot run (`calendar_tools.py`,
    /// `gmail_tools.py`, `apple_health_tools.py`: "Google Calendar is not connected. Please connect …").
    static let connections: [(id: String, names: [String])] = [
        ("google_calendar", ["google calendar", "google kalender", "google-kalender", "your calendar", "deinen kalender", "dein kalender"]),
        ("gmail", ["gmail", "google account", "google-konto", "google konto"]),
        ("apple_health", ["apple health", "apple health app", "health app"]),
    ]

    /// How an answer says it is not there.
    static let missingPhrases = [
        "is not connected", "isn't connected", "not connected", "is not linked", "isn't linked", "not linked",
        "please connect", "connect your", "need to connect", "needs to be connected", "don't have access", "do not have access",
        "nicht verbunden", "nicht verknüpft", "verbinde ", "verbinden", "keinen zugriff",
    ]

    /// Connections the answer (or a step) says are missing, in the order of `connections`.
    public static func missingConnections(text: String, steps: [String] = []) -> [String] {
        let sentences = ([text] + steps)
            .flatMap { $0.lowercased().components(separatedBy: CharacterSet(charactersIn: ".!?\n")) }
            .map { $0.replacingOccurrences(of: "’", with: "'") }
        return connections.compactMap { connection in
            let named = sentences.contains { sentence in
                connection.names.contains { sentence.contains($0) } && missingPhrases.contains { sentence.contains($0) }
            }
            return named ? connection.id : nil
        }
    }

    /// The agent touched tasks: its steps name the task tools (`agentic.py` display names
    /// "Creating action item" / "Updating action item", or the raw tool names).
    public static func touchedTasks(steps: [String]) -> Bool {
        steps.contains { step in
            let step = step.lowercased()
            return step.contains("create_action_item") || step.contains("update_action_item")
                || (step.contains("action item") && (step.contains("creat") || step.contains("updat")))
        }
    }

    /// Tasks that appeared or were ticked off between the two lists.
    public static func taskChanges(before: [ActionItem], after: [ActionItem]) -> [ChatCard] {
        let previous = Dictionary(before.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        var cards: [ChatCard] = []
        for task in after {
            if let old = previous[task.id] {
                if !old.isCompleted, task.isCompleted { cards.append(.taskCompleted(id: task.id, title: task.description)) }
            } else {
                cards.append(.taskAdded(id: task.id, title: task.description))
            }
        }
        return cards
    }
}

public extension ChatStore {
    /// The cards under one answer.
    func cards(for messageID: String) -> [ChatCard] {
        cardsByMessage[messageID] ?? []
    }

    /// Takes a task card back: an added task is deleted, a ticked one opens again. The card goes.
    func undo(_ card: ChatCard, in messageID: String) async {
        guard let tasks else { return }
        switch card {
        case let .taskAdded(id, _): await tasks.delete(id)
        case let .taskCompleted(id, _): await tasks.setCompleted(id, false)
        case .connect: return
        }
        guard tasks.lastError == nil else { return }
        cardsByMessage[messageID]?.removeAll { $0 == card }
        undoneCards.insert(card.id)
    }

    /// A connect card the user dealt with (connected, or "Not now").
    func dismiss(_ card: ChatCard, in messageID: String) {
        cardsByMessage[messageID]?.removeAll { $0 == card }
    }

    /// After a turn: a missing connection, and the tasks it added or ticked off (the list is read
    /// again only when a step says the agent touched tasks).
    internal func collectCards(for messageID: String, tasksBefore: [ActionItem]?) async {
        guard let message = messages.first(where: { $0.id == messageID }), message.sender == .omi else { return }
        var cards = ChatCardDetector.missingConnections(text: message.text, steps: message.steps).map(ChatCard.connect)
        if let tasks, let tasksBefore, ChatCardDetector.touchedTasks(steps: message.steps) {
            await tasks.load()
            cards += ChatCardDetector.taskChanges(before: tasksBefore, after: tasks.tasks)
        }
        add(cards, to: messageID, newest: true)
    }

    /// Connect cards from stored answers (older pages): each connection's card stays on the newest
    /// answer that asked for it.
    internal func collectConnectCards(in page: [ChatMessage]) {
        for message in page.reversed() where message.sender == .omi && message.failure == nil {
            let cards = ChatCardDetector.missingConnections(text: message.text).map(ChatCard.connect)
            add(cards, to: message.id, newest: false)
        }
    }

    func add(_ cards: [ChatCard], to messageID: String, newest: Bool) {
        for card in cards where !(cardsByMessage[messageID] ?? []).contains(card) && !undoneCards.contains(card.id) {
            if case .connect = card {
                let elsewhere = cardsByMessage.contains { $0.key != messageID && $0.value.contains(card) }
                if elsewhere {
                    guard newest else { continue }
                    for key in cardsByMessage.keys { cardsByMessage[key]?.removeAll { $0 == card } }
                }
            }
            cardsByMessage[messageID, default: []].append(card)
        }
    }
}

#if DEBUG
    public extension ChatStore {
        /// Debug builds: a made-up exchange appended on this iPhone only (never sent, gone on the
        /// next load), for screenshots of grouped bubbles, a long answer in parts and a card stack
        /// on a test account whose thread is empty.
        func showDemoThread() {
            let start = Date.now.addingTimeInterval(-20 * 60)
            func at(_ minutes: Double) -> Date { start.addingTimeInterval(minutes * 60) }
            let long = """
            Here is where things stand with the **Q4 roadmap**.

            Anna wants the deck by Thursday; the open points are pricing and the launch date.

            What I would do next:

            - Send Anna the draft deck today
            - Ask Ben for the pricing numbers
            - Book 30 minutes with both on Wednesday

            Want me to draft the message to Anna? [The notes](https://omi.me) have the details.
            """
            messages += [
                ChatMessage(id: "demo-q1", text: "What did Anna say about the roadmap?", sender: .user, createdAt: at(0)),
                ChatMessage(id: "demo-q2", text: "And what should I do next?", sender: .user, createdAt: at(0.2)),
                ChatMessage(
                    id: "demo-a1", text: long, sender: .omi, createdAt: at(0.5),
                    references: [.init(conversationID: "demo-1", title: "Q4 roadmap with Anna", emoji: "🗺️", createdAt: at(-180))]
                ),
                ChatMessage(id: "demo-q3", text: "Add those as tasks", sender: .user, createdAt: at(2)),
                ChatMessage(id: "demo-a2", text: "Done, three new tasks.", sender: .omi, createdAt: at(2.2), steps: ["Adding tasks"]),
                ChatMessage(id: "demo-q4", text: "Thanks!", sender: .user, createdAt: at(3)),
                ChatMessage(
                    id: "demo-a3", text: "Anytime.\n\nI will remind you on Wednesday morning.", sender: .omi, createdAt: at(3.1),
                    followUp: "Should I also invite Ben to the Wednesday meeting?"
                ),
            ]
            add(
                [
                    .taskAdded(id: "demo-t1", title: "Send Anna the draft deck"),
                    .taskAdded(id: "demo-t2", title: "Ask Ben for the pricing numbers"),
                    .taskAdded(id: "demo-t3", title: "Book 30 minutes with Anna and Ben"),
                ],
                to: "demo-a2", newest: false
            )
        }

        /// Debug builds: a connect card, a task card and source chips on the newest answer, without
        /// a turn (screenshots). Undo on the task card changes nothing real (no such task).
        func showDemoCards() {
            guard let index = messages.lastIndex(where: { $0.sender == .omi }) else { return }
            let id = messages[index].id
            let task = ChatCard.taskAdded(id: "demo-task", title: "Send Anna the Thursday follow-up")
            add([.connect("google_calendar"), task], to: id, newest: false)
            guard messages[index].references.isEmpty else { return }
            let start = Date.now.addingTimeInterval(-3 * 3600)
            messages[index].references = [
                .init(conversationID: "demo-1", title: "Q4 roadmap with Anna", emoji: "🗺️", createdAt: start),
                .init(conversationID: "demo-2", title: "Standup", emoji: "☕️", createdAt: start.addingTimeInterval(-86400)),
            ]
            messages[index].evidence = [
                ChatEvidence(
                    id: "e1", kind: .conversationSegment, state: .available, conversationID: "demo-1", segmentID: "s4", startMs: 754_000
                ),
            ]
        }
    }
#endif
