import OmiKit
import SwiftUI

// Tasks page, ported from `react-native/src/pages/Tasks.tsx`: search over
// loaded tasks, Today/Tomorrow/Later groups with counts, completion toggles,
// the inline description editor, Load-more pagination, and the ReadStatus
// footer. Writes go through the store's service-binding route; missing
// authority leaves tasks read-only.

public struct TasksPage: View {
    public var embedded: Bool = false

    @EnvironmentObject private var store: AppStore
    @State private var query: String = ""
    @State private var selectedId: String?
    @State private var nowMs: Int64 = Int64(Date().timeIntervalSince1970 * 1000)

    public init(embedded: Bool = false) {
        self.embedded = embedded
    }

    private var writesAvailable: Bool {
        store.tasksRead?.accountEpoch != nil
    }

    private var tasks: [TaskProjection] {
        store.tasksRead?.items ?? []
    }

    private var filtered: [TaskProjection] {
        tasks.filter { matchesSearchQuery($0.title, query) }
    }

    private var groups: [(label: String, tasks: [TaskProjection])] {
        [
            (label: "Today", tasks: filtered.filter { taskBucket($0) == TaskGroup.today }),
            (label: "Tomorrow", tasks: filtered.filter { taskBucket($0) == TaskGroup.tomorrow }),
            (label: "Later", tasks: filtered.filter { taskBucket($0) == TaskGroup.later }),
        ]
    }

    private func taskBucket(_ task: TaskProjection) -> TaskGroup {
        taskGroup(dueAt: task.dueAt, nowMilliseconds: nowMs)
    }

    private var error: String? {
        guard let read = store.tasksRead else { return nil }
        // Task read failures surface through the merged outcomes error copy.
        if case .error(let message) = store.outcomes?.tasks { return message }
        _ = read
        return nil
    }

    private var loading: Bool { store.readsLoading && store.tasksRead == nil }

    private var filtering: Bool {
        !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if !embedded {
                Text("Tasks")
                    .font(TypeStyle(size: 22, lineHeight: 28, weight: .semibold).font)
                    .foregroundColor(Color.white)
                    .padding(.bottom, 18)
            }
            searchBox
                .padding(.bottom, 14)
            TaskMutationStatusView(
                writesAvailable: writesAvailable, mutationError: nil,
                onRetry: nil, onDismiss: nil
            )
            if loading {
                VStack(spacing: 12) {
                    ProgressView().tint(OmiColor.hex(0x888888))
                    Text("Loading tasks…")
                        .font(Typography.caption.font)
                        .foregroundColor(Palette.textMuted)
                }
                .frame(maxWidth: .infinity)
                .padding(24)
            } else if let error {
                VStack(spacing: 8) {
                    Text("Tasks unavailable")
                        .font(TypeStyle(size: 16, lineHeight: 22, weight: .semibold).font)
                        .foregroundColor(Palette.text)
                    Text(error)
                        .font(Typography.caption.font)
                        .foregroundColor(Palette.textMuted)
                        .accessibilityLabel(error)
                }
                .frame(maxWidth: .infinity)
                .padding(24)
            } else if filtered.isEmpty {
                VStack(spacing: 6) {
                    Text(filtering ? "No loaded tasks match." : "No tasks yet.")
                        .font(TypeStyle(size: 16, lineHeight: 22, weight: .semibold).font)
                        .foregroundColor(Palette.text)
                    if filtering {
                        Text("Search covers task descriptions already loaded on this device.")
                            .font(Typography.caption.font)
                            .foregroundColor(Palette.textMuted)
                    }
                }
                .frame(maxWidth: .infinity)
                .padding(24)
            } else {
                list
            }
            pagination
            shortcuts
        }
        .onAppear { nowMs = Int64(Date().timeIntervalSince1970 * 1000) }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var searchBox: some View {
        HStack(spacing: Space.sm) {
            KitIcon(.search, size: 17, color: OmiColor.hex(0x777777))
            TextField("Search loaded tasks", text: $query)
                .font(Typography.body.font)
                .foregroundColor(Color.white)
                .frame(minHeight: 44)
                .accessibilityLabel("Search loaded tasks")
        }
        .padding(.horizontal, Space.md)
        .background(Palette.input)
        .overlay(
            RoundedRectangle(cornerRadius: Radius.md)
                .strokeBorder(Palette.line, lineWidth: Borders.width)
        )
        .clipShape(RoundedRectangle(cornerRadius: Radius.md))
    }

    private var list: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                ForEach(groups, id: \.label) { group in
                    if !group.tasks.isEmpty {
                        VStack(alignment: .leading, spacing: 7) {
                            HStack {
                                Text(group.label)
                                    .font(TypeStyle(size: 15, lineHeight: 20, weight: .semibold).font)
                                    .foregroundColor(Color.white)
                                Spacer()
                                Text("\(group.tasks.count)")
                                    .font(TypeStyle(size: 11, lineHeight: 14, weight: .regular).font)
                                    .foregroundColor(OmiColor.hex(0x737373))
                            }
                            ForEach(group.tasks) { task in
                                TaskCard(
                                    task: task,
                                    selected: task.id == selectedId,
                                    writesAvailable: writesAvailable,
                                    busy: false,
                                    onToggle: { id in
                                        if let projection = tasks.first(where: { $0.id == id }) {
                                            Task { await store.toggleTask(projection) }
                                        }
                                    },
                                    onEdit: { id, description in
                                        if let projection = tasks.first(where: { $0.id == id }) {
                                            Task {
                                                await store.renameTask(
                                                    projection, title: description
                                                )
                                            }
                                        }
                                    },
                                    onSelect: { id in
                                        selectedId = selectedId == id ? nil : id
                                    },
                                    onCloseEditor: { selectedId = nil }
                                )
                            }
                        }
                    }
                }
                if let read = store.tasksRead {
                    ReadStatusView(label: "Tasks", page: read.page)
                }
            }
            .padding(.top, 18)
            .padding(.bottom, 78)
        }
    }

    @ViewBuilder
    private var pagination: some View {
        if let read = store.tasksRead, read.page.hasMore {
            Button(action: { Task { await store.loadOlderTasks() } }) {
                Text("Load more tasks")
                    .font(Typography.caption.font)
                    .foregroundColor(Palette.textMuted)
                    .frame(maxWidth: .infinity, alignment: .leading).frame(minHeight: 44)
            }
            .buttonStyle(KitPressableStyle())
            .accessibilityLabel("Load more tasks")
        }
    }

    private var shortcuts: some View {
        HStack(spacing: Space.lg) {
            Text("Tab · Focus")
                .font(TypeStyle(size: 11, lineHeight: 14, weight: .semibold).font)
                .foregroundColor(OmiColor.hex(0x858585))
            Text("Enter · Select")
                .font(TypeStyle(size: 11, lineHeight: 14, weight: .semibold).font)
                .foregroundColor(OmiColor.hex(0x858585))
        }
        .accessibilityLabel("Task keyboard shortcuts")
    }
}

public struct TaskCard: View {
    public let task: TaskProjection
    public let selected: Bool
    public let writesAvailable: Bool
    public let busy: Bool
    public let onToggle: (String) -> Void
    public let onEdit: (String, String) -> Void
    public let onSelect: (String) -> Void
    public let onCloseEditor: () -> Void

    public init(
        task: TaskProjection, selected: Bool, writesAvailable: Bool, busy: Bool,
        onToggle: @escaping (String) -> Void, onEdit: @escaping (String, String) -> Void,
        onSelect: @escaping (String) -> Void, onCloseEditor: @escaping () -> Void
    ) {
        self.task = task
        self.selected = selected
        self.writesAvailable = writesAvailable
        self.busy = busy
        self.onToggle = onToggle
        self.onEdit = onEdit
        self.onSelect = onSelect
        self.onCloseEditor = onCloseEditor
    }

    private var dueCopy: String {
        if task.completed {
            return "Completed · \(KitFormat.taskDue(task.dueAt))"
        }
        return KitFormat.taskDue(task.dueAt)
    }

    private var toggleDisabled: Bool { !writesAvailable || busy }

    public var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .top, spacing: 0) {
                Button(action: { onToggle(task.id) }) {
                    ZStack {
                        RoundedRectangle(cornerRadius: 5)
                            .strokeBorder(
                                task.completed
                                    ? OmiColor.hex(0xD8D8D8) : Palette.lineStrong,
                                lineWidth: 1
                            )
                        if task.completed {
                            RoundedRectangle(cornerRadius: 5)
                                .fill(OmiColor.hex(0xD8D8D8))
                            Text("✓")
                                .font(TypeStyle(size: 12, lineHeight: 14, weight: .heavy).font)
                                .foregroundColor(OmiColor.hex(0x1A1A1A))
                        }
                    }
                    .frame(width: 20, height: 20)
                    .frame(minWidth: 44, minHeight: 44)
                }
                .buttonStyle(KitPressableStyle())
                .disabled(toggleDisabled)
                .opacity(toggleDisabled ? Opacity.disabled : 1)
                .accessibilityLabel(toggleAccessibility)
                .accessibilityAddTraits(task.completed ? [.isSelected] : [])
                Button(action: { onSelect(task.id) }) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(task.title)
                            .font(Typography.body.font)
                            .foregroundColor(task.completed ? OmiColor.hex(0x777777) : OmiColor.hex(0xEEEEEE))
                            .strikethrough(task.completed)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        Text(dueCopy)
                            .font(TypeStyle(size: 11, lineHeight: 14, weight: .regular).font)
                            .foregroundColor(OmiColor.hex(0x707070))
                    }
                    .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                    .padding(.leading, Space.sm)
                }
                .buttonStyle(KitPressableStyle())
                .accessibilityLabel("\(task.completed ? "Completed" : "Open") task: \(task.title)")
                .accessibilityAddTraits(selected ? [.isSelected] : [])
            }
            if selected && writesAvailable {
                TaskEditorView(
                    taskId: task.id, title: task.title, busy: busy,
                    onSave: onEdit, onClose: onCloseEditor
                )
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: Radius.lg)
                .fill(selected ? OmiColor.hex(0x292929) : Palette.surface)
        )
        .overlay(
            RoundedRectangle(cornerRadius: Radius.lg)
                .strokeBorder(
                    selected ? OmiColor.hex(0x686868) : Palette.line, lineWidth: Borders.width
                )
        )
    }

    private var toggleAccessibility: String {
        let state: String
        if writesAvailable {
            state = task.completed ? "Reopen" : "Complete"
        } else {
            state = task.completed ? "Completed" : "Open"
        }
        return "\(state) \(task.title)"
    }
}
