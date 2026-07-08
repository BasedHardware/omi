import SwiftUI

/// The calm "Today" tasks screen — mockup `tasks.html`, live-wired to `TasksStore`.
///
/// A single centered column: a mono date + "Today" header, then grouped sections
/// with eyebrow labels — "Do this next" (overdue + today), "Later this week"
/// (no due date), and "Done" (completed, struck through). Each row toggles the
/// real store completion. Shows the mockup's calm empty-state card when clear.
struct RedesignTasksPage: View {
  @ObservedObject var tasksStore = TasksStore.shared
  @Binding var selectedIndex: Int

  @State private var showAdd = false
  @State private var newTaskText = ""
  @FocusState private var addFocused: Bool

  // MARK: Derived groups

  /// "Do this next" — anything already due (overdue first, then today).
  private var doThisNext: [TaskActionItem] {
    tasksStore.overdueTasks + tasksStore.todaysTasks
  }

  /// "Later this week" — incomplete tasks without a due date.
  private var laterThisWeek: [TaskActionItem] {
    tasksStore.tasksWithoutDueDate
  }

  private var done: [TaskActionItem] {
    tasksStore.completedTasks
  }

  private var isEmpty: Bool {
    doThisNext.isEmpty && laterThisWeek.isEmpty && done.isEmpty
  }

  private var dateLine: String {
    let f = DateFormatter()
    f.dateFormat = "EEEE, MMMM d"
    return f.string(from: Date())
  }

  // MARK: Body

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 0) {
        header
          .padding(.bottom, 4)

        if showAdd { addRow }

        if isEmpty && !showAdd {
          emptyCard
            .padding(.top, InkSpace.s5)
        } else {
          section("Do this next", tasks: doThisNext)
          section("Later this week", tasks: laterThisWeek)
          section("Done", tasks: done, done: true)
        }
      }
      .frame(maxWidth: 720, alignment: .leading)
      .frame(maxWidth: .infinity, alignment: .center)
      .padding(.horizontal, 48)
      .padding(.vertical, 44)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(Ink.canvas)
    .onAppear {
      tasksStore.isActive = true
      Task {
        await tasksStore.loadTasksIfNeeded()
        await tasksStore.loadCompletedTasks()
      }
    }
    .onDisappear { tasksStore.isActive = false }
  }

  private var header: some View {
    HStack(alignment: .top) {
      VStack(alignment: .leading, spacing: 8) {
        Text(dateLine).inkMonoCaption()
        Text("Today").inkH1()
      }
      Spacer()
      InkButton(title: "Add", systemImage: "plus", kind: .ghost, size: .sm) {
        showAdd = true
        addFocused = true
      }
    }
  }

  /// Inline new-task entry — creates a real task via the store on submit.
  private var addRow: some View {
    HStack(spacing: 12) {
      Circle().strokeBorder(Ink.hair2, lineWidth: 1.6).frame(width: 20, height: 20)
      TextField("Add a task…", text: $newTaskText)
        .textFieldStyle(.plain)
        .font(InkFont.sans(14.5))
        .foregroundColor(Ink.ink)
        .focused($addFocused)
        .onSubmit { commitNewTask() }
      Spacer()
    }
    .padding(.horizontal, 12)
    .padding(.vertical, 12)
    .padding(.top, InkSpace.s4)
  }

  private func commitNewTask() {
    let text = newTaskText.trimmingCharacters(in: .whitespacesAndNewlines)
    newTaskText = ""
    showAdd = false
    addFocused = false
    guard !text.isEmpty else { return }
    Task { _ = await tasksStore.createTask(description: text, dueAt: nil, priority: nil) }
  }

  // MARK: Section

  @ViewBuilder
  private func section(_ label: String, tasks: [TaskActionItem], done: Bool = false) -> some View {
    if !tasks.isEmpty {
      Text(label)
        .inkEyebrow()
        .padding(.top, InkSpace.s5)
        .padding(.bottom, InkSpace.s1)
        .padding(.horizontal, 12)
      VStack(alignment: .leading, spacing: 0) {
        ForEach(tasks) { task in
          RedesignTaskRow(task: task, isDone: done) {
            Task { await tasksStore.toggleTask(task) }
          }
        }
      }
    }
  }

  // MARK: Empty state

  private var emptyCard: some View {
    InkCard(padding: 28, recessed: true) {
      VStack(spacing: 8) {
        Text("When you're clear, this is what you'll see —")
          .font(InkFont.sans(13)).foregroundColor(Ink.body)
        Text("Nothing on your plate yet.")
          .font(InkFont.serif(19, .medium)).foregroundColor(Ink.ink).tracking(-0.3)
        Text("I'll add things as they come up.").inkSmall()
      }
      .multilineTextAlignment(.center)
      .frame(maxWidth: .infinity)
    }
  }
}

// MARK: - Task Row

private struct RedesignTaskRow: View {
  let task: TaskActionItem
  let isDone: Bool
  let onToggle: () -> Void

  @State private var hovering = false

  var body: some View {
    HStack(alignment: .top, spacing: 13) {
      checkbox
      VStack(alignment: .leading, spacing: 5) {
        Text(task.description)
          .font(InkFont.sans(14.5))
          .foregroundColor(isDone ? Ink.faint : Ink.ink)
          .strikethrough(isDone, color: Ink.faint)
          .lineSpacing(2)
          .fixedSize(horizontal: false, vertical: true)
        if !isDone {
          metaLine
        }
      }
      Spacer(minLength: 0)
    }
    .padding(.vertical, 14)
    .padding(.horizontal, 12)
    .background(
      RoundedRectangle(cornerRadius: 11, style: .continuous)
        .fill(hovering ? Ink.surface2 : .clear))
    .contentShape(Rectangle())
    .onHover { hovering = $0 }
  }

  private var checkbox: some View {
    Button(action: onToggle) {
      ZStack {
        Circle()
          .fill(isDone ? Ink.ink : Color.clear)
          .overlay(
            Circle().strokeBorder(isDone ? Color.clear : Ink.hair2, lineWidth: 1.6))
          .frame(width: 20, height: 20)
        if isDone {
          Image(systemName: "checkmark")
            .font(.system(size: 11, weight: .bold))
            .foregroundColor(Ink.accentInk)
        }
      }
      .frame(width: 20, height: 20)
    }
    .buttonStyle(.plain)
    .padding(.top, 1)
  }

  @ViewBuilder
  private var metaLine: some View {
    let source = sourceLabel
    let badge = dueBadge
    if source != nil || badge != nil {
      HStack(spacing: 8) {
        if let source {
          Text(source).inkCaption()
        }
        if let badge {
          // Warn "needs-you" styling for anything due.
          InkBadge(text: badge.0, kind: .needs).fixedSize()
        }
      }
    }
  }

  /// A calm, humanized description of where the task came from.
  private var sourceLabel: String? {
    let src = (task.source ?? "").lowercased()
    if src.isEmpty { return nil }
    if src.contains("screenshot") { return "caught on your screen" }
    if src.contains("transcription") { return "from a conversation" }
    if src == "manual" { return "added by you" }
    if src == "recurring" { return "recurring" }
    return nil
  }

  /// A warn badge when the task is due. Returns (label, isOverdue).
  private var dueBadge: (String, Bool)? {
    guard let due = task.dueAt else { return nil }
    let cal = Calendar.current
    let startOfToday = cal.startOfDay(for: Date())
    if due < startOfToday { return ("Overdue", true) }
    if cal.isDateInToday(due) { return ("Due today", false) }
    return nil
  }
}
