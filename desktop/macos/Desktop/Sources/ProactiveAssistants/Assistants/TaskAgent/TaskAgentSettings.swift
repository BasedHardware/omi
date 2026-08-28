import Foundation
import OmiTheme
import SwiftUI

/// Settings for the task chat thread.
///
/// The terminal task agent (tmux + CLI) and every "execute this task" affordance
/// were removed: tasks are a list the user keeps, not an agent surface. What
/// remains is the workstream-backed chat thread and the prompt that opens it.
class TaskAgentSettings: ObservableObject, @unchecked Sendable {
  static let shared = TaskAgentSettings()

  /// Whether "Work on this with Omi" (the task chat thread) is available.
  @Published var isChatEnabled: Bool {
    didSet { UserDefaults.standard.set(isChatEnabled, forKey: "taskChatAgentEnabled") }
  }

  /// Working directory handed to the task chat thread.
  @Published var workingDirectory: String {
    didSet { UserDefaults.standard.set(workingDirectory, forKey: "taskAgentWorkingDirectory") }
  }

  /// Optional user prefix prepended to the canonical task prompt.
  @Published var customPromptPrefix: String {
    didSet { UserDefaults.standard.set(customPromptPrefix, forKey: "taskAgentPromptPrefix") }
  }

  /// Instructions appended to the canonical task prompt.
  @Published var defaultPrompt: String {
    didSet { UserDefaults.standard.set(defaultPrompt, forKey: "taskAgentDefaultPrompt") }
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
    self.isChatEnabled = UserDefaults.standard.bool(forKey: "taskChatAgentEnabled")
    self.workingDirectory = UserDefaults.standard.string(forKey: "taskAgentWorkingDirectory") ?? ""
    self.customPromptPrefix = UserDefaults.standard.string(forKey: "taskAgentPromptPrefix") ?? ""
    self.defaultPrompt = UserDefaults.standard.string(forKey: "taskAgentDefaultPrompt") ?? Self.defaultPromptTemplate
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
}
