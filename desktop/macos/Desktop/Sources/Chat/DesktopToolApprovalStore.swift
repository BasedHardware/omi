import Combine
import Foundation

/// One answer the card can give. The runtime is the only place the decision is
/// applied; this type only knows how to say it in `resolve_desktop_dispatch`'s
/// input shape.
enum DesktopToolApprovalAnswer: String, Equatable, Sendable {
  case allowOnce = "allow_once"
  case allowForSession = "allow_session"
  case deny

  /// How long "Allow for this chat" lasts. The kernel caps grants at 24 h;
  /// an hour is the issue's product decision for the card.
  static let sessionGrantDuration: TimeInterval = 60 * 60

  /// The control-tool input for this answer. Allow once mints nothing; allow
  /// for this chat mints one session-scoped grant for exactly the request's
  /// capability, operation and resource; deny carries no grant.
  func controlToolInput(
    for request: DesktopToolApprovalRequest, now: Date, resolvedBy: String = "user"
  ) -> [String: Any] {
    var input: [String: Any] = [
      "dispatchId": request.approvalId,
      "status": "resolved",
      "resolvedBy": resolvedBy,
      "resolution": ["decision": self == .deny ? "deny" : "allow", "selectedOptionId": rawValue],
    ]
    if self == .allowForSession, let resourceRef = request.resourceRef {
      input["grant"] =
        [
          "runId": NSNull(),
          "capability": request.capability,
          "operation": request.operation,
          "resourcePattern": resourceRef,
          "effect": "allow",
          "source": "user",
          "expiresAtMs": Int((now.timeIntervalSince1970 + Self.sessionGrantDuration) * 1_000),
        ] as [String: Any]
    }
    return input
  }
}

struct DesktopToolApprovalOption: Equatable, Sendable {
  let id: String
  let effect: String
  let scope: String
  /// Plain words for what an `allow_session` grant would cover.
  let covers: String?

  init?(_ dictionary: [String: Any]) {
    guard let id = dictionary["id"] as? String, !id.isEmpty,
      let effect = dictionary["effect"] as? String,
      let scope = dictionary["scope"] as? String
    else { return nil }
    self.id = id
    self.effect = effect
    self.scope = scope
    self.covers = (dictionary["covers"] as? String).flatMap { $0.isEmpty ? nil : $0 }
  }

  init(id: String, effect: String, scope: String, covers: String? = nil) {
    self.id = id
    self.effect = effect
    self.scope = scope
    self.covers = covers
  }
}

/// One `approval_requested` frame, as the card shows it. Everything here is a
/// display projection of the kernel's dispatch; the dispatch id is the only
/// handle the answer sends back.
struct DesktopToolApprovalRequest: Equatable, Sendable {
  struct PreviewField: Equatable, Sendable {
    let key: String
    let value: String
  }

  let approvalId: String
  let ownerId: String
  let sessionId: String
  let runId: String
  let attemptId: String
  let invocationId: String
  let adapterId: String
  let surfaceKind: String
  let toolName: String
  let capability: String
  let operation: String
  /// The exact resource the kernel bound the dispatch to; this is what a
  /// session grant covers, so it is never altered for display.
  let resourceRef: String?
  /// `resourceRef` as the card shows it, with invisible and direction-changing
  /// characters made visible.
  let displayResourceRef: String?
  let title: String
  let decisionPrompt: String
  let preview: [PreviewField]
  let previewTruncated: Bool
  let options: [DesktopToolApprovalOption]
  let defaultOptionId: String
  let requestedAt: Date
  let expiresAt: Date

  /// Fields each tool shows first; anything else follows alphabetically.
  private static let previewOrder: [String: [String]] = [
    "send_message": ["to", "text", "service", "file_path"],
    "run_applescript": ["script", "timeout_seconds"],
    "read_message_history": ["chat_id", "handle", "limit"],
    "list_message_chats": ["limit"],
    "list_mail_messages": ["limit"],
  ]

  static func parse(_ payload: [String: Any]) -> DesktopToolApprovalRequest? {
    guard payload["type"] as? String == "approval_requested",
      let approvalId = nonEmpty(payload["approvalId"]),
      let ownerId = nonEmpty(payload["ownerId"]),
      let sessionId = nonEmpty(payload["sessionId"]),
      let runId = nonEmpty(payload["runId"]),
      let attemptId = nonEmpty(payload["attemptId"]),
      let invocationId = nonEmpty(payload["invocationId"]),
      let toolName = nonEmpty(payload["toolName"]),
      let capability = nonEmpty(payload["capability"]),
      let operation = nonEmpty(payload["operation"]),
      let requestedAtMs = payload["requestedAtMs"] as? Double,
      let expiresAtMs = payload["expiresAtMs"] as? Double
    else { return nil }
    let rawPreview = payload["preview"] as? [String: Any] ?? [:]
    let preferred = previewOrder[toolName] ?? []
    let orderedKeys =
      preferred.filter { rawPreview[$0] != nil }
      + rawPreview.keys.filter { !preferred.contains($0) }.sorted()
    let preview = orderedKeys.compactMap { key -> PreviewField? in
      switch rawPreview[key] {
      case let string as String: return PreviewField(key: key, value: displaySafe(string))
      case let number as NSNumber: return PreviewField(key: key, value: number.stringValue)
      default: return nil
      }
    }
    let options = (payload["options"] as? [[String: Any]] ?? []).compactMap(DesktopToolApprovalOption.init)
    return DesktopToolApprovalRequest(
      approvalId: approvalId,
      ownerId: ownerId,
      sessionId: sessionId,
      runId: runId,
      attemptId: attemptId,
      invocationId: invocationId,
      adapterId: payload["adapterId"] as? String ?? "",
      surfaceKind: payload["surfaceKind"] as? String ?? "",
      toolName: toolName,
      capability: capability,
      operation: operation,
      resourceRef: nonEmpty(payload["resourceRef"]),
      displayResourceRef: nonEmpty(payload["resourceRef"]).map(displaySafe),
      title: nonEmpty(payload["title"]).map(displaySafe) ?? "Needs approval",
      decisionPrompt: nonEmpty(payload["decisionPrompt"]).map(displaySafe) ?? "Allow this action?",
      preview: preview,
      previewTruncated: payload["previewTruncated"] as? Bool ?? false,
      options: options,
      defaultOptionId: payload["defaultOptionId"] as? String ?? "deny",
      requestedAt: Date(timeIntervalSince1970: requestedAtMs / 1_000),
      expiresAt: Date(timeIntervalSince1970: expiresAtMs / 1_000)
    )
  }

  /// The card offers only what the runtime offered. `allow_session` is absent
  /// when the request has no exact resource for a grant to cover.
  var offersSessionGrant: Bool { sessionGrantOption != nil }
  var sessionGrantOption: DesktopToolApprovalOption? {
    options.first { $0.id == DesktopToolApprovalAnswer.allowForSession.rawValue && $0.effect == "allow" }
  }

  /// Model-authored text goes on the card verbatim except for characters that
  /// can lie about it: bidirectional controls that reorder a recipient,
  /// invisible characters that hide inside one, and control characters other
  /// than newline and tab. Each is shown as its code point, `⟨U+202E⟩`, so the
  /// person sees that it is there rather than a cleaned-up string. Newlines
  /// stay so the person sees the whole message; the card draws multi-line
  /// values as one block so they cannot pose as another row. Zero-width
  /// joiners are left alone: emoji sequences need them.
  static func displaySafe(_ value: String) -> String {
    var out = ""
    for scalar in value.unicodeScalars {
      if scalar == "\n" || scalar == "\t" {
        out.unicodeScalars.append(scalar)
        continue
      }
      switch scalar.value {
      case 0x00...0x1F, 0x7F...0x9F,
        0x00AD, 0x061C, 0x180E, 0x200B, 0x200E, 0x200F, 0x202A...0x202E,
        0x2060...0x2064, 0x2066...0x2069, 0xFEFF:
        out += String(format: "⟨U+%04X⟩", scalar.value)
      default:
        out.unicodeScalars.append(scalar)
      }
    }
    return out
  }

  private static func nonEmpty(_ value: Any?) -> String? {
    guard let string = value as? String else { return nil }
    let trimmed = string.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? nil : trimmed
  }
}

/// Where a card is in its life. The kernel's `approval.resolved` is the only
/// thing that makes a card final; `answering` is the local in-flight state
/// between a button press and the control tool's receipt.
enum DesktopToolApprovalState: Equatable, Sendable {
  case pending
  case answering(DesktopToolApprovalAnswer)
  case allowed(selectedOptionId: String, grantId: String?)
  case denied
  case expired
  case cancelled

  var isPending: Bool {
    switch self {
    case .pending, .answering: return true
    case .allowed, .denied, .expired, .cancelled: return false
    }
  }

  var isAnswering: Bool {
    if case .answering = self { return true }
    return false
  }

  static func fromResolution(decision: String, selectedOptionId: String?, grantId: String?) -> DesktopToolApprovalState?
  {
    switch decision {
    case "allow": return .allowed(selectedOptionId: selectedOptionId ?? "allow_once", grantId: grantId)
    case "deny": return .denied
    case "expired": return .expired
    case "cancelled": return .cancelled
    default: return nil
    }
  }
}

struct DesktopToolApproval: Identifiable, Equatable, Sendable {
  var id: String { request.approvalId }
  let request: DesktopToolApprovalRequest
  var state: DesktopToolApprovalState
  var resolvedAt: Date?
  var resolvedBy: String?
  /// The last answer that could not be delivered; the card stays pending and offers Try Again.
  var lastError: String?
}

/// What the daemon reported for an approval that this store had not seen yet,
/// kept until its request arrives so a fast resolution is never lost.
private struct DesktopToolApprovalEarlyResolution {
  let state: DesktopToolApprovalState
  let resolvedAt: Date
  let resolvedBy: String
}

/// Projection of the daemon's device-tool approvals for every chat surface.
/// Frames arrive from `AgentRuntimeProcess`; answers go back through the
/// trusted direct-control path. Nothing here is authority: a card that is
/// pressed twice, or pressed after the daemon already closed it, is refused
/// by the kernel and this store only mirrors what the kernel says.
@MainActor
final class DesktopToolApprovalStore: ObservableObject {
  static let shared = DesktopToolApprovalStore()

  typealias Resolver = @MainActor (_ approvalId: String, _ input: [String: Any]) async throws -> String

  /// Newest last. Resolved cards stay so the thread keeps its record; the
  /// store keeps a bounded tail.
  @Published private(set) var approvals: [DesktopToolApproval] = []

  private var earlyResolutions: [String: DesktopToolApprovalEarlyResolution] = [:]
  /// Arrival order of `earlyResolutions`, so the oldest is the one pruned.
  private var earlyResolutionOrder: [String] = []
  private var localExpiryTasks: [String: Task<Void, Never>] = [:]
  private let resolver: Resolver
  private let now: () -> Date
  private let retainedLimit = 50
  /// Resolutions that arrive before their request are kept only this long;
  /// a request that never follows is a card the daemon already closed.
  private let earlyResolutionLimit = 50

  init(
    resolver: @escaping Resolver = { approvalId, input in
      try await DesktopCoordinatorService.shared.resolveDispatchJSON(dispatchId: approvalId, input: input)
    },
    now: @escaping () -> Date = Date.init
  ) {
    self.resolver = resolver
    self.now = now
  }

  /// Drop every card: a new daemon handshake, the process ending, or an owner
  /// change makes them stale, because the kernel that would answer is gone.
  func reset() {
    approvals.removeAll()
    earlyResolutions.removeAll()
    earlyResolutionOrder.removeAll()
    for task in localExpiryTasks.values { task.cancel() }
    localExpiryTasks.removeAll()
  }

  /// Close every pending card whose deadline has passed. The daemon closes it
  /// too with `approval_resolved`, but a frame lost to a restart must not leave
  /// buttons on screen that can only fail.
  func expireOverdue(now reference: Date? = nil) {
    let at = reference ?? now()
    for index in approvals.indices where approvals[index].state == .pending && approvals[index].request.expiresAt <= at
    {
      approvals[index].state = .expired
      approvals[index].resolvedAt = approvals[index].request.expiresAt
      approvals[index].resolvedBy = "system"
      approvals[index].lastError = nil
    }
  }

  func approval(id approvalId: String) -> DesktopToolApproval? {
    approvals.first { $0.id == approvalId }
  }

  /// Cards for one kernel session, oldest first: every pending card plus the
  /// recently resolved ones so an answer does not make the card vanish.
  func approvals(forSessionId sessionId: String?) -> [DesktopToolApproval] {
    guard let sessionId, !sessionId.isEmpty else { return [] }
    return approvals.filter { $0.request.sessionId == sessionId }
  }

  func approvals(forRunId runId: String?) -> [DesktopToolApproval] {
    guard let runId, !runId.isEmpty else { return [] }
    return approvals.filter { $0.request.runId == runId }
  }

  var pendingApprovals: [DesktopToolApproval] {
    approvals.filter { $0.state.isPending }
  }

  /// Route a runtime frame. `approval_requested` opens a card; `approval_resolved`
  /// closes it whatever ended it (the user here, expiry, cancellation, an
  /// owner change). Anything else is ignored.
  func ingest(message: AgentRuntimeProcess.RuntimeMessage) {
    switch message.kind {
    case .approvalRequested:
      guard let request = DesktopToolApprovalRequest.parse(message.payload) else { return }
      ingest(request: request)
    case .approvalResolved:
      ingestResolution(message.payload)
    default:
      break
    }
  }

  func ingest(request: DesktopToolApprovalRequest) {
    // The daemon never re-sends a card; keep the first projection.
    guard !approvals.contains(where: { $0.id == request.approvalId }) else { return }
    var approval = DesktopToolApproval(
      request: request, state: .pending, resolvedAt: nil, resolvedBy: nil, lastError: nil)
    if let early = earlyResolutions.removeValue(forKey: request.approvalId) {
      earlyResolutionOrder.removeAll { $0 == request.approvalId }
      approval.state = early.state
      approval.resolvedAt = early.resolvedAt
      approval.resolvedBy = early.resolvedBy
    }
    approvals.append(approval)
    trim()
    scheduleLocalExpiry(for: request)
  }

  private func scheduleLocalExpiry(for request: DesktopToolApprovalRequest) {
    let delay = request.expiresAt.timeIntervalSince(now())
    guard delay > 0 else {
      expireOverdue()
      return
    }
    localExpiryTasks[request.approvalId]?.cancel()
    localExpiryTasks[request.approvalId] = Task { [weak self] in
      try? await Task.sleep(nanoseconds: UInt64((delay + 1) * 1_000_000_000))
      guard !Task.isCancelled else { return }
      self?.expireOverdue()
    }
  }

  private func ingestResolution(_ payload: [String: Any]) {
    guard let approvalId = payload["approvalId"] as? String, !approvalId.isEmpty,
      let decision = payload["decision"] as? String,
      let state = DesktopToolApprovalState.fromResolution(
        decision: decision,
        selectedOptionId: payload["selectedOptionId"] as? String,
        grantId: payload["grantId"] as? String)
    else { return }
    let resolvedAt = (payload["resolvedAtMs"] as? Double).map { Date(timeIntervalSince1970: $0 / 1_000) } ?? now()
    let resolvedBy = payload["resolvedBy"] as? String ?? "system"
    guard let index = approvals.firstIndex(where: { $0.id == approvalId }) else {
      if earlyResolutions[approvalId] == nil { earlyResolutionOrder.append(approvalId) }
      earlyResolutions[approvalId] = DesktopToolApprovalEarlyResolution(
        state: state, resolvedAt: resolvedAt, resolvedBy: resolvedBy)
      while earlyResolutionOrder.count > earlyResolutionLimit {
        earlyResolutions.removeValue(forKey: earlyResolutionOrder.removeFirst())
      }
      return
    }
    localExpiryTasks.removeValue(forKey: approvalId)?.cancel()
    approvals[index].state = state
    approvals[index].resolvedAt = resolvedAt
    approvals[index].resolvedBy = resolvedBy
    approvals[index].lastError = nil
  }

  /// Send the user's answer. The card shows the in-flight state until the
  /// kernel's receipt; a refused answer puts the card back to pending with the
  /// reason, and the user can try again. A card that is no longer pending
  /// ignores the press: the kernel has already decided.
  func answer(
    approvalId: String, with answer: DesktopToolApprovalAnswer, resolvedBy: String = "user"
  ) async {
    guard let index = approvals.firstIndex(where: { $0.id == approvalId }),
      approvals[index].state == .pending
    else { return }
    let request = approvals[index].request
    if answer == .allowForSession, !request.offersSessionGrant { return }
    if request.expiresAt <= now() {
      expireOverdue()
      return
    }
    approvals[index].state = .answering(answer)
    approvals[index].lastError = nil
    let input = answer.controlToolInput(for: request, now: now(), resolvedBy: resolvedBy)
    do {
      let receipt = try await resolver(approvalId, input)
      apply(receipt: receipt, to: approvalId, answer: answer)
    } catch {
      restorePending(approvalId: approvalId, error: Self.deliveryFailureMessage(error.localizedDescription))
    }
  }

  private func apply(receipt: String, to approvalId: String, answer: DesktopToolApprovalAnswer) {
    guard let index = approvals.firstIndex(where: { $0.id == approvalId }) else { return }
    let parsed = Self.parseReceipt(receipt)
    guard parsed.ok else {
      if Self.isNoLongerPendingRefusal(parsed.errorMessage) {
        // The kernel already closed this dispatch and the frame that said so
        // never reached us (a restart in between). Close the card the way the
        // kernel did rather than offering buttons that can only fail again.
        closeAsNoLongerPending(approvalId: approvalId)
      } else {
        restorePending(approvalId: approvalId, error: Self.deliveryFailureMessage(parsed.errorMessage))
      }
      return
    }
    // The approval_resolved frame may have landed already; it is authoritative.
    guard approvals[index].state.isAnswering else { return }
    approvals[index].state =
      answer == .deny
      ? .denied
      : .allowed(selectedOptionId: answer.rawValue, grantId: parsed.grantId)
    approvals[index].resolvedAt = now()
    approvals[index].resolvedBy = "user"
  }

  static func isNoLongerPendingRefusal(_ message: String?) -> Bool {
    message?.contains("is not pending") == true
  }

  private func closeAsNoLongerPending(approvalId: String) {
    guard let index = approvals.firstIndex(where: { $0.id == approvalId }), approvals[index].state.isAnswering
    else { return }
    let request = approvals[index].request
    approvals[index].state = request.expiresAt <= now() ? .expired : .cancelled
    approvals[index].resolvedAt = now()
    approvals[index].resolvedBy = "system"
    approvals[index].lastError = nil
  }

  private func restorePending(approvalId: String, error: String) {
    guard let index = approvals.firstIndex(where: { $0.id == approvalId }), approvals[index].state.isAnswering
    else { return }
    approvals[index].state = .pending
    approvals[index].lastError = error
  }

  private func trim() {
    guard approvals.count > retainedLimit else { return }
    // Drop the oldest resolved cards first; a pending card is never dropped.
    var excess = approvals.count - retainedLimit
    approvals.removeAll { approval in
      guard excess > 0, !approval.state.isPending else { return false }
      excess -= 1
      return true
    }
  }

  private static func parseReceipt(_ receipt: String) -> (ok: Bool, grantId: String?, errorMessage: String?) {
    guard let data = receipt.data(using: .utf8),
      let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else { return (false, nil, nil) }
    let ok = object["ok"] as? Bool ?? false
    let grantId = (object["grant"] as? [String: Any])?["grantId"] as? String
    let errorMessage = (object["error"] as? [String: Any])?["message"] as? String
    return (ok, grantId, errorMessage)
  }

  private static func deliveryFailureMessage(_ detail: String?) -> String {
    guard let detail, !detail.isEmpty else { return "Couldn't send your answer" }
    return "Couldn't send your answer: \(detail)"
  }
}
