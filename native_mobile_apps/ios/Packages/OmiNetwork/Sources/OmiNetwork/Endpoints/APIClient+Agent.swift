import CryptoKit
import Foundation
import OmiCore

/// Agent bookkeeping on backend workstreams (`routers/workstreams.py`). The backend records,
/// the chat agent works: the client opens a work intent, streams the task through `v2/messages`,
/// and records progress and the result on the workstream (same contract as the desktop app).
public extension APIClient {
    /// `GET v1/candidates/control` → account generation for task-intelligence writes.
    func accountGeneration() async throws -> Int {
        let data = try await data(.get, "v1/candidates/control")
        return try decode(OmiAPI.TaskWorkflowControl.self, from: data).accountGeneration ?? 0
    }

    /// `POST v1/work-intents` for a task. Idempotent per task.
    func startWork(onTask taskID: String, title: String, generation: Int) async throws -> String {
        let body = try JSONSerialization.data(withJSONObject: ["origin": "task", "task_id": taskID, "title": title])
        let data = try await data(.post, "v1/work-intents", body: .json(body), headers: [
            "Idempotency-Key": "work-intent:task:\(taskID)",
            "X-Account-Generation": String(generation),
        ])
        return try decode(OmiAPI.WorkIntentReceipt.self, from: data).workstreamId
    }

    /// `POST v1/workstreams/{id}/events` → event id.
    @discardableResult
    func recordWorkstreamEvent(
        _ ref: WorkstreamRef,
        kind: String,
        summary: String,
        evidence: [[String: String]],
        idempotencyKey: String
    ) async throws -> String {
        let body = try JSONSerialization.data(withJSONObject: [
            "kind": kind, "summary": String(summary.prefix(2000)), "evidence_refs": evidence, "sensitivity": "normal",
        ])
        let data = try await data(.post, "v1/workstreams/\(ref.id)/events", body: .json(body), headers: [
            "Idempotency-Key": idempotencyKey,
            "X-Account-Generation": String(ref.generation),
        ])
        return try decode(OmiAPI.WorkstreamEvent.self, from: data).eventId
    }

    /// `POST v1/workstreams/{id}/artifacts`: the result, pointing at the chat message that holds it.
    func recordResultArtifact(
        _ ref: WorkstreamRef,
        messageID: String,
        resultText: String,
        evidenceEventID: String,
        runID: String
    ) async throws {
        let hash = SHA256.hash(data: Data(resultText.utf8)).map { String(format: "%02x", $0) }.joined()
        let body = try JSONSerialization.data(withJSONObject: [
            "logical_key": "omi-result-\(runID)", "version": 1, "kind": "chat_answer",
            "uri": "omi://chat/messages/\(messageID)", "content_hash": hash, "source_run_id": runID,
            "evidence_event_ids": [evidenceEventID], "evidence_refs": [[String: String]](),
        ])
        _ = try await data(.post, "v1/workstreams/\(ref.id)/artifacts", body: .json(body), headers: [
            "Idempotency-Key": "artifact:\(runID)",
            "X-Account-Generation": String(ref.generation),
        ])
    }

    /// `PATCH v1/workstreams/{id}`
    func updateWorkstream(_ ref: WorkstreamRef, status: Workstream.Status?, summary: String?) async throws {
        var fields: [String: Any] = [:]
        if let status { fields["status"] = status.rawValue }
        if let summary { fields["current_state_summary"] = String(summary.prefix(2000)) }
        _ = try await data(.patch, "v1/workstreams/\(ref.id)", body: .json(JSONSerialization.data(withJSONObject: fields)), headers: [
            "Idempotency-Key": "workstream-update:\(ref.id):\(UUID().uuidString)",
            "X-Account-Generation": String(ref.generation),
        ])
    }

    /// `GET v1/workstreams/{id}`
    func workstream(_ workstreamID: String) async throws -> Workstream {
        let detail = try await decode(OmiAPI.WorkstreamDetailProjection.self, from: data(.get, "v1/workstreams/\(workstreamID)"))
        return Workstream(
            id: detail.workstream.workstreamId,
            title: detail.workstream.title,
            status: Workstream.Status(rawValue: detail.workstream.status.rawValue) ?? .unknown,
            summary: detail.workstream.currentStateSummary,
            events: detail.recentEvents.sorted { $0.sequence < $1.sequence }.map(WorkstreamMapper.event),
            updatedAt: BackendDate.parse(detail.workstream.updatedAt),
            lastProgressAt: BackendDate.parse(detail.workstream.lastMeaningfulProgressAt)
        )
    }

    /// `GET v1/what-matters-now` (up to three recommendations; empty is the normal case).
    func whatMattersNow() async throws -> [Recommendation] {
        let projection = try await decode(OmiAPI.WhatMattersNowProjection.self, from: data(.get, "v1/what-matters-now"))
        return projection.recommendations.map(RecommendationMapper.map)
    }

    /// `POST v1/task-intelligence/feedback`: what the user decided about a recommendation. The
    /// backend pauses it (later: a day, dismiss: a month) and learns from it.
    func sendRecommendationFeedback(_ recommendation: Recommendation, decision: Recommendation.Decision, generation: Int) async throws {
        let body = RecommendationMapper.feedbackBody(recommendation, decision: decision)
        _ = try await data(.post, "v1/task-intelligence/feedback", body: .json(JSONSerialization.data(withJSONObject: body)), headers: [
            "Idempotency-Key": "feedback:\(recommendation.id):\(decision.rawValue)",
            "X-Account-Generation": String(generation),
        ])
    }

    /// `GET v1/workstreams/{id}/events?after_sequence=`: the whole log, oldest first (paged by 200).
    func workstreamEvents(_ workstreamID: String, afterSequence: Int) async throws -> [Workstream.Event] {
        let events = try await decode([OmiAPI.WorkstreamEvent].self, from: data(.get, "v1/workstreams/\(workstreamID)/events", query: [
            URLQueryItem(name: "after_sequence", value: String(afterSequence)),
            URLQueryItem(name: "limit", value: "200"),
        ]))
        return events.sorted { $0.sequence < $1.sequence }.map(WorkstreamMapper.event)
    }
}

enum RecommendationMapper {
    static func map(_ dto: OmiAPI.Recommendation) -> Recommendation {
        Recommendation(
            id: dto.interventionId,
            headline: dto.headline,
            whyNow: dto.whyNow,
            action: dto.recommendedAction,
            taskID: dto.destinationTaskId,
            workstreamID: dto.destinationWorkstreamId,
            goalLabel: dto.goalOrWorkstreamLabel.flatMap { $0.isEmpty ? nil : $0 },
            alternativeAction: dto.alternativeAction.flatMap { $0.isEmpty ? nil : $0 },
            evidencePreview: dto.evidencePreview,
            evidence: dto.evidenceRefs.map { Recommendation.Evidence(kind: $0.kind.rawValue, id: $0.id) },
            feedbackSubjectKind: dto.feedbackSubjectKind.rawValue,
            feedbackSubjectID: dto.feedbackSubjectId,
            dedupeKey: dto.dedupeKey,
            expiresAt: BackendDate.parse(dto.expiresAt)
        )
    }

    /// `FeedbackCreate`: "already handled" is a dismiss with a reason; do now, later and dismiss
    /// must name the intervention.
    static func feedbackBody(_ recommendation: Recommendation, decision: Recommendation.Decision) -> [String: Any] {
        var body: [String: Any] = [
            "subject_kind": recommendation.feedbackSubjectKind,
            "subject_id": recommendation.feedbackSubjectID,
            "intervention_id": recommendation.id,
        ]
        switch decision {
        case .doNow: body["action"] = "do_now"
        case .later: body["action"] = "later"
        case .dismiss: body["action"] = "dismiss"
        case .complete: body["action"] = "complete"
        case .alreadyHandled:
            body["action"] = "dismiss"
            body["reason"] = "already_handled"
        }
        return body
    }
}

enum WorkstreamMapper {
    static func event(_ dto: OmiAPI.WorkstreamEvent) -> Workstream.Event {
        Workstream.Event(
            id: dto.eventId, kind: dto.kind.rawValue, summary: dto.summary, createdAt: BackendDate.parse(dto.createdAt),
            sequence: dto.sequence,
            evidence: (dto.evidenceRefs ?? []).map { Workstream.Event.Evidence(kind: $0.kind.rawValue, id: $0.id) }
        )
    }
}
