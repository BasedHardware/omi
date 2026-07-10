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

    func testTicket03CharacterizesCanonicalFieldsLostBySwiftWireAndCacheRoundTrip() throws {
        let source: [String: Any] = [
            "description": "Send the budget",
            "completed": false,
            "goal_id": "goal-1",
            "workstream_id": "workstream-1",
            "owner": "user",
            "source": "conversation",
            "provenance": [["kind": "conversation", "id": "conversation-1", "scope": "canonical"]],
            "due_confidence": 0.9,
        ]
        let decoded = try JSONDecoder().decode(ActionItem.self, from: JSONSerialization.data(withJSONObject: source))
        let encoded = try JSONEncoder().encode(decoded)
        let roundTrip = try XCTUnwrap(JSONSerialization.jsonObject(with: encoded) as? [String: Any])
        let options = XCTExpectedFailure.Options()
        options.isStrict = true

        XCTExpectFailure("#9352 Ticket 03 removes the Swift wire/cache canonical round-trip gap", options: options) {
            XCTAssertEqual(roundTrip["goal_id"] as? String, "goal-1")
            XCTAssertEqual(roundTrip["workstream_id"] as? String, "workstream-1")
            XCTAssertEqual(roundTrip["owner"] as? String, "user")
            XCTAssertEqual(roundTrip["source"] as? String, "conversation")
            XCTAssertNotNil(roundTrip["provenance"])
            XCTAssertEqual(roundTrip["due_confidence"] as? Double, 0.9)
        }
    }
}
