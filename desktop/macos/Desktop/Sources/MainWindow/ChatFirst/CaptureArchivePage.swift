import Foundation
import OmiTheme
import SwiftUI

enum CaptureArchiveFocusRoutingPolicy {
  static func initialMoment(
    for focus: ChatFirstPendingFocus?,
    captureID: String
  ) -> TimeInterval? {
    guard case .capture(let id, let momentTimestamp) = focus, id == captureID else { return nil }
    return momentTimestamp
  }

  static func resolvedFocus(
    for focus: ChatFirstPendingFocus?,
    captureID: String,
    didResolve: Bool
  ) -> ChatFirstPendingFocus? {
    guard didResolve,
      case .capture(let id, let momentTimestamp) = focus,
      id == captureID
    else { return nil }
    return .capture(id: id, momentTs: momentTimestamp)
  }
}

/// Universal device-capture archive. It owns only the Omi-source browser and
/// its loading/selection state. Once
/// a row is selected, the record is handed to `ConversationDetailView`, which
/// is the one canonical conversation presentation (including the Omi capture
/// playback and timestamp-focus affordances).
@MainActor
struct CaptureArchivePage: View {
  @ObservedObject var navigation: ChatFirstShellNavigation
  let appState: AppState
  let chatProvider: ChatProvider
  let automationRuntime: ChatFirstAutomationRuntime?
  @StateObject private var repository: CaptureArchiveRepository
  @State private var ownerScopeGeneration: UInt64 = 0

  init(
    navigation: ChatFirstShellNavigation,
    appState: AppState,
    chatProvider: ChatProvider,
    automationRuntime: ChatFirstAutomationRuntime? = nil
  ) {
    self.navigation = navigation
    self.appState = appState
    self.chatProvider = chatProvider
    self.automationRuntime = automationRuntime
    _repository = StateObject(wrappedValue: CaptureArchiveRepository())
  }

  var body: some View {
    HStack(spacing: 0) {
      captureList
        .frame(minWidth: 280, idealWidth: 340, maxWidth: 420)

      Divider().overlay(Ink.separator.opacity(0.45))

      captureDetail
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    .task(id: ownerScopeGeneration) { await repository.loadInitial() }
    .task(id: ownerScopeGeneration) {
      if appState.folders.isEmpty {
        await appState.loadFolders()
      }
    }
    .task(id: pendingFocusToken) { await resolvePendingFocusIfNeeded() }
    .onReceive(NotificationCenter.default.publisher(for: .runtimeOwnerDidChange)) { _ in
      ownerScopeGeneration &+= 1
    }
    .onAppear { registerAutomationActions() }
    .onDisappear { automationRuntime?.unregisterCapturePage() }
    .accessibilityIdentifier("chat-first-capture-archive")
  }

  private var captureList: some View {
    VStack(alignment: .leading, spacing: 0) {
      HStack(alignment: .firstTextBaseline) {
        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          Text("Conversations")
            .scaledFont(size: OmiType.title, weight: .bold)
            .foregroundStyle(Ink.primary)
          Text("Omi-device captures")
            .scaledFont(size: OmiType.caption)
            .foregroundStyle(Ink.secondary)
        }
        Spacer()
        Button {
          Task { await repository.refresh() }
        } label: {
          Image(systemName: "arrow.clockwise")
            .scaledFont(size: OmiType.body, weight: .medium)
        }
        .buttonStyle(.plain)
        .disabled(repository.isLoading)
        .accessibilityLabel("Refresh Omi-device captures")
        .accessibilityIdentifier("chat-first-capture-refresh")
      }
      .padding(.horizontal, OmiSpacing.xl)
      .padding(.vertical, OmiSpacing.lg)

      if let error = repository.errorMessage {
        unavailableState(message: error)
      }

      if repository.isLoading && repository.captures.isEmpty {
        ProgressView("Loading Omi-device captures")
          .frame(maxWidth: .infinity, maxHeight: .infinity)
      } else if repository.captures.isEmpty, repository.errorMessage == nil {
        emptyState
      } else {
        List {
          ForEach(repository.captures) { capture in
            Button {
              Task { await select(capture) }
            } label: {
              CaptureArchiveRow(capture: capture, isSelected: repository.selectedCapture?.id == capture.id)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(capture.accessibilitySummary)
            .accessibilityIdentifier("chat-first-capture-row-" + capture.id)
            .onAppear {
              guard capture.id == repository.captures.last?.id else { return }
              Task { await repository.loadNextPage() }
            }
          }
          if repository.isLoadingMore {
            HStack {
              Spacer()
              ProgressView()
              Spacer()
            }
            .accessibilityLabel("Loading more Omi-device captures")
          }
        }
        .listStyle(.plain)
        .scrollContentBackground(.hidden)
      }
    }
    .background(Ink.rowFill)
  }

  @ViewBuilder
  private var captureDetail: some View {
    if let capture = repository.selectedCapture {
      ConversationDetailView(
        conversation: capture,
        onBack: { repository.clearSelection() },
        folders: appState.folders,
        onMoveToFolder: { conversationID, folderID in
          await appState.moveConversationToFolder(conversationID, folderId: folderID)
          await repository.refresh()
        },
        onDelete: {
          repository.clearSelection()
          Task { await repository.refresh() }
        },
        onTitleUpdated: { _ in
          // The detail view owns the mutation; re-read the archive's page so
          // the selected row and its canonical detail share the new title.
          Task { await repository.refresh() }
        },
        initialCaptureMomentTimestamp: initialCaptureMomentTimestamp(for: capture),
        onCaptureFocusResolved: { didResolve in
          acknowledgeCaptureFocus(for: capture, didResolve: didResolve)
        },
        onDiscussInChat: {
          navigation.discuss(.capture(id: capture.id, momentTimestamp: nil), using: chatProvider)
        },
        onOpenLinkedTask: { taskID in
          navigation.open(focus: .task(id: taskID))
        }
      )
      .frame(maxWidth: .infinity, maxHeight: .infinity)
      .accessibilityIdentifier("chat-first-capture-detail-" + capture.id)
    } else {
      VStack(spacing: OmiSpacing.md) {
        Image(systemName: "waveform")
          .scaledFont(size: 36, weight: .medium)
          .foregroundStyle(Ink.secondary)
        Text("Select an Omi-device capture")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundStyle(Ink.primary)
        Text("Capture details, audio, and timestamped moments will appear here.")
          .scaledFont(size: OmiType.body)
          .foregroundStyle(Ink.secondary)
          .multilineTextAlignment(.center)
          .frame(maxWidth: 340)
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
  }

  private var emptyState: some View {
    VStack(spacing: OmiSpacing.md) {
      Image(systemName: "waveform")
        .scaledFont(size: 32, weight: .medium)
        .foregroundStyle(Ink.secondary)
      Text("No Omi-device captures yet")
        .scaledFont(size: OmiType.subheading, weight: .semibold)
        .foregroundStyle(Ink.primary)
      Text("Meetings and moments captured by your Omi device will appear here.")
        .scaledFont(size: OmiType.body)
        .foregroundStyle(Ink.secondary)
        .multilineTextAlignment(.center)
        .frame(maxWidth: 280)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .accessibilityIdentifier("chat-first-capture-empty")
  }

  private func unavailableState(message: String) -> some View {
    HStack(spacing: OmiSpacing.sm) {
      Image(systemName: "arrow.triangle.2.circlepath")
        .foregroundStyle(Ink.secondary)
      Text(message)
        .scaledFont(size: OmiType.caption)
        .foregroundStyle(Ink.secondary)
      Spacer(minLength: 0)
    }
    .padding(.horizontal, OmiSpacing.lg)
    .padding(.vertical, OmiSpacing.sm)
    .background(Ink.rowFillHover)
    .accessibilityIdentifier("chat-first-capture-unavailable")
  }

  private var pendingFocusToken: String {
    guard case .capture(let id, let momentTimestamp) = navigation.pendingFocus else { return "none" }
    let moment = momentTimestamp.map { String($0) } ?? ""
    return id + ":" + moment
  }

  private func initialCaptureMomentTimestamp(for capture: ServerConversation) -> TimeInterval? {
    CaptureArchiveFocusRoutingPolicy.initialMoment(
      for: navigation.pendingFocus,
      captureID: capture.id
    )
  }

  private func select(_ capture: ServerConversation) async {
    repository.select(capture)
    _ = await repository.loadDetail(id: capture.id)
  }

  private func resolvePendingFocusIfNeeded() async {
    guard case .capture(let id, _) = navigation.pendingFocus else { return }
    repository.clearSelection()
    _ = await repository.loadDetail(id: id)
    guard repository.selectedCapture?.id == id else { return }
    // Leave both timestamped and nil-moment capture focus pending until the
    // canonical detail reports that its initial playback/focus preparation
    // has completed. This keeps acknowledgement tied to what is actually
    // visible instead of merely to the archive fetch.
  }

  private func acknowledgeCaptureFocus(for capture: ServerConversation, didResolve: Bool) {
    guard
      let focus = CaptureArchiveFocusRoutingPolicy.resolvedFocus(
        for: navigation.pendingFocus,
        captureID: capture.id,
        didResolve: didResolve
      )
    else { return }
    _ = navigation.acknowledgeFocus(focus)
  }

  private func registerAutomationActions() {
    automationRuntime?.registerCapturePage(
      openCapture: { [repository] in
        guard let capture = repository.captures.first else { return false }
        repository.select(capture)
        let detail = await repository.loadDetail(id: capture.id)
        return detail != nil || repository.selectedCapture?.id == capture.id
      },
      discussCapture: { [navigation, chatProvider, repository] in
        guard let capture = repository.selectedCapture else { return false }
        navigation.discuss(.capture(id: capture.id, momentTimestamp: nil), using: chatProvider)
        return true
      },
      detailIsVisible: { [repository] in repository.selectedCapture != nil }
    )
  }
}

private struct CaptureArchiveRow: View {
  let capture: ServerConversation
  let isSelected: Bool

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.xs) {
      Text(capture.title)
        .scaledFont(size: OmiType.body, weight: isSelected ? .semibold : .regular)
        .foregroundStyle(Ink.primary)
        .lineLimit(2)
      Text(capture.listMetadata)
        .scaledFont(size: OmiType.caption)
        .foregroundStyle(Ink.secondary)
        .lineLimit(1)
    }
    .padding(.vertical, OmiSpacing.xs)
    .padding(.horizontal, OmiSpacing.sm)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
        .fill(isSelected ? Ink.rowFillHover : Color.clear)
    )
  }
}

extension ServerConversation {
  fileprivate var archiveDisplayDate: Date { startedAt ?? createdAt }

  fileprivate var listMetadata: String {
    "\(archiveDisplayDate.formatted(.relative(presentation: .named))) · \(formattedDuration)"
  }

  fileprivate var accessibilitySummary: String {
    "\(title), \(listMetadata), Omi-device capture"
  }
}
