import Foundation

/// The explicitly selected marketplace app for Main Chat.
///
/// App instructions are scoped to the app-specific main-chat surface. They
/// never become a global ChatProvider prompt and therefore cannot leak into a
/// floating, onboarding, or task conversation.
struct ChatAppContext: Equatable {
  let appId: String
  let appName: String
  let chatPrompt: String?

  init(appId: String, appName: String?, chatPrompt: String?) {
    self.appId = appId
    let trimmedName = appName?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    self.appName = trimmedName.isEmpty ? "Selected app" : trimmedName
    let trimmedPrompt = chatPrompt?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    self.chatPrompt = trimmedPrompt.isEmpty ? nil : trimmedPrompt
  }

  func appending(to baseContext: String?) -> String {
    var sections: [String] = []
    if let base = baseContext?.trimmingCharacters(in: .whitespacesAndNewlines), !base.isEmpty {
      sections.append(base)
    }
    var appSection = """
      [Active Chat App]
      Name: \(appName)
      ID: \(appId)
      """
    if let chatPrompt {
      appSection += "\nApp instructions:\n\(chatPrompt)"
    }
    sections.append(appSection)
    return sections.joined(separator: "\n\n")
  }

  static func scopedExperienceContext(
    selectedApp: ChatAppContext?,
    surfaceKind: String,
    baseContext: String?
  ) -> String? {
    guard surfaceKind == "main_chat", let selectedApp else { return baseContext }
    return selectedApp.appending(to: baseContext)
  }
}
