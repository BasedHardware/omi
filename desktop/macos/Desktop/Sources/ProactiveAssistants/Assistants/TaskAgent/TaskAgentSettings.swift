import Foundation
import OmiTheme
import SwiftUI

/// Settings for the Task Agent feature
class TaskAgentSettings: ObservableObject, @unchecked Sendable {
  static let shared = TaskAgentSettings()

  /// Whether the terminal task agent feature is enabled (Run Agent / terminal icon)
  @Published var isEnabled: Bool {
    didSet { UserDefaults.standard.set(isEnabled, forKey: "taskAgentEnabled") }
  }

  /// Whether the chat task agent is enabled (Investigate button + sidebar chat)
  @Published var isChatEnabled: Bool {
    didSet { UserDefaults.standard.set(isChatEnabled, forKey: "taskChatAgentEnabled") }
  }

  /// Whether to automatically launch agents for code-related tasks
  @Published var autoLaunch: Bool {
    didSet { UserDefaults.standard.set(autoLaunch, forKey: "taskAgentAutoLaunch") }
  }

  /// Default working directory for Claude agents
  @Published var workingDirectory: String {
    didSet { UserDefaults.standard.set(workingDirectory, forKey: "taskAgentWorkingDirectory") }
  }

  /// Custom prompt prefix to prepend to all agent prompts
  @Published var customPromptPrefix: String {
    didSet { UserDefaults.standard.set(customPromptPrefix, forKey: "taskAgentPromptPrefix") }
  }

  /// Default instructions template for how the agent should work with tasks
  @Published var defaultPrompt: String {
    didSet { UserDefaults.standard.set(defaultPrompt, forKey: "taskAgentDefaultPrompt") }
  }

  /// Whether to use --dangerously-skip-permissions flag
  @Published var skipPermissions: Bool {
    didSet { UserDefaults.standard.set(skipPermissions, forKey: "taskAgentSkipPermissions") }
  }

  static let defaultPromptTemplate = """
    Analyze this task and create an implementation plan. Consider:
    1. What files need to be modified
    2. What is the approach
    3. Any potential issues or considerations
    4. Estimated complexity

    After creating the plan, wait for user approval before implementing.
    """

  private init() {
    self.isEnabled = UserDefaults.standard.bool(forKey: "taskAgentEnabled")
    self.isChatEnabled = UserDefaults.standard.bool(forKey: "taskChatAgentEnabled")
    self.autoLaunch = UserDefaults.standard.bool(forKey: "taskAgentAutoLaunch")
    self.workingDirectory = UserDefaults.standard.string(forKey: "taskAgentWorkingDirectory") ?? ""
    self.customPromptPrefix = UserDefaults.standard.string(forKey: "taskAgentPromptPrefix") ?? ""
    self.defaultPrompt = UserDefaults.standard.string(forKey: "taskAgentDefaultPrompt") ?? Self.defaultPromptTemplate
    self.skipPermissions = UserDefaults.standard.object(forKey: "taskAgentSkipPermissions") as? Bool ?? true
  }

  /// Reset to default settings
  func resetToDefaults() {
    isEnabled = false
    isChatEnabled = false
    autoLaunch = false
    workingDirectory = ""
    customPromptPrefix = ""
    defaultPrompt = Self.defaultPromptTemplate
    skipPermissions = true
  }

  /// Build the bounded canonical prompt for the workstream-backed thread.
  /// Runtime history and prior output come from the kernel/context packet,
  /// never from the legacy tmux projection.
  func buildCanonicalTaskPrompt(for task: TaskActionItem) -> String {
    var prompt = "# Task\n\n\(task.chatContext)"

    let customPrefix = customPromptPrefix
    if !customPrefix.isEmpty {
      prompt += "\n\nAdditional context:\n\(customPrefix)"
    }

    let instructions = defaultPrompt
    prompt += "\n\n## Instructions\n\n\(instructions)"

    return prompt
  }

  /// Legacy tmux prompt builder retained until Ticket 14 removes that path.
  /// `@MainActor` because it reads `TaskAgentManager.shared.getSession`, which is
  /// now main-actor-isolated; the sole caller (`TaskAgentManager.buildPrompt`) is
  /// already on the main actor.
  @MainActor
  func buildTaskPrompt(for task: TaskActionItem) -> String {
    var prompt = buildCanonicalTaskPrompt(for: task)

    // Live agent output (from running/completed session)
    if let session = TaskAgentManager.shared.getSession(for: task.id),
      let output = session.output, !output.isEmpty
    {
      let truncated = String(output.prefix(2000))
      prompt += "\n\nAgent output so far:\n\(truncated)"
    }

    return prompt
  }

  /// Validate that required tools are installed
  func validateEnvironment() async -> EnvironmentValidation {
    var result = EnvironmentValidation()

    // Check tmux
    result.tmuxInstalled = await checkCommandExists("tmux")

    // Check claude
    result.claudeInstalled = await checkCommandExists("claude")

    // Check working directory exists
    result.workingDirectoryValid = FileManager.default.fileExists(atPath: workingDirectory)

    return result
  }

  private func checkCommandExists(_ command: String) async -> Bool {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/bin/zsh")
    process.arguments = ["-c", "source ~/.zprofile 2>/dev/null; source ~/.zshrc 2>/dev/null; which \(command)"]

    let pipe = Pipe()
    process.standardOutput = pipe
    process.standardError = pipe

    do {
      try process.run()
      process.waitUntilExit()
      return process.terminationStatus == 0
    } catch {
      return false
    }
  }

  struct EnvironmentValidation {
    var tmuxInstalled: Bool = false
    var claudeInstalled: Bool = false
    var workingDirectoryValid: Bool = false

    var isValid: Bool {
      tmuxInstalled && claudeInstalled && workingDirectoryValid
    }

    var issues: [String] {
      var issues: [String] = []
      if !tmuxInstalled {
        issues.append("tmux is not installed. Install with: brew install tmux")
      }
      if !claudeInstalled {
        issues.append("Claude CLI is not installed. Install from: https://claude.ai/claude-code")
      }
      if !workingDirectoryValid {
        issues.append("Working directory does not exist")
      }
      return issues
    }
  }
}

// MARK: - Settings View

/// The Task Agent block on the Assistants settings pane.
///
/// It is **not** a `Form`. This view is hosted inside `settingsCard(…)`, which already draws the
/// card the block sits on; a `Form { }.formStyle(.grouped)` inside it drew a *second*, opaque,
/// system-grouped ground over the glass — the "two grounds" failure the glass system exists to
/// prevent — and its own inset grouping fought the pane's rhythm. So the block is laid out with the
/// same vocabulary as every other settings block: `SettingsGlassKit`'s tile, well and hairline, the
/// two type rungs glass carries, and no background of its own.
struct TaskAgentSettingsView: View {
  @ObservedObject var settings = TaskAgentSettings.shared
  @State private var validation: TaskAgentSettings.EnvironmentValidation?
  @State private var isValidating = false

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      sectionHeader(icon: "terminal", title: "Terminal Task Agent")

      row(
        title: "Enable Terminal Task Agent",
        subtitle: "Launch Claude Code agents in a terminal for code-related tasks"
      ) {
        Toggle("", isOn: $settings.isEnabled)
          .toggleStyle(OmiToggleStyle())
      }

      if settings.isEnabled {
        row(
          title: "Auto-launch for code tasks",
          subtitle: "Automatically launch agents when code/feature/bug tasks are extracted"
        ) {
          Toggle("", isOn: $settings.autoLaunch)
            .toggleStyle(OmiToggleStyle())
        }

        GlassSeparator()

        promptSection(
          title: "Custom Prompt Prefix",
          icon: "text.quote",
          footnote: "Additional context to include in every agent prompt",
          minHeight: 80,
          text: $settings.customPromptPrefix
        )

        promptSection(
          title: "Default Prompt",
          icon: "text.page",
          footnote: "Instructions appended to every agent prompt",
          minHeight: 120,
          text: $settings.defaultPrompt
        ) {
          Button("Reset to Default") {
            settings.defaultPrompt = TaskAgentSettings.defaultPromptTemplate
          }
          .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
          .disabled(settings.defaultPrompt == TaskAgentSettings.defaultPromptTemplate)
        }

        GlassSeparator()

        sectionHeader(icon: "gearshape.2", title: "Advanced")

        row(
          title: "Skip permission prompts",
          subtitle: settings.skipPermissions
            ? "Claude will execute commands without asking for permission"
            : "Use the --dangerously-skip-permissions flag"
        ) {
          Toggle("", isOn: $settings.skipPermissions)
            .toggleStyle(OmiToggleStyle())
        }
        // A caution, not a failure: `SettingsInk.notice` is the state one step below `Ink.errorRed`.
        .foregroundStyle(settings.skipPermissions ? SettingsInk.notice : Ink.secondary)

        GlassSeparator()

        environmentSection
      }
    }
    .onAppear {
      if settings.isEnabled && validation == nil {
        revalidate()
      }
    }
  }

  // MARK: - Sections

  private var environmentSection: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      sectionHeader(icon: "checkmark.shield", title: "Environment Check")

      if isValidating {
        HStack(spacing: OmiSpacing.sm) {
          ProgressView().scaleEffect(0.6)
          Text("Validating environment...")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
        }
      } else if let validation {
        VStack(alignment: .leading, spacing: OmiSpacing.sm) {
          ValidationRow(label: "tmux", isValid: validation.tmuxInstalled)
          ValidationRow(label: "Claude CLI", isValid: validation.claudeInstalled)
          ValidationRow(label: "Working directory", isValid: validation.workingDirectoryValid)

          ForEach(validation.issues, id: \.self) { issue in
            Text(issue)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.errorRed)
              .fixedSize(horizontal: false, vertical: true)
          }
        }
      }

      Button("Validate Environment") { revalidate() }
        .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
        .disabled(isValidating)
    }
  }

  @ViewBuilder
  private func promptSection<Trailing: View>(
    title: String,
    icon: String,
    footnote: String,
    minHeight: CGFloat,
    text: Binding<String>,
    @ViewBuilder trailing: () -> Trailing = { EmptyView() }
  ) -> some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      sectionHeader(icon: icon, title: title)

      TextEditor(text: text)
        .font(.system(size: 12, design: .monospaced))
        .foregroundColor(Ink.primary)
        // A `TextEditor` paints an opaque ground of its own, which on glass is a grey slab.
        .scrollContentBackground(.hidden)
        .frame(minHeight: minHeight)
        .padding(OmiSpacing.sm)
        .settingsGlassWell()

      HStack(alignment: .firstTextBaseline) {
        Text(footnote)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
        Spacer(minLength: OmiSpacing.sm)
        trailing()
      }
    }
  }

  private func sectionHeader(icon: String, title: String) -> some View {
    HStack(spacing: SettingsGlassMetrics.rowContentSpacing) {
      SettingsIconTile(symbol: icon)
      Text(title)
        .scaledFont(size: OmiType.body, weight: .semibold)
        .foregroundColor(Ink.primary)
    }
  }

  private func row<Control: View>(
    title: String,
    subtitle: String,
    @ViewBuilder control: () -> Control
  ) -> some View {
    HStack(alignment: .center, spacing: OmiSpacing.md) {
      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        Text(title)
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(Ink.primary)
        Text(subtitle)
          .scaledFont(size: OmiType.caption)
          // The bottom rung on glass is `secondary`; there is no third one to spend here.
          .foregroundColor(Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
      }
      Spacer(minLength: OmiSpacing.md)
      control()
    }
  }

  private func revalidate() {
    Task {
      isValidating = true
      validation = await settings.validateEnvironment()
      isValidating = false
    }
  }
}

/// One environment prerequisite, present or missing.
///
/// `Ink.listeningGreen` / `Ink.errorRed` rather than `.green` / `.red`: the shorthands are SwiftUI's
/// own colours and do not track the panel's pinned appearance or brighten under Increase Contrast.
struct ValidationRow: View {
  let label: String
  let isValid: Bool

  var body: some View {
    HStack(spacing: OmiSpacing.sm) {
      Image(systemName: isValid ? "checkmark.circle.fill" : "xmark.circle.fill")
        .scaledFont(size: OmiType.body)
        .foregroundColor(isValid ? Ink.listeningGreen : Ink.errorRed)
      Text(label)
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.primary)
      Spacer()
    }
    .accessibilityElement(children: .combine)
    .accessibilityLabel(Text("\(label). \(isValid ? "Installed" : "Missing")"))
  }
}

#if canImport(PreviewsMacros)
  #Preview {
    TaskAgentSettingsView()
      .frame(width: 400)
      .padding()
  }
#endif
