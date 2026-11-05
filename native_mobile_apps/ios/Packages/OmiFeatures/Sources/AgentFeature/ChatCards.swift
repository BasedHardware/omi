import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// The cards under one answer, drawn by the app from what the turn did (never from the answer's
/// own text markup): Omi's open question, a missing connection, tasks Omi added or ticked off.
struct AnswerCards: View {
    @Environment(ChatStore.self) private var chat
    @Environment(CapabilitiesStore.self) private var capabilities
    @Environment(AppleHealthStore.self) private var health
    @Environment(\.openURL) private var openURL
    @Environment(\.chatBubbleWidth) private var bubbleWidth
    let message: ChatMessage

    var body: some View {
        let cards = chat.cards(for: message.id).filter(isRelevant)
        if (chat.pendingDeviceToolMessageID == message.id && chat.pendingDeviceTool != nil) || !cards.isEmpty {
            VStack(alignment: .leading, spacing: DS.Spacing.xs + 2) {
                if chat.pendingDeviceToolMessageID == message.id, let pending = chat.pendingDeviceTool {
                    OmiAsksCard(pending: pending) { choice in await chat.answerDeviceTool(choice) }
                }
                // Never two cards of one kind in a row: the first, and "2 more".
                ForEach(ChatStacking.stacks(cards, kind: \.kind), id: \.first?.id) { stack in
                    ChatCardStack(items: stack) { card in self.card(card) }
                }
            }
            // As wide as Omi's bubbles, not the whole row.
            .frame(maxWidth: bubbleWidth, alignment: .leading)
        }
    }

    @ViewBuilder
    private func card(_ card: ChatCard) -> some View {
        switch card {
        case let .connect(id):
            ConnectCard(id: id) { chat.dismiss(card, in: message.id) }
        case let .taskAdded(id, _), let .taskCompleted(id, _):
            TaskChangeCard(
                card: card,
                onOpen: { openURL(DeepLink.task(id: id).url) },
                onUndo: { Task { await chat.undo(card, in: message.id) } }
            )
        }
    }

    /// A connect card only while that connection is still missing.
    private func isRelevant(_ card: ChatCard) -> Bool {
        guard case let .connect(id) = card else { return true }
        if id == AppleHealthStore.key { return !health.isConnected && health.isAvailable }
        guard let integration = capabilities.integrations.first(where: { $0.id == id }) else { return false }
        return !integration.isConnected
    }
}

/// "Connect Google Calendar": the answer failed on a missing connection; connecting happens right
/// here (the same sign-in as Settings and Home).
struct ConnectCard: View {
    @Environment(CapabilitiesStore.self) private var capabilities
    @Environment(AppleHealthStore.self) private var health
    @Environment(\.webAuthenticationSession) private var webAuthentication
    let id: String
    let onDismiss: () -> Void

    var body: some View {
        DecisionCard(
            kicker: DecisionCard.Kicker(symbol: "link", text: L("nativeChatConnectKicker"), color: DS.Palette.agent),
            title: L("nativeChatConnectTitle", Self.name(id)),
            subtitle: subtitle,
            pulses: isConnecting,
            pills: [
                DecisionCard.Pill(title: L("nativeConnect"), isPrimary: true) { Task { await connect() } },
                DecisionCard.Pill(title: L("notNow"), action: onDismiss),
            ],
            compact: true,
            onTap: { Task { await connect() } }
        )
        .accessibilityIdentifier("chat.connect.\(id)")
    }

    static func name(_ id: String) -> String {
        id == AppleHealthStore.key ? "Apple Health" : CapabilitiesList.name(id)
    }

    private var isConnecting: Bool {
        id == AppleHealthStore.key ? health.phase == .connecting : capabilities.connecting == id
    }

    private var subtitle: String {
        if id != AppleHealthStore.key, let failure = capabilities.failures[id], !isConnecting {
            return CapabilitiesList.message(failure, name: Self.name(id))
        }
        return id == AppleHealthStore.key ? L("nativeCapabilityHealth") : L(CapabilitiesList.purposeKey(id))
    }

    private func connect() async {
        if id == AppleHealthStore.key {
            await health.connect()
        } else if let integration = capabilities.integrations.first(where: { $0.id == id }) {
            await CapabilitiesList.connect(integration, store: capabilities, webAuthentication: webAuthentication)
        }
    }
}

/// "Added task: …" / "Marked done: …": a tap opens the task, Undo takes it back.
struct TaskChangeCard: View {
    let card: ChatCard
    let onOpen: () -> Void
    let onUndo: () -> Void

    var body: some View {
        HStack(spacing: DS.Spacing.md) {
            Button(action: onOpen) {
                HStack(spacing: DS.Spacing.md) {
                    Image(systemName: isDone ? "checkmark.circle.fill" : "plus.circle")
                        .font(.system(size: 16, weight: .regular))
                        .foregroundStyle(isDone ? DS.Palette.success : DS.Palette.agent)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(isDone ? L("nativeChatTaskMarkedDone") : L("nativeChatTaskAdded"))
                            .font(DS.Typography.caption)
                            .foregroundStyle(DS.Palette.inkTertiary)
                        Text(title)
                            .font(DS.Typography.callout)
                            .foregroundStyle(DS.Palette.ink)
                            .lineLimit(1)
                    }
                    Spacer(minLength: 0)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityElement(children: .combine)
            Button(L("undo"), action: onUndo)
                .font(DS.Typography.caption.weight(.semibold))
                .foregroundStyle(DS.Palette.agent)
                .buttonStyle(.plain)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, DS.Spacing.sm + 1)
        .background(DS.Palette.card, in: RoundedRectangle(cornerRadius: DS.Radius.bubble, style: .continuous))
        .accessibilityIdentifier("chat.taskCard")
    }

    private var isDone: Bool {
        if case .taskCompleted = card { true } else { false }
    }

    private var title: String {
        switch card {
        case let .taskAdded(_, title), let .taskCompleted(_, title): title
        case .connect: ""
        }
    }
}

/// The conversations an answer drew on, as chips "Q4 roadmap · 14:05"; a tap opens that one.
struct CitationChips: View {
    let citations: [ChatCitation]
    let onOpen: ((String) -> Void)?

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: DS.Spacing.sm) {
                ForEach(citations) { citation in
                    Button {
                        DSHaptics.selection()
                        onOpen?(citation.conversationID)
                    } label: {
                        HStack(spacing: DS.Spacing.xs) {
                            if let emoji = citation.emoji, !emoji.isEmpty {
                                Text(emoji)
                            } else {
                                Image(systemName: "bubble.left").imageScale(.small)
                            }
                            Text(Self.label(citation)).lineLimit(1)
                        }
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.ink)
                        .padding(.horizontal, DS.Spacing.sm + 2)
                        .padding(.vertical, DS.Spacing.xs + 1)
                        .background(DS.Palette.fill, in: Capsule())
                    }
                    .buttonStyle(.plain)
                    .disabled(onOpen == nil)
                    .accessibilityIdentifier("chat.citation")
                }
            }
        }
    }

    /// "Q4 roadmap · 14:05"; an older one carries its day ("Q4 roadmap · Tue 14:05").
    static func label(_ citation: ChatCitation, now: Date = .now, calendar: Calendar = .current) -> String {
        let title = citation.title.isEmpty ? L("untitledConversation") : citation.title
        guard let time = citation.time else { return title }
        let style: Date.FormatStyle = if calendar.isDate(time, inSameDayAs: now) {
            .dateTime.hour().minute()
        } else if now.timeIntervalSince(time) < 6 * 86400 {
            .dateTime.weekday(.abbreviated).hour().minute()
        } else {
            .dateTime.day().month(.abbreviated)
        }
        return "\(title) · \(time.formatted(style))"
    }
}
