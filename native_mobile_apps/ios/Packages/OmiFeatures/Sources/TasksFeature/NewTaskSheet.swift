import OmiCore
import SwiftUI

/// "Add task" from outside the task list (the Home Screen quick action): the same form as the
/// list's add button.
public struct NewTaskSheet: View {
    public init() {}

    public var body: some View {
        TaskFormSheet(task: nil).presentationDetents([.medium])
    }
}

/// One task from Home (a Needs you card, a task link): the same detail as tapping it in the list,
/// with where it came from (the conversation opens from there).
public struct TaskDetailSheet: View {
    let task: ActionItem
    let onHandOver: ((ActionItem) -> Void)?

    public init(task: ActionItem, onHandOver: ((ActionItem) -> Void)? = nil) {
        self.task = task
        self.onHandOver = onHandOver
    }

    public var body: some View {
        TaskFormSheet(task: task, onHandOver: onHandOver).presentationDetents([.medium, .large])
    }
}
