import XCTest

@testable import Omi_Computer

final class TaskAssistantPromptTests: XCTestCase {
  func testRequestPromptsPutStableCapturePolicyBeforeVolatileFrameContext() {
    let prompts = TaskAssistant.requestPrompts(
      baseSystemPrompt: "custom detector rules",
      appName: "Slack",
      today: "2026-08-17 (Monday)",
      profileText: "Works on Omi",
      contextEvidence: "ACTIVE TASKS:\n- Ship cache change"
    )

    XCTAssertTrue(prompts.system.hasPrefix("custom detector rules\n\n"))
    XCTAssertTrue(prompts.system.hasSuffix(TaskAssistant.cacheStableCapturePolicy))
    XCTAssertFalse(prompts.user.contains(TaskAssistant.cacheStableCapturePolicy))
    XCTAssertTrue(prompts.user.contains("Screenshot from Slack. Today is 2026-08-17 (Monday)."))
    XCTAssertTrue(prompts.user.contains("REMINDER — THIS IS A MESSAGING APP:"))
    XCTAssertTrue(prompts.user.contains("Works on Omi"))
    XCTAssertTrue(prompts.user.hasSuffix("ACTIVE TASKS:\n- Ship cache change"))
  }

  func testRequestPromptsPreserveNonMessagingFrameContextWithoutProfile() {
    let prompts = TaskAssistant.requestPrompts(
      baseSystemPrompt: "detector rules",
      appName: "Safari",
      today: "2026-08-17 (Monday)",
      profileText: nil,
      contextEvidence: ""
    )

    XCTAssertEqual(prompts.system, "detector rules\n\n" + TaskAssistant.cacheStableCapturePolicy)
    XCTAssertFalse(prompts.user.contains("REMINDER — THIS IS A MESSAGING APP:"))
    XCTAssertFalse(prompts.user.contains("USER PROFILE"))
  }

  func testBrowserKeywordMatchingUsesUserLocaleRules() {
    XCTAssertTrue(
      TaskAssistantSettings.windowTitle("Résumé – Safari", matchesAny: ["resume"])
    )
    XCTAssertFalse(
      TaskAssistantSettings.windowTitle("Calendar – Safari", matchesAny: ["resume"])
    )
  }

  @MainActor
  func testDefaultPromptSkipsPublicChannelRequestsNotDirectedAtUser() {
    let prompt = TaskAssistantSettings.defaultAnalysisPrompt

    XCTAssertTrue(prompt.contains("PUBLIC/GROUP CHANNELS"))
    XCTAssertTrue(prompt.contains("visible evidence shows the user is directly involved"))
    XCTAssertTrue(prompt.contains("If they are only observing, or you cannot tell, call no_task_found"))
    XCTAssertTrue(prompt.contains("Do not extract broad community bug reports or feature requests"))
    XCTAssertTrue(prompt.contains("clearly addressed to them"))
    XCTAssertFalse(prompt.contains("It is a direct message (DM) thread, not a public or community channel"))
  }
}
