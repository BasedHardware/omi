import Foundation

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

    static func evaluate(_ facts: ScreenCaptureFacts) -> ScreenCaptureOutcome {
        if facts.alreadyDone { return .proposeCompletion }
        if facts.duplicateOf != nil { return .proposeEnrichment }
        if facts.refinesTask != nil { return .proposeUpdate }
        if facts.publicBroadcast && !facts.directMention { return .ignore }
        if facts.explicitCommand { return .createDirect }
        if facts.clearCommitment && facts.owner == "user" {
            if facts.concreteDeliverable && facts.captureConfidence >= minimumCaptureConfidence {
                return .autoAcceptSilent
            }
            return .pendingCandidate
        }
        if facts.directRequest || facts.inferredNextStep { return .pendingCandidate }
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

struct TaskLegacyEffectGate {
    private let modeProvider: () async -> OmiAPI.TaskWorkflowMode?

    init(modeProvider: @escaping () async -> OmiAPI.TaskWorkflowMode?) {
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

struct ScreenCandidateDecision {
    let outcome: ScreenCaptureOutcome
    let candidate: OmiAPI.CandidateCreate?

    var shouldAutoAccept: Bool {
        outcome == .autoAcceptSilent || outcome == .createDirect
    }
}

struct CanonicalScreenCandidateState {
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

enum ScreenCandidateAdapter {
    static func idempotencyKey(deviceID: String, localID: Int64) -> String {
        "screen:\(deviceID):\(localID)"
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
            duplicateOf: task.duplicateOf,
            refinesTask: task.refinesTask,
            captureConfidence: task.confidence,
            ownershipConfidence: task.ownershipConfidence ?? (task.owner == "user" ? task.confidence : 0.5)
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
            version: "capture.v1"
        )
        let owner = OmiAPI.TaskOwner(rawValue: facts.owner) ?? .unknown
        let priority = OmiAPI.TaskPriority(rawValue: task.priority.rawValue)
        let due = dueAt.map { formatter.string(from: $0) }

        if outcome == .proposeEnrichment || outcome == .proposeUpdate,
           let taskID = facts.duplicateOf ?? facts.refinesTask {
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
           let taskID = facts.refinesTask ?? facts.duplicateOf {
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
