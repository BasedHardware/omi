import Cocoa

extension DesktopAutomationActionRegistry {
  /// Named-bundle QA selects the same Open Omi presets as the settings buttons,
  /// then reads the real owner's registration trace around that atomic mutation.
  func registerOpenOmiShortcutActionsForQA() {
    #if DEBUG
      register(
        name: "set_open_omi_shortcut",
        summary: "Select an Open Omi shortcut preset through the production settings mutation. DEBUG non-prod only.",
        params: ["preset"]
      ) { params in
        guard AppBuild.isNonProduction else {
          return ["error": "set_open_omi_shortcut is disabled on production bundles"]
        }
        let shortcut: ShortcutSettings.KeyboardShortcut
        switch params["preset"] ?? "command_j" {
        case "command_o": shortcut = ShortcutSettings.askOmiCommandOShortcut
        case "command_return": shortcut = ShortcutSettings.askOmiCommandReturnShortcut
        case "command_j": shortcut = ShortcutSettings.askOmiCommandJShortcut
        default:
          throw DesktopAutomationActionError.invalidParams(
            "preset must be command_o, command_return, or command_j")
        }
        let settings = ShortcutSettings.shared
        let manager = GlobalShortcutManager.shared
        let previous = settings.askOmiShortcut.displayLabel
        manager.resetAskOmiRegistrationTraceForAutomation()
        settings.updateAskOmiRegistration(enabled: true, shortcut: shortcut)
        let outcomes = manager.askOmiRegistrationTraceForAutomation().map { outcome in
          switch outcome {
          case .registered: return "registered"
          case .alreadyInUse: return "already_in_use"
          case .otherFailure: return "other_failure"
          }
        }
        return [
          "previous_binding": previous,
          "current_binding": settings.askOmiShortcut.displayLabel,
          "enabled": settings.askOmiEnabled ? "true" : "false",
          "registration_attempt_count": "\(outcomes.count)",
          "registration_outcomes": outcomes.joined(separator: ","),
        ]
      }

      register(
        name: "trigger_open_omi_shortcut",
        summary: "Trigger the registered Open Omi shortcut action. DEBUG non-prod only."
      ) { _ in
        guard AppBuild.isNonProduction else {
          return ["error": "trigger_open_omi_shortcut is disabled on production bundles"]
        }
        GlobalShortcutManager.shared.triggerOpenOmiShortcutForAutomation()
        try? await Task.sleep(for: .milliseconds(100))
        let mainWindowVisible = NSApp.windows.contains { window in
          window.frame.width > 300 && window.frame.height > 200 && window.isVisible
        }
        return [
          "triggered": "true",
          "main_window_visible": mainWindowVisible ? "true" : "false",
        ]
      }
    #endif
  }
}
