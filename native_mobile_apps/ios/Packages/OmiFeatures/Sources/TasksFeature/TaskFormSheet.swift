import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// Write a task down by hand, or one task's own screen: what and by when (editable), where it
/// came from (the conversation opens, with the words it was based on), and every answer: Omi
/// takes over (where Omi can), done, later, not a task, share, delete (with Undo).
/// `task == nil` creates.
struct TaskFormSheet: View {
    @Environment(TasksStore.self) private var store
    @Environment(ConversationsStore.self) private var conversations
    @Environment(AgentStore.self) private var agent
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openURL) private var openURL
    let task: ActionItem?
    /// Opens the share sheet with a link to these tasks.
    var onShare: (([String]) -> Void)?
    /// "Omi takes over": the hand-over sheet, once this one is gone.
    var onHandOver: ((ActionItem) -> Void)?
    @State private var text = ""
    @State private var hasDue = false
    @State private var due = Calendar.current.date(byAdding: .day, value: 1, to: .now) ?? .now
    @State private var isSaving = false
    @FocusState private var focused: Bool

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField(L("nativeTaskPlaceholder"), text: $text, axis: .vertical)
                        .lineLimit(1 ... 4)
                        .focused($focused)
                    Toggle(L("addDueDate"), isOn: $hasDue.animation())
                    if hasDue {
                        // An overdue task keeps its date selectable.
                        DatePicker(L("dueDate"), selection: $due, in: min(task?.dueAt ?? .now, .now)...)
                    }
                    if let error = store.lastError {
                        Text(error).font(DS.Typography.caption).foregroundStyle(DS.Palette.live)
                    }
                } header: {
                    if let task { status(task) }
                }
                if let task, let conversation = conversations.source(of: task) {
                    source(task, conversation)
                }
                if let task { answers(current(task)) }
                if let task {
                    Section {
                        if let onShare {
                            Button(L("nativeShareLink")) {
                                dismiss()
                                onShare([task.id])
                            }
                        }
                        Button(L("deleteActionItem"), role: .destructive) {
                            dismiss()
                            store.deleteWithUndo([task.id])
                        }
                        .accessibilityIdentifier("tasks.delete")
                    }
                }
            }
            .scrollContentBackground(.hidden)
            .background(DS.Palette.background)
            .navigationTitle(task == nil ? L("newTask") : L("nativeTaskTitle"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(L("cancel")) { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button(L("save"), action: save)
                        .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSaving || !hasChanges)
                        .accessibilityIdentifier("tasks.save")
                }
            }
            .onAppear {
                if let task {
                    text = task.description
                    if let dueAt = task.dueAt {
                        hasDue = true
                        due = dueAt
                    }
                } else {
                    focused = true
                }
            }
        }
    }

    /// The task as the store has it now (ticked off from here, the sheet stays open).
    private func current(_ task: ActionItem) -> ActionItem {
        store.tasks.first { $0.id == task.id } ?? task
    }

    /// "Done", "Overdue · Due Wed, 7 Oct", "Due today", or "On Home again tomorrow".
    private func status(_ task: ActionItem) -> some View {
        let task = current(task)
        var parts: [String] = []
        if task.isCompleted {
            parts.append(L("nativeForYouMarkDone"))
        } else if let dueAt = task.dueAt {
            if dueAt < Calendar.current.startOfDay(for: .now) { parts.append(L("nativeOverdue")) }
            parts.append(L("taskDueDate", Formatting.relativeDay(dueAt)))
        }
        if !task.isCompleted, store.snoozes[task.id].map({ $0 > .now }) == true { parts.append(L("nativeTaskOnHomeTomorrow")) }
        return Text(parts.joined(separator: " · ")).textCase(nil)
    }

    /// Every answer to the task, the one Omi can take first.
    private func answers(_ task: ActionItem) -> some View {
        Section {
            if let onHandOver, !task.isCompleted, agent.canTakeOver(task) {
                Button {
                    dismiss()
                    // After this sheet is gone: two sheets cannot overlap.
                    Task {
                        try? await Task.sleep(for: .milliseconds(450))
                        onHandOver(task)
                    }
                } label: { Label(L("nativeOmiTakesOver"), systemImage: "sparkles") }
                    .accessibilityIdentifier("task.detail.takeOver")
            }
            Button {
                DSHaptics.selection()
                Task { await store.setCompleted(task.id, !task.isCompleted) }
            } label: {
                Label(
                    task.isCompleted ? L("nativeMarkNotDone") : L("nativeMarkDone"),
                    systemImage: task.isCompleted ? "arrow.uturn.backward.circle" : "checkmark.circle"
                )
            }
            .accessibilityIdentifier("task.detail.done")
            if !task.isCompleted {
                Button {
                    DSHaptics.selection()
                    store.snooze([task.id])
                    dismiss()
                } label: { Label(L("nativeForYouLater"), systemImage: "clock") }
                    .accessibilityIdentifier("task.detail.later")
                Button(role: .destructive) {
                    dismiss()
                    Task { await store.markNotTask([task.id]) }
                } label: { Label(L("nativeNotATask"), systemImage: "xmark.circle") }
                    .accessibilityIdentifier("task.detail.notTask")
            }
        } footer: {
            if !task.isCompleted { Text(L("nativeTaskAnswersFooter")) }
        }
        .tint(DS.Palette.ink)
    }

    /// "From": the conversation it came from (opens it) and, in full, the words it was based on.
    private func source(_ task: ActionItem, _ conversation: Conversation) -> some View {
        Section(L("nativeTaskFrom")) {
            Button {
                dismiss()
                openURL(DeepLink.conversation(id: conversation.id).url)
            } label: {
                HStack(spacing: DS.Spacing.md) {
                    Text(conversation.emoji ?? "💬").font(.system(size: 22)).accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(conversation.displayTitle).font(DS.Typography.cardTitle).foregroundStyle(DS.Palette.ink)
                        Text(conversation.date.formatted(date: .abbreviated, time: .shortened))
                            .font(DS.Typography.caption)
                            .foregroundStyle(DS.Palette.inkSecondary)
                    }
                }
            }
            .accessibilityIdentifier("task.detail.source")
            if let quote = conversations.quote(of: task) {
                Text(verbatim: "\u{201C}\(quote)\u{201D}")
                    .font(DS.Typography.callout)
                    .foregroundStyle(DS.Palette.inkSecondary)
                    .textSelection(.enabled)
            }
        }
        .task { await conversations.loadSources(for: [task]) }
    }

    private var dueAt: Date? {
        hasDue ? due : nil
    }

    private var hasChanges: Bool {
        guard let task else { return true }
        return text.trimmingCharacters(in: .whitespacesAndNewlines) != task.description || dueAt != task.dueAt
    }

    private func save() {
        isSaving = true
        Task {
            let saved = if let task {
                await store.update(task.id, description: text, dueAt: dueAt)
            } else {
                await store.add(text, dueAt: dueAt)
            }
            if saved {
                DSHaptics.success()
                dismiss()
            }
            isSaving = false
        }
    }
}
