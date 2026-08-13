import OmiTheme
import SwiftUI

/// Keeps the suggested-task fetch visible without adding or removing a row
/// above the task list while the result is pending.
enum SuggestedTasksPresentationPolicy {
  static func showsSection(candidateCount: Int) -> Bool {
    candidateCount > 0
  }

  static func showsCandidates(candidateCount: Int, isExpanded: Bool) -> Bool {
    candidateCount > 0 && isExpanded
  }

  static func showsFloatingLoadingIndicator(isLoading: Bool, candidateCount: Int) -> Bool {
    isLoading && candidateCount == 0
  }

  /// Deep-link scroll targets (`suggested-<id>`) only exist while the section
  /// is expanded, so navigation must expand before scrolling.
  static func shouldExpandBeforeScrollingToCandidate(isExpanded: Bool) -> Bool {
    !isExpanded
  }
}

/// One optional dismiss-attribution choice. An explicit `Identifiable` type
/// keeps ForEach and release type-checking off tuple key-paths.
struct SuggestedCandidateDismissChoice: Identifiable, Equatable {
  let label: String
  let reason: OmiAPI.TaskIntelligenceFeedbackReason

  var id: String { reason.rawValue }
}

/// Optional dismiss attribution choices shared by the Suggested card UI and tests.
enum SuggestedCandidateDismissReasons {
  static let choices: [SuggestedCandidateDismissChoice] = [
    SuggestedCandidateDismissChoice(label: "Already handled", reason: .already_handled),
    SuggestedCandidateDismissChoice(label: "Not mine", reason: .not_mine),
    SuggestedCandidateDismissChoice(label: "Not useful", reason: .not_useful),
  ]
}

struct SuggestedTasksLoadingIndicator: View {
  var body: some View {
    HStack(spacing: 8) {
      ProgressView().controlSize(.small)
      Text("Checking Suggested")
        .scaledFont(size: 12)
        .foregroundColor(Ink.secondary)
    }
    .padding(.horizontal, 10)
    .padding(.vertical, 6)
    .background(
      Capsule()
        .fill(Ink.rowFill.opacity(0.92))
    )
    .overlay(
      Capsule()
        .stroke(Ink.separator.opacity(0.8), lineWidth: 1)
    )
    .accessibilityIdentifier("suggested-loading")
  }
}

struct SuggestedTasksSection: View {
  @ObservedObject var store: SuggestedTasksStore
  @Binding var isExpanded: Bool
  let onCanonicalChange: () async -> Void

  // Keep the type checker from inferring the header, candidate list, error,
  // and chrome in one expression. Behavior and accessibility IDs are unchanged.
  var body: some View {
    if SuggestedTasksPresentationPolicy.showsSection(candidateCount: store.candidates.count) {
      SuggestedTasksSectionChrome {
        VStack(alignment: .leading, spacing: 10) {
          SuggestedTasksSectionHeader(
            candidateCount: store.candidates.count,
            isExpanded: $isExpanded
          )
          if SuggestedTasksPresentationPolicy.showsCandidates(
            candidateCount: store.candidates.count,
            isExpanded: isExpanded
          ) {
            SuggestedTasksCandidateList(store: store, onCanonicalChange: onCanonicalChange)
          }
          if let error = store.error {
            SuggestedTasksErrorText(message: error)
          }
        }
      }
    }
  }
}

private struct SuggestedTasksSectionChrome<Content: View>: View {
  let content: Content

  init(@ViewBuilder content: () -> Content) {
    self.content = content()
  }

  var body: some View {
    content
      .padding(12)
      .background(
        RoundedRectangle(cornerRadius: 12)
          .fill(Ink.rowFill.opacity(0.72))
      )
      .overlay(
        RoundedRectangle(cornerRadius: 12)
          .stroke(Ink.separator.opacity(0.8), lineWidth: 1)
      )
      .accessibilityIdentifier("suggested-section")
  }
}

private struct SuggestedTasksSectionHeader: View {
  let candidateCount: Int
  @Binding var isExpanded: Bool

  var body: some View {
    Button(action: toggleExpanded) {
      headerLabel
    }
    .buttonStyle(.plain)
    .accessibilityLabel("Suggested tasks")
    .accessibilityValue(isExpanded ? "Expanded" : "Collapsed")
    .accessibilityAddTraits(.isButton)
    .accessibilityIdentifier("suggested-section-toggle")
  }

  private func toggleExpanded() {
    isExpanded.toggle()
  }

  private var headerLabel: some View {
    HStack(spacing: 8) {
      Image(systemName: "tray")
        .scaledFont(size: 13)
        .foregroundColor(Ink.secondary)
      Text("Suggested")
        .scaledFont(size: 15, weight: .semibold)
        .foregroundColor(Ink.primary)
      Text("\(candidateCount)")
        .scaledFont(size: 11, weight: .medium)
        .foregroundColor(Ink.secondary)
      Image(systemName: isExpanded ? "chevron.down" : "chevron.right")
        .scaledFont(size: 10, weight: .semibold)
        .foregroundColor(Ink.secondary)
      Spacer()
      Text("Quietly captured for your review")
        .scaledFont(size: 11)
        .foregroundColor(Ink.secondary)
    }
    .contentShape(Rectangle())
  }
}

private struct SuggestedTasksCandidateList: View {
  @ObservedObject var store: SuggestedTasksStore
  let onCanonicalChange: () async -> Void

  var body: some View {
    ForEach(store.candidates) { candidate in
      SuggestedTasksCandidateRow(
        store: store,
        candidate: candidate,
        onCanonicalChange: onCanonicalChange
      )
    }
  }
}

private struct SuggestedTasksCandidateRow: View {
  @ObservedObject var store: SuggestedTasksStore
  let candidate: SuggestedCandidate
  let onCanonicalChange: () async -> Void

  var body: some View {
    SuggestedCandidateCard(
      candidate: candidate,
      isBusy: store.busyCandidateIDs.contains(candidate.id),
      onDoNow: handleDoNow,
      onLater: handleLater,
      onDismiss: handleDismiss
    )
    .id("suggested-\(candidate.id)")
    .task { await handlePresented() }
  }

  private func handleDoNow(_ editedTitle: String?) async {
    _ = await store.doNow(candidateID: candidate.id, editedTitle: editedTitle)
    await onCanonicalChange()
  }

  private func handleLater() async {
    await store.later(candidateID: candidate.id)
  }

  private func handleDismiss(_ reason: OmiAPI.TaskIntelligenceFeedbackReason?) async {
    await store.dismiss(candidateID: candidate.id, reason: reason)
  }

  private func handlePresented() async {
    await store.presented(candidateID: candidate.id)
  }
}

private struct SuggestedTasksErrorText: View {
  let message: String

  var body: some View {
    Text(message)
      .scaledFont(size: 11)
      .foregroundColor(Ink.secondary)
      .accessibilityIdentifier("suggested-error")
  }
}

private struct SuggestedCandidateCard: View {
  let candidate: SuggestedCandidate
  let isBusy: Bool
  let onDoNow: (String?) async -> Void
  let onLater: () async -> Void
  let onDismiss: (OmiAPI.TaskIntelligenceFeedbackReason?) async -> Void

  @State private var title: String
  @State private var showDismissReasons = false
  @State private var selectedDismissReason = false

  init(
    candidate: SuggestedCandidate,
    isBusy: Bool,
    onDoNow: @escaping (String?) async -> Void,
    onLater: @escaping () async -> Void,
    onDismiss: @escaping (OmiAPI.TaskIntelligenceFeedbackReason?) async -> Void
  ) {
    self.candidate = candidate
    self.isBusy = isBusy
    self.onDoNow = onDoNow
    self.onLater = onLater
    self.onDismiss = onDismiss
    _title = State(initialValue: candidate.title)
  }

  var body: some View {
    SuggestedCandidateCardChrome {
      VStack(alignment: .leading, spacing: 9) {
        SuggestedCandidateTitle(candidate: candidate, title: $title)
        if let detail = candidate.detail, !detail.isEmpty {
          Text(detail)
            .scaledFont(size: 12)
            .foregroundColor(Ink.secondary)
            .lineLimit(2)
        }
        SuggestedCandidateActions(
          candidateID: candidate.id,
          isEditableTask: candidate.isEditableTask,
          isBusy: isBusy,
          title: title,
          showDismissReasons: $showDismissReasons,
          selectedDismissReason: $selectedDismissReason,
          onDoNow: onDoNow,
          onLater: onLater,
          onDismiss: onDismiss
        )
      }
    }
    .onChange(of: candidate.title) { _, updated in
      handleTitleChange(updated)
    }
    .onChange(of: showDismissReasons) { wasShowing, isShowing in
      handleDismissPopoverChange(wasShowing: wasShowing, isShowing: isShowing)
    }
  }

  private func handleTitleChange(_ updated: String) {
    if !isBusy { title = updated }
  }

  private func handleDismissPopoverChange(wasShowing: Bool, isShowing: Bool) {
    guard wasShowing, !isShowing, !selectedDismissReason else { return }
    Task { await onDismiss(nil) }
  }
}

private struct SuggestedCandidateCardChrome<Content: View>: View {
  let content: Content

  init(@ViewBuilder content: () -> Content) {
    self.content = content()
  }

  var body: some View {
    content
      .padding(12)
      .background(
        RoundedRectangle(cornerRadius: 10)
          .fill(Ink.rowFillHover.opacity(0.75))
      )
      .overlay(
        RoundedRectangle(cornerRadius: 10)
          .stroke(Ink.separator.opacity(0.6), lineWidth: 1)
      )
  }
}

private struct SuggestedCandidateTitle: View {
  let candidate: SuggestedCandidate
  @Binding var title: String

  var body: some View {
    if candidate.isEditableTask {
      TextField("Suggested task", text: $title, axis: .vertical)
        .textFieldStyle(.plain)
        .scaledFont(size: 14, weight: .medium)
        .foregroundColor(Ink.primary)
        .lineLimit(1...3)
        .accessibilityIdentifier("suggested-title-\(candidate.id)")
    } else {
      Text(candidate.title)
        .scaledFont(size: 14, weight: .medium)
        .foregroundColor(Ink.primary)
        .lineLimit(3)
    }
  }
}

private struct SuggestedCandidateActions: View {
  let candidateID: String
  let isEditableTask: Bool
  let isBusy: Bool
  let title: String
  @Binding var showDismissReasons: Bool
  @Binding var selectedDismissReason: Bool
  let onDoNow: (String?) async -> Void
  let onLater: () async -> Void
  let onDismiss: (OmiAPI.TaskIntelligenceFeedbackReason?) async -> Void

  private var isDoNowDisabled: Bool {
    title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
  }

  var body: some View {
    HStack(spacing: 8) {
      Button("Do now", action: handleDoNow)
        .buttonStyle(.borderedProminent)
        .tint(Ink.primary)
        .foregroundColor(Ink.surface)
        // Empty-title gate applies only to task creation — Later/Dismiss must stay
        // usable even when the editable title is cleared.
        .disabled(isDoNowDisabled)
        .accessibilityIdentifier("suggested-do-now-\(candidateID)")

      Button("Later", action: handleLater)
        .buttonStyle(.bordered)
        .accessibilityIdentifier("suggested-later-\(candidateID)")

      Button("Dismiss", action: handleDismissTap)
        .buttonStyle(.bordered)
        .popover(isPresented: $showDismissReasons, arrowEdge: .bottom) {
          SuggestedCandidateDismissReasonsView(
            candidateID: candidateID,
            selectedDismissReason: $selectedDismissReason,
            showDismissReasons: $showDismissReasons,
            onDismiss: onDismiss
          )
        }
        .accessibilityIdentifier("suggested-dismiss-\(candidateID)")

      Spacer()
      if isBusy { ProgressView().controlSize(.small) }
    }
    .disabled(isBusy)
  }

  private func handleDoNow() {
    let editedTitle = isEditableTask ? title : nil
    Task { await onDoNow(editedTitle) }
  }

  private func handleLater() {
    Task { await onLater() }
  }

  private func handleDismissTap() {
    selectedDismissReason = false
    showDismissReasons = true
  }
}

private struct SuggestedCandidateDismissReasonsView: View {
  let candidateID: String
  @Binding var selectedDismissReason: Bool
  @Binding var showDismissReasons: Bool
  let onDismiss: (OmiAPI.TaskIntelligenceFeedbackReason?) async -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: 10) {
      Text("Optional reason")
        .scaledFont(size: 12, weight: .semibold)
        .foregroundColor(Ink.primary)
      Text("Close this menu to dismiss without a reason.")
        .scaledFont(size: 10)
        .foregroundColor(Ink.secondary)

      ForEach(SuggestedCandidateDismissReasons.choices) { choice in
        SuggestedCandidateDismissReasonButton(
          choice: choice,
          candidateID: candidateID,
          selectedDismissReason: $selectedDismissReason,
          showDismissReasons: $showDismissReasons,
          onDismiss: onDismiss
        )
      }
    }
    .padding(12)
    .frame(width: 230)
  }
}

private struct SuggestedCandidateDismissReasonButton: View {
  let choice: SuggestedCandidateDismissChoice
  let candidateID: String
  @Binding var selectedDismissReason: Bool
  @Binding var showDismissReasons: Bool
  let onDismiss: (OmiAPI.TaskIntelligenceFeedbackReason?) async -> Void

  var body: some View {
    Button(choice.label, action: handleSelect)
      .buttonStyle(.bordered)
      .frame(maxWidth: .infinity, alignment: .leading)
      .accessibilityIdentifier("suggested-reason-\(choice.reason.rawValue)-\(candidateID)")
  }

  private func handleSelect() {
    selectedDismissReason = true
    let reason = choice.reason
    Task { await onDismiss(reason) }
    showDismissReasons = false
  }
}

struct AutoAcceptedTaskWhyButton: View {
  let task: TaskActionItem
  @State private var isPresented = false

  private var shouldShow: Bool {
    task.source != nil && task.source != "manual" && !(task.provenance ?? []).isEmpty
  }

  var body: some View {
    if shouldShow {
      Button("Why") { isPresented = true }
        .buttonStyle(.plain)
        .scaledFont(size: 10, weight: .medium)
        .foregroundColor(Ink.secondary)
        .popover(isPresented: $isPresented) {
          AutoAcceptedTaskWhyPopover(
            description: provenanceDescription,
            linkedSourceSummary: linkedSourceSummary
          )
        }
        .accessibilityIdentifier("task-why-\(task.id)")
    }
  }

  private var provenanceDescription: String {
    let source = task.source ?? ""
    if source.contains("screen") { return "It matched context on this Mac." }
    if source.contains("transcription") || source.contains("conversation") {
      return "It came from a conversation you captured."
    }
    return "It came from an authorized Omi source."
  }

  private var linkedSourceSummary: String {
    let count = (task.provenance ?? []).count
    return "\(count) linked source\(count == 1 ? "" : "s")"
  }
}

private struct AutoAcceptedTaskWhyPopover: View {
  let description: String
  let linkedSourceSummary: String

  var body: some View {
    VStack(alignment: .leading, spacing: 6) {
      Text("Why Omi added this")
        .scaledFont(size: 12, weight: .semibold)
        .foregroundColor(Ink.primary)
      Text(description)
        .scaledFont(size: 11)
        .foregroundColor(Ink.secondary)
      Text(linkedSourceSummary)
        .scaledFont(size: 10)
        .foregroundColor(Ink.secondary)
    }
    .padding(12)
    .frame(width: 220)
  }
}
