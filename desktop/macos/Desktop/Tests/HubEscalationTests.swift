import XCTest

@testable import Omi_Computer

final class HubEscalationTests: XCTestCase {
  func testBodyHasSystemPromptAndAppendsContext() {
    let body = RealtimeHubTools.escalationBody(
      query: "What's the best plan?",
      context: "User is comparing the M3 and M4 MacBook.",
      aboutUser: "<about_user>\nName: Sam\n</about_user>")
    XCTAssertEqual(body["model"] as? String, "claude-sonnet-4-6")
    let messages = body["messages"] as! [[String: String]]
    XCTAssertEqual(messages[0]["role"], "system")
    XCTAssertTrue(messages[0]["content"]!.contains("<about_user>"))
    XCTAssertEqual(messages[1]["role"], "user")
    XCTAssertTrue(messages[1]["content"]!.contains("What's the best plan?"))
    XCTAssertTrue(messages[1]["content"]!.contains("M3 and M4"))  // context appended
  }

  func testBodyOmitsContextSectionWhenEmpty() {
    let body = RealtimeHubTools.escalationBody(
      query: "Capital of France?", context: "", aboutUser: "")
    let messages = body["messages"] as! [[String: String]]
    XCTAssertFalse(messages[1]["content"]!.contains("Context"))
    XCTAssertFalse(messages[1]["content"]!.contains("Answer concisely for a spoken reply"))
  }
}
