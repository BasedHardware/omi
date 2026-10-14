import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// "Omi asks": the words and choices for a device tool call Omi is waiting on mid-run (a message
/// to send, which contact, a permission). Home's For you card and the run's detail show the
/// same thing; nothing happens until the user taps a choice.
public struct OmiAsksPresentation {
    public struct Choice: Identifiable {
        public enum Kind {
            case answer(DeviceToolChoice)
            /// Change the message first (`OmiAsksEditSheet`).
            case edit
        }

        public let title: String
        public let isPrimary: Bool
        public let kind: Kind
        public var id: String {
            title
        }
    }

    public let title: String
    public let subtitle: String
    /// The task it is for, as the card's quiet line.
    public let source: String
    public let choices: [Choice]

    @MainActor
    public init(_ pending: PendingDeviceTool) {
        let request = pending.request
        source = pending.taskTitle.isEmpty ? "" : L("nativeOmiAsksFor", pending.taskTitle)
        switch request.tool {
        case .proposeMessage:
            title = L("nativeOmiAsksSendTo", request.recipients.joined(separator: ", "))
            subtitle = "“\(request.text.replacingOccurrences(of: "\n", with: " "))”"
            choices = [
                Choice(title: L("nativeOmiAsksSend"), isPrimary: true, kind: .answer(.send(text: request.text))),
                Choice(title: L("edit"), isPrimary: false, kind: .edit),
                Choice(title: L("notNow"), isPrimary: false, kind: .answer(.decline)),
            ]
        case .searchContacts where pending.needsContactsAccess:
            title = L("nativeOmiAsksLookUp", request.query)
            subtitle = L("nativeOmiAsksOnlyThePick")
            choices = [
                Choice(title: L("nativeOmiAsksAllow"), isPrimary: true, kind: .answer(.allow)),
                Choice(title: L("notNow"), isPrimary: false, kind: .answer(.decline)),
            ]
        case .searchContacts where pending.matches.isEmpty:
            title = L("nativeOmiAsksNoMatch", request.query)
            subtitle = L("nativeOmiAsksGoOnWithout")
            choices = [Choice(title: L("nativeOmiAsksGoOn"), isPrimary: true, kind: .answer(.decline))]
        case .searchContacts:
            title = L("nativeOmiAsksWhichOne", request.query)
            subtitle = L("nativeOmiAsksOnlyThePick")
            choices = pending.matches.prefix(2).enumerated().map { index, contact in
                Choice(title: contact.name, isPrimary: index == 0, kind: .answer(.pick(contact)))
            } + [Choice(title: L("notNow"), isPrimary: false, kind: .answer(.decline))]
        case .requestPermission:
            title = L("nativeOmiAsksContactsAccess")
            subtitle = L("nativeOmiAsksOnlyThePick")
            choices = [
                Choice(title: L("nativeOmiAsksAllow"), isPrimary: true, kind: .answer(.allow)),
                Choice(title: L("notNow"), isPrimary: false, kind: .answer(.decline)),
            ]
        case nil:
            title = L("nativeOmiAsksKicker")
            subtitle = ""
            choices = [Choice(title: L("notNow"), isPrimary: true, kind: .answer(.decline))]
        }
    }

    public static var kicker: DecisionCard.Kicker {
        DecisionCard.Kicker(symbol: "questionmark.bubble", text: L("nativeOmiAsksKicker"), color: DS.Palette.agent)
    }
}

/// "Omi asks" as a decision card: the question, the message or what it needs, the task it is
/// for, and the choices. Edit opens the message to change before the composer. A run's question
/// goes back to its run (`AgentStore`); the chat passes its own `onAnswer`.
public struct OmiAsksCard: View {
    @Environment(AgentStore.self) private var agent
    @State private var editing = false
    let pending: PendingDeviceTool
    /// The tap on the card when it has several choices (Home: the run it belongs to).
    let onOpen: (() -> Void)?
    private let onAnswer: (@MainActor (DeviceToolChoice) async -> Void)?
    /// In the chat thread: the compact card, as the bubbles.
    private var compact = false

    public init(pending: PendingDeviceTool, onOpen: (() -> Void)? = nil) {
        self.pending = pending
        self.onOpen = onOpen
        onAnswer = nil
    }

    /// For a question outside a run (the main chat): the tap goes to `onAnswer`. The thread's card
    /// is compact.
    public init(pending: PendingDeviceTool, onAnswer: @escaping @MainActor (DeviceToolChoice) async -> Void) {
        self.pending = pending
        onOpen = nil
        self.onAnswer = onAnswer
        compact = true
    }

    public var body: some View {
        let presentation = OmiAsksPresentation(pending)
        let pills = presentation.choices.map { choice in
            DecisionCard.Pill(title: choice.title, isPrimary: choice.isPrimary) { choose(choice) }
        }
        DecisionCard(
            kicker: OmiAsksPresentation.kicker, title: presentation.title, subtitle: presentation.subtitle,
            source: presentation.source, pills: pills.count > 1 ? pills : [], compact: compact,
            onTap: pills.count == 1 ? { presentation.choices.first.map(choose) } : onOpen
        )
        .accessibilityIdentifier("omiAsks.\(pending.id)")
        .sheet(isPresented: $editing) {
            OmiAsksEditSheet(pending: pending) { text in
                Task { await answer(.send(text: text)) }
            }
        }
    }

    private func choose(_ choice: OmiAsksPresentation.Choice) {
        switch choice.kind {
        case .edit:
            editing = true
        case let .answer(choice):
            DSHaptics.selection()
            Task { await answer(choice) }
        }
    }

    private func answer(_ choice: DeviceToolChoice) async {
        if let onAnswer { await onAnswer(choice) } else { await agent.answer(pending, choice) }
    }
}

/// The proposed message, editable, before the system composer opens (where the user sends it).
public struct OmiAsksEditSheet: View {
    @Environment(\.dismiss) private var dismiss
    @State private var text: String
    let pending: PendingDeviceTool
    let onSend: (String) -> Void

    public init(pending: PendingDeviceTool, onSend: @escaping (String) -> Void) {
        self.pending = pending
        self.onSend = onSend
        _text = State(initialValue: pending.request.text)
    }

    public var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: DS.Spacing.md) {
                Text(L("nativeOmiAsksSendTo", pending.request.recipients.joined(separator: ", ")))
                    .font(DS.Typography.caption)
                    .foregroundStyle(DS.Palette.inkSecondary)
                TextEditor(text: $text)
                    .font(DS.Typography.body)
                    .scrollContentBackground(.hidden)
                    .padding(DS.Spacing.sm)
                    .background(DS.Palette.card, in: RoundedRectangle(cornerRadius: DS.Radius.card, style: .continuous))
                Text(L("nativeOmiAsksComposerHint"))
                    .font(DS.Typography.caption)
                    .foregroundStyle(DS.Palette.inkTertiary)
            }
            .padding(DS.Spacing.gutter)
            .background(DS.Palette.background)
            .navigationTitle(L("edit"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(L("cancel")) { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(L("nativeOmiAsksSend")) {
                        let message = text
                        dismiss()
                        onSend(message)
                    }
                    .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }
        .presentationDetents([.medium, .large])
    }
}
