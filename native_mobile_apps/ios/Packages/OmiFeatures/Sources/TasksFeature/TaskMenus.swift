import OmiComponents
import OmiCore
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// The task apps the user connected (Capabilities) plus Reminders while it syncs, by backend key.
@MainActor
func exportTargets(_ capabilities: CapabilitiesStore, _ reminders: RemindersSyncStore) -> [String] {
    let apps = capabilities.integrations.filter { $0.kind == .taskApp && $0.isConnected }.map(\.id)
    return apps + (reminders.isEnabled ? [TasksStore.appleReminders] : [])
}

/// "Export to …" for the given tasks: one entry per connected app; a hint when none is connected.
struct ExportMenu: View {
    @Environment(TasksStore.self) private var store
    @Environment(CapabilitiesStore.self) private var capabilities
    @Environment(RemindersSyncStore.self) private var reminders
    let title: String
    let ids: () -> [String]
    var all = false
    var onDone: () -> Void = {}

    var body: some View {
        let targets = exportTargets(capabilities, reminders)
        if targets.isEmpty {
            Button {} label: { Label(L("connectTaskAppToExport"), systemImage: "square.and.arrow.up") }.disabled(true)
        } else if targets.count == 1 {
            button(targets[0], label: title.isEmpty ? L("nativeExportTo", TaskToasts.appName(targets[0])) : title)
        } else {
            Menu {
                ForEach(targets, id: \.self) { button($0, label: TaskToasts.appName($0)) }
            } label: {
                Label(title.isEmpty ? L("exportButton") : title, systemImage: "square.and.arrow.up")
            }
        }
    }

    private func button(_ app: String, label: String) -> some View {
        Button {
            let chosen = ids()
            Task {
                if all { await store.exportAllOpen(to: app) } else { await store.export(chosen, to: app) }
            }
            onDone()
        } label: {
            Label(label, systemImage: "square.and.arrow.up")
        }
    }
}

/// Long press on a task: edit, done, indent / outdent, export, share link, select, delete.
struct TaskContextMenu: View {
    @Environment(TasksStore.self) private var store
    let task: ActionItem
    let onEdit: () -> Void
    let onShare: ([String]) -> Void
    @Binding var selection: Set<String>?

    var body: some View {
        Button(action: onEdit) { Label(L("editActionItem"), systemImage: "pencil") }
        Button {
            Task { await store.setCompleted(task.id, !task.isCompleted) }
        } label: {
            if task.isCompleted {
                Label(L("nativeMarkOpen"), systemImage: "circle")
            } else {
                Label(L("nativeMarkDone"), systemImage: "checkmark.circle")
            }
        }
        if store.canIndent(task.id) {
            Button { Task { await store.indent(task.id) } } label: { Label(L("indentTask"), systemImage: "increase.indent") }
        }
        if store.canOutdent(task.id) {
            Button { Task { await store.outdent(task.id) } } label: { Label(L("outdentTask"), systemImage: "decrease.indent") }
        }
        if !task.isExported, task.owner != .other {
            ExportMenu(title: "", ids: { [task.id] })
        }
        Button { onShare([task.id]) } label: { Label(L("nativeShareLink"), systemImage: "link") }
        Button {
            selection = Set([task.id] + store.descendants(of: task.id))
        } label: {
            Label(L("selectOption"), systemImage: "checkmark.circle")
        }
        Button(role: .destructive) { store.deleteWithUndo([task.id]) } label: { Label(L("delete"), systemImage: "trash") }
    }
}

/// The Tasks header's "…": select, export all open, clear completed, Reminders sync, goals.
struct TasksHeaderMenu: View {
    @Environment(TasksStore.self) private var store
    @Environment(RemindersSyncStore.self) private var reminders
    @Binding var selection: Set<String>?
    let onGoals: () -> Void

    var body: some View {
        Menu {
            Button { selection = [] } label: { Label(L("selectOption"), systemImage: "checkmark.circle") }
                .disabled(store.tasks.isEmpty)
            ExportMenu(title: L("nativeExportAllOpen"), ids: { [] }, all: true)
            Button(role: .destructive) { store.clearCompleted() } label: { Label(L("nativeClearCompleted"), systemImage: "trash") }
                .disabled(!store.tasks.contains(where: \.isCompleted))
            Section {
                Toggle(isOn: Binding(get: { reminders.isEnabled }, set: { on in Task { await reminders.setEnabled(on) } })) {
                    Label(L("nativeSyncWithReminders"), systemImage: "list.bullet.rectangle")
                }
                if reminders.accessDenied {
                    Text(L("nativeRemindersAccessDenied"))
                }
            }
            Section {
                Button(action: onGoals) { Label(L("goals"), systemImage: "flag") }
            }
        } label: {
            OmiCircleIcon("ellipsis")
        }
        .accessibilityLabel(L("moreOptions"))
        .accessibilityIdentifier("tasks.menu")
    }
}
