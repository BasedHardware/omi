import XCTest

@testable import Omi_Computer

final class ChatResourceTests: XCTestCase {
  func testAttachmentResourcePreservesUploadStateAndThumbnail() throws {
    let tempDir = FileManager.default.temporaryDirectory
    let fileURL = tempDir.appendingPathComponent("receipt-\(UUID().uuidString).png")
    try Data([0x89, 0x50, 0x4E, 0x47]).write(to: fileURL)
    defer { try? FileManager.default.removeItem(at: fileURL) }

    let attachment = ChatAttachment(
      id: "local-1",
      fileName: "receipt.png",
      mimeType: "image/png",
      data: Data([0x89, 0x50, 0x4E, 0x47]),
      serverId: "file-1",
      localFileURL: fileURL,
      thumbnailURL: "https://example.com/thumb.png",
      state: .uploaded
    )

    let resource = ChatResource.attachment(attachment)

    XCTAssertEqual(resource.id, "attachment:file-1")
    XCTAssertEqual(resource.origin, .userAttachment)
    XCTAssertEqual(resource.title, "receipt.png")
    XCTAssertEqual(resource.mimeType, "image/png")
    XCTAssertEqual(resource.thumbnailURL, "https://example.com/thumb.png")
    XCTAssertEqual(resource.state, .ready)
    XCTAssertTrue(resource.isImage)
    XCTAssertEqual(resource.fileURL?.path, fileURL.path)
    XCTAssertTrue(resource.canOpen)
  }

  func testArtifactResourcePreservesCanonicalRuntimeIdentityAndFileActions() throws {
    let tempDir = FileManager.default.temporaryDirectory
    let fileURL = tempDir.appendingPathComponent("report-\(UUID().uuidString).md")
    try "# Report".write(to: fileURL, atomically: true, encoding: .utf8)
    defer { try? FileManager.default.removeItem(at: fileURL) }

    let result = """
      {
        "ok": true,
        "artifacts": [
          {
            "artifactId": "artifact-1",
            "sessionId": "session-1",
            "runId": "run-1",
            "kind": "markdown",
            "role": "result",
            "uri": "\(fileURL.absoluteString)",
            "displayName": "report.md",
            "mimeType": "text/markdown",
            "sizeBytes": 2048,
            "lifecycleState": "retained"
          }
        ]
      }
      """
    let artifact = try XCTUnwrap(AgentArtifactProjection.parseList(fromToolResult: result).first)

    let resource = ChatResource.artifact(artifact)

    XCTAssertEqual(resource.id, "artifact:artifact-1")
    XCTAssertEqual(resource.origin, .generatedArtifact)
    XCTAssertEqual(resource.title, "report.md")
    XCTAssertEqual(resource.subtitle, "text/markdown • 2 KB")
    XCTAssertEqual(resource.artifactId, "artifact-1")
    XCTAssertEqual(resource.sessionId, "session-1")
    XCTAssertEqual(resource.runId, "run-1")
    XCTAssertEqual(resource.state, .retained)
    XCTAssertEqual(resource.fileURL?.path, fileURL.path)
    XCTAssertTrue(resource.canOpen)
    XCTAssertTrue(resource.canRevealInFinder)
  }

  func testChatMessageDerivesDisplayResourcesFromLegacyAttachments() {
    let attachment = ChatAttachment(
      id: "file-local",
      fileName: "notes.txt",
      mimeType: "text/plain",
      serverId: "file-server",
      state: .uploaded
    )
    let message = ChatMessage(text: "see attached", sender: .user, attachments: [attachment])

    XCTAssertEqual(message.displayResources.map(\.id), ["attachment:file-server"])
  }

  func testChatMessagePrefersExplicitResourcesOverAttachments() {
    let explicit = ChatResource(
      id: "artifact:artifact-1",
      origin: .generatedArtifact,
      title: "result.json",
      subtitle: "application/json",
      mimeType: "application/json",
      thumbnailURL: nil,
      imageData: nil,
      uri: "omi-artifact://artifact-1",
      artifactId: "artifact-1",
      sessionId: "session-1",
      runId: "run-1",
      state: .ready
    )
    let attachment = ChatAttachment(
      id: "file-local",
      fileName: "notes.txt",
      mimeType: "text/plain",
      serverId: "file-server",
      state: .uploaded
    )
    let message = ChatMessage(text: "done", sender: .ai, attachments: [attachment], resources: [explicit])

    XCTAssertEqual(message.displayResources, [explicit])
  }

  func testMessageMetadataRoundTripsArtifactResources() {
    let resource = ChatResource(
      id: "artifact:artifact-1",
      origin: .generatedArtifact,
      title: "rat-facts.html",
      subtitle: "text/html",
      mimeType: "text/html",
      thumbnailURL: nil,
      imageData: nil,
      uri: "file:///tmp/rat-facts.html",
      artifactId: "artifact-1",
      sessionId: "session-1",
      runId: "run-1",
      state: .ready
    )
    let metadata = ChatResource.mergeResourcesIntoMessageMetadata(
      #"{"tool_calls":[{"name":"inspect_agent_run"}]}"#,
      resources: [resource]
    )

    let decoded = ChatResource.decodeResourcesFromMessageMetadata(metadata)

    XCTAssertEqual(decoded.map(\.id), ["artifact:artifact-1"])
    XCTAssertEqual(decoded.first?.title, "rat-facts.html")
    XCTAssertEqual(decoded.first?.artifactId, "artifact-1")
    XCTAssertEqual(decoded.first?.uri, "file:///tmp/rat-facts.html")
  }

  func testHydrateFileStatesMarksMissingArtifactAsDeletedOrMoved() {
    let resource = ChatResource(
      id: "artifact:artifact-1",
      origin: .generatedArtifact,
      title: "rat-facts.html",
      subtitle: "text/html",
      mimeType: "text/html",
      thumbnailURL: nil,
      imageData: nil,
      uri: "file:///tmp/does-not-exist-rat-facts.html",
      artifactId: "artifact-1",
      sessionId: "session-1",
      runId: "run-1",
      state: .ready
    )

    let hydrated = ChatResource.hydrateFileStates([resource]).first

    XCTAssertEqual(hydrated?.state, .failed(ChatResource.unavailableOnDiskMessage))
    XCTAssertEqual(hydrated?.subtitle, ChatResource.unavailableOnDiskMessage)
    XCTAssertFalse(hydrated?.canOpen ?? true)
  }

  func testChatMessageFromPersistedMetadataHydratesMissingFiles() {
    let metadata = ChatResource.mergeResourcesIntoMessageMetadata(
      nil,
      resources: [
        ChatResource(
          id: "artifact:artifact-1",
          origin: .generatedArtifact,
          title: "rat-facts.html",
          subtitle: "text/html",
          mimeType: "text/html",
          thumbnailURL: nil,
          imageData: nil,
          uri: "file:///tmp/does-not-exist-rat-facts.html",
          artifactId: "artifact-1",
          sessionId: "session-1",
          runId: "run-1",
          state: .ready
        )
      ]
    )
    let resources = ChatResource.decodeResourcesFromMessageMetadata(metadata)
    let message = ChatMessage(text: "Done.", sender: .ai, resources: resources)

    XCTAssertEqual(message.resources.count, 1)
    XCTAssertEqual(message.displayResources.first?.subtitle, ChatResource.unavailableOnDiskMessage)
  }

  func testAttachmentContextPromptGivesAgentLocalPathAndDeicticInstruction() throws {
    let url = URL(fileURLWithPath: "/Users/dazheng/vibespace/codebase-audit-SKILL.md")
    let attachment = ChatAttachment(
      id: "local-1",
      fileName: "codebase-audit-SKILL.md",
      mimeType: "text/plain",
      serverId: "file-server",
      localFileURL: url,
      state: .localOnly
    )

    let prompt = try XCTUnwrap(ChatProvider.attachmentContextPrompt(for: [attachment]))

    XCTAssertTrue(prompt.contains("[Attached Files]"))
    XCTAssertTrue(prompt.contains("The user attached 1 file to this exact message"))
    XCTAssertTrue(prompt.contains("what do you think of this"))
    XCTAssertTrue(prompt.contains("local_path: /Users/dazheng/vibespace/codebase-audit-SKILL.md"))
    XCTAssertTrue(prompt.contains("uploaded_file_id: file-server"))
  }
}
