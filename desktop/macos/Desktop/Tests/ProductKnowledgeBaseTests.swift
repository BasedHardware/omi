import XCTest

@testable import Omi_Computer

final class ProductKnowledgeBaseTests: XCTestCase {
  private let indexedIDs = ["capture-modes", "permissions", "surfaces", "data-and-account"]

  func testBundledKnowledgeBaseParsesEveryIndexedDocument() throws {
    let library = try XCTUnwrap(
      ProductKnowledgeLibrary.loadBundled(),
      "Shipped product knowledge was not in the resource bundle")
    XCTAssertEqual(library.documents.map(\.id), indexedIDs)
    for document in library.documents {
      XCTAssertFalse(document.title.isEmpty, document.id)
      XCTAssertFalse(document.body.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, document.id)
      XCTAssertFalse(document.sources.isEmpty, document.id)
      XCTAssertFalse(document.keywords.isEmpty, document.id)
    }
  }

  func testMeetingQueriesReturnTheCaptureModeGuide() throws {
    let library = try XCTUnwrap(ProductKnowledgeLibrary.loadBundled())
    for query in ["meeting only recording", "Only Meetings"] {
      let result = ProductKnowledgeTool.execute(query: query, topic: nil, library: library)
      XCTAssertTrue(result.contains("Only Meetings"), query)
      XCTAssertTrue(result.contains("Settings → General → Audio Recording"), query)
      XCTAssertTrue(result.contains("Always On"), query)
      XCTAssertFalse(result.contains(ProductKnowledgeTool.noMatchMessage), query)
      XCTAssertFalse(result.isEmpty, query)
    }
  }

  func testPermissionsQueryReturnsThePermissionsGuide() throws {
    let library = try XCTUnwrap(ProductKnowledgeLibrary.loadBundled())
    let result = ProductKnowledgeTool.execute(query: "permissions", topic: nil, library: library)
    XCTAssertTrue(result.contains("Screen Recording"))
    XCTAssertTrue(result.contains("Settings → Privacy & Security → Microphone"))
    XCTAssertTrue(result.contains("(permissions)"))
    XCTAssertFalse(result.contains(ProductKnowledgeTool.noMatchMessage))
  }

  func testUnknownQueryReturnsTheHonestFallback() throws {
    let library = try XCTUnwrap(ProductKnowledgeLibrary.loadBundled())
    let result = ProductKnowledgeTool.execute(query: "flux capacitor", topic: nil, library: library)
    XCTAssertTrue(result.contains(ProductKnowledgeTool.noMatchMessage))
    XCTAssertTrue(result.contains("capture-modes"))
    XCTAssertFalse(result.contains("Only Meetings"))
    XCTAssertFalse(result.contains("Settings → General → Audio Recording"))
    XCTAssertFalse(result.isEmpty)
  }

  func testTopicReadAndEmptyQueryListStayInsideTheIndex() throws {
    let library = try XCTUnwrap(ProductKnowledgeLibrary.loadBundled())
    let topic = ProductKnowledgeTool.execute(query: nil, topic: "capture-modes", library: library)
    XCTAssertTrue(topic.contains("Only Meetings"))
    XCTAssertTrue(topic.contains("(capture-modes)"))

    let listed = ProductKnowledgeTool.execute(query: "  ", topic: " ", library: library)
    for id in indexedIDs {
      XCTAssertTrue(listed.contains(id), id)
    }
    XCTAssertFalse(listed.contains(ProductKnowledgeTool.noMatchMessage))
  }

  func testMissingKnowledgeBaseSaysItIsUnavailable() {
    let missing = ProductKnowledgeLibrary.load(from: [
      URL(fileURLWithPath: NSTemporaryDirectory())
        .appendingPathComponent("omi-product-kb-missing-\(UUID().uuidString)")
    ])
    XCTAssertNil(missing)
    let result = ProductKnowledgeTool.execute(query: "Only Meetings", topic: nil, library: nil)
    XCTAssertTrue(result.contains("knowledge base unavailable"))
    XCTAssertEqual(result, ProductKnowledgeTool.unavailableMessage)
    XCTAssertFalse(result.contains("Only Meetings"))
  }

  func testDesktopChatCapabilityIncludesProductKnowledge() {
    let names = DesktopCapabilityRegistry.capabilities(for: .desktopChat).map(\.toolName)
    XCTAssertTrue(names.contains("get_product_kb"))
    XCTAssertTrue(DesktopCapabilityRegistry.desktopToolNames.contains("get_product_kb"))
    let prompt = DesktopCapabilityRegistry.desktopToolPrompt
    XCTAssertTrue(prompt.contains("**get_product_kb**"))
    XCTAssertTrue(prompt.contains("Only Meetings"))
    XCTAssertTrue(prompt.contains("personal conversations, memories, tasks, or screen history"))
  }
}
