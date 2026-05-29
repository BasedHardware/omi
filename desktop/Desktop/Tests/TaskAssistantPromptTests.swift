import XCTest
@testable import Omi_Computer

final class TaskAssistantPromptTests: XCTestCase {
    @MainActor
    func testDefaultPromptSkipsPublicChannelRequestsNotDirectedAtUser() {
        let prompt = TaskAssistantSettings.defaultAnalysisPrompt

        XCTAssertTrue(prompt.contains("CRITICAL FOR PUBLIC/GROUP CHANNELS"))
        XCTAssertTrue(prompt.contains("visible evidence shows the user is directly involved"))
        XCTAssertTrue(prompt.contains("call no_task_found"))
        XCTAssertTrue(prompt.contains("questions posted to the community at large"))
    }
}
