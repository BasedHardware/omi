import OmiTheme
import SwiftUI

// MARK: - Goals Widget

struct GoalsWidget: View {
  let goals: [Goal]
  let onCreateGoal: (String, Double, Double) -> Void  // (title, currentValue, targetValue)
  let onUpdateGoal: (Goal, String, Double, Double) -> Void
  let onUpdateProgress: (Goal, Double) -> Void
  let onDeleteGoal: (Goal) -> Void

  @State private var editingGoal: Goal? = nil
  @State private var showingCreateSheet = false
  @State private var showingHistory = false
  @State private var isGeneratingGoal = false

  // AI Features
  @State private var selectedGoalForInsight: Goal? = nil

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      // Header
      HStack {
        Text("Goals")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)

        Spacer()

        // Add goal button (only if less than 3 goals)
        if goals.count < 4 {
          GoalHeaderButton(icon: "plus", tooltip: "Add goal", color: OmiColors.textTertiary) {
            showingCreateSheet = true
          }
        }
      }

      if goals.isEmpty {
        // Empty state — header already has a + button, so just offer
        // the AI generation action centered in the empty area.
        VStack(spacing: 0) {
          Spacer(minLength: 0)

          Button(action: { triggerGoalGeneration() }) {
            HStack(spacing: OmiSpacing.xs) {
              if isGeneratingGoal {
                ProgressView()
                  .scaleEffect(0.6)
                  .frame(width: 12, height: 12)
              } else {
                Image(systemName: "sparkles")
                  .scaledFont(size: OmiType.caption)
              }
              Text(isGeneratingGoal ? "Generating..." : "Generate AI Goal")
                .scaledFont(size: OmiType.body, weight: .medium)
            }
            .foregroundColor(OmiColors.accent)
            .padding(.horizontal, OmiSpacing.md)
            .padding(.vertical, OmiSpacing.sm)
            .omiControlSurface(fill: OmiColors.accent.opacity(0.12), radius: OmiChrome.chipRadius)
          }
          .buttonStyle(.plain)
          .disabled(isGeneratingGoal)

          Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      } else {
        // Goals list — centered vertically in remaining cell height
        // so a shorter Goals list floats to the middle when the
        // Tasks card determines the row's intrinsic height.
        VStack(spacing: 0) {
          Spacer(minLength: 0)

          VStack(spacing: OmiSpacing.md) {
            ForEach(Array(goals.enumerated()), id: \.element.id) { index, goal in
              GoalRowView(
                goal: goal,
                index: index,
                onTap: { editingGoal = goal },
                onUpdateProgress: { value in onUpdateProgress(goal, value) },
                onDelete: { onDeleteGoal(goal) },
                onGetInsight: {
                  selectedGoalForInsight = goal
                }
              )
            }
          }

          Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      }
    }
    .padding(OmiSpacing.xl)
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    .omiPanel(fill: OmiColors.backgroundSecondary)
    .sheet(isPresented: $showingCreateSheet) {
      GoalEditSheet(
        goal: nil,
        onSave: { title, current, target in
          onCreateGoal(title, current, target)
        },
        onDelete: nil,
        onDismiss: { showingCreateSheet = false }
      )
    }
    .sheet(item: $editingGoal) { goal in
      GoalEditSheet(
        goal: goal,
        onSave: { title, current, target in
          onUpdateGoal(goal, title, current, target)
        },
        onDelete: {
          onDeleteGoal(goal)
        },
        onDismiss: { editingGoal = nil }
      )
    }
    .sheet(item: $selectedGoalForInsight) { goal in
      GoalInsightSheet(
        goal: goal,
        onDismiss: { selectedGoalForInsight = nil }
      )
    }
    .sheet(isPresented: $showingHistory) {
      GoalsHistoryPage(onDismiss: { showingHistory = false })
        .frame(width: 480, height: 500)
    }
  }

  private func triggerGoalGeneration() {
    isGeneratingGoal = true
    Task {
      await GoalGenerationService.shared.generateNow()
      isGeneratingGoal = false
    }
  }
}

// MARK: - Goal Row View

struct GoalRowView: View {
  let goal: Goal
  let index: Int
  let onTap: () -> Void
  let onUpdateProgress: (Double) -> Void
  let onDelete: () -> Void
  var onGetInsight: (() -> Void)? = nil

  @State private var isHovering = false
  @State private var isDragging = false
  @State private var dragValue: Double? = nil
  @State private var isExpanded = false
  @State private var linkedTasks: [TaskActionItem] = []
  @State private var hasLoadedTasks = false

  /// The progress fraction (0-1) to display, using drag value when active
  private var displayProgress: Double {
    if let dv = dragValue {
      return min(max(dv, 0), 1)
    }
    return min(goal.progress / 100.0, 1.0)
  }

  private var progressColor: Color {
    let progress = displayProgress
    if progress >= 0.8 {
      return Color(red: 0.133, green: 0.773, blue: 0.369)  // #22C55E Green
    } else if progress >= 0.6 {
      return Color(red: 0.518, green: 0.8, blue: 0.086)  // #84CC16 Lime
    } else if progress >= 0.4 {
      return Color(red: 0.984, green: 0.749, blue: 0.141)  // #FBBF24 Yellow
    } else if progress >= 0.2 {
      return Color(red: 0.976, green: 0.451, blue: 0.086)  // #F97316 Orange
    } else {
      return OmiColors.textTertiary
    }
  }

  private var dragProgressText: String {
    let currentVal: Double
    if let dv = dragValue {
      let raw = goal.minValue + dv * (goal.targetValue - goal.minValue)
      currentVal = max(goal.minValue, min(raw, goal.targetValue))
    } else {
      currentVal = goal.currentValue
    }
    return "\(Int(currentVal.rounded()))/\(Int(goal.targetValue.rounded()))"
  }

  var body: some View {
    HStack(spacing: OmiSpacing.md) {
      // Emoji icon - tapping opens edit sheet
      ZStack {
        RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
          .fill(OmiColors.backgroundRaised.opacity(0.9))
          .frame(width: 36, height: 36)
        Text(goalEmoji)
          .scaledFont(size: OmiType.subheading)
      }
      .onTapGesture { onTap() }

      // Content
      VStack(alignment: .leading, spacing: OmiSpacing.md) {
        HStack {
          Text(goal.title)
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(OmiColors.textPrimary)
            .lineLimit(1)
            .onTapGesture { onTap() }

          Spacer()

          // Expand/collapse button (if has description or linked tasks)
          if goal.description != nil || !linkedTasks.isEmpty {
            Button(action: {
              OmiMotion.withGated(.easeInOut(duration: 0.2)) {
                isExpanded.toggle()
              }
            }) {
              Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                .scaledFont(size: OmiType.micro, weight: .medium)
                .foregroundColor(OmiColors.textTertiary)
            }
            .buttonStyle(.plain)
          }

          // Advice button (shown on hover)
          if isHovering, let onGetInsight = onGetInsight {
            Button(action: onGetInsight) {
              Image(systemName: "lightbulb.fill")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(.yellow)
            }
            .buttonStyle(.plain)
            .transition(.opacity)
          }

          // Progress value (current/target)
          Text(dragProgressText)
            .scaledFont(size: OmiType.caption)
            .foregroundColor(isDragging ? OmiColors.textPrimary : OmiColors.textTertiary)
            .omiAnimation(.easeInOut(duration: 0.15), value: isDragging)
        }

        // Progress bar with drag gesture
        GeometryReader { geometry in
          ZStack(alignment: .leading) {
            // Background track - visible light gray
            RoundedRectangle(cornerRadius: OmiChrome.stripRadius)
              .fill(Color.white.opacity(0.12))
              .frame(height: isDragging ? 8 : 6)

            // Progress fill
            RoundedRectangle(cornerRadius: OmiChrome.stripRadius)
              .fill(progressColor)
              .frame(
                width: max(0, geometry.size.width * displayProgress),
                height: isDragging ? 8 : 6
              )

            // Drag thumb - always visible
            Circle()
              .fill(.white)
              .frame(width: 14, height: 14)
              .shadow(color: .black.opacity(0.25), radius: 2, y: 1)
              .offset(x: max(0, min(geometry.size.width * displayProgress - 7, geometry.size.width - 14)))
          }
          .frame(maxHeight: .infinity)
          .contentShape(Rectangle())
          .gesture(
            DragGesture(minimumDistance: 0)
              .onChanged { value in
                isDragging = true
                let fraction = value.location.x / geometry.size.width
                dragValue = min(max(fraction, 0), 1)
              }
              .onEnded { _ in
                if let dv = dragValue {
                  let finalValue = goal.minValue + dv * (goal.targetValue - goal.minValue)
                  let clampedValue = max(goal.minValue, min(finalValue, goal.targetValue))
                  let roundedValue = clampedValue.rounded()
                  onUpdateProgress(roundedValue)
                }
                isDragging = false
                dragValue = nil
              }
          )
        }
        .frame(height: 18)
        .omiAnimation(.easeInOut(duration: 0.15), value: isDragging)

        // Expanded section: description + linked tasks
        if isExpanded {
          VStack(alignment: .leading, spacing: OmiSpacing.sm) {
            // Description
            if let desc = goal.description, !desc.isEmpty {
              Text(desc)
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textSecondary)
                .lineLimit(3)
            }

            // Linked tasks
            if !linkedTasks.isEmpty {
              VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
                Text("Linked Tasks")
                  .scaledFont(size: OmiType.micro, weight: .semibold)
                  .foregroundColor(OmiColors.textTertiary)
                  .textCase(.uppercase)

                ForEach(linkedTasks) { task in
                  HStack(spacing: OmiSpacing.xs) {
                    Image(systemName: task.completed ? "checkmark.circle.fill" : "circle")
                      .scaledFont(size: OmiType.caption)
                      .foregroundColor(
                        task.completed ? Color(red: 0.133, green: 0.773, blue: 0.369) : OmiColors.textTertiary)

                    Text(task.description)
                      .scaledFont(size: OmiType.caption)
                      .foregroundColor(task.completed ? OmiColors.textTertiary : OmiColors.textPrimary)
                      .strikethrough(task.completed)
                      .lineLimit(1)
                  }
                }
              }
            }
          }
          .padding(.top, OmiSpacing.hairline)
          .transition(.opacity.combined(with: .move(edge: .top)))
        }
      }
    }
    .padding(.vertical, OmiSpacing.md)
    .padding(.horizontal, OmiSpacing.md)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.controlRadius, style: .continuous)
        .fill(OmiColors.backgroundTertiary.opacity(isHovering ? 0.9 : 0.72))
    )
    .onHover { hovering in
      OmiMotion.withGated(.easeInOut(duration: 0.15)) {
        isHovering = hovering
      }
    }
    .task {
      guard !hasLoadedTasks else { return }
      hasLoadedTasks = true
      await loadLinkedTasks()
    }
  }

  private func loadLinkedTasks() async {
    do {
      let response = try await APIClient.shared.getActionItems(limit: 100, completed: nil)
      linkedTasks = response.items.filter { $0.goalId == goal.id }
    } catch {
      // Silently fail — linked tasks are supplementary
    }
  }

  private var goalEmoji: String {
    let title = goal.title.lowercased()

    // Money/Revenue
    if title.contains("revenue") || title.contains("money") || title.contains("income") || title.contains("profit")
      || title.contains("sales") || title.contains("$") || title.contains("dollar") || title.contains("earn")
    {
      return "💰"
    }
    // Growth/Users
    if title.contains("users") || title.contains("customers") || title.contains("clients")
      || title.contains("subscribers") || title.contains("followers") || title.contains("growth")
      || title.contains("million") || title.contains("1m") || title.contains("10k") || title.contains("100k")
      || title.contains("mrr") || title.contains("arr")
    {
      return "🚀"
    }
    // Startup/Business
    if title.contains("startup") || title.contains("launch") || title.contains("business") || title.contains("company")
    {
      return "🏆"
    }
    // Investment
    if title.contains("invest") || title.contains("stock") || title.contains("crypto") || title.contains("trading") {
      return "📈"
    }
    // Workout/Gym
    if title.contains("workout") || title.contains("gym") || title.contains("exercise") || title.contains("lift")
      || title.contains("muscle") || title.contains("strength") || title.contains("pushup") || title.contains("pullup")
    {
      return "💪"
    }
    // Running/Cardio
    if title.contains("run") || title.contains("marathon") || title.contains("jog") || title.contains("cardio")
      || title.contains("steps") || title.contains("walk") || title.contains("mile") || title.contains("km")
    {
      return "🏃"
    }
    // Weight/Diet
    if title.contains("weight") || title.contains("lose") || title.contains("fat") || title.contains("diet")
      || title.contains("calories") || title.contains("kg") || title.contains("lbs") || title.contains("pounds")
    {
      return "⚖️"
    }
    // Meditation/Yoga
    if title.contains("meditat") || title.contains("mindful") || title.contains("yoga") || title.contains("breath")
      || title.contains("calm") || title.contains("peace") || title.contains("zen")
    {
      return "🧘"
    }
    // Sleep
    if title.contains("sleep") || title.contains("rest") || title.contains("hours") {
      return "😴"
    }
    // Water/Hydration
    if title.contains("water") || title.contains("hydrat") || title.contains("drink") {
      return "💧"
    }
    // Health
    if title.contains("health") || title.contains("wellness") || title.contains("healthy") {
      return "❤️"
    }
    // Reading
    if title.contains("read") || title.contains("book") || title.contains("pages") || title.contains("chapter") {
      return "📚"
    }
    // Learning
    if title.contains("learn") || title.contains("study") || title.contains("course") || title.contains("class")
      || title.contains("skill") || title.contains("certif")
    {
      return "🎓"
    }
    // Coding
    if title.contains("code") || title.contains("program") || title.contains("develop") || title.contains("app")
      || title.contains("software") || title.contains("tech")
    {
      return "💻"
    }
    // Language
    if title.contains("language") || title.contains("spanish") || title.contains("french") || title.contains("chinese")
      || title.contains("english") || title.contains("german")
    {
      return "🗣️"
    }
    // Writing
    if title.contains("write") || title.contains("blog") || title.contains("article") || title.contains("post")
      || title.contains("content") || title.contains("words")
    {
      return "✍️"
    }
    // Video
    if title.contains("video") || title.contains("youtube") || title.contains("tiktok") || title.contains("film") {
      return "🎬"
    }
    // Music
    if title.contains("music") || title.contains("song") || title.contains("piano") || title.contains("guitar")
      || title.contains("sing")
    {
      return "🎵"
    }
    // Art
    if title.contains("art") || title.contains("draw") || title.contains("paint") || title.contains("design")
      || title.contains("create")
    {
      return "🎨"
    }
    // Photo
    if title.contains("photo") || title.contains("picture") || title.contains("camera") {
      return "📸"
    }
    // Tasks
    if title.contains("task") || title.contains("todo") || title.contains("complete") || title.contains("finish")
      || title.contains("done")
    {
      return "✅"
    }
    // Habits
    if title.contains("habit") || title.contains("daily") || title.contains("streak") || title.contains("consistent")
      || title.contains("routine")
    {
      return "🔥"
    }
    // Time/Focus
    if title.contains("time") || title.contains("hour") || title.contains("minute") || title.contains("focus")
      || title.contains("pomodoro") || title.contains("productive")
    {
      return "⏰"
    }
    // Project/Ship
    if title.contains("project") || title.contains("ship") || title.contains("deliver") || title.contains("deadline")
      || title.contains("feature")
    {
      return "🎯"
    }
    // Travel
    if title.contains("travel") || title.contains("trip") || title.contains("visit") || title.contains("country")
      || title.contains("city") || title.contains("vacation")
    {
      return "✈️"
    }
    // Home
    if title.contains("home") || title.contains("house") || title.contains("apartment") || title.contains("move")
      || title.contains("buy")
    {
      return "🏠"
    }
    // Saving
    if title.contains("save") || title.contains("saving") || title.contains("budget")
      || title.contains("emergency fund")
    {
      return "🏦"
    }
    // Social
    if title.contains("friend") || title.contains("social") || title.contains("network") || title.contains("connect")
      || title.contains("meet") || title.contains("outreach")
    {
      return "👥"
    }
    // Family
    if title.contains("family") || title.contains("kids") || title.contains("parent") {
      return "👨‍👩‍👧"
    }
    // Relationship
    if title.contains("date") || title.contains("relationship") || title.contains("love") {
      return "💕"
    }
    // Win/Success
    if title.contains("win") || title.contains("first") || title.contains("best") || title.contains("top")
      || title.contains("champion")
    {
      return "🏆"
    }
    // Growth/Improve
    if title.contains("grow") || title.contains("improve") || title.contains("better") || title.contains("progress") {
      return "🌱"
    }
    // Star/Success
    if title.contains("star") || title.contains("success") || title.contains("excellent") {
      return "⭐"
    }

    // Default
    return "🎯"
  }
}

// MARK: - Goal Edit Sheet

struct GoalEditSheet: View {
  let goal: Goal?
  let onSave: (String, Double, Double) -> Void
  let onDelete: (() -> Void)?
  let onDismiss: () -> Void

  @State private var title: String = ""
  @State private var currentValue: String = "0"
  @State private var targetValue: String = "100"
  @State private var selectedEmoji: String = "🎯"

  private let availableEmojis = [
    "🎯", "💪", "📚", "💰", "🏃", "🧘", "💡", "🔥",
    "⭐", "🚀", "💎", "🏆", "📈", "❤️", "🎨", "🎵",
    "✈️", "🏠", "🌱", "⏰",
  ]

  var isNewGoal: Bool { goal == nil }

  var body: some View {
    VStack(spacing: 0) {
      // Header
      HStack {
        Text(isNewGoal ? "Add Goal" : "Edit Goal")
          .scaledFont(size: OmiType.heading, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)

        Spacer()

        Button(action: onDismiss) {
          Image(systemName: "xmark")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(OmiColors.textTertiary)
            .frame(width: 28, height: 28)
            .background(OmiColors.backgroundTertiary.opacity(0.5))
            .clipShape(Circle())
        }
        .buttonStyle(.plain)
      }
      .padding(.horizontal, OmiSpacing.xl)
      .padding(.top, OmiSpacing.xl)
      .padding(.bottom, OmiSpacing.lg)

      Divider()
        .background(OmiColors.backgroundTertiary)

      ScrollView {
        VStack(alignment: .leading, spacing: OmiSpacing.xl) {

          // Title field
          VStack(alignment: .leading, spacing: OmiSpacing.sm) {
            Text("Goal Title")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.textTertiary)

            TextField("Enter goal title", text: $title)
              .textFieldStyle(.plain)
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textPrimary)
              .padding(.horizontal, OmiSpacing.md)
              .padding(.vertical, OmiSpacing.md)
              .background(
                RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
                  .fill(OmiColors.backgroundTertiary.opacity(0.5))
              )
          }

          // Current & Target fields
          HStack(spacing: OmiSpacing.md) {
            VStack(alignment: .leading, spacing: OmiSpacing.sm) {
              Text("Current")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textTertiary)

              TextField("0", text: $currentValue)
                .textFieldStyle(.plain)
                .scaledFont(size: OmiType.body)
                .foregroundColor(OmiColors.textPrimary)
                .padding(.horizontal, OmiSpacing.md)
                .padding(.vertical, OmiSpacing.md)
                .background(
                  RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
                    .fill(OmiColors.backgroundTertiary.opacity(0.5))
                )
            }

            VStack(alignment: .leading, spacing: OmiSpacing.sm) {
              Text("Target")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textTertiary)

              TextField("100", text: $targetValue)
                .textFieldStyle(.plain)
                .scaledFont(size: OmiType.body)
                .foregroundColor(OmiColors.textPrimary)
                .padding(.horizontal, OmiSpacing.md)
                .padding(.vertical, OmiSpacing.md)
                .background(
                  RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
                    .fill(OmiColors.backgroundTertiary.opacity(0.5))
                )
            }
          }
        }
        .padding(OmiSpacing.xl)
      }

      Divider()
        .background(OmiColors.backgroundTertiary)

      // Actions
      HStack(spacing: OmiSpacing.md) {
        // Delete button (only for existing goals)
        if !isNewGoal, let onDelete = onDelete {
          Button(action: {
            onDelete()
            onDismiss()
          }) {
            Text("Delete")
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundColor(.red)
          }
          .buttonStyle(.plain)
        }

        Spacer()

        // Cancel button
        Button(action: onDismiss) {
          Text("Cancel")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(OmiColors.textTertiary)
        }
        .buttonStyle(.plain)

        // Save button
        Button(action: {
          let current = Double(currentValue) ?? 0
          let target = Double(targetValue) ?? 100
          onSave(title, current, target)
          onDismiss()
        }) {
          Text(isNewGoal ? "Add Goal" : "Save")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(OmiColors.backgroundPrimary)
            .padding(.horizontal, OmiSpacing.xl)
            .padding(.vertical, OmiSpacing.sm)
            .background(
              RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
                .fill(OmiColors.accent)
            )
        }
        .buttonStyle(.plain)
        .disabled(title.isEmpty)
        .opacity(title.isEmpty ? 0.5 : 1)
      }
      .padding(OmiSpacing.xl)
    }
    .frame(width: 400, height: isNewGoal ? 320 : 420)
    .background(OmiColors.backgroundSecondary)
    .onAppear {
      if let goal = goal {
        title = goal.title
        currentValue =
          goal.currentValue == goal.currentValue.rounded()
          ? String(format: "%.0f", goal.currentValue)
          : String(format: "%.1f", goal.currentValue)
        targetValue =
          goal.targetValue == goal.targetValue.rounded()
          ? String(format: "%.0f", goal.targetValue)
          : String(format: "%.1f", goal.targetValue)
      }
    }
  }
}

// MARK: - Goal Advice Sheet

struct GoalInsightSheet: View {
  let goal: Goal
  let onDismiss: () -> Void

  @State private var isLoading = true
  @State private var insight: String? = nil
  @State private var errorMessage: String? = nil

  var body: some View {
    VStack(spacing: 0) {
      // Header
      HStack {
        HStack(spacing: OmiSpacing.sm) {
          Image(systemName: "lightbulb.fill")
            .scaledFont(size: OmiType.subheading)
            .foregroundColor(.yellow)
          Text("Goal Insight")
            .scaledFont(size: OmiType.heading, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
        }

        Spacer()

        Button(action: onDismiss) {
          Image(systemName: "xmark")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(OmiColors.textTertiary)
            .frame(width: 28, height: 28)
            .background(OmiColors.backgroundTertiary.opacity(0.5))
            .clipShape(Circle())
        }
        .buttonStyle(.plain)
      }
      .padding(.horizontal, OmiSpacing.xl)
      .padding(.top, OmiSpacing.xl)
      .padding(.bottom, OmiSpacing.lg)

      Divider()
        .background(OmiColors.backgroundTertiary)

      // Goal info
      HStack(spacing: OmiSpacing.md) {
        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          Text(goal.title)
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(OmiColors.textPrimary)
            .lineLimit(1)

          Text("\(Int(goal.currentValue))/\(Int(goal.targetValue)) (\(Int(goal.progress))%)")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textTertiary)
        }

        Spacer()

        // Progress indicator
        ZStack {
          Circle()
            .stroke(OmiColors.backgroundTertiary, lineWidth: 3)
          Circle()
            .trim(from: 0, to: min(goal.progress / 100, 1.0))
            .stroke(OmiColors.accent, style: StrokeStyle(lineWidth: 3, lineCap: .round))
            .rotationEffect(.degrees(-90))
        }
        .frame(width: 36, height: 36)
      }
      .padding(.horizontal, OmiSpacing.xl)
      .padding(.vertical, OmiSpacing.md)
      .background(OmiColors.backgroundTertiary.opacity(0.3))

      // Content
      VStack(spacing: OmiSpacing.lg) {
        if isLoading {
          VStack(spacing: OmiSpacing.md) {
            ProgressView()
              .scaleEffect(1.2)
            Text("Getting personalized insight...")
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textTertiary)
          }
          .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let error = errorMessage {
          VStack(spacing: OmiSpacing.md) {
            Image(systemName: "exclamationmark.triangle")
              .scaledFont(size: 32)
              .foregroundColor(.orange)
            Text(error)
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textSecondary)
              .multilineTextAlignment(.center)
          }
          .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let insightText = insight {
          VStack(alignment: .leading, spacing: OmiSpacing.md) {
            Text("This week's action:")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.textTertiary)

            Text(insightText)
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textPrimary)
              .fixedSize(horizontal: false, vertical: true)
          }
          .padding(OmiSpacing.xl)
          .frame(maxWidth: .infinity, alignment: .leading)
        }
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity)

      Divider()
        .background(OmiColors.backgroundTertiary)

      // Actions
      HStack(spacing: OmiSpacing.md) {
        // Refresh button
        Button(action: loadInsight) {
          HStack(spacing: OmiSpacing.xxs) {
            Image(systemName: "arrow.clockwise")
              .scaledFont(size: OmiType.caption)
            Text("Refresh")
          }
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(OmiColors.textTertiary)
        }
        .buttonStyle(.plain)
        .disabled(isLoading)

        Spacer()

        // Done button
        Button(action: onDismiss) {
          Text("Done")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(OmiColors.backgroundPrimary)
            .padding(.horizontal, OmiSpacing.xl)
            .padding(.vertical, OmiSpacing.sm)
            .background(
              RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
                .fill(OmiColors.accent)
            )
        }
        .buttonStyle(.plain)
      }
      .padding(OmiSpacing.xl)
    }
    .frame(width: 400, height: 380)
    .background(OmiColors.backgroundSecondary)
    .onAppear {
      loadInsight()
    }
  }

  private func loadInsight() {
    isLoading = true
    errorMessage = nil

    Task {
      do {
        let result = try await GoalsAIService.shared.getGoalInsight(goal: goal)
        await MainActor.run {
          insight = result
          isLoading = false
        }
      } catch {
        await MainActor.run {
          errorMessage = UserFacingErrorPresentation.message(for: error, while: .goals)
          isLoading = false
        }
      }
    }
  }
}

// MARK: - Goal Header Button with Tooltip

private struct GoalHeaderButton: View {
  let icon: String
  let tooltip: String
  let color: Color
  var isLoading: Bool = false
  let action: () -> Void

  @State private var isHovered = false

  var body: some View {
    Button(action: action) {
      if isLoading {
        ProgressView()
          .scaleEffect(0.6)
          .frame(width: 14, height: 14)
      } else {
        Image(systemName: icon)
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(color)
      }
    }
    .buttonStyle(.plain)
    .disabled(isLoading)
    .overlay(alignment: .bottom) {
      if isHovered {
        Text(tooltip)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textPrimary)
          .padding(.horizontal, OmiSpacing.sm)
          .padding(.vertical, OmiSpacing.xxs)
          .background(
            RoundedRectangle(cornerRadius: OmiChrome.badgeRadius)
              .fill(OmiColors.backgroundTertiary)
              .shadow(color: .black.opacity(0.2), radius: 4, y: 2)
          )
          .fixedSize()
          .offset(y: 24)
          .transition(.opacity)
      }
    }
    .onHover { hovering in
      OmiMotion.withGated(.easeInOut(duration: 0.15)) {
        isHovered = hovering
      }
    }
  }
}

#if canImport(PreviewsMacros)
  #Preview {
    GoalsWidget(
      goals: [],
      onCreateGoal: { _, _, _ in },
      onUpdateGoal: { _, _, _, _ in },
      onUpdateProgress: { _, _ in },
      onDeleteGoal: { _ in }
    )
    .frame(width: 350)
    .padding()
    .background(OmiColors.backgroundPrimary)
  }
#endif
