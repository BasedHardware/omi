import AppKit
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

/// Exit timing matches `TaskRow.handleToggle`: confirm the control, then fade
/// the row, then mutate so the row never pops away under the click.
enum SuggestedRowDismissal {
  static let checkmarkBounceNanos: UInt64 = 150_000_000
  static let checkmarkSettleNanos: UInt64 = 250_000_000
  static let exitStartNanos: UInt64 = 400_000_000
  static let exitDuration: TimeInterval = 0.3
  static let exitDurationNanos: UInt64 = 300_000_000
  static let exitOffset: CGFloat = 50

  enum Kind: Equatable {
    case complete
    case accept
    case reject

    /// Complete/accept keep the task, so the row leaves to the right like a
    /// checked item. Reject dismisses the other way so the two actions read
    /// as opposites without extra chrome.
    var offset: CGFloat {
      switch self {
      case .complete, .accept: return SuggestedRowDismissal.exitOffset
      case .reject: return -SuggestedRowDismissal.exitOffset
      }
    }
  }
}

/// One optional dismiss-attribution choice. An explicit `Identifiable` type
/// keeps ForEach and release type-checking off tuple key-paths.
struct SuggestedCandidateDismissChoice: Identifiable, Equatable {
  let label: String
  let reason: OmiAPI.TaskIntelligenceFeedbackReason

  var id: String { reason.rawValue }
}

/// Optional dismiss attribution choices shared by Suggested reject and tests.
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
  let onCompleteCreatedTask: (String) async -> Void

  var body: some View {
    if SuggestedTasksPresentationPolicy.showsSection(candidateCount: store.candidates.count) {
      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        SuggestedTasksSectionHeader(
          candidateCount: store.candidates.count,
          isExpanded: $isExpanded
        )
        if SuggestedTasksPresentationPolicy.showsCandidates(
          candidateCount: store.candidates.count,
          isExpanded: isExpanded
        ) {
          SuggestedTasksCandidateList(
            store: store,
            onCanonicalChange: onCanonicalChange,
            onCompleteCreatedTask: onCompleteCreatedTask
          )
        }
        if let error = store.error {
          SuggestedTasksErrorText(message: error)
        }
      }
      .accessibilityElement(children: .contain)
      .accessibilityIdentifier("suggested-section")
      .frame(maxWidth: .infinity, alignment: .leading)
    }
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
    HStack(spacing: OmiSpacing.sm) {
      Image(systemName: "sparkles")
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)
      Text("Suggested")
        .scaledFont(size: OmiType.subheading, weight: .semibold)
        .foregroundColor(Ink.primary)
      Text("\(candidateCount)")
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundColor(Ink.secondary)
        .padding(.horizontal, OmiSpacing.sm)
        .padding(.vertical, OmiSpacing.hairline)
        .background(
          Capsule()
            .fill(Ink.secondary.opacity(0.1))
        )
      Image(systemName: isExpanded ? "chevron.down" : "chevron.right")
        .scaledFont(size: OmiType.caption, weight: .semibold)
        .foregroundColor(Ink.secondary)
      Spacer()
    }
    .padding(.horizontal, OmiSpacing.xxs)
    .contentShape(Rectangle())
  }
}

/// SwiftUI `frame(width:)` + `Color.clear` compresses to 0 next to a
/// `maxWidth: .infinity` title. AppKit compression resistance does not.
private struct RigidLeadingGutter: NSViewRepresentable {
  var width: CGFloat

  func makeNSView(context: Context) -> NSView {
    let view = RigidLeadingGutterView(width: width)
    view.setContentHuggingPriority(.required, for: .horizontal)
    view.setContentCompressionResistancePriority(.required, for: .horizontal)
    return view
  }

  func updateNSView(_ nsView: NSView, context: Context) {
    nsView.setContentHuggingPriority(.required, for: .horizontal)
    nsView.setContentCompressionResistancePriority(.required, for: .horizontal)
  }

  func sizeThatFits(_ proposal: ProposedViewSize, nsView: NSView, context: Context) -> CGSize? {
    CGSize(width: width, height: 24)
  }
}

private final class RigidLeadingGutterView: NSView {
  private let rigidWidth: CGFloat

  init(width: CGFloat) {
    self.rigidWidth = width
    super.init(frame: NSRect(x: 0, y: 0, width: width, height: 24))
  }

  required init?(coder: NSCoder) {
    fatalError("init(coder:) has not been implemented")
  }

  override var intrinsicContentSize: NSSize {
    NSSize(width: rigidWidth, height: 24)
  }
}

private struct SuggestedTasksCandidateList: View {
  @ObservedObject var store: SuggestedTasksStore
  let onCanonicalChange: () async -> Void
  let onCompleteCreatedTask: (String) async -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      ForEach(store.candidates) { candidate in
        HStack(spacing: OmiSpacing.sm) {
          SuggestedTasksCandidateRow(
            store: store,
            candidate: candidate,
            onCanonicalChange: onCanonicalChange,
            onCompleteCreatedTask: onCompleteCreatedTask
          )
        }
        .frame(maxWidth: .infinity, alignment: .leading)
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
  }
}

private struct SuggestedTasksCandidateRow: View {
  @ObservedObject var store: SuggestedTasksStore
  let candidate: SuggestedCandidate
  let onCanonicalChange: () async -> Void
  let onCompleteCreatedTask: (String) async -> Void

  var body: some View {
    SuggestedCandidateRow(
      candidate: candidate,
      isBusy: store.busyCandidateIDs.contains(candidate.id),
      onAccept: handleAccept,
      onCheckOff: handleCheckOff,
      onReject: handleReject
    )
    .id("suggested-\(candidate.id)")
    .task { await handlePresented() }
  }

  private func handleAccept(_ editedTitle: String?) async {
    _ = await store.doNow(candidateID: candidate.id, editedTitle: editedTitle)
    await onCanonicalChange()
  }

  private func handleCheckOff(_ editedTitle: String?) async {
    guard let taskID = await store.doNow(candidateID: candidate.id, editedTitle: editedTitle)
    else { return }
    await onCompleteCreatedTask(taskID)
  }

  private func handleReject() async {
    await store.dismiss(candidateID: candidate.id, reason: nil)
  }

  private func handlePresented() async {
    await store.presented(candidateID: candidate.id)
  }
}

private struct SuggestedTasksErrorText: View {
  let message: String

  var body: some View {
    Text(message)
      .scaledFont(size: OmiType.caption)
      .foregroundColor(Ink.secondary)
      .accessibilityIdentifier("suggested-error")
  }
}

private struct SuggestedCandidateRow: View {
  let candidate: SuggestedCandidate
  let isBusy: Bool
  let onAccept: (String?) async -> Void
  let onCheckOff: (String?) async -> Void
  let onReject: () async -> Void

  @State private var title: String
  @State private var dismissal: SuggestedRowDismissal.Kind?
  @State private var rowOpacity: Double = 1.0
  @State private var rowOffset: CGFloat = 0
  @State private var checkmarkScale: CGFloat = 1.0

  private var isDismissing: Bool { dismissal != nil }
  private var isCompletingAnimation: Bool { dismissal == .complete }

  init(
    candidate: SuggestedCandidate,
    isBusy: Bool,
    onAccept: @escaping (String?) async -> Void,
    onCheckOff: @escaping (String?) async -> Void,
    onReject: @escaping () async -> Void
  ) {
    self.candidate = candidate
    self.isBusy = isBusy
    self.onAccept = onAccept
    self.onCheckOff = onCheckOff
    self.onReject = onReject
    _title = State(initialValue: candidate.title)
  }

  private var isAcceptDisabled: Bool {
    title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
  }

  var body: some View {
    HStack(alignment: .center, spacing: 0) {
      RigidLeadingGutter(width: TaskRowChrome.leadingHandleWidth)
        .frame(width: TaskRowChrome.leadingHandleWidth, height: 24)
        .accessibilityHidden(true)
        .allowsHitTesting(false)

      HStack(alignment: .center, spacing: OmiSpacing.md) {
        Button(action: handleCheckOff) {
          ZStack {
            Circle()
              .stroke(
                isCompletingAnimation ? Ink.primary : Ink.secondary, lineWidth: 1.5
              )
              .frame(width: 20, height: 20)

            if isCompletingAnimation {
              Circle()
                .fill(Ink.primary)
                .frame(width: 20, height: 20)
                .scaleEffect(checkmarkScale)

              Image(systemName: "checkmark")
                .scaledFont(size: OmiType.caption, weight: .bold)
                .foregroundColor(Ink.surface)
                .scaleEffect(checkmarkScale)
            }
          }
          .frame(width: 24, height: 24)
          .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(isBusy || isAcceptDisabled || isDismissing)
        .accessibilityLabel("Complete suggested task")
        .accessibilityIdentifier("suggested-complete-\(candidate.id)")

        VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
          SuggestedCandidateTitle(candidate: candidate, title: $title)
          if let detail = candidate.detail, !detail.isEmpty {
            Text(detail)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)
              .lineLimit(2)
          }
        }
        .frame(maxWidth: .infinity, alignment: .leading)

        HStack(spacing: OmiSpacing.xs) {
          ForEach(SuggestedActionPolicy.actions(for: isBusy ? .busy : .ready), id: \.self) { action in
            suggestedActionButton(action)
          }
          if isBusy && !isDismissing { ProgressView().controlSize(.small) }
        }
      }
      .padding(.leading, OmiSpacing.md)
      .frame(maxWidth: .infinity, alignment: .leading)
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .padding(.vertical, OmiSpacing.xxs)
    .opacity(rowOpacity)
    .offset(x: rowOffset)
    .disabled(isBusy || isDismissing)
    .allowsHitTesting(!isDismissing)
    .onChange(of: candidate.title) { _, updated in
      if !isBusy { title = updated }
    }
  }

  private func handleCheckOff() {
    playDismissal(.complete) {
      await onCheckOff(candidate.isEditableTask ? title : nil)
    }
  }

  private func playDismissal(
    _ kind: SuggestedRowDismissal.Kind,
    then commit: @escaping () async -> Void
  ) {
    guard !isBusy, dismissal == nil else { return }
    if kind != .reject, isAcceptDisabled { return }
    dismissal = kind
    if kind == .complete {
      OmiMotion.withGated(.spring(response: 0.3, dampingFraction: 0.5)) {
        checkmarkScale = 1.2
      }
    }
    Task { @MainActor in
      if !OmiMotion.reduceMotion {
        if kind == .complete {
          try? await Task.sleep(nanoseconds: SuggestedRowDismissal.checkmarkBounceNanos)
          OmiMotion.withGated(.spring(response: 0.2, dampingFraction: 0.7)) {
            checkmarkScale = 1.0
          }
          try? await Task.sleep(nanoseconds: SuggestedRowDismissal.checkmarkSettleNanos)
        } else {
          try? await Task.sleep(nanoseconds: SuggestedRowDismissal.exitStartNanos)
        }
        OmiMotion.withGated(.easeInOut(duration: SuggestedRowDismissal.exitDuration)) {
          rowOpacity = 0
          rowOffset = kind.offset
        }
        try? await Task.sleep(nanoseconds: SuggestedRowDismissal.exitDurationNanos)
      }
      await commit()
      restoreRowIfStillPresent()
    }
  }

  private func restoreRowIfStillPresent() {
    guard dismissal != nil else { return }
    OmiMotion.withGated(.easeOut(duration: 0.2)) {
      rowOpacity = 1
      rowOffset = 0
      checkmarkScale = 1
      dismissal = nil
    }
  }

  @ViewBuilder
  private func suggestedActionButton(_ action: SuggestedCardAction) -> some View {
    let isConfirmed =
      (action == .doNow && dismissal == .accept)
      || (action == .dismiss && dismissal == .reject)
    Button(action.label) {
      switch action {
      case .doNow:
        playDismissal(.accept) {
          await onAccept(candidate.isEditableTask ? title : nil)
        }
      case .dismiss:
        playDismissal(.reject) {
          await onReject()
        }
      case .later, .saveEdit, .cancelEdit:
        break
      }
    }
    .buttonStyle(.plain)
    .scaledFont(size: OmiType.caption, weight: .semibold)
    .foregroundColor(isConfirmed ? Ink.surface : Ink.primary)
    .padding(.horizontal, OmiSpacing.sm)
    .padding(.vertical, 3)
    .background(Capsule().fill(isConfirmed ? Ink.primary : Ink.rowFillHover))
    .opacity(dismissal == nil || isConfirmed ? 1 : 0.35)
    .disabled(action == .doNow && isAcceptDisabled)
    .accessibilityIdentifier("suggested-\(action.accessibilityID)-\(candidate.id)")
  }
}

private struct SuggestedCandidateTitle: View {
  let candidate: SuggestedCandidate
  @Binding var title: String

  var body: some View {
    if candidate.isEditableTask {
      TextField("Suggested task", text: $title, axis: .vertical)
        .textFieldStyle(.plain)
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundColor(Ink.primary)
        .lineLimit(1...3)
        .accessibilityIdentifier("suggested-title-\(candidate.id)")
    } else {
      Text(candidate.title)
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundColor(Ink.primary)
        .lineLimit(3)
    }
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
