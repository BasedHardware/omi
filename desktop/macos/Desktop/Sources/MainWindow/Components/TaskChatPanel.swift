import SwiftUI
import OmiTheme

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
                .background(OmiColors.backgroundTertiary)

            if coordinator.activeTaskId == nil {
                // No task selected — prompt user to pick one
                noTaskSelectedView
            } else if coordinator.isOpening {
                // Loading state while session is being created
                VStack(spacing: 12) {
                    Spacer()
                    ProgressView()
                        .scaleEffect(0.8)
                    Text("Setting up chat...")
                        .scaledFont(size: 12)
                        .foregroundColor(OmiColors.textTertiary)
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
                    Divider().background(OmiColors.backgroundTertiary)
                }
                // Messages area fills all remaining space.
                // ChatInputView lives in .safeAreaInset so its height changes (editorHeight,
                // Wispr Flow insertions, etc.) never trigger re-measurement of ChatMessagesView.
                // Putting both in the same VStack caused a recursive StackLayout sizing loop
                // (FlexFrame → ZStack → StackLayout → FlexFrame at 100% CPU) every time the
                // input field changed height.
                ChatMessagesView(
                    messages: taskState.messages,
                    isSending: taskState.isSending,
                    hasMoreMessages: false,
                    isLoadingMoreMessages: false,
                    isLoadingInitial: false,
                    app: nil,
                    onLoadMore: { },
                    onRate: { _, _ in },
                    localSendToken: taskState.localSendToken,
                    welcomeContent: { taskWelcome }
                )
                .frame(maxHeight: .infinity)
                .safeAreaInset(edge: .bottom, spacing: 0) {
                    VStack(spacing: 0) {
                        // Error banner
                        if let error = taskState.errorMessage {
                            HStack(spacing: 8) {
                                Image(systemName: "exclamationmark.triangle.fill")
                                    .foregroundColor(OmiColors.warning)
                                    .scaledFont(size: 14)
                                Text(error)
                                    .scaledFont(size: 13)
                                    .foregroundColor(OmiColors.textSecondary)
                                Spacer()
                                Button {
                                    taskState.errorMessage = nil
                                } label: {
                                    Image(systemName: "xmark")
                                        .scaledFont(size: 11)
                                        .foregroundColor(OmiColors.textTertiary)
                                }
                                .buttonStyle(.plain)
                            }
                            .padding(.horizontal, 16)
                            .padding(.vertical, 10)
                            .background(OmiColors.backgroundSecondary)
                        }

                        // Input area
                        ChatInputView(
                            onSend: { text in
                                AnalyticsManager.shared.chatMessageSent(messageLength: text.count, source: "task_chat")
                                Task {
                                    await taskState.sendMessage(
                                        text,
                                        taskContext: coordinator.activeContextPacket
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
                            inputText: $taskState.draftText
                        )
                        .padding(12)
                    }
                    .background(OmiColors.backgroundPrimary)
                }
            }
        }
        .background(OmiColors.backgroundPrimary)
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
            HStack(spacing: 8) {
                Image(systemName: "bubble.left.and.bubble.right")
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textSecondary)

                Text(task?.description ?? coordinator.activeThreadProjection?.title ?? "Omi thread")
                    .scaledFont(size: 13, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)
                    .lineLimit(1)
                    .truncationMode(.tail)

                Spacer()

                Button(action: onClose) {
                    Image(systemName: "xmark")
                        .scaledFont(size: 11, weight: .medium)
                        .foregroundColor(OmiColors.textTertiary)
                        .frame(width: 20, height: 20)
                }
                .buttonStyle(.plain)
                .help("Close chat panel")
            }

            // Workspace path indicator (only when a task is active)
            if coordinator.activeTaskId != nil {
                HStack(spacing: 4) {
                    Image(systemName: "folder")
                        .scaledFont(size: 9)
                    Text(displayPath)
                        .scaledFont(size: 10)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    Spacer()
                }
                .foregroundColor(OmiColors.textTertiary.opacity(0.7))
                .padding(.top, 4)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(OmiColors.backgroundTertiary.opacity(0.5))
    }

    // MARK: - Empty State

    private var noTaskSelectedView: some View {
        VStack(spacing: 16) {
            Spacer()

            Image(systemName: "text.bubble")
                .scaledFont(size: 36)
                .foregroundColor(OmiColors.textTertiary.opacity(0.4))

            Text("Open a task thread")
                .scaledFont(size: 14, weight: .medium)
                .foregroundColor(OmiColors.textSecondary)

            Text("Choose Work on this with Omi on a task, or open one that already has a thread.")
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textTertiary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 24)

            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Welcome

    private var taskWelcome: some View {
        VStack(spacing: 12) {
            Image(systemName: "bubble.left.and.bubble.right")
                .scaledFont(size: 32)
                .foregroundColor(OmiColors.textTertiary.opacity(0.5))

            Text("Work on this with Omi")
                .scaledFont(size: 14, weight: .medium)
                .foregroundColor(OmiColors.textSecondary)

            Text("Continue the same work as context changes, without starting over.")
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textTertiary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 20)
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
                VStack(alignment: .leading, spacing: 12) {
                    contextSection("Current state") {
                        Text(projection.currentSummary)
                    }

                    if let runtimeProjection, runtimeProjection.status.isActive {
                        contextSection("Omi activity") {
                            HStack(spacing: 6) {
                                ProgressView().controlSize(.small)
                                Text(runtimeProjection.statusText ?? runtimeProjection.status.rawValue.replacingOccurrences(of: "_", with: " ").capitalized)
                            }
                        }
                    }

                    if !projection.recentEvents.isEmpty {
                        contextSection("Recent changes") {
                            ForEach(projection.recentEvents, id: \.eventId) { event in
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(event.summary)
                                    evidenceRow(event.evidenceRefs ?? [])
                                }
                            }
                        }
                    }

                    if !projection.scopedTasks.isEmpty {
                        contextSection("Tasks") {
                            ForEach(projection.scopedTasks, id: \.id) { item in
                                HStack(alignment: .top, spacing: 6) {
                                    Image(systemName: item.completed ? "checkmark.circle.fill" : "circle")
                                        .foregroundColor(item.id == projection.activeTaskID ? OmiColors.textPrimary : OmiColors.textTertiary)
                                    Text(item.description_)
                                        .fontWeight(item.id == projection.activeTaskID ? .semibold : .regular)
                                }
                            }
                        }
                    }

                    if !projection.artifactVersions.isEmpty {
                        contextSection("Artifacts") {
                            ForEach(projection.artifactVersions, id: \.artifactId) { artifact in
                                VStack(alignment: .leading, spacing: 3) {
                                    HStack(spacing: 6) {
                                        Text(
                                            artifact.logicalKey
                                                .replacingOccurrences(of: "_", with: " ")
                                                .replacingOccurrences(of: "-", with: " ")
                                                .capitalized
                                        )
                                            .fontWeight(.medium)
                                        Text("v\(artifact.version)")
                                            .foregroundColor(OmiColors.textTertiary)
                                        if artifact.supersedesArtifactId == nil {
                                            Text("Original")
                                                .foregroundColor(OmiColors.textTertiary)
                                        }
                                    }
                                    evidenceRow(artifact.evidenceRefs ?? [])
                                    if let url = URL(string: artifact.uri), !artifact.uri.isEmpty {
                                        Link("Open artifact", destination: url)
                                            .foregroundColor(OmiColors.textPrimary)
                                    }
                                }
                            }
                        }
                    }
                }
                .padding(.horizontal, 12)
                .padding(.bottom, 10)
            }
            .frame(maxHeight: 340)
        } label: {
            HStack {
                Text("Ongoing work")
                    .scaledFont(size: 11, weight: .semibold)
                Spacer()
                Text("\(projection.scopedTasks.count) tasks · \(projection.artifactVersions.count) artifacts")
                    .scaledFont(size: 10)
                    .foregroundColor(OmiColors.textTertiary)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .foregroundColor(OmiColors.textSecondary)
        .background(OmiColors.backgroundSecondary.opacity(0.5))
    }

    private func contextSection<Content: View>(
        _ title: String,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(title.uppercased())
                .scaledFont(size: 9, weight: .semibold)
                .foregroundColor(OmiColors.textTertiary)
            content()
                .scaledFont(size: 11)
                .foregroundColor(OmiColors.textSecondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder
    private func evidenceRow(_ refs: [OmiAPI.EvidenceRef]) -> some View {
        if !refs.isEmpty {
            HStack(spacing: 4) {
                Image(systemName: "link")
                Text(refs.prefix(3).map { "\($0.kind.userFacingLabel):\($0.id)" }.joined(separator: " · "))
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            .scaledFont(size: 9)
            .foregroundColor(OmiColors.textTertiary)
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
            HStack(spacing: 8) {
                Image(systemName: "bubble.left.and.bubble.right")
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textSecondary)
                Text("Task Chat")
                    .scaledFont(size: 13, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)
                Spacer()
                Button(action: onClose) {
                    Image(systemName: "xmark")
                        .scaledFont(size: 11, weight: .medium)
                        .foregroundColor(OmiColors.textTertiary)
                        .frame(width: 20, height: 20)
                }
                .buttonStyle(.plain)
                .help("Close chat panel")
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(OmiColors.backgroundTertiary.opacity(0.5))

            Divider()
                .background(OmiColors.backgroundTertiary)

            // Empty state
            VStack(spacing: 16) {
                Spacer()
                Image(systemName: coordinator.errorMessage == nil ? "text.bubble" : "exclamationmark.triangle")
                    .scaledFont(size: 36)
                    .foregroundColor(OmiColors.textTertiary.opacity(0.4))
                Text(coordinator.errorMessage == nil ? "Select a task to continue" : "Couldn’t open this work")
                    .scaledFont(size: 14, weight: .medium)
                    .foregroundColor(OmiColors.textSecondary)
                Text(coordinator.errorMessage ?? "Choose Work on this with Omi when a task deserves ongoing context.")
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textTertiary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 24)
                Spacer()
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .background(OmiColors.backgroundPrimary)
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
