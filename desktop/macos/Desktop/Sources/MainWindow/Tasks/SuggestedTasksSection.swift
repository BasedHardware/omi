import OmiTheme
import SwiftUI

struct SuggestedTasksSection: View {
  @ObservedObject var store: SuggestedTasksStore
  let onCanonicalChange: () async -> Void

  var body: some View {
    if store.isLoading && store.candidates.isEmpty {
      HStack(spacing: 8) {
        ProgressView().controlSize(.small)
        Text("Checking Suggested")
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.textTertiary)
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      .padding(.vertical, 8)
      .accessibilityIdentifier("suggested-loading")
    } else if !store.candidates.isEmpty {
      VStack(alignment: .leading, spacing: 10) {
        HStack(spacing: 8) {
          Image(systemName: "tray")
            .scaledFont(size: 13)
            .foregroundColor(OmiColors.textSecondary)
          Text("Suggested")
            .scaledFont(size: 15, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
          Text("\(store.candidates.count)")
            .scaledFont(size: 11, weight: .medium)
            .foregroundColor(OmiColors.textTertiary)
          Spacer()
          Text("Quietly captured for your review")
            .scaledFont(size: 11)
            .foregroundColor(OmiColors.textTertiary)
        }

        ForEach(store.candidates) { candidate in
          SuggestedCandidateCard(
            candidate: candidate,
            isBusy: store.busyCandidateIDs.contains(candidate.id),
            onDoNow: { editedTitle in
              _ = await store.doNow(candidateID: candidate.id, editedTitle: editedTitle)
              await onCanonicalChange()
            },
            onLater: { await store.later(candidateID: candidate.id) },
            onDismiss: { reason in
              await store.dismiss(candidateID: candidate.id, reason: reason)
            }
          )
          .id("suggested-\(candidate.id)")
          .task { await store.presented(candidateID: candidate.id) }
        }

        if let error = store.error {
          Text(error)
            .scaledFont(size: 11)
            .foregroundColor(OmiColors.textSecondary)
            .accessibilityIdentifier("suggested-error")
        }
      }
      .padding(12)
      .background(
        RoundedRectangle(cornerRadius: 12)
          .fill(OmiColors.backgroundSecondary.opacity(0.72))
      )
      .overlay(
        RoundedRectangle(cornerRadius: 12)
          .stroke(OmiColors.border.opacity(0.8), lineWidth: 1)
      )
      .accessibilityIdentifier("suggested-section")
    }
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
    VStack(alignment: .leading, spacing: 9) {
      if candidate.isEditableTask {
        TextField("Suggested task", text: $title, axis: .vertical)
          .textFieldStyle(.plain)
          .scaledFont(size: 14, weight: .medium)
          .foregroundColor(OmiColors.textPrimary)
          .lineLimit(1...3)
          .accessibilityIdentifier("suggested-title-\(candidate.id)")
      } else {
        Text(candidate.title)
          .scaledFont(size: 14, weight: .medium)
          .foregroundColor(OmiColors.textPrimary)
          .lineLimit(3)
      }

      if let detail = candidate.detail, !detail.isEmpty {
        Text(detail)
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.textSecondary)
          .lineLimit(2)
      }

      HStack(spacing: 8) {
        Label(candidate.provenanceLabel, systemImage: "link")
        if candidate.evidenceCount > 0 {
          Text("\(candidate.evidenceCount) source\(candidate.evidenceCount == 1 ? "" : "s")")
        }
      }
      .scaledFont(size: 10)
      .foregroundColor(OmiColors.textTertiary)

      HStack(spacing: 8) {
        Button("Do now") {
          Task { await onDoNow(candidate.isEditableTask ? title : nil) }
        }
        .buttonStyle(.borderedProminent)
        .tint(OmiColors.textPrimary)
        .foregroundColor(.black)
        // Empty-title gate applies only to task creation — Later/Dismiss must stay
        // usable even when the editable title is cleared.
        .disabled(title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        .accessibilityIdentifier("suggested-do-now-\(candidate.id)")

        Button("Later") {
          Task { await onLater() }
        }
        .buttonStyle(.bordered)
        .accessibilityIdentifier("suggested-later-\(candidate.id)")

        Button("Dismiss") {
          selectedDismissReason = false
          showDismissReasons = true
        }
        .buttonStyle(.bordered)
        .popover(isPresented: $showDismissReasons, arrowEdge: .bottom) {
          dismissReasons
        }
        .accessibilityIdentifier("suggested-dismiss-\(candidate.id)")

        Spacer()
        if isBusy { ProgressView().controlSize(.small) }
      }
      .disabled(isBusy)
    }
    .padding(12)
    .background(
      RoundedRectangle(cornerRadius: 10)
        .fill(OmiColors.backgroundTertiary.opacity(0.75))
    )
    .overlay(
      RoundedRectangle(cornerRadius: 10)
        .stroke(OmiColors.border.opacity(0.6), lineWidth: 1)
    )
    .onChange(of: candidate.title) { _, updated in
      if !isBusy { title = updated }
    }
    .onChange(of: showDismissReasons) { wasShowing, isShowing in
      guard wasShowing, !isShowing, !selectedDismissReason else { return }
      Task { await onDismiss(nil) }
    }
  }

  private var dismissReasons: some View {
    VStack(alignment: .leading, spacing: 10) {
      Text("Optional reason")
        .scaledFont(size: 12, weight: .semibold)
        .foregroundColor(OmiColors.textPrimary)
      Text("Close this menu to dismiss without a reason.")
        .scaledFont(size: 10)
        .foregroundColor(OmiColors.textTertiary)

      ForEach(dismissReasonChoices, id: \.label) { choice in
        Button(choice.label) {
          selectedDismissReason = true
          let reasonRaw = choice.reason.rawValue
          Task {
            await onDismiss(OmiAPI.TaskIntelligenceFeedbackReason(rawValue: reasonRaw))
          }
          showDismissReasons = false
        }
        .buttonStyle(.bordered)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityIdentifier("suggested-reason-\(choice.reason.rawValue)-\(candidate.id)")
      }
    }
    .padding(12)
    .frame(width: 230)
  }

  private var dismissReasonChoices: [(label: String, reason: OmiAPI.TaskIntelligenceFeedbackReason)] {
    [
      ("Already handled", .already_handled),
      ("Not mine", .not_mine),
      ("Not useful", .not_useful),
    ]
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
        .foregroundColor(OmiColors.textSecondary)
        .popover(isPresented: $isPresented) {
          VStack(alignment: .leading, spacing: 6) {
            Text("Why Omi added this")
              .scaledFont(size: 12, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
            Text(provenanceDescription)
              .scaledFont(size: 11)
              .foregroundColor(OmiColors.textSecondary)
            Text("\((task.provenance ?? []).count) linked source\((task.provenance ?? []).count == 1 ? "" : "s")")
              .scaledFont(size: 10)
              .foregroundColor(OmiColors.textTertiary)
          }
          .padding(12)
          .frame(width: 220)
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
}
