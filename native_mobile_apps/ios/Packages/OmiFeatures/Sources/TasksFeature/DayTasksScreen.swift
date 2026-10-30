import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// One day's tasks (Flutter `day_tasks_page.dart`): due that day and added that day, with the
/// previous / next day in the toolbar (never past today, as in Flutter).
public struct DayTasksScreen: View {
    @Environment(TasksStore.self) private var store
    @Environment(ConversationsStore.self) private var conversations
    @Environment(\.openURL) private var openURL
    @State private var day: Date
    @State private var editing: ActionItem?

    public init(date: Date) {
        _day = State(initialValue: Calendar.current.startOfDay(for: date))
    }

    public var body: some View {
        let tasks = store.day(day)
        List {
            if !tasks.due.isEmpty {
                Section { ForEach(tasks.due) { row($0) } } header: { label(L("nativeDueThatDay")) }
            }
            if !tasks.added.isEmpty {
                Section { ForEach(tasks.added) { row($0) } } header: { label(L("nativeAddedThatDay")) }
            }
        }
        .listStyle(.grouped)
        .listSectionSpacing(DS.Spacing.sm)
        .scrollContentBackground(.hidden)
        .background(DS.Palette.background)
        .overlay {
            if tasks.due.isEmpty, tasks.added.isEmpty {
                OmiEmptyState(L("noTasksOnDate", day.formatted(date: .abbreviated, time: .omitted)), systemImage: "checklist")
            }
        }
        .safeAreaInset(edge: .bottom) { TaskToasts().padding(.bottom, DS.Spacing.sm) }
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Button { move(by: -1) } label: { Image(systemName: "chevron.left") }
                    .accessibilityLabel(L("previousDay"))
                Button { move(by: 1) } label: { Image(systemName: "chevron.right") }
                    .accessibilityLabel(L("nextDay"))
                    .disabled(Calendar.current.isDateInToday(day))
            }
        }
        .sheet(item: $editing) { TaskFormSheet(task: $0).presentationDetents([.medium, .large]) }
        .refreshable { await store.load() }
        // The source line needs the conversations (this page can open before Home loaded them).
        .task(id: tasks.due.map(\.id) + tasks.added.map(\.id)) {
            if conversations.phase == .idle { await conversations.load() }
            await conversations.loadSources(for: tasks.due + tasks.added)
        }
        .animation(DS.Motion.standard, value: day)
        .omiPage(Formatting.relativeDay(day))
    }

    private func label(_ title: String) -> some View {
        Text(title).font(DS.Typography.sectionLabel).foregroundStyle(DS.Palette.inkSecondary).textCase(nil)
    }

    private func row(_ task: ActionItem) -> some View {
        let source = conversations.source(of: task)
        return TaskRow(
            task,
            source: source.map(\.displayTitle),
            sourceEmoji: source?.emoji,
            quote: conversations.quote(of: task),
            onOpenSource: source.map { conversation in { openURL(DeepLink.conversation(id: conversation.id).url) } },
            onToggle: { Task { await store.setCompleted(task.id, !task.isCompleted) } }
        )
        .contentShape(Rectangle())
        .listRowBackground(Color.clear)
        .listRowSeparator(.hidden)
        .onTapGesture { editing = task }
        .swipeActions {
            Button(role: .destructive) { store.deleteWithUndo([task.id]) } label: { Label(L("delete"), systemImage: "trash") }
        }
    }

    private func move(by days: Int) {
        DSHaptics.selection()
        day = Calendar.current.date(byAdding: .day, value: days, to: day) ?? day
    }
}
