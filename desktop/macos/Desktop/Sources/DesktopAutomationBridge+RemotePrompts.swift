import Foundation

/// Remote-prompt automation actions: drive the admin-authored prompt engine
/// without cursor clicks. `remote_prompt_answer` runs the same
/// `RemotePromptEngine.answer` the visible controls call.
extension DesktopAutomationActionRegistry {
  func registerRemotePromptActions() {
    register(
      name: "remote_prompts_state",
      summary: "Return the remote-prompt engine's fetched specs and active prompt"
    ) { _ in
      await MainActor.run {
        let engine = RemotePromptEngine.shared
        return [
          "schema": "current_id,current_type,spec_count,spec_ids",
          "current_id": engine.current?.id ?? "",
          "current_type": engine.current?.type ?? "",
          "spec_count": "\(engine.specs.count)",
          "spec_ids": engine.specs.map(\.id).joined(separator: ","),
        ]
      }
    }

    register(
      name: "remote_prompts_refresh",
      summary: "Fetch prompts from the backend now (same call as the 5-minute poll)"
    ) { _ in
      await RemotePromptEngine.shared.refreshFromServer()
      return await MainActor.run {
        let engine = RemotePromptEngine.shared
        return [
          "refreshed": "true",
          "spec_count": "\(engine.specs.count)",
          "current_id": engine.current?.id ?? "",
        ]
      }
    }

    register(
      name: "remote_prompt_answer",
      summary: "Answer the active remote prompt through the same path as its buttons",
      params: ["value"]
    ) { params in
      let value = params["value"] ?? ""
      return await MainActor.run {
        let engine = RemotePromptEngine.shared
        guard let spec = engine.current else {
          return ["answered": "false", "reason": "no active prompt"]
        }
        let id = spec.id
        engine.answer(value: value)
        return ["answered": "true", "prompt_id": id, "value": value]
      }
    }

    register(
      name: "remote_prompt_dismiss",
      summary: "Dismiss the active remote prompt through the same path as its close button"
    ) { _ in
      await MainActor.run {
        let engine = RemotePromptEngine.shared
        guard engine.current != nil else {
          return ["dismissed": "false", "reason": "no active prompt"]
        }
        engine.dismissCurrent()
        return ["dismissed": "true"]
      }
    }

    register(
      name: "remote_prompts_reset",
      summary: "Forget local prompt resolutions and counters so triggers can be exercised again"
    ) { _ in
      await MainActor.run {
        RemotePromptEngine.shared.resetForTesting()
        return ["reset": "true"]
      }
    }
  }
}
