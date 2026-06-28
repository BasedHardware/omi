import XCTest
@testable import Omi_Computer

final class TaskAssistantPromptTests: XCTestCase {
    @MainActor
    func testDefaultPromptSkipsPublicChannelRequestsNotDirectedAtUser() {
        let prompt = TaskAssistantSettings.defaultAnalysisPrompt

        XCTAssertTrue(prompt.contains("CRITICAL FOR PUBLIC/GROUP CHANNELS"))
        XCTAssertTrue(prompt.contains("visible evidence shows the user is directly involved"))
        XCTAssertTrue(prompt.contains("merely observing a public channel"))
        XCTAssertTrue(prompt.contains("cannot tell whether the request is directed at them"))
        XCTAssertTrue(prompt.contains("otherwise clearly addressed to the user"))
        XCTAssertTrue(prompt.contains("questions posted to the community at large"))
        XCTAssertFalse(prompt.contains("It is a direct message (DM) thread, not a public or community channel"))
    }
}
