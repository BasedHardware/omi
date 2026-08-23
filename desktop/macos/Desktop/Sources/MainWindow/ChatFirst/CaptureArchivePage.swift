import Foundation
import OmiTheme
import SwiftUI

/// Universal device-capture archive. This is intentionally a read-only
/// archive surface: no chat history, composer, search, edit, or delete paths
/// are inherited from the legacy Conversations page.
@MainActor
struct CaptureArchivePage: View {
  @ObservedObject var navigation: ChatFirstShellNavigation
  let chatProvider: ChatProvider
  let automationRuntime: ChatFirstAutomationRuntime?
  @StateObject private var repository: CaptureArchiveRepository
  @StateObject private var playback: CapturePlaybackController

  init(
    navigation: ChatFirstShellNavigation,
    chatProvider: ChatProvider,
    automationRuntime: ChatFirstAutomationRuntime? = nil
  ) {
    self.navigation = navigation
    self.chatProvider = chatProvider
    self.automationRuntime = automationRuntime
    _repository = StateObject(wrappedValue: CaptureArchiveRepository())
    _playback = StateObject(wrappedValue: CapturePlaybackController())
  }

  var body: some View {
    HStack(spacing: 0) {
      captureList
        .frame(minWidth: 280, idealWidth: 340, maxWidth: 420)

      Divider().overlay(Ink.separator.opacity(0.45))

      captureDetail
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    .task { await repository.loadInitial() }
    .task(id: pendingFocusToken) { await resolvePendingFocusIfNeeded() }
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
            .accessibilityIdentifier("chat-first-capture-row-\(capture.id)")
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
      ScrollView {
        VStack(alignment: .leading, spacing: OmiSpacing.xxl) {
          detailHeader(capture)
          playbackSection(capture)

          summarySection(capture)

          if !capture.transcriptSegments.isEmpty {
            momentsSection(capture)
          }

          linkedItemsSection(capture)
        }
        .padding(OmiSpacing.xxl)
      }
      .accessibilityIdentifier("chat-first-capture-detail-\(capture.id)")
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

  /// The written summary, at the same fidelity the full editor shows it.
  ///
  /// This pane used to render `capture.overview` in a plain `Text`. Two things were wrong with
  /// that: the backend moved the substance of a summary into `structured.sections` and left
  /// `overview` a short compatibility paragraph, and even that paragraph is markdown — so its
  /// syntax was being drawn as literal characters. Action items are shown for the same reason the
  /// editor shows them: they are part of what the capture produced, not a different feature.
  @ViewBuilder
  private func summarySection(_ capture: ServerConversation) -> some View {
    let primary = ConversationSummarySelection.primarySummary(for: capture)
    // Same provenance rule as the full editor: an app summary replaces Omi's own, sections included.
    let sections = primary.appId == nil ? capture.structured.sections : []
    if !primary.content.isEmpty || !sections.isEmpty {
      detailSection("Summary") {
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
          if !primary.content.isEmpty {
            OmiMarkdown(text: primary.content, style: .assistant)
          }
          ConversationSummarySections(sections: sections)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
      }
    }
    if !capture.structured.actionItems.isEmpty {
      detailSection("Action items") {
        VStack(alignment: .leading, spacing: OmiSpacing.sm) {
          ForEach(capture.structured.actionItems) { item in
            HStack(alignment: .top, spacing: OmiSpacing.sm) {
              Image(systemName: item.completed ? "checkmark.circle.fill" : "circle")
                .scaledFont(size: OmiType.body)
                .foregroundStyle(Ink.secondary)
              Text(item.description)
                .scaledFont(size: OmiType.body)
                .foregroundStyle(Ink.secondary)
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
          }
        }
      }
    }
  }

  private func detailHeader(_ capture: ServerConversation) -> some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      HStack(alignment: .top, spacing: OmiSpacing.lg) {
        VStack(alignment: .leading, spacing: OmiSpacing.xs) {
          Text(capture.title)
            .scaledFont(size: OmiType.title, weight: .bold)
            .foregroundStyle(Ink.primary)
            .textSelection(.enabled)
          Text(capture.detailMetadata)
            .scaledFont(size: OmiType.caption)
            .foregroundStyle(Ink.secondary)
        }
        Spacer()
        Button("Discuss in Chat") {
          navigation.discuss(.capture(id: capture.id, momentTimestamp: nil), using: chatProvider)
        }
        .buttonStyle(.borderedProminent)
        .tint(Ink.primary)
        .accessibilityLabel("Discuss this capture in Chat")
        .accessibilityIdentifier("chat-first-capture-discuss-\(capture.id)")
      }
      if let address = capture.geolocation?.address, !address.isEmpty {
        Label(address, systemImage: "mappin.and.ellipse")
          .scaledFont(size: OmiType.caption)
          .foregroundStyle(Ink.secondary)
      }
      if !capture.participantLabels.isEmpty {
        Label(capture.participantLabels.joined(separator: ", "), systemImage: "person.2")
          .scaledFont(size: OmiType.caption)
          .foregroundStyle(Ink.secondary)
      }
    }
  }

  @ViewBuilder
  private func playbackSection(_ capture: ServerConversation) -> some View {
    detailSection("Playback") {
      if playback.isResolving {
        HStack(spacing: OmiSpacing.sm) {
          ProgressView()
          Text("Preparing audio")
            .scaledFont(size: OmiType.body)
            .foregroundStyle(Ink.secondary)
        }
      } else if let resolution = playback.resolution {
        HStack(spacing: OmiSpacing.md) {
          switch resolution {
          case .readyAggregate, .fileFallback:
            Button {
              playback.playOrPause()
            } label: {
              Label("Play audio", systemImage: "play.fill")
            }
            .buttonStyle(.bordered)
            .accessibilityLabel("Play capture audio")
            .accessibilityIdentifier("chat-first-capture-play")
          case .pending, .locked, .unavailable, .noAudio:
            Button("Check audio") {
              Task { _ = await playback.prepare(for: capture, forceRefresh: true) }
            }
            .buttonStyle(.bordered)
            .disabled(capture.isLocked)
            .accessibilityLabel("Check capture audio")
            .accessibilityIdentifier("chat-first-capture-check-audio-\(capture.id)")
          }
          Text(resolution.userFacingMessage)
            .scaledFont(size: OmiType.caption)
            .foregroundStyle(Ink.secondary)
        }
      } else {
        Button("Prepare audio") {
          Task { _ = await playback.prepare(for: capture) }
        }
        .buttonStyle(.bordered)
        .accessibilityIdentifier("chat-first-capture-prepare-audio")
      }
    }
  }

  private func momentsSection(_ capture: ServerConversation) -> some View {
    detailSection("Timestamped moments") {
      VStack(alignment: .leading, spacing: OmiSpacing.xs) {
        ForEach(Array(capture.transcriptSegments.prefix(12))) { segment in
          Button {
            Task { _ = await playback.seekToMoment(wallOffset: segment.start) }
          } label: {
            HStack(alignment: .top, spacing: OmiSpacing.md) {
              Text(segment.shortTimestamp)
                .scaledFont(size: OmiType.caption, weight: .semibold)
                .foregroundStyle(Ink.secondary)
                .frame(width: 60, alignment: .leading)
              Text(segment.text)
                .scaledFont(size: OmiType.body)
                .foregroundStyle(Ink.primary)
                .lineLimit(2)
              Spacer(minLength: 0)
              Image(systemName: "play.circle")
                .foregroundStyle(Ink.secondary)
            }
            .padding(.vertical, OmiSpacing.xs)
            .contentShape(Rectangle())
          }
          .buttonStyle(.plain)
          .disabled(!canSeekMoment(segment))
          .accessibilityLabel("Seek to \(segment.shortTimestamp): \(segment.text)")
          .accessibilityHint(canSeekMoment(segment) ? "Seeks the capture audio" : "Audio is still preparing")
          .accessibilityIdentifier("chat-first-capture-moment-\(segment.id)")
        }
      }
    }
  }

  private func linkedItemsSection(_ capture: ServerConversation) -> some View {
    detailSection("Linked to this capture") {
      let taskLinks = capture.structured.actionItems.compactMap(\.targetTaskID)
      if taskLinks.isEmpty {
        Text("No linked tasks or goals are available for this capture.")
          .scaledFont(size: OmiType.body)
          .foregroundStyle(Ink.secondary)
      } else {
        VStack(alignment: .leading, spacing: OmiSpacing.xs) {
          ForEach(taskLinks, id: \.self) { taskID in
            Button {
              navigation.open(focus: .task(id: taskID))
            } label: {
              Label("Open linked task", systemImage: "checklist")
                .scaledFont(size: OmiType.body, weight: .medium)
            }
            .buttonStyle(.bordered)
            .accessibilityLabel("Open linked task")
            .accessibilityIdentifier("chat-first-capture-task-\(taskID)")
          }
        }
      }
    }
  }

  private func detailSection<Content: View>(
    _ title: String,
    @ViewBuilder content: () -> Content
  ) -> some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      Text(title)
        .scaledFont(size: OmiType.subheading, weight: .semibold)
        .foregroundStyle(Ink.primary)
      content()
    }
    .padding(OmiSpacing.lg)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.controlRadius, style: .continuous)
        .fill(Ink.rowFill)
    )
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
    return "\(id):\(moment)"
  }

  private func select(_ capture: ServerConversation) async {
    playback.clear()
    repository.select(capture)
    guard let detail = await repository.loadDetail(id: capture.id), repository.selectedCapture?.id == capture.id else {
      return
    }
    _ = await playback.prepare(for: detail)
  }

  private func resolvePendingFocusIfNeeded() async {
    guard case .capture(let id, let momentTimestamp) = navigation.pendingFocus else { return }
    playback.clear()
    guard let detail = await repository.loadDetail(id: id), repository.selectedCapture?.id == id else { return }
    guard let resolution = await playback.prepare(for: detail), repository.selectedCapture?.id == id else { return }
    if let momentTimestamp {
      let didCompleteSeek = await playback.seekToMoment(wallOffset: momentTimestamp)
      guard
        CaptureFocusAcknowledgementPolicy.canAcknowledge(
          requestedMoment: momentTimestamp,
          resolution: resolution,
          didCompleteSeek: didCompleteSeek
        )
      else { return }
    }
    _ = navigation.acknowledgeFocus(.capture(id: id, momentTs: momentTimestamp))
  }

  private func registerAutomationActions() {
    automationRuntime?.registerCapturePage(
      openCapture: { [repository, playback] in
        guard let capture = repository.captures.first else { return false }
        playback.clear()
        repository.select(capture)
        guard let detail = await repository.loadDetail(id: capture.id), repository.selectedCapture?.id == capture.id
        else {
          return false
        }
        _ = await playback.prepare(for: detail)
        return true
      },
      discussCapture: { [navigation, chatProvider, repository] in
        guard let capture = repository.selectedCapture else { return false }
        navigation.discuss(.capture(id: capture.id, momentTimestamp: nil), using: chatProvider)
        return true
      },
      detailIsVisible: { [repository] in repository.selectedCapture != nil }
    )
  }

  private func canSeekMoment(_ segment: TranscriptSegment) -> Bool {
    guard case .readyAggregate(let artifact) = playback.resolution else { return false }
    return artifact.artifactOffset(forWallOffset: segment.start) != nil
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

  fileprivate var detailMetadata: String {
    let date = archiveDisplayDate.formatted(date: .abbreviated, time: .shortened)
    return "\(date) · \(formattedDuration)"
  }

  fileprivate var participantLabels: [String] {
    Array(Set(transcriptSegments.compactMap(\.speaker))).sorted()
  }

  fileprivate var accessibilitySummary: String {
    "\(title), \(listMetadata), Omi-device capture"
  }
}

extension TranscriptSegment {
  fileprivate var shortTimestamp: String {
    let totalSeconds = Int(start)
    return String(format: "%02d:%02d", totalSeconds / 60, totalSeconds % 60)
  }
}
