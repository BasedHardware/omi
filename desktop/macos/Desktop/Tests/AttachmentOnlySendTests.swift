import XCTest

@testable import Omi_Computer

/// **A file dropped in with no words is a message.** Attaching a PDF and pressing return used to do
/// nothing: every composer either disabled the send or the provider's empty-text guard swallowed the
/// turn, so the reader had to invent words ("look at this") to get the attachment in front of the
/// model. These tests hold the seam where that turned around: the provider admits the send, the row
/// carries a caption the journal and backend both accept, and the model is asked about the
/// attachment rather than being handed a label.
@MainActor
final class AttachmentOnlySendTests: XCTestCase {
  private func stagedFile(_ name: String = "notes.pdf") -> ChatAttachment {
    ChatAttachment(fileName: name, mimeType: "application/pdf", data: Data([0x25, 0x50, 0x44, 0x46]))
  }

  private func stagedConversation() -> ChatComposerReference {
    ChatComposerReference(kind: .conversation, sourceID: "conv-1", title: "Standup")
  }

  // MARK: - The provider admits the send

  /// The busy refusal is the first thing past the empty-text guard that speaks, so a refusal *with*
  /// an explanation is proof the attachment-only send was admitted as a turn — while an empty
  /// composer with nothing staged still returns silently, as an inert key should.
  func testAnEmptyMessageWithAStagedFileIsATurn() async {
    let provider = ChatProvider()
    provider.isSending = true
    provider.pendingAttachments = [stagedFile()]

    let result = await provider.sendMessage("   ")

    XCTAssertNil(result, "The provider is busy, so no turn starts")
    XCTAssertEqual(
      provider.errorMessage, ChatProvider.sendRefusedWhileBusyMessage,
      "Reaching the busy guard means the empty-text guard let the attachment-only send through"
    )
    XCTAssertEqual(provider.pendingAttachments.count, 1, "A refused send keeps the staged file")
  }

  func testAnEmptyMessageWithAStagedConversationIsATurn() async {
    let provider = ChatProvider()
    provider.isSending = true
    provider.pendingComposerReferences = [stagedConversation()]

    _ = await provider.sendMessage("")

    XCTAssertEqual(provider.errorMessage, ChatProvider.sendRefusedWhileBusyMessage)
  }

  func testAnEmptyMessageWithNothingStagedIsStillInert() async {
    let provider = ChatProvider()
    provider.isSending = true

    let result = await provider.sendMessage("  \n ")

    XCTAssertNil(result)
    XCTAssertNil(provider.errorMessage, "Nothing was sent, so there is nothing to refuse")
    XCTAssertTrue(provider.messages.isEmpty)
  }

  func testSendableSubjectIsWordsOrAStagedItem() {
    XCTAssertFalse(ChatProvider.hasSendableSubject(text: " \n", attachmentCount: 0, referenceCount: 0))
    XCTAssertTrue(ChatProvider.hasSendableSubject(text: "hi", attachmentCount: 0, referenceCount: 0))
    XCTAssertTrue(ChatProvider.hasSendableSubject(text: "", attachmentCount: 1, referenceCount: 0))
    XCTAssertTrue(ChatProvider.hasSendableSubject(text: "", attachmentCount: 0, referenceCount: 1))
  }

  // MARK: - What the row says and what the model is asked

  /// The journal tombstones an empty user turn and the backend rejects one, so the row needs words —
  /// and the honest words are what was attached, not a sentence the reader never typed.
  func testTheCaptionSaysWhatWasAttached() {
    XCTAssertEqual(ChatProvider.attachmentOnlyCaption(attachmentCount: 1, referenceCount: 0), "1 file attached")
    XCTAssertEqual(ChatProvider.attachmentOnlyCaption(attachmentCount: 3, referenceCount: 0), "3 files attached")
    XCTAssertEqual(
      ChatProvider.attachmentOnlyCaption(attachmentCount: 0, referenceCount: 1), "1 conversation attached")
    XCTAssertEqual(
      ChatProvider.attachmentOnlyCaption(attachmentCount: 2, referenceCount: 2),
      "2 files and 2 conversations attached")
    XCTAssertEqual(ChatProvider.attachmentOnlyCaption(attachmentCount: 0, referenceCount: 0), "")
  }

  /// A label is not a request. Handed only "1 file attached", the model asks the reader what they
  /// want; the prompt has to say there were no words and ask for a direct response instead.
  func testTheModelIsAskedToRespondToTheAttachmentDirectly() {
    let prompt = ChatProvider.attachmentOnlyModelPrompt(attachmentCount: 1, referenceCount: 0)
    XCTAssertTrue(prompt.contains("no text"), "The model is told the reader typed nothing")
    XCTAssertTrue(prompt.contains("1 file attached"), "…and what they sent instead")
    XCTAssertTrue(prompt.contains("Respond to the attachment(s) directly"))
    XCTAssertTrue(prompt.contains("Do not ask what the user wants"), "The skipped question stays skipped")
  }

  /// Attachments are the subject, so an attachment-only turn never captures or describes the screen.
  func testAnAttachmentOnlyTurnAddsNoScreenContext() {
    for owner in [ChatTurnOwner.mainChat, .floatingDefault, .taskChat("task-1")] {
      XCTAssertNil(
        ScreenContextAutoIncludePolicy.reason(
          userText: "",
          systemPromptStyle: .floating,
          turnOwner: owner,
          hasAttachments: true),
        "\(owner) must not capture the screen for a message that is only an attachment"
      )
    }
  }
}
