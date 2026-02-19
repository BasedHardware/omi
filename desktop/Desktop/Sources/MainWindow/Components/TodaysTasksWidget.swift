import SwiftUI

struct TasksWidget: View {
    let overdueTasks: [TaskActionItem]
    let todaysTasks: [TaskActionItem]
    let recentTasks: [TaskActionItem]
    let onToggleCompletion: (TaskActionItem) -> Void

    private var totalTaskCount: Int {
        overdueTasks.count + todaysTasks.count + recentTasks.count
    }

    /// Combine overdue + today tasks into one "Today" section (like Flutter)
    private var combinedTodayTasks: [TaskActionItem] {
        // Sort: overdue first (by due date), then today's tasks (by due date)
        let sorted = (overdueTasks + todaysTasks).sorted { a, b in
            guard let aDate = a.dueAt, let bDate = b.dueAt else { return a.dueAt != nil }
            return aDate < bDate
        }
        return sorted
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header
            Text("Tasks")
                .scaledFont(size: 16, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

            if totalTaskCount == 0 {
                // Empty state
                VStack(spacing: 8) {
                    Image(systemName: "checkmark.circle")
                        .scaledFont(size: 28)
                        .foregroundColor(OmiColors.textQuaternary)
                    Text("No incomplete tasks")
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textTertiary)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 20)
            } else {
                let allTasks = (combinedTodayTasks + recentTasks).prefix(3)

                VStack(spacing: 6) {
                    ForEach(Array(allTasks)) { task in
                        TaskRowView(
                            task: task,
                            onToggle: { onToggleCompletion(task) }
                        )
                    }
                }

                // View all link
                Button(action: {
                    // Navigate to Tasks tab
                    NotificationCenter.default.post(
                        name: .navigateToTasks,
                        object: nil
                    )
                }) {
                    HStack {
                        Spacer()
                        Text("View all tasks")
                            .scaledFont(size: 12, weight: .medium)
                            .foregroundColor(OmiColors.textSecondary)
                        Image(systemName: "chevron.right")
                            .scaledFont(size: 10)
                            .foregroundColor(OmiColors.textSecondary)
                        Spacer()
                    }
                }
                .buttonStyle(.plain)
                .padding(.top, 4)
            }
        }
        .padding(20)
        .frame(maxHeight: .infinity, alignment: .topLeading)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(OmiColors.backgroundTertiary.opacity(0.5))
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .stroke(OmiColors.backgroundQuaternary.opacity(0.5), lineWidth: 1)
                )
        )
    }
}

// MARK: - Task Row View

struct TaskRowView: View {
    let task: TaskActionItem
    let onToggle: () -> Void

    @State private var isToggling = false

    var body: some View {
        HStack(spacing: 10) {
            // Checkbox
            Button(action: {
                guard !isToggling else { return }
                isToggling = true
                onToggle()
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                    isToggling = false
                }
            }) {
                Image(systemName: task.completed ? "checkmark.circle.fill" : "circle")
                    .scaledFont(size: 18)
                    .foregroundColor(task.completed ? OmiColors.textPrimary : OmiColors.textTertiary)
            }
            .buttonStyle(.plain)
            .disabled(isToggling)
            .opacity(isToggling ? 0.5 : 1)

            Text(task.description)
                .scaledFont(size: 13)
                .foregroundColor(task.completed ? OmiColors.textTertiary : OmiColors.textPrimary)
                .strikethrough(task.completed)
                .lineLimit(2)

            Spacer()
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 10)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(task.completed ? OmiColors.backgroundQuaternary.opacity(0.3) : Color.clear)
        )
    }
}

#Preview {
    TasksWidget(
        overdueTasks: [],
        todaysTasks: [],
        recentTasks: [],
        onToggleCompletion: { _ in }
    )
    .frame(width: 350)
    .padding()
    .background(OmiColors.backgroundPrimary)
}
