import OmiTheme
import SwiftUI

struct WhatMattersNowSection: View {
  @ObservedObject var store: DashboardIntelligenceStore
  let onOpen: (DashboardRecommendation) async -> Bool

  var body: some View {
    if !store.recommendations.isEmpty {
      VStack(alignment: .leading, spacing: 10) {
        HStack {
          Text("What matters now")
            .scaledFont(size: 15, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
          Spacer()
        }

        HStack(alignment: .top, spacing: 10) {
          ForEach(store.recommendations) { recommendation in
            WhatMattersNowCard(
              recommendation: recommendation,
              onPrimary: {
                if await onOpen(recommendation) {
                  await store.recordPrimaryAction(recommendation)
                }
              },
              onLater: { await store.later(recommendation) },
              onDismiss: { reason in await store.dismiss(recommendation, reason: reason) }
            )
          }
        }
      }
      .padding(12)
      .background(
        RoundedRectangle(cornerRadius: 14, style: .continuous)
          .fill(OmiColors.backgroundSecondary.opacity(0.72))
      )
      .overlay(
        RoundedRectangle(cornerRadius: 14, style: .continuous)
          .stroke(OmiColors.border.opacity(0.55), lineWidth: 1)
      )
      .accessibilityIdentifier("what-matters-now")
    }
  }
}

private struct WhatMattersNowCard: View {
  let recommendation: DashboardRecommendation
  let onPrimary: () async -> Void
  let onLater: () async -> Void
  let onDismiss: (OmiAPI.TaskIntelligenceFeedbackReason?) async -> Void

  @State private var showDismissReasons = false
  @State private var choseReason = false

  var body: some View {
    VStack(alignment: .leading, spacing: 7) {
      Text(recommendation.headline)
        .scaledFont(size: 13, weight: .semibold)
        .foregroundColor(OmiColors.textPrimary)
        .lineLimit(2)

      Text(recommendation.whyNow)
        .scaledFont(size: 11)
        .foregroundColor(OmiColors.textSecondary)
        .lineLimit(3)

      if let context = recommendation.contextLabel, !context.isEmpty {
        Label(context, systemImage: "target")
          .scaledFont(size: 9)
          .foregroundColor(OmiColors.textTertiary)
          .lineLimit(1)
      }

      if !recommendation.evidencePreview.isEmpty {
        HStack(spacing: 5) {
          Image(systemName: "link")
          Text(recommendation.evidencePreview)
            .lineLimit(1)
        }
        .scaledFont(size: 9)
        .foregroundColor(OmiColors.textTertiary)
      }

      Spacer(minLength: 0)

      HStack(spacing: 6) {
        Button(recommendation.recommendedAction) { Task { await onPrimary() } }
          .buttonStyle(.borderedProminent)
          .tint(OmiColors.textPrimary)
          .foregroundColor(.black)
          .lineLimit(1)
          .accessibilityIdentifier("wmn-primary-\(recommendation.interventionID)")

        Button("Later") { Task { await onLater() } }
          .buttonStyle(.bordered)
          .accessibilityIdentifier("wmn-later-\(recommendation.interventionID)")

        Button("Dismiss") {
          choseReason = false
          showDismissReasons = true
        }
        .buttonStyle(.bordered)
        .popover(isPresented: $showDismissReasons) {
          VStack(alignment: .leading, spacing: 8) {
            Text("Optional reason")
              .scaledFont(size: 11, weight: .semibold)
            ForEach(reasonChoices, id: \.label) { choice in
              Button(choice.label) {
                choseReason = true
                Task { await onDismiss(choice.reason) }
                showDismissReasons = false
              }
              .buttonStyle(.bordered)
            }
          }
          .padding(12)
          .frame(width: 210)
        }
        .accessibilityIdentifier("wmn-dismiss-\(recommendation.interventionID)")
      }
      .controlSize(.small)
    }
    .padding(10)
    .frame(maxWidth: .infinity, minHeight: 152, alignment: .topLeading)
    .background(
      RoundedRectangle(cornerRadius: 10, style: .continuous)
        .fill(OmiColors.backgroundTertiary.opacity(0.72))
    )
    .onChange(of: showDismissReasons) { wasShowing, isShowing in
      guard wasShowing, !isShowing, !choseReason else { return }
      Task { await onDismiss(nil) }
    }
  }

  private var reasonChoices: [(label: String, reason: OmiAPI.TaskIntelligenceFeedbackReason)] {
    [
      ("Already handled", .already_handled),
      ("Not mine", .not_mine),
      ("Not useful", .not_useful),
    ]
  }
}

struct FocusedGoalsSection: View {
  @ObservedObject var store: DashboardIntelligenceStore
  let onOpenGoal: (String) async -> Void
  let onShowAll: () -> Void

  var body: some View {
    if !store.focusedGoals.isEmpty {
      HStack(spacing: 8) {
        Text("Focused goals")
          .scaledFont(size: 11, weight: .semibold)
          .foregroundColor(OmiColors.textSecondary)
        ForEach(store.focusedGoals.prefix(5), id: \.goalId) { goal in
          Button {
            Task { await onOpenGoal(goal.goalId) }
          } label: {
            Text(goal.title)
              .scaledFont(size: 10, weight: .medium)
              .lineLimit(1)
              .padding(.horizontal, 9)
              .padding(.vertical, 6)
              .background(Capsule().fill(OmiColors.backgroundSecondary.opacity(0.8)))
          }
          .buttonStyle(.plain)
          .accessibilityIdentifier("focused-goal-\(goal.goalId)")
        }
        Spacer()
        Button("All goals", action: onShowAll)
          .buttonStyle(.plain)
          .scaledFont(size: 10, weight: .medium)
          .foregroundColor(OmiColors.textSecondary)
      }
      .accessibilityIdentifier("focused-goals")
    } else if store.accountGeneration != nil {
      HStack {
        Text("No focused goals")
          .scaledFont(size: 10)
          .foregroundColor(OmiColors.textTertiary)
        Spacer()
        Button(store.goals.isEmpty ? "Add goal" : "Choose focus", action: onShowAll)
          .buttonStyle(.plain)
          .scaledFont(size: 10, weight: .medium)
      }
    }
  }
}

struct AllGoalsSheet: View {
  @ObservedObject var store: DashboardIntelligenceStore
  let onOpenGoal: (String) async -> Void
  let onDismiss: () -> Void

  @State private var showHistory = false
  @State private var focusTarget: GoalFocusTarget?
  @State private var replacementGoalID: String = ""
  @State private var showingCreateGoal = false

  var body: some View {
    VStack(alignment: .leading, spacing: 14) {
      HStack {
        Text("All goals")
          .scaledFont(size: 20, weight: .semibold)
        Spacer()
        Picker("View", selection: $showHistory) {
          Text("Current").tag(false)
          Text("History").tag(true)
        }
        .pickerStyle(.segmented)
        .frame(width: 180)
        Button("Add goal") { showingCreateGoal = true }
          .buttonStyle(.bordered)
        Button("Done", action: onDismiss)
          .buttonStyle(.borderedProminent)
          .tint(OmiColors.textPrimary)
          .foregroundColor(.black)
      }

      ScrollView {
        LazyVStack(spacing: 8) {
          ForEach(displayedGoals, id: \.goalId) { goal in
            goalRow(goal)
          }
        }
      }

      if let error = store.error {
        Text(error)
          .scaledFont(size: 10)
          .foregroundColor(OmiColors.textSecondary)
      }
    }
    .padding(20)
    .frame(width: 620, height: 540)
    .sheet(item: $focusTarget) { target in
      focusReplacementSheet(target.goal)
    }
    .sheet(isPresented: $showingCreateGoal) {
      CanonicalGoalCreateSheet(
        error: store.error,
        onSave: { title, outcome, why, criteria, idempotencyKey in
          if await store.createGoal(
            title: title,
            desiredOutcome: outcome,
            whyItMatters: why,
            successCriteria: criteria,
            idempotencyKey: idempotencyKey
          ) {
            showingCreateGoal = false
          }
        },
        onDismiss: { showingCreateGoal = false }
      )
    }
  }

  private var displayedGoals: [OmiAPI.GoalResponse] {
    showHistory ? store.endedGoals : store.currentGoals
  }

  private func goalRow(_ goal: OmiAPI.GoalResponse) -> some View {
    HStack(spacing: 12) {
      VStack(alignment: .leading, spacing: 3) {
        Text(goal.title)
          .scaledFont(size: 13, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Text(goal.desiredOutcome)
          .scaledFont(size: 10)
          .foregroundColor(OmiColors.textSecondary)
          .lineLimit(1)
      }
      Spacer()
      Text(goal.status.rawValue.capitalized)
        .scaledFont(size: 9)
        .foregroundColor(OmiColors.textTertiary)

      Button("Open") { Task { await onOpenGoal(goal.goalId) } }
        .buttonStyle(.bordered)

      if !showHistory {
        Button(goal.status == .focused ? "Unfocus" : "Focus") {
          Task {
            if goal.status == .focused {
              await store.unfocus(goalID: goal.goalId)
            } else {
              let focused = await store.focus(goalID: goal.goalId, replacing: nil)
              if !focused, store.focusReplacementGoalID == goal.goalId {
                replacementGoalID = store.focusedGoals.first?.goalId ?? ""
                focusTarget = GoalFocusTarget(goal: goal)
              }
            }
          }
        }
        .buttonStyle(.bordered)

        Menu("More") {
          Button("Pause") { Task { await store.transition(goalID: goal.goalId, status: .paused) } }
          Button("Mark achieved") { Task { await store.transition(goalID: goal.goalId, status: .achieved) } }
          Button("Abandon") { Task { await store.transition(goalID: goal.goalId, status: .abandoned) } }
        }
        .menuStyle(.borderlessButton)
        .frame(width: 55)
      }
    }
    .padding(10)
    .background(RoundedRectangle(cornerRadius: 9).fill(OmiColors.backgroundSecondary.opacity(0.7)))
  }

  private struct GoalFocusTarget: Identifiable {
    let goal: OmiAPI.GoalResponse
    var id: String { goal.goalId }
  }

  private func focusReplacementSheet(_ goal: OmiAPI.GoalResponse) -> some View {
    VStack(alignment: .leading, spacing: 14) {
      Text("Replace a focused goal")
        .scaledFont(size: 16, weight: .semibold)
      Text("Your focus set is full. Nothing is archived; the replaced goal moves to All goals.")
        .scaledFont(size: 11)
        .foregroundColor(OmiColors.textSecondary)
      Picker("Replace", selection: $replacementGoalID) {
        ForEach(store.focusedGoals, id: \.goalId) { focused in
          Text(focused.title).tag(focused.goalId)
        }
      }
      HStack {
        Button("Cancel") { focusTarget = nil }
        Spacer()
        Button("Replace focus") {
          Task {
            if await store.focus(goalID: goal.goalId, replacing: replacementGoalID) {
              focusTarget = nil
            }
          }
        }
        .buttonStyle(.borderedProminent)
        .tint(OmiColors.textPrimary)
        .foregroundColor(.black)
      }
    }
    .padding(20)
    .frame(width: 420)
  }
}

private struct CanonicalGoalCreateSheet: View {
  let error: String?
  let onSave: (String, String, String?, [String], String) async -> Void
  let onDismiss: () -> Void

  @State private var title = ""
  @State private var desiredOutcome = ""
  @State private var whyItMatters = ""
  @State private var successCriteria = ""
  @State private var createGoalOccurrenceID = UUID().uuidString.lowercased()

  var body: some View {
    VStack(alignment: .leading, spacing: 14) {
      Text("Add goal")
        .scaledFont(size: 18, weight: .semibold)
      TextField("Short name", text: $title)
        .textFieldStyle(.roundedBorder)
      TextField("Desired outcome", text: $desiredOutcome, axis: .vertical)
        .textFieldStyle(.roundedBorder)
        .lineLimit(2...4)
      TextField("Why it matters (optional)", text: $whyItMatters, axis: .vertical)
        .textFieldStyle(.roundedBorder)
        .lineLimit(2...4)
      TextField("Success criteria, one per line", text: $successCriteria, axis: .vertical)
        .textFieldStyle(.roundedBorder)
        .lineLimit(2...5)
      if let error, !error.isEmpty {
        Text(error)
          .scaledFont(size: 10)
          .foregroundColor(OmiColors.textSecondary)
      }
      HStack {
        Button("Cancel", action: onDismiss)
        Spacer()
        Button("Add goal") {
          let criteria = successCriteria.split(separator: "\n").map {
            String($0).trimmingCharacters(in: .whitespacesAndNewlines)
          }.filter { !$0.isEmpty }
          Task {
            await onSave(
              title.trimmingCharacters(in: .whitespacesAndNewlines),
              desiredOutcome.trimmingCharacters(in: .whitespacesAndNewlines),
              whyItMatters.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty,
              criteria,
              createGoalOccurrenceID
            )
          }
        }
        .buttonStyle(.borderedProminent)
        .tint(OmiColors.textPrimary)
        .foregroundColor(.black)
        .disabled(
          title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            || desiredOutcome.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
      }
    }
    .padding(20)
    .frame(width: 460)
  }
}

extension String {
  fileprivate var nilIfEmpty: String? { isEmpty ? nil : self }
}

struct CanonicalGoalDetailSheet: View {
  let detail: OmiAPI.GoalDetailProjection
  let error: String?
  let onResumeThread: (String) async -> Void
  let onStartWork: () async -> Void
  let onDismiss: () -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: 14) {
      HStack {
        VStack(alignment: .leading, spacing: 3) {
          Text(detail.goal.title)
            .scaledFont(size: 20, weight: .semibold)
          Text(detail.goal.desiredOutcome)
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textSecondary)
        }
        Spacer()
        Button("Done", action: onDismiss)
      }

      ScrollView {
        VStack(alignment: .leading, spacing: 14) {
          if let why = detail.goal.whyItMatters, !why.isEmpty {
            goalDetailBlock(title: "Why it matters", text: why)
          }
          if let criteria = detail.goal.successCriteria, !criteria.isEmpty {
            goalDetailBlock(title: "Success looks like", text: criteria.joined(separator: " • "))
          }
          if let metric = detail.goal.metric {
            goalDetailBlock(
              title: "Progress",
              text: "\(metric.current.formatted()) / \(metric.target.formatted()) \(metric.unit ?? "")"
            )
          }

          if !detail.activeThreads.isEmpty {
            Text("Active work")
              .scaledFont(size: 12, weight: .semibold)
            ForEach(detail.activeThreads, id: \.workstreamId) { work in
              HStack {
                VStack(alignment: .leading, spacing: 3) {
                  Text(work.title)
                    .scaledFont(size: 12, weight: .semibold)
                  Text(work.currentStateSummary ?? work.objective)
                    .scaledFont(size: 10)
                    .foregroundColor(OmiColors.textSecondary)
                    .lineLimit(2)
                }
                Spacer()
                Button("Continue") { Task { await onResumeThread(work.workstreamId) } }
                  .buttonStyle(.bordered)
              }
              .padding(10)
              .background(RoundedRectangle(cornerRadius: 9).fill(OmiColors.backgroundSecondary.opacity(0.7)))
            }
          }

          if !detail.progressEvents.isEmpty {
            Text("Meaningful progress")
              .scaledFont(size: 12, weight: .semibold)
            ForEach(detail.progressEvents, id: \.eventId) { event in
              HStack(alignment: .top, spacing: 8) {
                Circle().fill(OmiColors.textTertiary).frame(width: 5, height: 5).padding(.top, 5)
                Text(event.summary)
                  .scaledFont(size: 10)
                  .foregroundColor(OmiColors.textSecondary)
              }
            }
          }
        }
      }

      Button("Work on this with Omi") { Task { await onStartWork() } }
        .buttonStyle(.borderedProminent)
        .tint(OmiColors.textPrimary)
        .foregroundColor(.black)
        .accessibilityIdentifier("goal-work-with-omi-\(detail.goal.goalId)")
      if let error, !error.isEmpty {
        Text(error)
          .scaledFont(size: 10)
          .foregroundColor(OmiColors.textSecondary)
      }
    }
    .padding(20)
    .frame(width: 620, height: 600)
  }

  private func goalDetailBlock(title: String, text: String) -> some View {
    VStack(alignment: .leading, spacing: 4) {
      Text(title).scaledFont(size: 11, weight: .semibold)
      Text(text).scaledFont(size: 10).foregroundColor(OmiColors.textSecondary)
    }
  }
}
