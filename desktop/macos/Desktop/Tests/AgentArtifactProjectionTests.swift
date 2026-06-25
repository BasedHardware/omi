import XCTest

@testable import Omi_Computer

final class AgentArtifactProjectionTests: XCTestCase {
  func testParsesArtifactMetadataProjection() throws {
    let result = """
      {
        "ok": true,
        "artifacts": [
          {
            "artifactId": "artifact-1",
            "omiSessionId": "session-1",
            "runId": "run-1",
            "attemptId": "attempt-1",
            "kind": "json",
            "role": "result",
            "uri": "omi-artifact://artifact-1",
            "displayName": "summary.json",
            "mimeType": "application/json",
            "contentHash": "sha256:abc",
            "sizeBytes": 42,
            "lifecycleState": "opened",
            "lifecycleUpdatedAtMs": 1234,
            "metadata": {
              "adapter": "pi-mono",
              "nested": { "index": 2 }
            },
            "createdAtMs": 99
          }
        ]
      }
      """

    let artifacts = try AgentArtifactProjection.parseList(fromToolResult: result)

    XCTAssertEqual(artifacts.count, 1)
    XCTAssertEqual(artifacts[0].artifactId, "artifact-1")
    XCTAssertEqual(artifacts[0].omiSessionId, "session-1")
    XCTAssertEqual(artifacts[0].runId, "run-1")
    XCTAssertEqual(artifacts[0].attemptId, "attempt-1")
    XCTAssertEqual(artifacts[0].title, "summary.json")
    XCTAssertEqual(artifacts[0].mimeType, "application/json")
    XCTAssertEqual(artifacts[0].sizeBytes, 42)
    XCTAssertEqual(artifacts[0].lifecycleState, "opened")
    XCTAssertEqual(artifacts[0].lifecycleUpdatedAtMs, 1234)
    XCTAssertEqual(artifacts[0].createdAtMs, 99)
    XCTAssertEqual(artifacts[0].metadataRows, ["adapter: pi-mono", #"nested: {"index":2}"#])
  }

  func testDefaultProjectionRequestIsUnscoped() {
    let request = AgentArtifactProjectionRequest()

    XCTAssertFalse(request.isScoped)
    XCTAssertTrue(request.toolInput.isEmpty)
  }

  func testProjectionStoreGatesStaleLoadResults() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentArtifactProjection.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("private var loadGeneration = 0"))
    XCTAssertTrue(source.contains("let generation = loadGeneration"))
    XCTAssertTrue(source.contains("guard loadGeneration == generation else { return }"))
  }

  func testProjectionBuildsScopedControlToolInput() {
    let request = AgentArtifactProjectionRequest(
      sessionId: "session-1",
      runId: "run-1",
      attemptId: "attempt-1",
      role: "result",
      limit: 10
    )

    XCTAssertTrue(request.isScoped)
    XCTAssertEqual(request.toolInput["sessionId"] as? String, "session-1")
    XCTAssertEqual(request.toolInput["runId"] as? String, "run-1")
    XCTAssertEqual(request.toolInput["attemptId"] as? String, "attempt-1")
    XCTAssertEqual(request.toolInput["role"] as? String, "result")
    XCTAssertEqual(request.toolInput["limit"] as? Int, 10)
  }

  func testProjectionSurfacesToolErrors() {
    let result = #"{"ok":false,"error":{"code":"control_tool_failed","message":"wrong owner"}}"#

    XCTAssertThrowsError(try AgentArtifactProjection.parseList(fromToolResult: result)) { error in
      XCTAssertEqual(error as? AgentArtifactProjectionError, .toolFailed("wrong owner"))
    }
  }
}
