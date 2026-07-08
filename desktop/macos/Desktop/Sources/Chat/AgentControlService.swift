import Foundation

@MainActor
final class AgentControlService {
  private enum ToolName {
    static let listAgentSessions = "list_agent_sessions"
    static let getAgentRun = "get_agent_run"
    static let cancelAgentRun = "cancel_agent_run"
    static let inspectAgentArtifacts = "inspect_agent_artifacts"
    static let updateAgentArtifactLifecycle = "update_agent_artifact_lifecycle"
  }

  private struct AgentHandle {
    let sessionId: String?
    let runId: String?
    let attemptId: String?
  }

  private let runtime: AgentRuntimeProcess
  private var agentHandles: [String: AgentHandle] = [:]
  private var artifactHandles: [String: String] = [:]

  init(runtime: AgentRuntimeProcess = .shared) {
    self.runtime = runtime
  }

  func executeVoiceTool(name: String, arguments: [String: Any]) async throws -> String {
    if let unresolved = unresolvedVoiceHandleError(name: name, arguments: arguments) {
      return unresolved
    }
    let input = canonicalizeVoiceArguments(name: name, arguments: arguments)
    if let missing = missingScopeError(name: name, input: input) {
      return missing
    }
    let raw = try await runtime.directControlTool(
      clientId: "realtime-hub",
      harnessMode: Self.currentHarnessMode(),
      name: name,
      input: input
    )
    return summarizeVoiceResult(name: name, raw: raw)
  }

  /// Enforces the "agentRef or runId" / "artifactRef or artifactId" preconditions
  /// that were previously expressed as root-level `anyOf` in the provider-facing
  /// tool schemas. Keeping the schemas flat avoids provider compatibility issues
  /// (some Realtime/Gemini environments reject or ignore root composite keywords),
  /// while this guard gives the model a helpful voice message instead of a raw
  /// runtime error when it omits the identifying reference.
  func missingScopeError(name: String, input: [String: Any]) -> String? {
    switch name {
    case ToolName.getAgentRun, ToolName.cancelAgentRun:
      let hasScope = stringValue(input["runId"]) != nil || stringValue(input["sessionId"]) != nil
      return hasScope ? nil
        : "I need an agent reference or run id for that. Try listing the agents first with list_agent_sessions."
    case ToolName.inspectAgentArtifacts:
      let hasScope = ["artifactId", "sessionId", "runId", "attemptId"].contains { stringValue(input[$0]) != nil }
      return hasScope ? nil
        : "I need an agent, artifact, session, run, or attempt reference to inspect artifacts. Try listing the agents first."
    case ToolName.updateAgentArtifactLifecycle:
      let hasArtifact = stringValue(input["artifactId"]) != nil
      return hasArtifact ? nil
        : "I need an artifact reference or id to update its lifecycle. Try inspecting the artifacts first."
    default:
      return nil
    }
  }

  static func currentHarnessMode() -> String {
    let mode = UserDefaults.standard.string(forKey: "chatBridgeMode") ?? "piMono"
    return mode == "piMono" ? "piMono" : "acp"
  }

  func logDetail(name: String, arguments: [String: Any]) -> String {
    switch name {
    case ToolName.getAgentRun, ToolName.cancelAgentRun:
      return stringValue(arguments["agentRef"]).map { "agentRef=\($0)" } ?? hasCanonicalScope(arguments)
    case ToolName.inspectAgentArtifacts:
      return stringValue(arguments["agentRef"]).map { "agentRef=\($0)" }
        ?? stringValue(arguments["artifactRef"]).map { "artifactRef=\($0)" }
        ?? hasCanonicalScope(arguments)
    case ToolName.updateAgentArtifactLifecycle:
      return stringValue(arguments["artifactRef"]).map { "artifactRef=\($0)" } ?? ""
    default:
      return ""
    }
  }

  func summarizeVoiceResult(name: String, raw: String) -> String {
    guard let data = raw.data(using: .utf8),
      let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else {
      return raw
    }
    if object["ok"] as? Bool == false {
      clearVoiceHandles(for: name)
      return "Agent control failed. Try listing the agents again and retry with the matching item."
    }
    switch name {
    case ToolName.listAgentSessions:
      return summarizeAgentSessions(object)
    case ToolName.getAgentRun:
      return summarizeAgentRun(object)
    case ToolName.cancelAgentRun:
      return summarizeAgentCancellation(object)
    case ToolName.inspectAgentArtifacts:
      return summarizeAgentArtifacts(object)
    case ToolName.updateAgentArtifactLifecycle:
      return summarizeArtifactLifecycle(object)
    default:
      return raw
    }
  }

  func canonicalizeVoiceArguments(name: String, arguments: [String: Any]) -> [String: Any] {
    var input = resolveVoiceHandles(in: arguments)
    let aliases = [
      "parent_run_id": "parentRunId",
      "run_id": "runId",
      "session_id": "sessionId",
      "attempt_id": "attemptId",
      "artifact_id": "artifactId",
      "owner_id": "ownerId",
      "max_depth": "maxDepth",
      "max_budget_usd": "maxBudgetUsd",
      "run_mode": "runMode",
    ]
    for (alias, canonical) in aliases {
      if input[canonical] == nil, let value = input[alias] {
        input[canonical] = value
      }
      input.removeValue(forKey: alias)
    }
    switch name {
    case "spawn_agent":
      input.removeValue(forKey: "brief")
    default:
      break
    }
    return input
  }

  func unresolvedVoiceHandleError(name: String, arguments: [String: Any]) -> String? {
    if let agentRef = stringValue(arguments["agentRef"]), agentHandles[agentRef] == nil {
      return "I couldn't resolve that agent reference. Try listing the agents again, then retry with the matching item."
    }
    if let artifactRef = stringValue(arguments["artifactRef"]), artifactHandles[artifactRef] == nil {
      return "I couldn't resolve that artifact reference. Try inspecting the artifacts again, then retry with the matching item."
    }
    return nil
  }

  func resolveVoiceHandles(in arguments: [String: Any]) -> [String: Any] {
    var input = arguments
    if let agentRef = stringValue(input["agentRef"]), let handle = agentHandles[agentRef] {
      if input["sessionId"] == nil, let sessionId = handle.sessionId { input["sessionId"] = sessionId }
      if input["runId"] == nil, let runId = handle.runId { input["runId"] = runId }
      if input["attemptId"] == nil, let attemptId = handle.attemptId { input["attemptId"] = attemptId }
    }
    if let artifactRef = stringValue(input["artifactRef"]), let artifactId = artifactHandles[artifactRef], input["artifactId"] == nil {
      input["artifactId"] = artifactId
    }
    input.removeValue(forKey: "agentRef")
    input.removeValue(forKey: "artifactRef")
    return input
  }

  private func summarizeAgentSessions(_ object: [String: Any]) -> String {
    let sessions = object["sessions"] as? [[String: Any]] ?? []
    if sessions.isEmpty {
      agentHandles.removeAll()
      return "No canonical Omi agent sessions found."
    }

    agentHandles.removeAll()
    let rows = sessions.prefix(8).enumerated().map { index, summary -> String in
      let agentRef = "agent_\(index + 1)"
      let session = summary["session"] as? [String: Any] ?? [:]
      let latestRun = summary["latestRun"] as? [String: Any] ?? [:]
      let activeRun = summary["activeRun"] as? [String: Any] ?? [:]
      let selectedRun = activeRun.isEmpty ? latestRun : activeRun
      let latestAttempt = summary["latestAttempt"] as? [String: Any] ?? [:]
      let activeAttempt = summary["activeAttempt"] as? [String: Any] ?? [:]
      let selectedAttempt = activeRun.isEmpty ? latestAttempt : activeAttempt
      let title = stringValue(session["title"]) ?? stringValue(session["surfaceKind"]) ?? "Untitled agent"
      let status = stringValue(selectedRun["status"]) ?? stringValue(session["status"]) ?? "unknown"
      let mode = stringValue(selectedRun["mode"])
      let updatedAt = stringValue(session["updatedAt"]) ?? stringValue(selectedRun["updatedAt"])
      agentHandles[agentRef] = AgentHandle(
        sessionId: stringValue(session["sessionId"]),
        runId: stringValue(selectedRun["runId"]),
        attemptId: stringValue(selectedAttempt["attemptId"])
      )

      var parts = ["\(agentRef): \(title)", status]
      if let mode { parts.append("mode \(mode)") }
      if let updatedAt { parts.append("updated \(updatedAt)") }
      return "- \(parts.joined(separator: ", "))"
    }.joined(separator: "\n")
    let suffix = sessions.count > 8 ? "\nShowing 8 of \(sessions.count)." : ""
    return "Canonical Omi agent sessions. Use agentRef values internally for follow-up tool calls; do not say them aloud.\n\(rows)\(suffix)"
  }

  private func summarizeAgentRun(_ object: [String: Any]) -> String {
    let run = object["run"] as? [String: Any] ?? [:]
    let attempts = object["attempts"] as? [[String: Any]] ?? []
    let events = object["events"] as? [[String: Any]] ?? []
    let status = stringValue(run["status"]) ?? "unknown"
    let mode = stringValue(run["mode"]) ?? "unknown"
    let terminalStatus = stringValue(run["terminalStatus"])
    let terminalText = terminalStatus.map { ", terminal status \($0)" } ?? ""
    return "The selected canonical run is \(status), mode \(mode)\(terminalText). Attempts: \(attempts.count). Events returned: \(events.count)."
  }

  private func summarizeAgentCancellation(_ object: [String: Any]) -> String {
    let cancellation = object["cancellation"] as? [String: Any] ?? [:]
    let run = object["run"] as? [String: Any] ?? [:]
    let status = stringValue(run["status"]) ?? "unknown"
    let accepted = cancellation["accepted"] as? Bool
    let dispatched = (cancellation["dispatchAttempted"] as? Bool) ?? (cancellation["dispatched"] as? Bool)
    let acknowledged = (cancellation["adapterAcknowledged"] as? Bool) ?? (cancellation["acknowledged"] as? Bool)
    return "Cancel request: accepted=\(accepted?.description ?? "unknown"), dispatched=\(dispatched?.description ?? "unknown"), acknowledged=\(acknowledged?.description ?? "unknown"). Current status: \(status)."
  }

  private func summarizeAgentArtifacts(_ object: [String: Any]) -> String {
    let artifacts = object["artifacts"] as? [[String: Any]] ?? []
    if artifacts.isEmpty {
      artifactHandles.removeAll()
      return "No canonical agent artifacts found for that scope."
    }

    artifactHandles.removeAll()
    let rows = artifacts.prefix(8).enumerated().map { index, artifact -> String in
      let artifactRef = "artifact_\(index + 1)"
      if let artifactId = stringValue(artifact["artifactId"]) {
        artifactHandles[artifactRef] = artifactId
      }
      let role = stringValue(artifact["role"]) ?? "unknown"
      let state = stringValue(artifact["lifecycleState"]) ?? stringValue(artifact["state"]) ?? "unknown"
      let name = stringValue(artifact["displayName"]) ?? stringValue(artifact["path"])
      let label = name.map { "\($0), " } ?? ""
      return "- \(artifactRef): \(label)role \(role), state \(state)"
    }.joined(separator: "\n")
    let suffix = artifacts.count > 8 ? "\nShowing 8 of \(artifacts.count)." : ""
    return "Canonical agent artifacts. Use artifactRef values internally for follow-up tool calls; do not say them aloud.\n\(rows)\(suffix)"
  }

  private func summarizeArtifactLifecycle(_ object: [String: Any]) -> String {
    let artifact = object["artifact"] as? [String: Any] ?? [:]
    let state = stringValue(artifact["lifecycleState"]) ?? stringValue(artifact["state"]) ?? "unknown"
    let changed = object["changed"] as? Bool
    return "Artifact lifecycle is now \(state). Changed: \(changed?.description ?? "unknown")."
  }

  private func clearVoiceHandles(for name: String) {
    switch name {
    case ToolName.listAgentSessions,
      ToolName.getAgentRun,
      ToolName.cancelAgentRun,
      ToolName.inspectAgentArtifacts,
      ToolName.updateAgentArtifactLifecycle:
      agentHandles.removeAll()
      artifactHandles.removeAll()
    default:
      break
    }
  }

  private func hasCanonicalScope(_ arguments: [String: Any]) -> String {
    for key in ["sessionId", "runId", "attemptId"] where stringValue(arguments[key]) != nil {
      return "\(key)=present"
    }
    return ""
  }

  private func stringValue(_ value: Any?) -> String? {
    guard let text = value as? String else { return nil }
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? nil : trimmed
  }
}
