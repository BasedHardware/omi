import OmiTheme
import SwiftUI

/// Task-scoped view into one durable Omi thread. Multiple tasks may project the
/// same messages, artifacts, and kernel run while keeping distinct UI scope.
struct TaskChatPanel: View {
  @ObservedObject var taskState: TaskChatState
  @ObservedObject var coordinator: TaskChatCoordinator
  let task: TaskActionItem?
  let onClose: () -> Void
  @State private var showsThreadContext = true
  @ObservedObject private var runtimeStatusStore = AgentRuntimeStatusStore.shared

  var body: some View {
    VStack(spacing: 0) {
      // Compact header
      panelHeader

      Divider()
        .background(Ink.rowFillHover)

      if coordinator.activeTaskId == nil {
        // No task selected — prompt user to pick one
        noTaskSelectedView
      } else if coordinator.isOpening {
        // Loading state while session is being created
        VStack(spacing: OmiSpacing.md) {
          Spacer()
          ProgressView()
            .scaleEffect(0.8)
          Text("Setting up chat...")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
          Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      } else {
        if let projection = coordinator.activeThreadProjection {
          TaskThreadOverview(
            projection: projection,
            runtimeProjection: runtimeStatusStore.projection(
              for: .workstream(workstreamId: projection.workstreamID)
            ),
            isExpanded: $showsThreadContext
          )
          Divider().background(Ink.rowFillHover)
        }
        // Messages area fills all remaining space.
        // ChatInputView lives in .safeAreaInset so its height changes (editorHeight,
        // Wispr Flow insertions, etc.) never trigger re-measurement of ChatMessagesView.
        // Putting both in the same VStack caused a recursive StackLayout sizing loop
        // (FlexFrame → ZStack → StackLayout → FlexFrame at 100% CPU) every time the
        // input field changed height.
        ChatMessagesView(
          messages: taskState.messages,
          conversationIdentity: coordinator.activeTaskId ?? "task-chat-none",
          isSending: taskState.isSending,
          hasMoreMessages: false,
          isLoadingMoreMessages: false,
          isLoadingInitial: false,
          app: nil,
          onLoadMore: {},
          onRate: { _, _ in },
          localSendToken: taskState.localSendToken,
          enablesPromptTimeline: false,
          welcomeContent: { taskWelcome }
        )
        .frame(maxHeight: .infinity)
        .safeAreaInset(edge: .bottom, spacing: 0) {
          VStack(spacing: 0) {
            // Error banner
            if let error = taskState.errorMessage {
              HStack(spacing: OmiSpacing.sm) {
                Image(systemName: "exclamationmark.triangle.fill")
                  .foregroundColor(PageGlass.warning)
                  .scaledFont(size: OmiType.body)
                Text(error)
                  .scaledFont(size: OmiType.body)
                  .foregroundColor(Ink.secondary)
                Spacer()
                Button {
                  taskState.errorMessage = nil
                } label: {
                  Image(systemName: "xmark")
                    .scaledFont(size: OmiType.caption)
                    .foregroundColor(Ink.secondary)
                }
                .buttonStyle(.plain)
              }
              .padding(.horizontal, OmiSpacing.lg)
              .padding(.vertical, OmiSpacing.sm)
              .background(Ink.rowFill)
            }

            // Input area
            ChatInputView(
              onSend: { text in
                Task {
                  await taskState.sendMessage(
                    text,
                    taskContext: coordinator.activeContextPacket,
                    onAccepted: {
                      AnalyticsManager.shared.chatMessageSent(
                        messageLength: text.count, source: "task_chat")
                    }
                  )
                  await coordinator.refreshActiveThread()
                }
              },
              onStop: {
                taskState.stopAgent()
              },
              isSending: taskState.isSending,
              isStopping: taskState.isStopping,
              placeholder: "Continue this work...",
              mode: $taskState.chatMode,
              pendingText: $coordinator.pendingInputText,
              inputText: $taskState.draftText,
              // Task-thread voice routing is not wired yet; keep the shared
              // composer from exposing the global push-to-talk route here.
              showsPushToTalk: false
            )
            .padding(OmiSpacing.md)
          }
          .background(Ink.rowFill)
        }
      }
    }
    .background(Color.clear)
  }

  // MARK: - Header

  /// Abbreviate a path for display: ~/Projects/my-app
  private var displayPath: String {
    let path = coordinator.workspacePath
    let home = NSHomeDirectory()
    if path.hasPrefix(home) {
      return "~" + path.dropFirst(home.count)
    }
    return path
  }

  private var panelHeader: some View {
    VStack(spacing: 0) {
      HStack(spacing: OmiSpacing.sm) {
        Image(systemName: "bubble.left.and.bubble.right")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)

        Text(task?.description ?? coordinator.activeThreadProjection?.title ?? "Omi thread")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(Ink.primary)
          .lineLimit(1)
          .truncationMode(.tail)

        Spacer()

        Button(action: onClose) {
          Image(systemName: "xmark")
            .scaledFont(size: OmiType.caption, weight: .medium)
            .foregroundColor(Ink.secondary)
            .frame(width: 20, height: 20)
        }
        .buttonStyle(.plain)
        .help("Close chat panel")
      }

      // Workspace path indicator (only when a task is active)
      if coordinator.activeTaskId != nil {
        HStack(spacing: OmiSpacing.xxs) {
          Image(systemName: "folder")
            .scaledFont(size: OmiType.micro)
          Text(displayPath)
            .scaledFont(size: OmiType.micro)
            .lineLimit(1)
            .truncationMode(.middle)
          Spacer()
        }
        .foregroundColor(Ink.secondary)
        .padding(.top, OmiSpacing.xxs)
      }
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.sm)
    .background(Ink.rowFillHover.opacity(0.5))
  }

  // MARK: - Empty State

  private var noTaskSelectedView: some View {
    VStack(spacing: OmiSpacing.lg) {
      Spacer()

      Image(systemName: "text.bubble")
        .scaledFont(size: 36)
        .foregroundColor(Ink.secondary)

      Text("Open a task thread")
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundColor(Ink.secondary)

      Text("Choose Work on this with Omi on a task, or open one that already has a thread.")
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.secondary)
        .multilineTextAlignment(.center)
        .padding(.horizontal, OmiSpacing.xxl)

      Spacer()
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }

  // MARK: - Welcome

  private var taskWelcome: some View {
    VStack(spacing: OmiSpacing.md) {
      Image(systemName: "bubble.left.and.bubble.right")
        .scaledFont(size: 32)
        .foregroundColor(Ink.secondary)

      Text("Work on this with Omi")
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundColor(Ink.secondary)

      Text("Continue the same work as context changes, without starting over.")
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.secondary)
        .multilineTextAlignment(.center)
        .padding(.horizontal, OmiSpacing.xl)
    }
    .frame(maxWidth: .infinity)
    .padding()
    .padding(.vertical, 60)
  }
}

private struct TaskThreadOverview: View {
  let projection: TaskThreadProjection
  let runtimeProjection: AgentRunProjection?
  @Binding var isExpanded: Bool

  var body: some View {
    DisclosureGroup(isExpanded: $isExpanded) {
      ScrollView(.vertical) {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          contextSection("Current state") {
            Text(projection.currentSummary)
          }

          if let runtimeProjection, runtimeProjection.status.isActive {
            contextSection("Omi activity") {
              HStack(spacing: OmiSpacing.xs) {
                ProgressView().controlSize(.small)
                Text(
                  runtimeProjection.statusText
                    ?? runtimeProjection.status.rawValue.replacingOccurrences(of: "_", with: " ").capitalized)
              }
            }
          }

          if !projection.recentEvents.isEmpty {
            contextSection("Recent changes") {
              ForEach(projection.recentEvents, id: \.eventId) { event in
                VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                  Text(event.summary)
                  evidenceRow(event.evidenceRefs ?? [])
                }
              }
            }
          }

          if !projection.scopedTasks.isEmpty {
            contextSection("Tasks") {
              ForEach(projection.scopedTasks, id: \.id) { item in
                HStack(alignment: .top, spacing: OmiSpacing.xs) {
                  Image(systemName: item.completed ? "checkmark.circle.fill" : "circle")
                    .foregroundColor(
                      item.id == projection.activeTaskID ? Ink.primary : Ink.secondary)
                  Text(item.description_)
                    .fontWeight(item.id == projection.activeTaskID ? .semibold : .regular)
                }
              }
            }
          }

          if !projection.artifactVersions.isEmpty {
            contextSection("Artifacts") {
              ForEach(projection.artifactVersions, id: \.artifactId) { artifact in
                VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                  HStack(spacing: OmiSpacing.xs) {
                    Text(
                      artifact.logicalKey
                        .replacingOccurrences(of: "_", with: " ")
                        .replacingOccurrences(of: "-", with: " ")
                        .capitalized
                    )
                    .fontWeight(.medium)
                    Text("v\(artifact.version)")
                      .foregroundColor(Ink.secondary)
                    if artifact.supersedesArtifactId == nil {
                      Text("Original")
                        .foregroundColor(Ink.secondary)
                    }
                  }
                  evidenceRow(artifact.evidenceRefs ?? [])
                  if let url = URL(string: artifact.uri), !artifact.uri.isEmpty {
                    Link("Open artifact", destination: url)
                      .foregroundColor(Ink.primary)
                  }
                }
              }
            }
          }
        }
        .padding(.horizontal, OmiSpacing.md)
        .padding(.bottom, OmiSpacing.sm)
      }
      .frame(maxHeight: 340)
    } label: {
      HStack {
        Text("Ongoing work")
          .scaledFont(size: OmiType.caption, weight: .semibold)
        Spacer()
        Text("\(projection.scopedTasks.count) tasks · \(projection.artifactVersions.count) artifacts")
          .scaledFont(size: OmiType.micro)
          .foregroundColor(Ink.secondary)
      }
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.sm)
    .foregroundColor(Ink.secondary)
    .background(Ink.rowFill.opacity(0.5))
  }

  private func contextSection<Content: View>(
    _ title: String,
    @ViewBuilder content: () -> Content
  ) -> some View {
    VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
      Text(title.uppercased())
        .scaledFont(size: OmiType.micro, weight: .semibold)
        .foregroundColor(Ink.secondary)
      content()
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.secondary)
    }
    .frame(maxWidth: .infinity, alignment: .leading)
  }

  @ViewBuilder
  private func evidenceRow(_ refs: [OmiAPI.EvidenceRef]) -> some View {
    if !refs.isEmpty {
      HStack(spacing: OmiSpacing.xxs) {
        Image(systemName: "link")
        Text(refs.prefix(3).map { "\($0.kind.userFacingLabel):\($0.id)" }.joined(separator: " · "))
          .lineLimit(1)
          .truncationMode(.middle)
      }
      .scaledFont(size: OmiType.micro)
      .foregroundColor(Ink.secondary)
    }
  }
}

/// Placeholder shown when the chat panel is open but no task is selected.
struct TaskChatPanelPlaceholder: View {
  @ObservedObject var coordinator: TaskChatCoordinator
  let onClose: () -> Void

  var body: some View {
    VStack(spacing: 0) {
      // Header
      HStack(spacing: OmiSpacing.sm) {
        Image(systemName: "bubble.left.and.bubble.right")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
        Text("Task Chat")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(Ink.primary)
        Spacer()
        Button(action: onClose) {
          Image(systemName: "xmark")
            .scaledFont(size: OmiType.caption, weight: .medium)
            .foregroundColor(Ink.secondary)
            .frame(width: 20, height: 20)
        }
        .buttonStyle(.plain)
        .help("Close chat panel")
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)
      .background(Ink.rowFillHover.opacity(0.5))

      Divider()
        .background(Ink.rowFillHover)

      // Empty state
      VStack(spacing: OmiSpacing.lg) {
        Spacer()
        Image(systemName: coordinator.errorMessage == nil ? "text.bubble" : "exclamationmark.triangle")
          .scaledFont(size: 36)
          .foregroundColor(Ink.secondary)
        Text(coordinator.errorMessage == nil ? "Select a task to continue" : "Couldn’t open this work")
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(Ink.secondary)
        Text(coordinator.errorMessage ?? "Choose Work on this with Omi when a task deserves ongoing context.")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
          .multilineTextAlignment(.center)
          .padding(.horizontal, OmiSpacing.xxl)
        Spacer()
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    .background(Color.clear)
  }
}

extension OmiAPI.EvidenceKind {
  /// Human labels for evidence chips — never expose internal nouns like "workstream".
  var userFacingLabel: String {
    switch self {
    case .conversation: return "Conversation"
    case .memory_item: return "Memory"
    case .workstream_event: return "Thread event"
    case .artifact: return "Artifact"
    case .chat_message: return "Chat"
    case .local_screen: return "Screen"
    case .external: return "Journal"
    case ._unknown: return "Evidence"
    }
  }
}
