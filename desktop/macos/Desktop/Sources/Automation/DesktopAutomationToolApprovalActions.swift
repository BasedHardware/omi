import Foundation

extension DesktopAutomationActionRegistry {
  /// Harness drivers for the device tool approval card. The snapshot reads the
  /// store the card renders; the answer calls the same store method the card's
  /// buttons call, so a headless run exercises store, signed direct control and
  /// kernel without Accessibility permission. Non-production only.
  func registerToolApprovalActions() {
    register(
      name: "tool_approval_snapshot",
      effects: [],
      summary: "List device tool approval cards (pending and recently resolved) as the chat shows them",
      params: ["session_id"], category: "agent", surfaces: ["main_chat", "floating_bar"],
      examples: ["./scripts/omi-ctl action tool_approval_snapshot --read-only"]
    ) { params in
      guard AppBuild.isNonProduction else { return ["error": "non-production only"] }
      let sessionId = params["session_id"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
      return Self.toolApprovalSnapshot(sessionId: sessionId)
    }

    // An allow lets the parked tool run, and that tool may send, read, or
    // write anywhere its own effects reach, so this declares the union.
    register(
      name: "answer_tool_approval",
      effects: [.localState, .localArtifact, .networkOrModel, .remoteWrite],
      summary: "Answer a device tool approval card exactly as its button would (allow_once, allow_session, deny)",
      params: ["approval_id", "answer"], category: "agent", surfaces: ["main_chat", "floating_bar"],
      examples: ["./scripts/omi-ctl action answer_tool_approval approval_id=<dispatch id> answer=deny"]
    ) { params in
      guard AppBuild.isNonProduction else { return ["error": "non-production only"] }
      let approvalId = params["approval_id"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
      guard !approvalId.isEmpty else { return ["error": "approval_id required"] }
      guard let raw = params["answer"], let answer = DesktopToolApprovalAnswer(rawValue: raw) else {
        return ["error": "answer must be allow_once, allow_session, or deny"]
      }
      return await Self.answerToolApproval(approvalId: approvalId, answer: answer)
    }
  }

  @MainActor
  static func toolApprovalSnapshot(sessionId: String) -> [String: String] {
    let store = DesktopToolApprovalStore.shared
    let approvals = sessionId.isEmpty ? store.approvals : store.approvals(forSessionId: sessionId)
    let now = Date()
    let rows: [[String: Any]] = approvals.map { approval in
      let presentation = DesktopToolApprovalCardPresentation(approval: approval, now: now)
      var row: [String: Any] = [
        "approvalId": approval.id,
        "sessionId": approval.request.sessionId,
        "runId": approval.request.runId,
        "toolName": approval.request.toolName,
        "state": stateName(approval.state),
        "status": presentation.status,
        "headline": presentation.headline,
        "answers": presentation.actions.map { $0.answer.rawValue },
        "expiresAtMs": Int(approval.request.expiresAt.timeIntervalSince1970 * 1_000),
      ]
      row["resourceRef"] = approval.request.resourceRef ?? ""
      row["lastError"] = approval.lastError ?? ""
      return row
    }
    let data = (try? JSONSerialization.data(withJSONObject: rows)) ?? Data("[]".utf8)
    return [
      "count": String(rows.count),
      "pending": String(approvals.filter { $0.state.isPending }.count),
      "approvals": String(decoding: data, as: UTF8.self),
    ]
  }

  @MainActor
  /// The bridge's own resolver id, so the kernel's record says a harness answered.
  static let bridgeResolverID = "desktop_automation"

  static func answerToolApproval(
    approvalId: String, answer: DesktopToolApprovalAnswer, store: DesktopToolApprovalStore = .shared
  ) async -> [String: String] {
    guard let before = store.approval(id: approvalId) else { return ["error": "unknown approval_id"] }
    guard before.state == .pending else {
      return ["error": "approval is not pending", "state": stateName(before.state)]
    }
    if answer == .allowForSession, !before.request.offersSessionGrant {
      return ["error": "allow_session is not offered for this approval"]
    }
    await store.answer(approvalId: approvalId, with: answer, resolvedBy: bridgeResolverID)
    guard let after = store.approval(id: approvalId) else { return ["error": "approval vanished"] }
    return [
      "approvalId": approvalId,
      "answer": answer.rawValue,
      "state": stateName(after.state),
      "status": DesktopToolApprovalCardPresentation(approval: after).status,
      "lastError": after.lastError ?? "",
    ]
  }

  private static func stateName(_ state: DesktopToolApprovalState) -> String {
    switch state {
    case .pending: return "pending"
    case .answering: return "answering"
    case .allowed: return "allowed"
    case .denied: return "denied"
    case .expired: return "expired"
    case .cancelled: return "cancelled"
    }
  }
}
