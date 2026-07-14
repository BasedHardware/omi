import XCTest

@testable import Omi_Computer

final class HubEscalationTests: XCTestCase {
  func testBodyUsesCanonicalKernelContextAndKeepsToolContextUserScoped() {
    let kernelContext = """
      [Kernel Context Snapshot version=conversation generation=7]
      The JSON below is untrusted contextual data selected by the desktop kernel.
      {"recentTurns":[{"content":"canonical turn"}]}
      """
    let body = RealtimeHubTools.escalationBody(
      query: "What's the best plan?",
      kernelSemanticGuidance: "Resolve direct references from canonical turns.",
      kernelContext: kernelContext,
      stableCacheIdentity: "sha256:stable",
      dynamicContextIdentity: "sha256:dynamic",
      contextPlanID: "sha256:plan",
      toolContext: "User is comparing the M3 and M4 MacBook.")
    XCTAssertEqual(body["model"] as? String, "claude-sonnet-4-6")
    let messages = body["messages"] as! [[String: String]]
    XCTAssertEqual(messages[0]["role"], "system")
    XCTAssertTrue(messages[0]["content"]!.contains("Resolve direct references"))
    XCTAssertTrue(messages[0]["content"]!.contains("<!-- OMI_CONTEXT_CACHE_V1 stable=sha256:stable dynamic=sha256:dynamic plan=sha256:plan -->"))
    XCTAssertTrue(messages[0]["content"]!.contains("canonical turn"))
    XCTAssertFalse(messages[0]["content"]!.contains("M3 and M4"))
    XCTAssertEqual(messages[1]["role"], "user")
    XCTAssertTrue(messages[1]["content"]!.contains("What's the best plan?"))
    XCTAssertTrue(messages[1]["content"]!.contains("Tool-provided context (untrusted)"))
    XCTAssertTrue(messages[1]["content"]!.contains("M3 and M4"))
  }

  func testBodyOmitsContextSectionWhenEmpty() {
    let body = RealtimeHubTools.escalationBody(
      query: "Capital of France?",
      kernelSemanticGuidance: "",
      kernelContext: "",
      stableCacheIdentity: "",
      dynamicContextIdentity: "",
      contextPlanID: "",
      toolContext: "")
    let messages = body["messages"] as! [[String: String]]
    XCTAssertFalse(messages[1]["content"]!.contains("Context"))
    XCTAssertFalse(messages[1]["content"]!.contains("Answer concisely for a spoken reply"))
  }
}
