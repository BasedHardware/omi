import Foundation

enum ScreenCandidateReconciliation {
  /// Repeated screen observations arrive in short bursts while the user moves
  /// between apps. Keep this intentionally narrow so a genuinely repeated task
  /// later in the day can become a new Candidate.
  static let reuseWindow: TimeInterval = 30 * 60

  static func isEquivalent(_ lhs: StagedTaskRecord, _ rhs: StagedTaskRecord) -> Bool {
    guard normalized(lhs.sourceApp) == normalized(rhs.sourceApp) else { return false }
    guard compatibleDueDates(lhs.dueAt, rhs.dueAt) else { return false }

    let lhsMetadata = lhs.metadata ?? [:]
    let rhsMetadata = rhs.metadata ?? [:]
    // Distinct action intents must stay separate (Approve ≠ Review/Close) even
    // when entity tokens overlap. Channel phrasing that encodes the same intent
    // ("Reply … to approve opening" vs "Approve … to open") shares a signature.
    // Generic/object-only phrasing without a distinguishing verb does not match
    // a strong intent — that keeps Review/Close from collapsing into a vague
    // "reply about opening" observation via Jaccard alone.
    guard
      actionSignature(for: lhs.description, metadata: lhsMetadata)
        == actionSignature(for: rhs.description, metadata: rhsMetadata)
    else { return false }

    let lhsTarget = canonicalTarget(in: lhsMetadata)
    let rhsTarget = canonicalTarget(in: rhsMetadata)
    if lhsTarget != rhsTarget { return false }

    let lhsTokens = semanticTokens(lhs.description)
    let rhsTokens = semanticTokens(rhs.description)
    guard !lhsTokens.isEmpty, !rhsTokens.isEmpty else { return false }

    // Identifiers are high-signal task identity. In particular, PR #123 and
    // PR #124 must not collapse merely because the surrounding prose matches.
    let lhsIdentifiers = Set(lhsTokens.filter(containsDigit))
    let rhsIdentifiers = Set(rhsTokens.filter(containsDigit))
    guard lhsIdentifiers == rhsIdentifiers else { return false }

    if lhsTokens == rhsTokens { return true }
    let intersection = lhsTokens.intersection(rhsTokens).count
    let union = lhsTokens.union(rhsTokens).count
    return union > 0 && Double(intersection) / Double(union) >= 0.72
  }

  private static func normalized(_ value: String?) -> String {
    value?
      .folding(options: [.diacriticInsensitive, .caseInsensitive], locale: .current)
      .trimmingCharacters(in: .whitespacesAndNewlines)
      .lowercased() ?? ""
  }

  /// Burst-dedupe due policy:
  /// - both nil → compatible
  /// - both present → compatible only when within 60s (same inferred instant)
  /// - exactly one nil → compatible, so flaky deadline inference on the same
  ///   screen does not mint a second Candidate inside the reuse window
  /// Distinct non-nil dues remain separate via the both-present branch.
  private static func compatibleDueDates(_ lhs: Date?, _ rhs: Date?) -> Bool {
    switch (lhs, rhs) {
    case (nil, nil): true
    case (.some(let lhs), .some(let rhs)): abs(lhs.timeIntervalSince(rhs)) < 60
    case (nil, .some), (.some, nil): true
    }
  }

  private static let channelActionStems: Set<String> = [
    "reply", "respond", "message", "tell", "ask", "ping", "dm", "text",
  ]

  private static let negationStems: Set<String> = [
    "not", "never", "no", "dont", "don't", "don",
    // Apostrophe forms tokenize to the prefix stem (`won't` → `won`); keep both.
    "cannot", "cant", "wont", "won't", "won", "shouldnt", "shouldn't", "shouldn",
  ]

  /// Ordered strongest-first. First matching purpose class wins unless a
  /// channel verb is leading and a later purpose verb is present.
  /// `open` is intentionally omitted: it is usually the object of another
  /// intent ("approve … to open") rather than a distinguishing action.
  private static let purposeActionClasses: [(canonical: String, stems: Set<String>)] = [
    ("approve", ["approve", "authoriz", "greenlight"]),
    ("review", ["review", "inspect", "audit"]),
    ("close", ["close", "shut", "archive", "dismiss"]),
    ("delete", ["delete", "remov"]),
    ("merge", ["merge"]),
    ("deploy", ["deploy", "releas"]),
    ("fix", ["fix", "repair", "patch"]),
    ("test", ["test"]),
    ("update", ["update", "updat", "edit", "chang"]),
    ("send", ["send", "share", "forward", "ship"]),
    ("complete", ["complete", "finish"]),
  ]

  static func actionSignature(for description: String, metadata: [String: Any]) -> String {
    if (metadata["already_done"] as? Bool) == true { return "complete" }

    let stems = orderedStems(description)
    guard !stems.isEmpty else { return "capture" }

    let purposeHits: [(index: Int, canonical: String)] = stems.enumerated().compactMap {
      index, stem in
      guard let canonical = purposeClass(for: stem) else { return nil }
      return (index, canonical)
    }
    guard !purposeHits.isEmpty else { return "capture" }

    let leadingIsChannel = stems.prefix(3).contains(where: { channelActionStems.contains($0) })
    let selected: (index: Int, canonical: String)
    if leadingIsChannel, let purpose = purposeHits.first(where: { $0.index > 0 }) {
      selected = purpose
    } else {
      selected = purposeHits[0]
    }

    // Polarity: "do not approve" / "never approve" must not collapse into approve.
    // Channel phrasing ("reply … to approve") keeps the positive purpose class.
    if hasNegation(before: selected.index, in: stems) {
      return "not_\(selected.canonical)"
    }
    return selected.canonical
  }

  private static func hasNegation(before purposeIndex: Int, in stems: [String]) -> Bool {
    guard purposeIndex > 0 else { return false }
    let windowStart = max(0, purposeIndex - 3)
    return stems[windowStart..<purposeIndex].contains(where: { negationStems.contains($0) })
  }

  private static func purposeClass(for stem: String) -> String? {
    for entry in purposeActionClasses {
      if entry.stems.contains(where: { stem == $0 || stem.hasPrefix($0) }) {
        return entry.canonical
      }
    }
    return nil
  }

  private static func canonicalTarget(in metadata: [String: Any]) -> String? {
    (metadata["duplicate_of"] as? String) ?? (metadata["refines_task"] as? String)
  }

  private static func containsDigit(_ token: String) -> Bool {
    token.unicodeScalars.contains { CharacterSet.decimalDigits.contains($0) }
  }

  private static func orderedStems(_ value: String) -> [String] {
    let folded = value.folding(
      options: [.diacriticInsensitive, .caseInsensitive], locale: .current)
    let words = folded.lowercased().components(separatedBy: CharacterSet.alphanumerics.inverted)
    return words.compactMap { word in
      guard word.count > 1 else { return nil }
      return stem(word)
    }
  }

  private static func semanticTokens(_ value: String) -> Set<String> {
    let ignored: Set<String> = [
      "a", "about", "an", "and", "for", "in", "of", "on", "the", "to", "with",
    ]
    return Set(
      orderedStems(value).compactMap { word in
        guard !ignored.contains(word) else { return nil }
        return word
      })
  }

  private static func stem(_ word: String) -> String {
    if word == "opening" || word == "opened" || word == "opens" { return "open" }
    if word == "approving" || word == "approved" || word == "approves" { return "approve" }
    if word == "replying" || word == "replied" || word == "replies" { return "reply" }
    if word == "reviewing" || word == "reviewed" || word == "reviews" { return "review" }
    if word == "closing" || word == "closed" || word == "closes" { return "close" }
    if word == "sending" || word == "sent" || word == "sends" { return "send" }
    if word == "responding" || word == "responded" || word == "responds" { return "respond" }
    return word
  }
}

enum ScreenCaptureOutcome: String, Codable {
  case ignore
  case createDirect = "create_direct"
  case autoAcceptSilent = "auto_accept_silent"
  case pendingCandidate = "pending_candidate"
  case proposeEnrichment = "propose_enrichment"
  case proposeUpdate = "propose_update"
  case proposeCompletion = "propose_completion"
}

struct ScreenCaptureFacts: Codable, Equatable {
  var explicitCommand = false
  var clearCommitment = false
  /// Fail closed: unknown deliverable must not silent-accept.
  var concreteDeliverable = false
  var directRequest = false
  var inferredNextStep = false
  var owner = "unknown"
  var publicBroadcast = false
  var directMention = false
  var alreadyDone = false
  var duplicateOf: String?
  var refinesTask: String?
  var captureConfidence = 0.5
  var ownershipConfidence = 0.5
}

enum ScreenCapturePolicy {
  /// Keep in sync with `backend/utils/task_intelligence/capture_policy.py`.
  static let minimumCaptureConfidence = 0.8
  static let minimumOwnershipConfidence = 0.8

  private static func meetsUserCaptureFloor(_ facts: ScreenCaptureFacts) -> Bool {
    facts.owner == "user"
      && facts.concreteDeliverable
      && facts.captureConfidence >= minimumCaptureConfidence
      && facts.ownershipConfidence >= minimumOwnershipConfidence
  }

  static func evaluate(_ facts: ScreenCaptureFacts) -> ScreenCaptureOutcome {
    if facts.alreadyDone { return .proposeCompletion }
    if facts.duplicateOf != nil { return .proposeEnrichment }
    if facts.refinesTask != nil { return .proposeUpdate }
    if facts.publicBroadcast && !facts.directMention { return .ignore }
    if facts.explicitCommand { return .createDirect }
    if facts.clearCommitment && facts.owner == "user" {
      guard facts.concreteDeliverable else { return .ignore }
      if meetsUserCaptureFloor(facts) {
        return .autoAcceptSilent
      }
      return .pendingCandidate
    }
    if facts.directRequest && meetsUserCaptureFloor(facts) { return .pendingCandidate }
    if facts.inferredNextStep && meetsUserCaptureFloor(facts) { return .pendingCandidate }
    return .ignore
  }
}

enum TaskCaptureModePolicy {
  static func usesLegacyStaging(_ mode: OmiAPI.TaskWorkflowMode?) -> Bool {
    switch mode {
    case .off, .shadow, .write:
      return true
    case .read, ._unknown, nil:
      return false
    }
  }

  static func allowsLegacyPromotion(_ mode: OmiAPI.TaskWorkflowMode?) -> Bool {
    usesLegacyStaging(mode)
  }

  static func allowsLegacyRanking(_ mode: OmiAPI.TaskWorkflowMode?) -> Bool {
    usesLegacyStaging(mode)
  }

  static func allowsDestructiveLegacyDeduplication(_ mode: OmiAPI.TaskWorkflowMode?) -> Bool {
    usesLegacyStaging(mode)
  }

  static func allowsTaskCreatedNotification(_ mode: OmiAPI.TaskWorkflowMode?) -> Bool {
    usesLegacyStaging(mode)
  }

  static func allows(_ effect: TaskLegacyEffect, mode: OmiAPI.TaskWorkflowMode?) -> Bool {
    switch effect {
    case .promotion: allowsLegacyPromotion(mode)
    case .notification: allowsTaskCreatedNotification(mode)
    case .ranking: allowsLegacyRanking(mode)
    case .destructiveDeduplication: allowsDestructiveLegacyDeduplication(mode)
    }
  }
}

enum TaskLegacyEffect: CaseIterable {
  case promotion
  case notification
  case ranking
  case destructiveDeduplication
}

struct TaskLegacyEffectGate: Sendable {
  private let modeProvider: @Sendable () async -> OmiAPI.TaskWorkflowMode?

  init(modeProvider: @escaping @Sendable () async -> OmiAPI.TaskWorkflowMode?) {
    self.modeProvider = modeProvider
  }

  func isAllowed(_ effect: TaskLegacyEffect) async -> Bool {
    TaskCaptureModePolicy.allows(effect, mode: await modeProvider())
  }

  func perform<Value>(
    _ effect: TaskLegacyEffect,
    operation: () async throws -> Value
  ) async rethrows -> Value? {
    guard await isAllowed(effect) else { return nil }
    return try await operation()
  }

  static let live = TaskLegacyEffectGate {
    let control = try? await APIClient.shared.getCandidateWorkflowControl()
    return control?.workflowMode
  }
}

/// `CandidateCreate` is a generated Codable model (value type) that is only
/// forwarded to `APIClient` for serialization, never mutated concurrently.
/// The `@unchecked Sendable` conformance lets it cross the `APIClient` actor
/// boundary from the (non-isolated) adapter.
extension OmiAPI.CandidateCreate: @unchecked Sendable {}

struct ScreenCandidateDecision {
  let outcome: ScreenCaptureOutcome
  let candidate: OmiAPI.CandidateCreate?

  var shouldAutoAccept: Bool {
    outcome == .autoAcceptSilent || outcome == .createDirect
  }
}

struct CanonicalScreenCandidateState: @unchecked Sendable {
  let candidateID: String
  let status: OmiAPI.CandidateStatus
  let taskID: String?
}

protocol CanonicalScreenCandidateClient {
  func create(
    _ candidate: OmiAPI.CandidateCreate,
    idempotencyKey: String,
    accountGeneration: Int
  ) async throws -> CanonicalScreenCandidateState

  func accept(candidateID: String, accountGeneration: Int) async throws -> CanonicalScreenCandidateState
}

struct APICanonicalScreenCandidateClient: CanonicalScreenCandidateClient {
  func create(
    _ candidate: OmiAPI.CandidateCreate,
    idempotencyKey: String,
    accountGeneration: Int
  ) async throws -> CanonicalScreenCandidateState {
    let record = try await APIClient.shared.createCanonicalCandidate(
      candidate,
      idempotencyKey: idempotencyKey,
      accountGeneration: accountGeneration
    )
    return CanonicalScreenCandidateState(
      candidateID: record.candidateId,
      status: record.status ?? .pending,
      taskID: record.resultTaskId
    )
  }

  func accept(candidateID: String, accountGeneration: Int) async throws -> CanonicalScreenCandidateState {
    let receipt = try await APIClient.shared.acceptCanonicalCandidate(
      candidateID: candidateID,
      accountGeneration: accountGeneration
    )
    return CanonicalScreenCandidateState(
      candidateID: receipt.candidateId,
      status: receipt.status,
      taskID: receipt.taskId
    )
  }
}

struct CanonicalScreenCandidateDelivery {
  let client: any CanonicalScreenCandidateClient

  func deliver(
    _ decision: ScreenCandidateDecision,
    localID: Int64,
    deviceID: String,
    accountGeneration: Int
  ) async throws -> CanonicalScreenCandidateState? {
    guard let candidate = decision.candidate else { return nil }
    var state = try await client.create(
      candidate,
      idempotencyKey: ScreenCandidateAdapter.idempotencyKey(deviceID: deviceID, localID: localID),
      accountGeneration: accountGeneration
    )
    if decision.shouldAutoAccept && state.status == .pending {
      state = try await client.accept(
        candidateID: state.candidateID,
        accountGeneration: accountGeneration
      )
    }
    return state
  }
}

/// Retry classification for canonical capture outbox delivery failures.
///
/// Transport failures and server-side conditions (5xx, 401 auth refresh, 409
/// generation mismatch, 429 throttling) are transient: the same payload can
/// succeed later, so the outbox row must stay retryable. Validation-class
/// rejections (400/413/415/422) are deterministic — the payload itself can
/// never succeed — so retrying them forever only wedges the queue behind
/// permanently rejected rows.
enum CandidateOutboxRetryPolicy {
  /// Permanent validation rejections tolerated before a row is poisoned.
  /// More than one attempt guards against a backend contract briefly rejecting
  /// a valid payload mid-deploy; three failures on a deterministic 4xx is
  /// conclusive.
  static let maxPermanentRejections = 3

  static func isPermanentRejection(statusCode: Int) -> Bool {
    switch statusCode {
    case 400, 413, 415, 422: return true
    default: return false
    }
  }

  static func isPermanentRejection(_ error: Error) -> Bool {
    guard case APIError.httpError(let statusCode, _) = error else { return false }
    return isPermanentRejection(statusCode: statusCode)
  }

  /// Transient failures stay retryable forever; validation-class rejections
  /// are counted per row and the row is poisoned after a small number of
  /// attempts so a permanently rejected capture cannot wedge the outbox drain.
  static func handleDeliveryFailure(_ error: Error, localID: Int64) async {
    guard isPermanentRejection(error),
      let outcome = try? await StagedTaskStorage.shared.recordCanonicalOutboxRejection(id: localID)
    else {
      logError("Task: Candidate outbox delivery failed; will retry", error: error)
      return
    }
    switch outcome {
    case .willRetry(let rejections):
      logError(
        "Task: Candidate outbox delivery rejected by validation (attempt \(rejections)/\(maxPermanentRejections)); will retry",
        error: error
      )
    case .poisoned(let rejections):
      logError(
        "Task: Candidate outbox delivery rejected by validation \(rejections) times; poisoned row \(localID) and stopped retrying",
        error: error
      )
    }
  }
}

enum ScreenCandidateAdapter {
  static func idempotencyKey(deviceID: String, localID: Int64) -> String {
    "screen:\(deviceID):\(localID)"
  }

  /// Canonical task references must be backend StableIds
  /// (`^[A-Za-z0-9][A-Za-z0-9._:-]*$`, 1–128 chars; keep in sync with
  /// `backend/models/task_intelligence.py`). The extraction model is asked for
  /// a task id in `duplicate_of`/`refines_task` but sometimes echoes the
  /// task's *title* instead. Forwarding that string as `task_id` makes
  /// POST /v1/candidates fail Pydantic validation (HTTP 422) on every outbox
  /// retry, forever. Treat any non-conforming reference as absent so the
  /// capture policy decides create/complete/ignore without a bogus target.
  static func canonicalTaskReference(_ raw: String?) -> String? {
    guard let raw, !raw.isEmpty, raw.count <= 128 else { return nil }
    for (index, scalar) in raw.unicodeScalars.enumerated() {
      let isAlphanumeric =
        (scalar >= "A" && scalar <= "Z")
        || (scalar >= "a" && scalar <= "z")
        || (scalar >= "0" && scalar <= "9")
      if index == 0 {
        guard isAlphanumeric else { return nil }
      } else {
        guard isAlphanumeric || scalar == "." || scalar == "_" || scalar == ":" || scalar == "-"
        else { return nil }
      }
    }
    return raw
  }

  static func facts(for task: ExtractedTask) -> ScreenCaptureFacts {
    let kind = task.captureKind ?? "direct_request"
    return ScreenCaptureFacts(
      explicitCommand: kind == "explicit_command",
      clearCommitment: kind == "clear_commitment",
      concreteDeliverable: task.concreteDeliverable ?? false,
      directRequest: kind == "direct_request",
      inferredNextStep: kind == "inferred_next_step",
      owner: task.owner ?? "unknown",
      publicBroadcast: task.publicBroadcast ?? false,
      directMention: task.directMention ?? false,
      alreadyDone: task.alreadyDone ?? (kind == "already_done"),
      duplicateOf: canonicalTaskReference(task.duplicateOf),
      refinesTask: canonicalTaskReference(task.refinesTask),
      captureConfidence: task.confidence,
      ownershipConfidence: task.ownershipConfidence ?? 0.5
    )
  }

  static func adapt(
    task: ExtractedTask,
    dueAt: Date?,
    localEvidenceID: String,
    deviceID: String
  ) -> ScreenCandidateDecision {
    let facts = facts(for: task)
    let outcome = ScreenCapturePolicy.evaluate(facts)
    guard outcome != .ignore else { return ScreenCandidateDecision(outcome: outcome, candidate: nil) }

    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    let evidence = OmiAPI.EvidenceRef(
      deviceId: deviceID,
      excerptHash: nil,
      id: localEvidenceID,
      kind: .local_screen,
      scope: .device_local,
      version: "capture.v2"
    )
    let owner = OmiAPI.TaskOwner(rawValue: facts.owner) ?? .unknown
    let priority = OmiAPI.TaskPriority(rawValue: task.priority.rawValue)
    let due = dueAt.map { formatter.string(from: $0) }

    if outcome == .proposeEnrichment || outcome == .proposeUpdate,
      let taskID = facts.duplicateOf ?? facts.refinesTask
    {
      let change = OmiAPI.TaskChangePayload(
        description_: task.title,
        dueAt: due,
        dueConfidence: due == nil ? nil : 1,
        owner: owner,
        priority: priority,
        recurrenceParentId: nil,
        recurrenceRule: nil,
        status: nil,
        supersededBy: nil
      )
      return ScreenCandidateDecision(
        outcome: outcome,
        candidate: .taskUpdate(
          OmiAPI.TaskUpdateCandidate(
            captureConfidence: facts.captureConfidence,
            evidenceRefs: [evidence],
            goalId: nil,
            ownershipConfidence: facts.ownershipConfidence,
            proposedAction: "update",
            sourceSurface: "screen",
            subjectKind: "task",
            taskChange: change,
            taskId: taskID,
            workstreamId: nil
          )
        )
      )
    }

    if outcome == .proposeCompletion,
      let taskID = facts.refinesTask ?? facts.duplicateOf
    {
      let change = OmiAPI.TaskChangePayload(
        description_: nil,
        dueAt: nil,
        dueConfidence: nil,
        owner: nil,
        priority: nil,
        recurrenceParentId: nil,
        recurrenceRule: nil,
        status: .completed,
        supersededBy: nil
      )
      return ScreenCandidateDecision(
        outcome: outcome,
        candidate: .taskComplete(
          OmiAPI.TaskCompleteCandidate(
            captureConfidence: facts.captureConfidence,
            evidenceRefs: [evidence],
            goalId: nil,
            ownershipConfidence: facts.ownershipConfidence,
            proposedAction: "complete",
            sourceSurface: "screen",
            subjectKind: "task",
            taskChange: change,
            taskId: taskID,
            workstreamId: nil
          )
        )
      )
    }
    guard outcome != .proposeCompletion else {
      return ScreenCandidateDecision(outcome: outcome, candidate: nil)
    }
    let payload = OmiAPI.TaskCreatePayload(
      description_: task.title,
      dueAt: due,
      dueConfidence: due == nil ? nil : 1,
      owner: owner,
      priority: priority,
      recurrenceParentId: nil,
      recurrenceRule: nil
    )
    return ScreenCandidateDecision(
      outcome: outcome,
      candidate: .taskCreate(
        OmiAPI.TaskCreateCandidate(
          captureConfidence: facts.captureConfidence,
          evidenceRefs: [evidence],
          goalId: nil,
          ownershipConfidence: facts.ownershipConfidence,
          proposedAction: "create",
          sourceSurface: "screen",
          subjectKind: "task",
          taskChange: payload,
          workstreamId: nil
        )
      )
    )
  }
}
