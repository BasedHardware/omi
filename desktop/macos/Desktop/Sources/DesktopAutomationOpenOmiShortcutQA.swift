import Cocoa

extension DesktopAutomationActionRegistry {
  /// Named-bundle QA selects the same Open Omi presets as the settings buttons,
  /// then reads the real owner's registration trace around that atomic mutation.
  func registerOpenOmiShortcutActionsForQA() {
    #if DEBUG
      register(
        name: "proactive_assistant_proxy_routes",
        summary: "Resolve the Gemini and embedding proxy routes through their production clients. DEBUG non-prod only."
      ) { _ in
        guard AppBuild.isNonProduction else {
          return ["error": "proactive_assistant_proxy_routes is disabled on production bundles"]
        }
        return [
          "gemini_proxy_base_url": GeminiClient.proxyBaseURL,
          "embedding_proxy_base_url": EmbeddingService.proxyBaseURL,
          "proactivity_base_url": ProactiveLaneClient.backendBaseURL,
        ]
      }

      register(
        name: "knowledge_ledger_foundation_contracts",
        summary: "Exercise the pure knowledge-ledger prompt and trigger projections. DEBUG non-prod only."
      ) { _ in
        guard AppBuild.isNonProduction else {
          return ["error": "knowledge_ledger_foundation_contracts is disabled on production bundles"]
        }
        let prompt = KnowledgeLedgerPromptProjection(
          rows: [
            .init(
              id: "mem_profile",
              content: "Paris",
              metadata: [
                "ledger_schema_version": KnowledgeLedgerPromptProjection.schemaVersion,
                "kind": "fact",
                "subject_scope": "primary_user",
                "slot": "home_city",
                "intent_backed": "true",
                "status": "active",
              ]
            )
          ]
        ).render(userName: "Test")
        let row = try KnowledgeLedgerTriggerRow(
          id: "trigger_focus",
          triggerCondition: [
            "schema_version": "jit_trigger.v1",
            "keywords": ["focus"],
          ]
        )
        guard case .success(let trigger) = KnowledgeLedgerTriggerCompiler.compile(row) else {
          return ["error": "knowledge ledger trigger fixture did not compile"]
        }
        let decision = KnowledgeLedgerTriggerEvaluator.evaluate(
          trigger,
          observation: .init(text: "focus now"),
          day: "2026-08-23"
        )
        return [
          "prompt_contains_profile_fact": prompt?.contains("home_city: Paris") == true ? "true" : "false",
          "trigger_status": decision.status.rawValue,
          "trigger_wakeups_used": "\(decision.wakeupsUsed)",
        ]
      }

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
