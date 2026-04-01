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
        VStack(alignment: .leading, spacing: 10) {
            // Header
            HStack(alignment: .center) {
                Text("Tasks")
                    .scaledFont(size: 15, weight: .semibold)
                    .foregroundColor(NootoColors.textPrimary)
                if totalTaskCount > 0 {
                    Text("\(totalTaskCount)")
                        .scaledFont(size: 11, weight: .medium)
                        .foregroundColor(NootoColors.textTertiary)
                }
                Spacer()
                Button(action: {
                    NotificationCenter.default.post(name: .navigateToTasks, object: nil)
                }) {
                    Text("View all")
                        .scaledFont(size: 12, weight: .medium)
                        .foregroundColor(NootoColors.textTertiary)
                }
                .buttonStyle(.plain)
            }

            if totalTaskCount == 0 {
                VStack(spacing: 6) {
                    Image(systemName: "checkmark.circle")
                        .scaledFont(size: 24)
                        .foregroundColor(NootoColors.textQuaternary)
                    Text("No incomplete tasks")
                        .scaledFont(size: 12)
                        .foregroundColor(NootoColors.textTertiary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                let allTasks = (combinedTodayTasks + recentTasks).prefix(4)

                VStack(spacing: 2) {
                    ForEach(Array(allTasks)) { task in
                        TaskRowView(
                            task: task,
                            onToggle: { onToggleCompletion(task) }
                        )
                    }
                }
            }
        }
        .padding(14)
        .frame(maxHeight: .infinity, alignment: .topLeading)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(NootoColors.backgroundSecondary)
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(NootoColors.border.opacity(0.4), lineWidth: 1)
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
        HStack(spacing: 8) {
            Button(action: {
                guard !isToggling else { return }
                isToggling = true
                onToggle()
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                    isToggling = false
                }
            }) {
                Image(systemName: task.completed ? "checkmark.circle.fill" : "circle")
                    .scaledFont(size: 15)
                    .foregroundColor(task.completed ? NootoColors.brandPrimary : NootoColors.textTertiary)
            }
            .buttonStyle(.plain)
            .disabled(isToggling)
            .opacity(isToggling ? 0.5 : 1)

            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(task.description)
                        .scaledFont(size: 13)
                        .foregroundColor(task.completed ? NootoColors.textTertiary : NootoColors.textPrimary)
                        .strikethrough(task.completed)
                        .lineLimit(2)

                    if task.recurrenceRule == "daily" {
                        Image(systemName: "repeat")
                            .scaledFont(size: 10)
                            .foregroundColor(NootoColors.brandPrimary.opacity(0.7))
                    }
                }

                if task.recurrenceRule == "daily" {
                    Text("Daily")
                        .scaledFont(size: 10, weight: .medium)
                        .foregroundColor(NootoColors.brandPrimary.opacity(0.8))
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(
                            RoundedRectangle(cornerRadius: 4)
                                .fill(NootoColors.brandPrimary.opacity(0.1))
                        )
                }
            }

            Spacer()
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 10)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(task.completed ? NootoColors.backgroundQuaternary.opacity(0.3) : Color.clear)
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
    .background(NootoColors.backgroundPrimary)
}
