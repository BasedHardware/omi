import OmiDesign
import OmiService
import SwiftUI

/// "Task deleted · Undo" while a task delete waits out its undo window, then any short outcome
/// (exported, shared tasks added, …) for a few seconds.
public struct TaskToasts: View {
    @Environment(TasksStore.self) private var tasks

    public init() {}

    public var body: some View {
        Group {
            if let pending = tasks.pendingDeletion {
                OmiToast(
                    text: pending.ids.count == 1 ? L("actionItemDeleted") : L("nativeTasksDeleted", String(pending.ids.count)),
                    systemImage: "trash",
                    actionTitle: L("undo")
                ) {
                    DSHaptics.tap()
                    withAnimation(DS.Motion.standard) { tasks.undoDelete() }
                }
                .id(pending.ids)
                .transition(.move(edge: .bottom).combined(with: .opacity))
            } else if let notice = tasks.notice {
                OmiToast(text: Self.text(notice.kind), systemImage: Self.symbol(notice.kind))
                    .id(notice.id)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                    .task(id: notice.id) {
                        try? await Task.sleep(for: .seconds(3))
                        withAnimation(DS.Motion.standard) { tasks.clearNotice(notice) }
                    }
            }
        }
        .animation(DS.Motion.standard, value: tasks.pendingDeletion)
        .animation(DS.Motion.standard, value: tasks.notice)
    }

    static func text(_ kind: TaskNotice.Kind) -> String {
        switch kind {
        case let .exported(app, count, 0): L("nativeExportedCount", appName(app), String(count))
        case let .exported(app, count, failed): L("nativeExportedSomeFailed", appName(app), String(count), String(failed))
        case .alreadyExported: L("nativeAlreadyExported")
        case let .exportFailed(app): L("nativeExportFailed", appName(app))
        case let .sharedAdded(count): L("nativeSharedTasksAdded", String(count))
        case .shareExpired: L("sharedTasksLinkExpired")
        case .shareFailed: L("sharedTasksAcceptFailed")
        case .shareLinkFailed: L("nativeShareLinkFailed")
        }
    }

    static func symbol(_ kind: TaskNotice.Kind) -> String {
        switch kind {
        case .exported, .alreadyExported: "square.and.arrow.up"
        case .sharedAdded: "checkmark.circle"
        default: "exclamationmark.circle"
        }
    }

    /// Display name of a task app by backend key.
    public static func appName(_ key: String) -> String {
        key == TasksStore.appleReminders ? L("nativeRemindersName") : CapabilitiesList.name(key)
    }
}

/// "Goal deleted · Undo" while a goal delete waits out its undo window.
public struct GoalUndoToast: View {
    @Environment(GoalsStore.self) private var goals

    public init() {}

    public var body: some View {
        Group {
            if let pending = goals.pendingDeletion {
                OmiToast(text: L("goalDeleted"), systemImage: "trash", actionTitle: L("undo")) {
                    DSHaptics.tap()
                    withAnimation(DS.Motion.standard) { goals.undoDelete() }
                }
                .id(pending.id)
                .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .animation(DS.Motion.standard, value: goals.pendingDeletion)
    }
}
