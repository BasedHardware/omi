import OmiTheme
import SwiftUI

// MARK: - Agent status colour

/// The one status → colour decision for the task agent.
///
/// It was written out twice — once on the row indicator and once on the detail sheet — with the two
/// copies already disagreeing about nothing only by luck. A status readout that means "this failed"
/// is exactly the kind of thing that drifts silently when the palette moves under it, so the switch
/// lives once, as a pure function, and the glass ladder it uses is a claim a test can hold.
///
/// **Two rungs, not three.** These readouts sit on the glass panel, where `Ink.tertiary` measures
/// under WCAG AA (see its documentation), so every state that is not saying something specific is
/// `Ink.secondary` rather than a fainter grey.
///
/// `@MainActor` because `TaskAgentManager.AgentStatus` is nested in a main-actor-isolated type.
enum TaskAgentStatusInk {
  @MainActor
  static func color(for status: TaskAgentManager.AgentStatus) -> Color {
    switch status {
    // In flight. Nothing to do about it yet, so it stays the reading rung.
    case .pending, .processing, .editing: return Ink.secondary
    // Done is the one state with a result to look at, so it gets the top rung.
    case .completed: return Ink.primary
    // Failed is the one state this app is allowed to raise its voice for. It used to render in the
    // faintest grey in the file, which is the opposite of what a failure has to do.
    case .failed: return Ink.errorRed
    }
  }
}

// MARK: - Task Classification Badge

/// Displays a task tag as-is
struct TaskClassificationBadge: View {
  let category: String

  var body: some View {
    Text(category.capitalized)
      .scaledFont(size: OmiType.micro, weight: .medium)
      .foregroundColor(Ink.secondary)
  }
}

// MARK: - Agent Status Indicator

/// Shows the status of a Claude agent working on a task.
/// Terminal icon launches the agent (if none) or opens Terminal directly (if running/done).
/// No detail modal — purely a quick-action control.
struct AgentStatusIndicator: View {
  let task: TaskActionItem
  @ObservedObject private var manager = TaskAgentManager.shared
  @ObservedObject private var settings = TaskAgentSettings.shared
  @State private var isLaunching = false
  @State private var showError = false
  @State private var errorMessage = ""

  private var taskId: String { task.id }

  private var session: TaskAgentManager.AgentSession? {
    manager.getSession(for: taskId)
  }

  private var statusText: String {
    guard let session = session else { return "" }
    let fileCount = session.editedFiles.count
    switch session.status {
    case .pending:
      return "Starting..."
    case .processing:
      return "Running..."
    case .editing:
      return fileCount > 0 ? "Editing (\(fileCount))" : "Editing..."
    case .completed:
      return fileCount > 0 ? "Done (\(fileCount) files)" : "Done"
    case .failed:
      return "Failed"
    }
  }

  var body: some View {
    HStack(spacing: OmiSpacing.xxs) {
      if let session = session {
        // Has a session — terminal icon opens Terminal directly
        Button {
          manager.openInTerminal(taskId: taskId)
        } label: {
          Image(systemName: "terminal")
            .scaledFont(size: OmiType.micro)
            .foregroundColor(Ink.secondary)
            .frame(width: 20, height: 20)
        }
        .buttonStyle(.plain)
        .help("Open in Terminal")

        // Status text
        HStack(spacing: OmiSpacing.xxs) {
          statusIcon(for: session.status)

          Text(statusText)
            .scaledFont(size: OmiType.micro, weight: .medium)
        }
        .foregroundColor(TaskAgentStatusInk.color(for: session.status))
      } else if settings.isEnabled {
        // No session — terminal icon launches the agent
        Button {
          launchAgent()
        } label: {
          HStack(spacing: OmiSpacing.xxs) {
            if isLaunching {
              ProgressView()
                .scaleEffect(0.5)
                .frame(width: 12, height: 12)
            } else {
              Image(systemName: "terminal")
                .scaledFont(size: OmiType.micro)
                .foregroundColor(Ink.secondary)
            }

            Text(isLaunching ? "Launching..." : "Run Agent")
              .scaledFont(size: OmiType.micro, weight: .medium)
              .foregroundColor(Ink.secondary)
          }
        }
        .buttonStyle(.plain)
        .disabled(isLaunching)
        .help("Launch Claude agent for this task")
        .alert("Agent Error", isPresented: $showError) {
          Button("OK") {}
        } message: {
          Text(errorMessage)
        }
      }
    }
  }

  private func launchAgent() {
    isLaunching = true

    Task {
      do {
        let store = TasksStore.shared
        let latestTask =
          store.incompleteTasks.first(where: { $0.id == task.id })
          ?? store.completedTasks.first(where: { $0.id == task.id })
          ?? task

        let context = TaskAgentContext()
        try await manager.launchAgent(for: latestTask, context: context)
      } catch {
        errorMessage = error.localizedDescription
        showError = true
      }
      isLaunching = false
    }
  }

  @ViewBuilder
  private func statusIcon(for status: TaskAgentManager.AgentStatus) -> some View {
    switch status {
    case .pending, .processing, .editing:
      ProgressView()
        .scaleEffect(0.5)
        .frame(width: 10, height: 10)
    case .completed:
      Image(systemName: "checkmark.circle.fill")
        .scaledFont(size: OmiType.micro)
    case .failed:
      Image(systemName: "xmark.circle.fill")
        .scaledFont(size: OmiType.micro)
    }
  }

}

// MARK: - Task Agent Detail View

/// Detailed view showing agent status, prompt, and output for a task
struct TaskAgentDetailView: View {
  let task: TaskActionItem
  var onDismiss: (() -> Void)? = nil

  @ObservedObject private var manager = TaskAgentManager.shared
  @ObservedObject private var settings = TaskAgentSettings.shared
  @Environment(\.dismiss) private var environmentDismiss

  @State private var editedPrompt: String = ""
  @State private var isEditingPrompt = false
  @State private var isRestarting = false

  private var session: TaskAgentManager.AgentSession? {
    manager.getSession(for: task.id)
  }

  private func dismissSheet() {
    if let onDismiss = onDismiss {
      onDismiss()
    } else {
      environmentDismiss()
    }
  }

  var body: some View {
    VStack(spacing: 0) {
      // Header
      header

      GlassSeparator()

      // Content
      ScrollView {
        VStack(alignment: .leading, spacing: OmiSpacing.xl) {
          // Task Info
          taskInfoSection

          // Agent Status
          if let session = session {
            agentStatusSection(session: session)
          } else if settings.isEnabled {
            launchSection
          } else {
            disabledSection
          }

          // Prompt Section
          if let session = session {
            promptSection(session: session)
          }

          // Output Section
          if let session = session, let output = session.output, !output.isEmpty {
            outputSection(output: output)
          }
        }
        .padding(OmiSpacing.xl)
      }

      GlassSeparator()

      // Footer
      footer
    }
    .frame(width: 550, height: 600)
    // No ground of its own: the sheet's glass owns it. See `glassContent()`.
    .glassContent()
    .onAppear {
      if let session = session {
        editedPrompt = session.prompt
      }
    }
  }

  // MARK: - Sections

  private var header: some View {
    HStack {
      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        Text("Task Agent")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(Ink.primary)

        HStack(spacing: OmiSpacing.xxs) {
          ForEach(task.tags.prefix(3), id: \.self) { tag in
            TaskClassificationBadge(category: tag)
          }
        }
      }

      Spacer()

      DismissButton(action: dismissSheet)
    }
    .padding(.horizontal, OmiSpacing.xl)
    .padding(.vertical, OmiSpacing.lg)
  }

  private var taskInfoSection: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      Text("Task")
        .scaledFont(size: OmiType.body, weight: .semibold)
        .foregroundColor(Ink.secondary)

      Text(task.description)
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.primary)
        .padding(OmiSpacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCard(cornerRadius: PageGlass.rowRadius)
    }
  }

  private func agentStatusSection(session: TaskAgentManager.AgentSession) -> some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      Text("Agent Status")
        .scaledFont(size: OmiType.body, weight: .semibold)
        .foregroundColor(Ink.secondary)

      HStack(spacing: OmiSpacing.lg) {
        // Status badge
        HStack(spacing: OmiSpacing.sm) {
          Image(systemName: session.status.icon)
            .scaledFont(size: OmiType.subheading)
            .foregroundColor(TaskAgentStatusInk.color(for: session.status))

          VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
            HStack(spacing: OmiSpacing.xs) {
              Text(session.status.displayName)
                .scaledFont(size: OmiType.body, weight: .medium)
                .foregroundColor(Ink.primary)

              if !session.editedFiles.isEmpty {
                Text("\(session.editedFiles.count) files edited")
                  .scaledFont(size: OmiType.caption, weight: .medium)
                  .foregroundColor(Ink.secondary)
                  .padding(.horizontal, OmiSpacing.xs)
                  .padding(.vertical, OmiSpacing.hairline)
                  .glassChip()
              }
            }

            Text("Session: \(session.sessionName)")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)
          }
        }

        Spacer()

        // Action buttons
        HStack(spacing: OmiSpacing.sm) {
          Button {
            manager.openInTerminal(taskId: task.id)
          } label: {
            HStack(spacing: OmiSpacing.xxs) {
              Image(systemName: "terminal")
                .scaledFont(size: OmiType.caption)
              Text("Open Terminal")
                .scaledFont(size: OmiType.caption, weight: .medium)
            }
            .foregroundColor(Ink.primary)
            .padding(.horizontal, OmiSpacing.sm)
            .padding(.vertical, OmiSpacing.xs)
            .glassChip()
          }
          .buttonStyle(.plain)

          if session.status == .processing || session.status == .pending || session.status == .editing {
            Button {
              manager.stopAgent(taskId: task.id)
            } label: {
              HStack(spacing: OmiSpacing.xxs) {
                Image(systemName: "stop.fill")
                  .scaledFont(size: OmiType.caption)
                Text("Stop")
                  .scaledFont(size: OmiType.caption, weight: .medium)
              }
              .foregroundColor(Ink.primary)
              .padding(.horizontal, OmiSpacing.sm)
              .padding(.vertical, OmiSpacing.xs)
              .glassChip()
            }
            .buttonStyle(.plain)
          }
        }
      }
      .padding(OmiSpacing.md)
      .glassCard(cornerRadius: PageGlass.rowRadius)
    }
  }

  private var launchSection: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      Text("Agent Status")
        .scaledFont(size: OmiType.body, weight: .semibold)
        .foregroundColor(Ink.secondary)

      VStack(spacing: OmiSpacing.md) {
        Image(systemName: "terminal")
          .scaledFont(size: 32)
          .foregroundColor(Ink.secondary)

        Text("No agent running")
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(Ink.secondary)

        Text("Launch a Claude agent to analyze this task and create an implementation plan.")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
          .multilineTextAlignment(.center)
      }
      .frame(maxWidth: .infinity)
      .padding(OmiSpacing.xl)
      .glassCard(cornerRadius: PageGlass.rowRadius)
    }
  }

  private var disabledSection: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      Text("Agent Status")
        .scaledFont(size: OmiType.body, weight: .semibold)
        .foregroundColor(Ink.secondary)

      VStack(spacing: OmiSpacing.md) {
        Image(systemName: "terminal")
          .scaledFont(size: 32)
          .foregroundColor(Ink.secondary)

        Text("Task Agent Disabled")
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(Ink.secondary)

        Text("Enable Task Agent in settings to launch Claude agents for code-related tasks.")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
          .multilineTextAlignment(.center)

        Button {
          NotificationCenter.default.post(
            name: .navigateToTaskSettings,
            object: nil
          )
          dismissSheet()
        } label: {
          Text("Open Settings")
            .scaledFont(size: OmiType.caption, weight: .medium)
            .foregroundColor(Ink.secondary)
        }
        .buttonStyle(.plain)
      }
      .frame(maxWidth: .infinity)
      .padding(OmiSpacing.xl)
      .glassCard(cornerRadius: PageGlass.rowRadius)
    }
  }

  private func promptSection(session: TaskAgentManager.AgentSession) -> some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      HStack {
        Text("Prompt")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(Ink.secondary)

        Spacer()

        if !isEditingPrompt {
          Button {
            editedPrompt = session.prompt
            isEditingPrompt = true
          } label: {
            HStack(spacing: OmiSpacing.xxs) {
              Image(systemName: "pencil")
                .scaledFont(size: OmiType.micro)
              Text("Edit")
                .scaledFont(size: OmiType.caption, weight: .medium)
            }
            .foregroundColor(Ink.secondary)
          }
          .buttonStyle(.plain)
        }
      }

      if isEditingPrompt {
        VStack(spacing: OmiSpacing.sm) {
          TextEditor(text: $editedPrompt)
            .scaledFont(size: OmiType.caption, design: .monospaced)
            .foregroundColor(Ink.primary)
            // A `TextEditor` paints an opaque ground of its own, which on glass is a grey slab.
            .scrollContentBackground(.hidden)
            .frame(minHeight: 150)
            .padding(OmiSpacing.sm)
            .glassField(cornerRadius: PageGlass.rowRadius)

          HStack {
            Button("Cancel") {
              isEditingPrompt = false
              editedPrompt = session.prompt
            }
            .buttonStyle(OmiButtonStyle(.secondary, size: .compact))

            Spacer()

            Button {
              Task {
                await restartWithNewPrompt()
              }
            } label: {
              if isRestarting {
                ProgressView()
                  .scaleEffect(0.8)
              } else {
                Text("Restart Agent")
              }
            }
            .buttonStyle(OmiButtonStyle(.primary, size: .compact))
            .disabled(isRestarting || editedPrompt.isEmpty)
          }
        }
      } else {
        Text(session.prompt)
          .scaledFont(size: OmiType.caption, design: .monospaced)
          .foregroundColor(Ink.secondary)
          .padding(OmiSpacing.md)
          .frame(maxWidth: .infinity, alignment: .leading)
          .glassCard(cornerRadius: PageGlass.rowRadius)
      }
    }
  }

  private func outputSection(output: String) -> some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      HStack {
        Text("Agent Output")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(Ink.secondary)

        Spacer()

        Button {
          NSPasteboard.general.clearContents()
          NSPasteboard.general.setString(output, forType: .string)
        } label: {
          HStack(spacing: OmiSpacing.xxs) {
            Image(systemName: "doc.on.doc")
              .scaledFont(size: OmiType.micro)
            Text("Copy")
              .scaledFont(size: OmiType.caption, weight: .medium)
          }
          .foregroundColor(Ink.secondary)
        }
        .buttonStyle(.plain)
      }

      ScrollView {
        Text(output)
          .scaledFont(size: OmiType.caption, design: .monospaced)
          .foregroundColor(Ink.secondary)
          .frame(maxWidth: .infinity, alignment: .leading)
      }
      .frame(maxHeight: 200)
      .padding(OmiSpacing.md)
      .glassField(cornerRadius: PageGlass.rowRadius)
    }
  }

  private var footer: some View {
    HStack {
      if session != nil {
        Button("Remove Session") {
          manager.removeSession(taskId: task.id)
        }
        .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
      }

      Spacer()

      Button("Close") {
        dismissSheet()
      }
      .buttonStyle(OmiButtonStyle(.primary, size: .compact))
    }
    .padding(OmiSpacing.xl)
  }

  // MARK: - Helpers

  private func restartWithNewPrompt() async {
    isRestarting = true

    do {
      let context = TaskAgentContext()
      try await manager.updatePromptAndRestart(
        taskId: task.id,
        newPrompt: editedPrompt,
        context: context
      )
      isEditingPrompt = false
    } catch {
      // Handle error
    }

    isRestarting = false
  }
}

// MARK: - Preview

#if canImport(PreviewsMacros)
  #Preview("Classification Badge") {
    VStack(spacing: OmiSpacing.sm) {
      ForEach(["feature", "bug", "code", "work", "personal", "research"], id: \.self) { category in
        TaskClassificationBadge(category: category)
      }
    }
    .padding()
  }
#endif

#if canImport(PreviewsMacros)
  #Preview("Agent Status") {
    VStack(spacing: OmiSpacing.lg) {
      AgentStatusIndicator(
        task: TaskActionItem(id: "test-1", description: "Test task", completed: false, createdAt: Date()))
    }
    .padding()
  }
#endif
