import OmiTheme
import SwiftUI

/// Follow-ups tab: real backend action items (TasksStore) with one-tap complete,
/// a done section, and the task-export destinations rendered as connect-style
/// stub rows (those integrations don't exist upstream — see plan deviation).
struct SBFollowUpsContainer: View {
  @Environment(\.sbTheme) private var sb
  @ObservedObject private var tasks = TasksStore.shared
  var onOpenSettings: () -> Void

  // Task-export destinations from the design copy. None are implemented upstream;
  // shown as connect-style rows so the surface is honest, not fake toggles.
  private let exportDestinations: [(name: String, sub: String)] = [
    ("Apple Reminders", "two-way — check it off anywhere"),
    ("Todoist", "one-way export"),
    ("Google Tasks", "one-way export"),
    ("ClickUp", "one-way export"),
    ("Asana", "one-way export"),
  ]

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 0) {
        let open = tasks.incompleteTasks
        SBSectionLabel(text: "Follow-ups · \(open.count)")
          .padding(.bottom, 2)

        if open.isEmpty {
          Text("No follow-ups waiting. Go have meetings — I'll handle the aftermath.")
            .geist(size: 14).foregroundStyle(sb.ink(.w35))
            .padding(.vertical, 14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .overlay(alignment: .bottom) { hairline }
        } else {
          ForEach(open) { task in taskRow(task, done: false) }
        }

        let done = Array(tasks.completedTasks.prefix(8))
        if !done.isEmpty {
          SBSectionLabel(text: "Done").padding(.top, 18).padding(.bottom, 2)
          ForEach(done) { task in taskRow(task, done: true) }
        }

        SBSectionLabel(text: "Send follow-ups to").padding(.top, 20).padding(.bottom, 2)
        ForEach(exportDestinations, id: \.name) { dest in
          SBHairlineRow(title: dest.name, subtitle: dest.sub) {
            Button(action: onOpenSettings) {
              Text("Connect")
                .geistMono(size: 12).foregroundStyle(sb.ink(.w6))
                .underline()
            }
            .buttonStyle(.plain)
          }
        }
        Text("Two-way sync with Apple Reminders and Todoist is coming — connect in Settings → Integrations.")
          .geist(size: 12.5).foregroundStyle(sb.ink(.w32)).padding(.top, 12)
      }
      .padding(.horizontal, 30)
      .padding(.bottom, 24)
    }
    .task { await tasks.loadTasksIfNeeded() }
    .onAppear { tasks.isActive = true }
    .onDisappear { tasks.isActive = false }
  }

  private var hairline: some View { Rectangle().fill(sb.ink(.w07)).frame(height: 1) }

  private func taskRow(_ task: TaskActionItem, done: Bool) -> some View {
    HStack(spacing: 12) {
      Button {
        Task { await tasks.toggleTask(task) }
      } label: {
        ZStack {
          Circle()
            .strokeBorder(sb.ink(.w3), lineWidth: 1.5)
            .background(Circle().fill(done ? sb.ink : .clear))
            .frame(width: 15, height: 15)
          if done {
            Text("✓").font(.system(size: 10)).foregroundStyle(sb.inkInverted)
          }
        }
      }
      .buttonStyle(.plain)

      Text(task.description)
        .geist(size: 15)
        .foregroundStyle(done ? sb.ink(.w35) : sb.ink(.w9))
        .strikethrough(done, color: sb.ink(.w35))
      Spacer(minLength: 8)
      Text(dueLabel(task))
        .geistMono(size: 12.5)
        .foregroundStyle(sb.ink(.w35))
    }
    .padding(.vertical, 11)
    .overlay(alignment: .bottom) { hairline }
  }

  private func dueLabel(_ task: TaskActionItem) -> String {
    guard let due = task.dueAt else { return task.sourceLabel }
    let cal = Calendar.current
    if cal.isDateInToday(due) { return "today" }
    if cal.isDateInTomorrow(due) { return "tomorrow" }
    let f = DateFormatter(); f.dateFormat = "EEE"
    return f.string(from: due)
  }
}
