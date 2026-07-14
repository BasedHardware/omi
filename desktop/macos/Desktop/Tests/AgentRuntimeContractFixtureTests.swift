import Foundation
import XCTest

@testable import Omi_Computer

final class AgentRuntimeContractFixtureTests: XCTestCase {
  func testSharedV1FixtureCoversRuntimeContractsAndSessionListingBudget() throws {
    let contract = try fixture(named: "agent-runtime-contract.fixture.json")
    let schema = try fixture(named: "agent-runtime-contract.schema.json")

    XCTAssertEqual(contract["version"] as? Int, 1)
    XCTAssertTrue(validateFixture(value: contract, schema: schema).isEmpty)
    let contextPlan = try XCTUnwrap((contract["contextSnapshot"] as? [String: Any])?["contextPlan"] as? [String: Any])
    let plan = try XCTUnwrap(AgentConversationContextPlan(dictionary: contextPlan))
    XCTAssertEqual(plan.olderHistoryStrategy, "truncated")
    XCTAssertEqual(plan.omittedTurnCount, 1)

    let envelope = try XCTUnwrap(contract["toolResultEnvelope"] as? [String: Any])
    XCTAssertEqual(envelope["originalBytes"] as? Int, 634_880)
    XCTAssertEqual(envelope["projectedBytes"] as? Int, 8_192)
    XCTAssertEqual((contract["sessionListingBudget"] as? [String: Any])?["maxBytes"] as? Int, 8_192)
    XCTAssertTrue((contract["failureTaxonomy"] as? [String] ?? []).contains("bridge_start_failed"))
    XCTAssertEqual((contract["permissionDecision"] as? [String: Any])?["decision"] as? String, "approved")
    XCTAssertEqual((contract["toolInvocation"] as? [String: Any])?["invocationId"] as? String,
      ((envelope["provenance"] as? [String: Any])?["invocationId"] as? String))
    XCTAssertEqual((contract["lifecycle"] as? [String: [String]])?["run"]?.contains("succeeded"), true)
    XCTAssertEqual((contract["adapterConformance"] as? [[String: Any]])?.count, 6)
    XCTAssertTrue((contract["adapterConformance"] as? [[String: Any]] ?? []).contains {
      $0["adapterId"] as? String == "openai-realtime" && $0["transport"] as? String == "swift_realtime"
    })
  }

  func testSharedMalformedFixtureFailsTheSwiftContextPlanContract() throws {
    let malformed = try fixture(named: "malformed-context-plan.fixture.json")
    let dictionary = try XCTUnwrap((malformed["contextSnapshot"] as? [String: Any])?["contextPlan"] as? [String: Any])
    XCTAssertNil(AgentConversationContextPlan(dictionary: dictionary))
  }

  func testSharedSchemaRejectsMalformedContractsAtEveryBoundary() throws {
    let schema = try fixture(named: "agent-runtime-contract.schema.json")
    var contract = try fixture(named: "agent-runtime-contract.fixture.json")
    var adapters = try XCTUnwrap(contract["adapterConformance"] as? [[String: Any]])
    adapters[0]["expectsToolEnvelope"] = false
    contract["adapterConformance"] = adapters

    XCTAssertTrue(validate(value: contract, schema: schema)
      .contains("$.adapterConformance[0].expectsToolEnvelope: const mismatch"))

    for (name, key) in [
      ("malformed-tool-result-envelope.fixture.json", "toolResultEnvelope"),
      ("malformed-permission-decision.fixture.json", "permissionDecision"),
      ("malformed-tool-invocation.fixture.json", "toolInvocation"),
      ("malformed-lifecycle.fixture.json", "lifecycle"),
      ("malformed-failure-taxonomy.fixture.json", "failureTaxonomy"),
    ] {
      let malformed = try fixture(named: name)
      var candidate = try fixture(named: "agent-runtime-contract.fixture.json")
      candidate[key] = malformed[key]
      XCTAssertTrue(
        validateFixture(value: candidate, schema: schema).contains(malformed["expectedError"] as? String ?? ""),
        "Expected \(name) to fail its shared contract boundary")
    }
  }

  func testSwiftRealtimeAdaptersExecuteSharedLifecycleFailureAndOversizedToolFixture() throws {
    let contract = try fixture(named: "agent-runtime-contract.fixture.json")
    let adapters = try XCTUnwrap(contract["adapterConformance"] as? [[String: Any]])
    let toolName = try XCTUnwrap((contract["toolInvocation"] as? [String: Any])?["toolName"] as? String)
    let oversizedOutput = try XCTUnwrap(String(
      data: JSONSerialization.data(withJSONObject: [
        "ok": true,
        "payload": String(repeating: "x", count: RealtimeProviderToolResultPolicy.maximumByteCount + 1),
        "toolResultEnvelope": contract["toolResultEnvelope"] as Any,
      ]),
      encoding: .utf8))

    for adapter in adapters where adapter["transport"] as? String == "swift_realtime" {
      let provider: RealtimeHubProvider = adapter["adapterId"] as? String == "gemini-realtime" ? .gemini : .openai
      XCTAssertTrue([RealtimeHubProvider.gemini, .openai].contains(provider))
      let providerResult = RealtimeProviderToolResultPolicy.prepare(
        provider: provider,
        name: toolName,
        output: oversizedOutput)
      let output = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(providerResult.output.utf8)) as? [String: Any])
      let envelope = try XCTUnwrap(output["toolResultEnvelope"] as? [String: Any])
      XCTAssertTrue(providerResult.wasOversized)
      XCTAssertEqual(envelope["status"] as? String, "failed")
      XCTAssertEqual(envelope["truncated"] as? Bool, true)
      XCTAssertEqual(envelope["fullOutputRef"] as? String, "artifact:tool-output:example")
      let scenarios = try XCTUnwrap(adapter["scenarios"] as? [[String: Any]])
      for scenario in scenarios {
        XCTAssertEqual(scenario["runState"] as? String, "failed")
        XCTAssertEqual(scenario["attemptState"] as? String, "failed")
        XCTAssertEqual(scenario["turnState"] as? String, "failed")
        XCTAssertTrue((contract["failureTaxonomy"] as? [String] ?? []).contains(scenario["failureCode"] as? String ?? ""))
        XCTAssertEqual(scenario["consumesToolInvocation"] as? Bool, true)
        XCTAssertEqual(scenario["expectsTruncatedToolEnvelope"] as? Bool, true)
      }
    }
  }

  private func fixture(named name: String) throws -> [String: Any] {
    let macosDirectory = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
    let url = macosDirectory.appendingPathComponent("agent/contracts/v1/\(name)")
    let data = try Data(contentsOf: url)
    return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
  }

  private func validateFixture(value: [String: Any], schema: [String: Any]) -> [String] {
    var errors = validate(value: value, schema: schema)
    let envelope = value["toolResultEnvelope"] as? [String: Any]
    let provenance = envelope?["provenance"] as? [String: Any]
    let invocation = value["toolInvocation"] as? [String: Any]
    let permission = value["permissionDecision"] as? [String: Any]
    for field in ["invocationId", "runId", "attemptId", "toolName"] {
      if let provenance, let invocation, !jsonEqual(provenance[field] as Any, invocation[field] as Any) {
        errors.append("$.toolInvocation.\(field): does not match envelope provenance")
      }
    }
    if let provenance, let permission, !jsonEqual(provenance["invocationId"] as Any, permission["invocationId"] as Any) {
      errors.append("$.permissionDecision.invocationId: does not match envelope provenance")
    }
    if let envelope, envelope["truncated"] as? Bool == true, !(envelope["fullOutputRef"] is String) {
      errors.append("$.toolResultEnvelope.fullOutputRef: truncated output requires an artifact reference")
    }
    let expectedLifecycle: [String: [String]] = [
      "session": ["open", "archived", "closed"],
      "run": [
        "queued", "starting", "running", "waiting_input", "waiting_approval", "cancelling", "succeeded", "failed",
        "cancelled", "timed_out", "orphaned",
      ],
      "attempt": [
        "queued", "starting", "running", "waiting_input", "waiting_approval", "cancelling", "succeeded", "failed",
        "cancelled", "timed_out", "orphaned",
      ],
      "turn": ["pending", "streaming", "completed", "failed"],
    ]
    if let lifecycle = value["lifecycle"] as? [String: [String]] {
      for (name, expected) in expectedLifecycle where lifecycle[name] != expected {
        errors.append("$.lifecycle.\(name): must declare the complete production state set")
      }
    }
    return errors
  }

  /// Dependency-free subset used by the shared fixture's checked-in JSON
  /// Schema. The Node test runs the same schema; both languages therefore fail
  /// when its wire contract diverges instead of merely reading documentation.
  private func validate(value: Any, schema: [String: Any], path: String = "$") -> [String] {
    var errors: [String] = []
    if let declared = schema["type"] {
      let types = declared as? [String] ?? (declared as? String).map { [$0] } ?? []
      if !types.contains(where: { matches(value: value, type: $0) }) {
        return ["\(path): expected \(types.joined(separator: " | "))"]
      }
    }
    if let constant = schema["const"], !jsonEqual(value, constant) {
      errors.append("\(path): const mismatch")
    }
    if let allowed = schema["enum"] as? [Any], !allowed.contains(where: { jsonEqual(value, $0) }) {
      errors.append("\(path): value is outside enum")
    }
    if let string = value as? String, let minimum = schema["minLength"] as? Int, string.count < minimum {
      errors.append("\(path): string is shorter than minLength")
    }
    if let number = value as? NSNumber, let minimum = schema["minimum"] as? Int, number.intValue < minimum {
      errors.append("\(path): number is below minimum")
    }
    if let values = value as? [Any] {
      if let minimum = schema["minItems"] as? Int, values.count < minimum {
        errors.append("\(path): array has too few items")
      }
      if let itemSchema = schema["items"] as? [String: Any] {
        for (index, item) in values.enumerated() {
          errors += validate(value: item, schema: itemSchema, path: "\(path)[\(index)]")
        }
      }
    }
    if let object = value as? [String: Any] {
      let properties = schema["properties"] as? [String: [String: Any]] ?? [:]
      for key in schema["required"] as? [String] ?? [] where object[key] == nil {
        errors.append("\(path): missing \(key)")
      }
      if schema["additionalProperties"] as? Bool == false {
        for key in object.keys where properties[key] == nil {
          errors.append("\(path): unexpected \(key)")
        }
      }
      for (key, childSchema) in properties where object[key] != nil {
        errors += validate(value: object[key] as Any, schema: childSchema, path: "\(path).\(key)")
      }
    }
    return errors
  }

  private func matches(value: Any, type: String) -> Bool {
    switch type {
    case "object": return value is [String: Any]
    case "array": return value is [Any]
    case "string": return value is String
    case "boolean": return value is Bool
    case "null": return value is NSNull
    case "integer": return (value as? NSNumber).map { Double($0.intValue) == $0.doubleValue } ?? false
    default: return value is NSNumber
    }
  }

  private func jsonEqual(_ lhs: Any, _ rhs: Any) -> Bool {
    switch (lhs, rhs) {
    case let (lhs as NSNumber, rhs as NSNumber): return lhs == rhs
    case let (lhs as String, rhs as String): return lhs == rhs
    case let (lhs as Bool, rhs as Bool): return lhs == rhs
    default: return false
    }
  }
}
