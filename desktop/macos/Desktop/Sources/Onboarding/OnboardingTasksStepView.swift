import OmiTheme
import SwiftUI

/// Onboarding step explaining that omi auto-creates tasks.
struct OnboardingTasksStepView: View {
  var stepIndex: Int
  var totalSteps: Int
  var onComplete: () -> Void
  var onSkip: (() -> Void)? = nil
  var onForceComplete: (() -> Void)?

  @State private var pulseAnimation = false
  @State private var showTasks = false

  @ObservedObject private var tasksStore = TasksStore.shared

  /// Shown only when the user has no real tasks yet (fresh account, or Gmail/Calendar
  /// not connected so onboarding synthesis created nothing).
  private let placeholderTasks: [(String, String, Bool)] = [
    ("Task 1", "From today's meeting", false),
    ("Task 2", "Mentioned in Slack", false),
    ("Task 3", "Getting started", true),
  ]

  /// Real tasks when present, otherwise the placeholder. Always ends on a "done"
  /// card (a real completed task when there is one, otherwise the last row shown
  /// as complete) so the task-done treatment stays part of the screen.
  private var displayTasks: [(String, String, Bool)] {
    let open = tasksStore.incompleteTasks
    guard !open.isEmpty || !tasksStore.completedTasks.isEmpty else { return placeholderTasks }

    if let done = tasksStore.completedTasks.first {
      let openRows = open.prefix(2).map { ($0.description, taskSubtitle(for: $0), false) }
      return openRows + [(done.description, taskSubtitle(for: done), true)]
    }

    // No completed task yet: render the last open row as the done illustration.
    var rows = open.prefix(3).map { ($0.description, taskSubtitle(for: $0), false) }
    if rows.count > 1 { rows[rows.count - 1].2 = true }
    return rows
  }

  private func taskSubtitle(for task: TaskActionItem) -> String {
    if let due = task.dueAt {
      return "Due " + due.formatted(date: .abbreviated, time: .omitted)
    }
    if let category = task.category, !category.isEmpty {
      return category.capitalized
    }
    return "From your recent activity"
  }

  var body: some View {
    VStack(spacing: 0) {
      // Header
      HStack {
        OnboardingLogoMark(onForceComplete: onForceComplete)
        Spacer()
      }
      .padding(.horizontal, OmiSpacing.xxl)
      .padding(.vertical, OmiSpacing.lg)

      GlassSeparator()

      OnboardingProgressBar(stepIndex: stepIndex, totalSteps: totalSteps)
        .frame(maxWidth: .infinity, alignment: .center)
        .padding(.top, OmiSpacing.xl)

      Spacer()

      VStack(spacing: OmiSpacing.xxl) {
        // Icon with glow
        ZStack {
          // A wash rather than a white bloom: on a light panel a white glow is invisible, and the
          // halo has to darken the ground for the pulse to read at all.
          Circle()
            .fill(Ink.rowFillHover)
            .frame(width: 100, height: 100)
            .blur(radius: 20)
            .scaleEffect(pulseAnimation ? 1.2 : 1.0)
            .omiAnimation(.easeInOut(duration: 2).repeatForever(autoreverses: true), value: pulseAnimation)

          Image(systemName: "checklist")
            .font(.system(size: 44))
            .foregroundStyle(Ink.primary)
        }
        .onAppear { pulseAnimation = true }

        VStack(spacing: OmiSpacing.sm) {
          Text("Auto-created Tasks")
            .inkStyle(InkType.stepHeadline, color: Ink.primary)
            .multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true)

          Text(
            "omi listens to your conversations and automatically\ncreates tasks, action items, and follow-ups for you."
          )
          .inkStyle(InkType.prose, color: Ink.secondary)
          .multilineTextAlignment(.center)
          .fixedSize(horizontal: false, vertical: true)
        }

        // Task cards — real onboarding tasks, or the placeholder when none exist yet
        if showTasks {
          ScrollView {
            LazyVStack(spacing: OmiSpacing.sm) {
              ForEach(Array(displayTasks.enumerated()), id: \.offset) { index, task in
                mockTaskRow(title: task.0, subtitle: task.1, checked: task.2)
                  .transition(
                    .asymmetric(
                      insertion: .move(edge: .bottom).combined(with: .opacity),
                      removal: .opacity
                    ))
              }
            }
          }
          .scrollIndicators(.never)
          .frame(maxWidth: 420, maxHeight: 180)
        }
      }
      .padding(.horizontal, OmiSpacing.page)

      Spacer()

      HStack(spacing: OmiSpacing.md) {
        OnboardingBackButton()

        Button(action: onComplete) {
          Text("Take me to Omi")
        }
        .buttonStyle(InkButtonStyle(kind: .primary))
        .keyboardShortcut(.defaultAction)
      }
      .padding(.bottom, OmiSpacing.section)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .onAppear {
      // Stagger task card appearance
      DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
        OmiMotion.withGated(.spring(response: 0.5, dampingFraction: 0.8)) {
          showTasks = true
        }
      }
    }
    .task {
      // Pull the tasks onboarding synthesis just created (Gmail/Calendar follow-ups)
      // so the cards show the user's real tasks instead of the placeholder, plus a
      // completed one to keep the task-done card.
      await tasksStore.loadTasksIfNeeded()
      await tasksStore.loadCompletedTasks()
    }
  }

  private func mockTaskRow(title: String, subtitle: String, checked: Bool) -> some View {
    HStack(spacing: OmiSpacing.md) {
      Image(systemName: checked ? "checkmark.circle.fill" : "circle")
        .font(.system(size: 18))
        .foregroundColor(checked ? Ink.listeningGreen : Ink.secondary)

      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        // The row wraps and never truncates: a task description given less height than it needs
        // ends in an ellipsis, which is copy quietly disappearing rather than a layout that fails.
        Text(title)
          .inkStyle(InkType.rowCopy, color: checked ? Ink.secondary : Ink.primary)
          .strikethrough(checked)
          .fixedSize(horizontal: false, vertical: true)

        Text(subtitle)
          .inkStyle(InkType.statusLabel, color: Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
      }

      Spacer()
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.sm)
    .glassCard(cornerRadius: PageGlass.rowRadius)
  }
}
