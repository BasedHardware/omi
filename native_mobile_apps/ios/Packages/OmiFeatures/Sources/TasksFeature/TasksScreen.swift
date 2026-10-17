import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// Who does what: my tasks by due date, what others committed to, what is done. Subtasks indent
/// under their parent; long press for indent, export, share and select.
public struct TasksScreen: View {
    @Environment(TasksStore.self) private var store
    @Environment(ConversationsStore.self) private var conversations
    @Environment(AgentStore.self) private var agent
    @Environment(CapabilitiesStore.self) private var capabilities
    @Environment(RemindersSyncStore.self) private var reminders
    @Environment(\.openURL) private var openURL
    @State private var showsCompleted = false
    @State private var query = ""
    @State private var showsNewTask = DebugLaunch.flag("omiNewTask")
    @State private var editing: ActionItem?
    /// Tasks picked for a bulk action; `nil` outside selection mode.
    @State private var selection: Set<String>?
    @State private var sharing: SharedLink?
    @State private var showsGoals = false
    @State private var showsToday = DebugLaunch.flag("omiTasksDay")
    private let onHandOver: (ActionItem) -> Void

    public init(onHandOver: @escaping (ActionItem) -> Void) {
        self.onHandOver = onHandOver
    }

    public var body: some View {
        // The search row stays put above the list, at the same place as on Memories.
        VStack(spacing: 0) {
            header
                .padding(.horizontal, DS.Spacing.gutter)
                .padding(.bottom, DS.Spacing.xs)
            list
        }
    }

    private var list: some View {
        List {
            if store.phase == .loading, store.tasks.isEmpty {
                ForEach(0 ..< 5, id: \.self) { _ in SkeletonBlock(height: 52).listRowSeparator(.hidden) }
            }
            ForEach(store.sections(matching: query), id: \.bucket) { section in
                let indents = store.displayIndents(section.tasks)
                if section.bucket == .completed {
                    Section {
                        DisclosureGroup(isExpanded: $showsCompleted) {
                            ForEach(section.tasks) { row($0, indent: indents[$0.id] ?? 0) }
                        } label: {
                            Text(L("nativeDoneCount", String(section.tasks.count)))
                                .font(DS.Typography.sectionLabel)
                                .foregroundStyle(DS.Palette.inkSecondary)
                        }
                        .tint(DS.Palette.inkSecondary)
                        .listRowBackground(Color.clear)
                        .listRowSeparator(.hidden)
                    }
                } else {
                    Section {
                        ForEach(section.tasks) { task in
                            row(task, indent: indents[task.id] ?? 0)
                        }
                    } header: {
                        sectionHeader(section.bucket)
                    } footer: {
                        if section.bucket == .waitingOnOthers { Text(L("nativeWaitingOnOthersFooter")) }
                    }
                }
            }
        }
        // Text-first on the page: no grouped cards, a small gray label over each bucket.
        .listStyle(.grouped)
        .listSectionSpacing(DS.Spacing.sm)
        .contentMargins(.top, DS.Spacing.xs, for: .scrollContent)
        .scrollContentBackground(.hidden)
        .scrollDismissesKeyboard(.immediately)
        .animation(DS.Motion.standard, value: store.tasks)
        .safeAreaInset(edge: .bottom) {
            VStack(spacing: DS.Spacing.sm) {
                TaskToasts()
                if selection != nil {
                    TaskSelectionBar(selection: $selection, onShare: share)
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                }
            }
            .padding(.bottom, DS.Spacing.sm)
        }
        .animation(DS.Motion.standard, value: selection == nil)
        .sheet(isPresented: $showsNewTask) { TaskFormSheet(task: nil, onShare: share).presentationDetents([.medium]) }
        .sheet(item: $editing) { TaskFormSheet(task: $0, onShare: share, onHandOver: onHandOver).presentationDetents([.medium, .large]) }
        .navigationDestination(isPresented: $showsToday) { DayTasksScreen(date: .now) }
        .sheet(isPresented: $showsGoals) { NavigationStack { GoalsScreen() } }
        .sheet(item: $sharing) { ActivitySheet(items: [$0.url]).presentationDetents([.medium, .large]) }
        .sheet(item: Binding(get: { store.incomingShare }, set: { if $0 == nil { store.dismissShare() } })) { share in
            SharedTasksSheet(share: share).presentationDetents([.medium, .large])
        }
        .refreshable {
            await store.load()
            await reminders.syncIfDue()
        }
        .task { if store.phase == .idle { await store.load() } }
        .task { if conversations.phase == .idle { await conversations.load() } }
        .task {
            await capabilities.load()
            await reminders.refresh()
            await reminders.syncIfDue()
        }
        .task(id: store.tasks.count) { await agent.loadWorkstreams(for: store.tasks) }
        // Where each open task came from: its conversation's words, loaded once per conversation.
        .task(id: store.tasks.count) { await conversations.loadSources(for: store.tasks.filter { !$0.isCompleted }) }
        .overlay {
            if store.phase == .loaded, store.tasks.isEmpty {
                OmiEmptyState(
                    L("nativeNoTasks"), systemImage: "checklist", message: L("nativeNoTasksBody"),
                    actionTitle: L("addTask")
                ) { showsNewTask = true }
                    .padding(.top, 72)
                    .frame(maxHeight: .infinity, alignment: .top)
            }
        }
    }

    private var header: some View {
        HStack(spacing: DS.Spacing.sm) {
            OmiSearchField(L("nativeSearchTasks"), text: $query, clearLabel: L("cancel"))
            TasksHeaderMenu(selection: $selection) { showsGoals = true }
            CircleIconButton("plus") { showsNewTask = true }
                .accessibilityLabel(L("addTask"))
                .accessibilityIdentifier("tasks.add")
        }
    }

    /// A quiet gray label over each bucket. "Today" also opens the day's page (due and added that
    /// day, as Flutter's one-day tasks page); the "…" menu has it too.
    @ViewBuilder
    private func sectionHeader(_ bucket: TasksStore.Bucket) -> some View {
        let title = Text(title(bucket))
            .font(DS.Typography.sectionLabel)
            .foregroundStyle(DS.Palette.inkSecondary)
            .textCase(nil)
        if bucket == .today {
            Button { showsToday = true } label: { title }
                .buttonStyle(.plain)
                .accessibilityHint(L("nativeShowDay"))
                .accessibilityIdentifier("tasks.day.today")
        } else {
            title
        }
    }

    /// In selection mode a tap picks the row (with its subtasks); otherwise it edits the task.
    private func row(_ task: ActionItem, indent: Int) -> some View {
        HStack(spacing: DS.Spacing.sm) {
            if let selection {
                Image(systemName: selection.contains(task.id) ? "checkmark.circle.fill" : "circle")
                    .font(.title3)
                    .foregroundStyle(selection.contains(task.id) ? DS.Palette.agent : DS.Palette.inkTertiary)
                    .accessibilityHidden(true)
            }
            if indent > 0 {
                Capsule().fill(DS.Palette.hairline).frame(width: 2, height: 20).accessibilityHidden(true)
            }
            let source = conversations.source(of: task)
            TaskRow(
                task,
                source: source.map(\.displayTitle),
                sourceEmoji: source?.emoji,
                quote: conversations.quote(of: task),
                onOpenSource: source.map { conversation in { openURL(DeepLink.conversation(id: conversation.id).url) } },
                agentStatus: AgentTaskStatus(task: task, agent: agent),
                onToggle: { Task { await store.setCompleted(task.id, !task.isCompleted) } },
                // Omi's work opens where it has some; a new hand-over only for what Omi can do digitally.
                onHandOver: AgentTaskStatus(task: task, agent: agent) != nil || agent.canTakeOver(task) ? { onHandOver(task) } : nil
            )
            .allowsHitTesting(selection == nil)
        }
        .padding(.leading, CGFloat(indent) * DS.Spacing.xl)
        .contentShape(Rectangle())
        .listRowBackground(Color.clear)
        .listRowSeparator(.hidden)
        .listRowInsets(EdgeInsets(top: DS.Spacing.xs, leading: DS.Spacing.gutter, bottom: DS.Spacing.xs, trailing: DS.Spacing.gutter))
        .onTapGesture { tap(task) }
        .contextMenu {
            if selection == nil { TaskContextMenu(task: task, onEdit: { editing = task }, onShare: share, selection: $selection) }
        }
        .accessibilityAddTraits(selection?.contains(task.id) == true ? .isSelected : [])
    }

    private func tap(_ task: ActionItem) {
        guard var chosen = selection else {
            editing = task
            return
        }
        DSHaptics.selection()
        let group = [task.id] + store.descendants(of: task.id)
        if chosen.contains(task.id) { chosen.subtract(group) } else { chosen.formUnion(group) }
        selection = chosen
    }

    private func share(_ ids: [String]) {
        Task {
            if let url = await store.shareLink(for: ids) { sharing = SharedLink(url: url) }
        }
    }

    private func title(_ bucket: TasksStore.Bucket) -> String {
        switch bucket {
        case .overdue: L("nativeOverdue")
        case .today: L("today")
        case .upcoming: L("nativeUpcoming")
        case .someday: L("nativeSomeday")
        case .waitingOnOthers: L("nativeWaitingOnOthers")
        case .completed: L("nativeDone")
        }
    }
}

/// A share link waiting for the system share sheet.
struct SharedLink: Identifiable {
    let id = UUID()
    let url: URL
}
