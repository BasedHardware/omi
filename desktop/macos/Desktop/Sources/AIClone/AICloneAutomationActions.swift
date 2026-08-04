import Foundation

extension DesktopAutomationActionRegistry {
  func registerAICloneAndRewindActions() {
    registerRewindArtifactRecoveryGauntlet()
    registerAICloneActions()
  }

  func registerAICloneActions() {
    register(
      name: "ai_clone_snapshot",
      summary:
        "Safe AI Clone state: connection, enabled flag, per-mode chat counts, activity counts (no message content, no token)",
      params: []
    ) { _ in
      let service = AICloneService.shared
      let config = service.configuration
      var modeCounts: [String: Int] = [:]
      for mode in config.chatModes.values {
        modeCounts[mode.rawValue, default: 0] += 1
      }
      let state: String
      switch service.connectionState {
      case .connected: state = "connected"
      case .connecting: state = "connecting"
      case .failed: state = "failed"
      case .disconnected: state = "disconnected"
      }
      return [
        "connection_state": state,
        "enabled": config.enabled ? "true" : "false",
        "has_access_token": service.hasAccessToken ? "true" : "false",
        "listening": service.isListening ? "true" : "false",
        "chat_count": "\(service.chats.count)",
        "mode_counts": modeCounts.map { "\($0.key)=\($0.value)" }.sorted().joined(separator: ","),
        "pending_approvals": "\(service.pendingApprovals.count)",
        "activity_count": "\(config.activityLog.count)",
        "benchmarked_chats": "\(config.benchmarkResults.count)",
      ]
    }

    register(
      name: "ai_clone_connect",
      summary: "Save a Beeper access token and run the live connect probe; returns the resulting connection state",
      params: ["token"]
    ) { params in
      guard let token = params["token"], !token.isEmpty else {
        return ["error": "missing token"]
      }
      AICloneService.shared.saveAccessToken(token)
      await AICloneService.shared.connect()
      let service = AICloneService.shared
      let state: String
      switch service.connectionState {
      case .connected(let accounts):
        state = "connected:" + accounts.map(\.displayNetwork).sorted().joined(separator: ",")
      case .connecting: state = "connecting"
      case .failed(let message): state = "failed:\(message)"
      case .disconnected: state = "disconnected"
      }
      return ["connection_state": state, "chat_count": "\(service.chats.count)"]
    }

    register(
      name: "ai_clone_set_enabled",
      summary: "Toggle the AI Clone master switch",
      params: ["enabled"]
    ) { params in
      let enabled = params["enabled"] == "true"
      AICloneService.shared.setEnabled(enabled)
      return [
        "enabled": AICloneService.shared.configuration.enabled ? "true" : "false",
        "listening": AICloneService.shared.isListening ? "true" : "false",
      ]
    }

    register(
      name: "ai_clone_set_mode",
      summary: "Set a chat's trust mode (off/draft/ask/auto); auto still requires a passing benchmark",
      params: ["chat_id", "mode"]
    ) { params in
      guard let chatID = params["chat_id"], let rawMode = params["mode"],
        let mode = AICloneChatMode(rawValue: rawMode)
      else { return ["error": "missing chat_id or invalid mode"] }
      guard let chat = AICloneService.shared.chats.first(where: { $0.id == chatID }) else {
        return ["error": "unknown chat_id"]
      }
      AICloneService.shared.setMode(mode, for: chat)
      return ["mode": AICloneService.shared.configuration.mode(for: chatID).rawValue]
    }

    register(
      name: "ai_clone_benchmark",
      summary: "Run the history-replay self-benchmark for one chat and return its match score",
      params: ["chat_id"]
    ) { params in
      guard let chatID = params["chat_id"] else { return ["error": "missing chat_id"] }
      guard let chat = AICloneService.shared.chats.first(where: { $0.id == chatID }) else {
        return ["error": "unknown chat_id"]
      }
      await AICloneService.shared.runBenchmark(for: chat)
      guard let result = AICloneService.shared.configuration.benchmarkResults[chatID] else {
        return ["error": "benchmark produced no result"]
      }
      return [
        "match_score": "\(result.matchScore)",
        "sample_count": "\(result.sampleCount)",
        "auto_unlocked": AICloneService.shared.configuration.canEnableAuto(for: chatID) ? "true" : "false",
      ]
    }
  }
}
