import Foundation
import SwiftUI

/// Settings for the Task Agent feature
class TaskAgentSettings: ObservableObject {
    static let shared = TaskAgentSettings()

    /// Whether the task agent feature is enabled
    @Published var isEnabled: Bool {
        didSet { UserDefaults.standard.set(isEnabled, forKey: "taskAgentEnabled") }
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

    /// Whether to use --dangerously-skip-permissions flag
    @Published var skipPermissions: Bool {
        didSet { UserDefaults.standard.set(skipPermissions, forKey: "taskAgentSkipPermissions") }
    }

    private init() {
        self.isEnabled = UserDefaults.standard.bool(forKey: "taskAgentEnabled")
        self.autoLaunch = UserDefaults.standard.bool(forKey: "taskAgentAutoLaunch")
        self.workingDirectory = UserDefaults.standard.string(forKey: "taskAgentWorkingDirectory") ?? ""
        self.customPromptPrefix = UserDefaults.standard.string(forKey: "taskAgentPromptPrefix") ?? ""
        self.skipPermissions = UserDefaults.standard.object(forKey: "taskAgentSkipPermissions") as? Bool ?? true
    }

    /// Reset to default settings
    func resetToDefaults() {
        isEnabled = false
        autoLaunch = false
        workingDirectory = ""
        customPromptPrefix = ""
        skipPermissions = true
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

struct TaskAgentSettingsView: View {
    @ObservedObject var settings = TaskAgentSettings.shared
    @State private var validation: TaskAgentSettings.EnvironmentValidation?
    @State private var isValidating = false
    @State private var showingDirectoryPicker = false

    var body: some View {
        Form {
            Section {
                Toggle("Enable Task Agent", isOn: $settings.isEnabled)
                    .help("Launch Claude Code agents for code-related tasks")

                if settings.isEnabled {
                    Toggle("Auto-launch for code tasks", isOn: $settings.autoLaunch)
                        .help("Automatically launch agents when code/feature/bug tasks are extracted")
                }
            } header: {
                Label("Task Agent", systemImage: "terminal")
            }

            if settings.isEnabled {
                Section {
                    HStack {
                        TextField("Working Directory", text: $settings.workingDirectory)
                            .textFieldStyle(.roundedBorder)

                        Button("Browse...") {
                            browseForDirectory()
                        }
                    }

                    Text("Claude agents will run from this directory")
                        .font(.caption)
                        .foregroundColor(.secondary)
                } header: {
                    Label("Working Directory", systemImage: "folder")
                }

                Section {
                    TextEditor(text: $settings.customPromptPrefix)
                        .frame(minHeight: 80)
                        .font(.system(.body, design: .monospaced))

                    Text("Additional context to include in every agent prompt")
                        .font(.caption)
                        .foregroundColor(.secondary)
                } header: {
                    Label("Custom Prompt Prefix", systemImage: "text.quote")
                }

                Section {
                    Toggle("Skip permission prompts", isOn: $settings.skipPermissions)
                        .help("Use --dangerously-skip-permissions flag")

                    if settings.skipPermissions {
                        Text("Warning: Claude will execute commands without asking for permission")
                            .font(.caption)
                            .foregroundColor(.orange)
                    }
                } header: {
                    Label("Advanced", systemImage: "gearshape.2")
                }

                Section {
                    if isValidating {
                        HStack {
                            ProgressView()
                                .scaleEffect(0.8)
                            Text("Validating environment...")
                                .foregroundColor(.secondary)
                        }
                    } else if let validation = validation {
                        VStack(alignment: .leading, spacing: 8) {
                            ValidationRow(label: "tmux", isValid: validation.tmuxInstalled)
                            ValidationRow(label: "Claude CLI", isValid: validation.claudeInstalled)
                            ValidationRow(label: "Working directory", isValid: validation.workingDirectoryValid)

                            if !validation.issues.isEmpty {
                                Divider()
                                ForEach(validation.issues, id: \.self) { issue in
                                    Text(issue)
                                        .font(.caption)
                                        .foregroundColor(.red)
                                }
                            }
                        }
                    }

                    Button("Validate Environment") {
                        Task {
                            isValidating = true
                            validation = await settings.validateEnvironment()
                            isValidating = false
                        }
                    }
                } header: {
                    Label("Environment Check", systemImage: "checkmark.shield")
                }
            }
        }
        .formStyle(.grouped)
        .onAppear {
            if settings.isEnabled && validation == nil {
                Task {
                    isValidating = true
                    validation = await settings.validateEnvironment()
                    isValidating = false
                }
            }
        }
    }

    private func browseForDirectory() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.canCreateDirectories = true
        panel.directoryURL = URL(fileURLWithPath: settings.workingDirectory)

        if panel.runModal() == .OK, let url = panel.url {
            settings.workingDirectory = url.path
        }
    }
}

struct ValidationRow: View {
    let label: String
    let isValid: Bool

    var body: some View {
        HStack {
            Image(systemName: isValid ? "checkmark.circle.fill" : "xmark.circle.fill")
                .foregroundColor(isValid ? .green : .red)
            Text(label)
            Spacer()
        }
    }
}

#Preview {
    TaskAgentSettingsView()
        .frame(width: 400)
}
