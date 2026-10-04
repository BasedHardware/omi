import Cocoa

extension DesktopAutomationActionRegistry {
  /// Named-bundle QA selects the same Open Omi presets as the settings buttons,
  /// then reads the real owner's registration trace around that atomic mutation.
  func registerOpenOmiShortcutActionsForQA() {
    #if DEBUG
      register(
        name: "proactive_assistant_proxy_routes",
        effects: [],
        summary: "Resolve the Gemini and embedding proxy routes through their production clients. DEBUG non-prod only."
      ) { _ in
        guard AppBuild.isNonProduction else {
          return ["error": "proactive_assistant_proxy_routes is disabled on production bundles"]
        }
        guard let geminiURL = URL(string: GeminiClient.proxyBaseURL) else {
          return ["error": "invalid gemini proxy base url"]
        }
        var geminiRequest = URLRequest(url: geminiURL)
        geminiRequest.applyGeminiProxyHeaders(
          lane: .taskExtraction,
          workload: .extraction,
          authorization: ""
        )
        // These echo the fixed sample this probe sends through the shared
        // header helper — they verify the helper contract, not that each real
        // request path (focus, memory, embedding, …) carries its own lane.
        return [
          "gemini_proxy_base_url": GeminiClient.proxyBaseURL,
          "embedding_proxy_base_url": EmbeddingService.proxyBaseURL,
          "proactivity_base_url": JITRolloutClient.backendBaseURL,
          "gemini_helper_sample_lane": geminiRequest.value(forHTTPHeaderField: "X-Omi-Lane") ?? "",
          "gemini_helper_sample_workload": geminiRequest.value(forHTTPHeaderField: "X-Omi-Workload") ?? "",
          "gemini_helper_sample_client_platform": geminiRequest.value(forHTTPHeaderField: "X-App-Platform") ?? "",
        ]
      }

      register(
        name: "knowledge_ledger_foundation_contracts",
        effects: [],
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
          ],
          hasAuthoritativeSnapshot: true
        ).render(userName: "Test")
        return ["prompt_contains_profile_fact": prompt?.contains("home_city: Paris") == true ? "true" : "false"]
      }

      register(
        name: "set_open_omi_shortcut",
        effects: [.localState],
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
        effects: [.localState],
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
