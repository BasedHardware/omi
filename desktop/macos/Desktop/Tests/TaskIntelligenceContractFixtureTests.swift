import Foundation
import XCTest

@testable import Omi_Computer

final class TaskIntelligenceContractFixtureTests: XCTestCase {
    private func repositoryRoot() -> URL {
        var url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        for _ in 0..<4 { url.deleteLastPathComponent() }
        return url
    }

    func testV1ContractHasCrossLaneDomainsAndExamples() throws {
        let url = repositoryRoot().appendingPathComponent("backend/config/task_intelligence_contract_v1.json")
        let data = try Data(contentsOf: url)
        let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let definitions = try XCTUnwrap(root["$defs"] as? [String: Any])
        let examples = try XCTUnwrap(root["examples"] as? [String: Any])
        let required = [
            "task", "candidate", "goal", "workstream", "workstream_event", "evidence_ref", "feedback",
            "recommendation", "decision_record", "kernel_workstream_bridge", "attribution_event",
        ]

        XCTAssertEqual(root["schema_version"] as? Int, 1)
        for domain in required {
            XCTAssertNotNil(definitions[domain], "Missing schema for \(domain)")
            XCTAssertNotNil(examples[domain], "Missing examples for \(domain)")
        }
        let taskExamples = try XCTUnwrap(examples["task"] as? [[String: Any]])
        XCTAssertEqual(taskExamples.first?["priority"] as? String, "high")
    }

    func testCaptureFixturesHaveIdenticalRecordedAdapterOutputsAcrossModalities() throws {
        let url = repositoryRoot()
            .appendingPathComponent("backend/tests/unit/fixtures/task_intelligence/capture_v1.json")
        let data = try Data(contentsOf: url)
        let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let cases = try XCTUnwrap(root["cases"] as? [[String: Any]])

        XCTAssertFalse(cases.isEmpty)
        for fixture in cases {
            let inputs = try XCTUnwrap(fixture["inputs"] as? [String: [String: Any]])
            let transcript = try XCTUnwrap(inputs["transcript"]?["stub_output"] as? NSDictionary)
            let screen = try XCTUnwrap(inputs["screen"]?["stub_output"] as? NSDictionary)
            XCTAssertEqual(transcript, screen, "Fixture modalities drifted for \(fixture["id"] ?? "unknown")")
        }
    }

    func testCanonicalTaskFieldsSurviveSwiftWireAndCacheRoundTrip() throws {
        let fixtureURL = repositoryRoot()
            .appendingPathComponent("backend/tests/unit/fixtures/task_intelligence/canonical_round_trip_v1.json")
        let fixture = try XCTUnwrap(
            JSONSerialization.jsonObject(with: Data(contentsOf: fixtureURL)) as? [String: Any]
        )
        let source = try XCTUnwrap(fixture["create_response"] as? [String: Any])
        let createPayload = try XCTUnwrap(fixture["create_request"] as? [String: Any])
        let updatePayload = try XCTUnwrap(fixture["update_request"] as? [String: Any])
        let listPayload = try XCTUnwrap(fixture["list_response"] as? [String: Any])
        let workstreamPayload = try XCTUnwrap(fixture["linked_workstream"] as? [String: Any])
        let createRequest = try JSONDecoder().decode(
            OmiAPI.ActionItemCreateRequest.self,
            from: JSONSerialization.data(withJSONObject: createPayload)
        )
        let updateRequest = try JSONDecoder().decode(
            OmiAPI.ActionItemUpdateRequest.self,
            from: JSONSerialization.data(withJSONObject: updatePayload)
        )
        let listResponse = try JSONDecoder().decode(
            OmiAPI.ActionItemsResponse.self,
            from: JSONSerialization.data(withJSONObject: listPayload)
        )
        let workstream = try JSONDecoder().decode(
            OmiAPI.Workstream.self,
            from: JSONSerialization.data(withJSONObject: workstreamPayload)
        )
        let decoded = try JSONDecoder().decode(TaskActionItem.self, from: JSONSerialization.data(withJSONObject: source))
        let restored = ActionItemRecord.from(decoded).toTaskActionItem()
        let encoded = try JSONEncoder().encode(restored)
        let roundTrip = try XCTUnwrap(JSONSerialization.jsonObject(with: encoded) as? [String: Any])

        XCTAssertEqual(roundTrip["goal_id"] as? String, "goal-1")
        XCTAssertEqual(roundTrip["workstream_id"] as? String, "workstream-1")
        XCTAssertEqual(roundTrip["owner"] as? String, "user")
        XCTAssertEqual(roundTrip["source"] as? String, "conversation")
        XCTAssertEqual(roundTrip["status"] as? String, "active")
        XCTAssertEqual(roundTrip["task_id"] as? String, "task-1")
        XCTAssertEqual(roundTrip["due_confidence"] as? Double, 0.9)
        XCTAssertEqual(roundTrip["sort_order"] as? Int, 4)
        XCTAssertEqual(roundTrip["indent_level"] as? Int, 1)
        XCTAssertEqual(roundTrip["recurrence_rule"] as? String, "weekly")
        XCTAssertNotNil(roundTrip["created_at"])
        XCTAssertNotNil(roundTrip["updated_at"])
        let provenance = try XCTUnwrap(roundTrip["provenance"] as? [[String: Any]])
        XCTAssertEqual(provenance.count, 2)
        XCTAssertEqual(provenance[1]["scope"] as? String, "device_local")
        XCTAssertEqual(provenance[1]["device_id"] as? String, "mac-1")
        XCTAssertEqual(createRequest.workstreamId, "workstream-1")
        guard case .value(.completed) = updateRequest.status else {
            return XCTFail("update fixture must carry an explicit completed status")
        }
        XCTAssertEqual(listResponse.actionItems.first?.workstreamId, "workstream-1")
        XCTAssertEqual(workstream.workstreamId, decoded.workstreamId)
        XCTAssertEqual(workstream.status, .open_)

        let unlink = OmiAPI.ActionItemUpdateRequest(
            description_: .value("Keep this field only"),
            goalId: .null
        )
        let unlinkData = try JSONEncoder().encode(unlink)
        let unlinkJSON = try XCTUnwrap(JSONSerialization.jsonObject(with: unlinkData) as? [String: Any])
        XCTAssertTrue(unlinkJSON.keys.contains("goal_id"))
        XCTAssertTrue(unlinkJSON["goal_id"] is NSNull)
        XCTAssertFalse(unlinkJSON.keys.contains("workstream_id"))

        let goalPatch = OmiAPI.GoalUpdate(
            desiredOutcome: .null,
            title: .value("Keep moving")
        )
        let goalPatchJSON = try XCTUnwrap(
            JSONSerialization.jsonObject(with: JSONEncoder().encode(goalPatch)) as? [String: Any]
        )
        XCTAssertTrue(goalPatchJSON["desired_outcome"] is NSNull)
        XCTAssertFalse(goalPatchJSON.keys.contains("why_it_matters"))

        let workstreamPatch = OmiAPI.WorkstreamUpdate(nextReviewAt: .null)
        let workstreamPatchJSON = try XCTUnwrap(
            JSONSerialization.jsonObject(with: JSONEncoder().encode(workstreamPatch)) as? [String: Any]
        )
        XCTAssertTrue(workstreamPatchJSON["next_review_at"] is NSNull)
        XCTAssertFalse(workstreamPatchJSON.keys.contains("objective"))
    }

    func testCandidateTaskChangeUsesDiscriminatedGeneratedPayload() throws {
        let data = try JSONSerialization.data(withJSONObject: [
            "candidate_id": "candidate-1",
            "subject_kind": "task",
            "proposed_action": "create",
            "task_change": ["description": "Send the budget", "owner": "user"],
            "capture_confidence": 0.9,
            "ownership_confidence": 1.0,
            "evidence_refs": [["kind": "conversation", "id": "conversation-1", "scope": "canonical"]],
            "source_surface": "desktop_screen",
            "status": "pending",
            "account_generation": 7,
            "idempotency_key": "idempotency-1",
            "created_at": "2026-07-09T12:00:00Z",
        ])
        let candidate = try JSONDecoder().decode(OmiAPI.CandidateRecord.self, from: data)

        guard case .create(let payload) = candidate.taskChange else {
            return XCTFail("create Candidate must decode a TaskCreatePayload")
        }
        XCTAssertEqual(payload.description_, "Send the budget")
    }
}

final class TaskIntelligenceSQLiteRoundTripTests: XCTestCase {
    private var testUserId: String!
    private var userDirectory: URL!

    override func setUp() async throws {
        try await super.setUp()
        testUserId = "task-intelligence-contract-\(UUID().uuidString)"
        await RewindDatabase.shared.close()
        await ActionItemStorage.shared.invalidateCache()
        let appSupport = FileManager.default
            .urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        userDirectory = appSupport
            .appendingPathComponent("Omi", isDirectory: true)
            .appendingPathComponent("users", isDirectory: true)
            .appendingPathComponent(testUserId, isDirectory: true)
        // Create the isolated destination first so initialization never treats
        // this test identity as a first real user and migrates anonymous data.
        try FileManager.default.createDirectory(
            at: userDirectory,
            withIntermediateDirectories: true
        )
        RewindDatabase.currentUserId = testUserId
        await RewindDatabase.shared.configure(userId: testUserId)
        try await RewindDatabase.shared.initialize()
    }

    override func tearDown() async throws {
        await RewindDatabase.shared.close()
        await ActionItemStorage.shared.invalidateCache()
        RewindDatabase.currentUserId = nil
        if let userDirectory { try? FileManager.default.removeItem(at: userDirectory) }
        try await super.tearDown()
    }

    func testCanonicalTaskFieldsSurviveSQLitePersistence() async throws {
        var root = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        for _ in 0..<4 { root.deleteLastPathComponent() }
        let fixtureURL = root
            .appendingPathComponent("backend/tests/unit/fixtures/task_intelligence/canonical_round_trip_v1.json")
        let fixture = try XCTUnwrap(
            JSONSerialization.jsonObject(with: Data(contentsOf: fixtureURL)) as? [String: Any]
        )
        let updateResponse = try XCTUnwrap(fixture["update_response"] as? [String: Any])
        let item = try JSONDecoder().decode(
            TaskActionItem.self,
            from: JSONSerialization.data(withJSONObject: updateResponse)
        )

        try await ActionItemStorage.shared.syncTaskActionItems([item])
        let stored = try await ActionItemStorage.shared.getLocalActionItem(byBackendId: item.id)
        let restored = try XCTUnwrap(stored)

        XCTAssertEqual(restored.goalId, "goal-1")
        XCTAssertEqual(restored.taskId, "task-1")
        XCTAssertEqual(restored.taskStatus, "completed")
        XCTAssertEqual(restored.taskOwner, "user")
        XCTAssertEqual(restored.workstreamId, "workstream-1")
        XCTAssertEqual(restored.dueConfidence, 1.0)
        XCTAssertEqual(restored.completedAt, item.completedAt)
        XCTAssertEqual(restored.createdAt, item.createdAt)
        XCTAssertEqual(restored.updatedAt, item.updatedAt)
        XCTAssertEqual(restored.sortOrder, 5)
        XCTAssertEqual(restored.indentLevel, 2)
        XCTAssertEqual(restored.recurrenceRule, "monthly")
        XCTAssertEqual(restored.provenance?.first?.version, "2")
    }
}
