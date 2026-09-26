import XCTest

@testable import Omi_Computer

final class ChatAppContextTests: XCTestCase {
  func testDecodedChatPromptIsAddedToExistingExperienceContext() {
    let context = ChatAppContext(
      appId: "outlook-local",
      appName: "Outlook",
      chatPrompt: "  Help with the selected Outlook mailbox.  "
    )

    XCTAssertEqual(
      context.appending(to: "Base experience"),
      """
      Base experience

      [Active Chat App]
      Name: Outlook
      ID: outlook-local
      App instructions:
      Help with the selected Outlook mailbox.
      """
    )
  }

  func testBlankPromptStillIdentifiesTheSelectedAppWithoutInventingInstructions() {
    let context = ChatAppContext(appId: "plain-chat", appName: "Plain Chat", chatPrompt: "  ")

    XCTAssertEqual(
      context.appending(to: nil),
      """
      [Active Chat App]
      Name: Plain Chat
      ID: plain-chat
      """
    )
    XCTAssertNil(context.chatPrompt)
  }

  func testSelectedAppInstructionsAreScopedToMainChat() {
    let context = ChatAppContext(
      appId: "outlook-local",
      appName: "Outlook",
      chatPrompt: "Use the mailbox connector"
    )

    XCTAssertTrue(
      ChatAppContext.scopedExperienceContext(
        selectedApp: context,
        surfaceKind: "main_chat",
        baseContext: nil
      )?.contains("Use the mailbox connector") == true
    )
    XCTAssertEqual(
      ChatAppContext.scopedExperienceContext(
        selectedApp: context,
        surfaceKind: "floating_chat",
        baseContext: "Floating base"
      ),
      "Floating base"
    )
  }
}
