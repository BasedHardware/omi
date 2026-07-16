import XCTest

@testable import Omi_Computer

@MainActor final class AgentArtifactProjectionTests: XCTestCase {
  func testParsesArtifactMetadataProjection() throws {
    let result = """
      {
        "ok": true,
        "artifacts": [
          {
            "artifactId": "artifact-1",
            "sessionId": "session-1",
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
    XCTAssertEqual(artifacts[0].sessionId, "session-1")
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

  @MainActor
  func testProjectionStoreIgnoresStaleLoadResults() async {
    let store = AgentArtifactProjectionStore()
    let bridge = DelayedArtifactProjectionLoader()
    let staleRequest = AgentArtifactProjectionRequest(sessionId: "session-stale")
    let currentRequest = AgentArtifactProjectionRequest(sessionId: "session-current")

    let staleLoad = Task { @MainActor in
      await store.load(request: staleRequest, bridge: bridge)
    }
    await bridge.waitForStaleRequest()
    await store.load(request: currentRequest, bridge: bridge)
    bridge.releaseStaleRequest()
    await staleLoad.value

    XCTAssertEqual(store.artifacts.map(\.artifactId), ["artifact-current"])
    XCTAssertFalse(store.isLoading)
    XCTAssertNil(store.errorMessage)
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

@MainActor
private final class DelayedArtifactProjectionLoader: @preconcurrency AgentArtifactProjectionLoading {
  private var staleStartedContinuation: CheckedContinuation<Void, Never>?
  private var staleReleaseContinuation: CheckedContinuation<Void, Never>?
  private var staleRequestStarted = false

  func waitForStaleRequest() async {
    if staleRequestStarted { return }
    await withCheckedContinuation { continuation in
      staleStartedContinuation = continuation
    }
  }

  func releaseStaleRequest() {
    staleReleaseContinuation?.resume()
    staleReleaseContinuation = nil
  }

  func controlTool(name: String, input: [String: Any]) async throws -> String {
    let sessionId = input["sessionId"] as? String ?? ""
    if sessionId == "session-stale" {
      staleRequestStarted = true
      staleStartedContinuation?.resume()
      staleStartedContinuation = nil
      await withCheckedContinuation { continuation in
        staleReleaseContinuation = continuation
      }
    }
    return """
      {
        "ok": true,
        "artifacts": [
          {
            "artifactId": "\(sessionId == "session-current" ? "artifact-current" : "artifact-stale")",
            "sessionId": "\(sessionId)",
            "kind": "json",
            "role": "result",
            "uri": "omi-artifact://\(sessionId)"
          }
        ]
      }
      """
  }
}
