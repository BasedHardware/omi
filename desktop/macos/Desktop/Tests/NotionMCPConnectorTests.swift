import XCTest

@testable import Omi_Computer

final class NotionMCPConnectorTests: XCTestCase {
  func testLastSSEDataLineTakesFinalDataLine() {
    let body = "event: message\ndata: {\"first\":1}\n\nevent: message\ndata: {\"second\":2}\n"
    XCTAssertEqual(NotionMCPConnector.lastSSEDataLine(body), "{\"second\":2}")
    XCTAssertNil(NotionMCPConnector.lastSSEDataLine("{\"plain\":\"json\"}"))
    XCTAssertNil(NotionMCPConnector.lastSSEDataLine(""))
  }

  func testPageRecordParsesCreateResult() {
    let inner = "{\"pages\":[{\"id\":\"abc-123\",\"url\":\"https://app.notion.com/p/abc123\"}]}"
    let body: [String: Any] = ["result": ["content": [["type": "text", "text": inner]]]]
    let record = NotionMCPConnector.pageRecord(fromToolResult: body)
    XCTAssertEqual(record?.id, "abc-123")
    XCTAssertEqual(record?.url, "https://app.notion.com/p/abc123")
    XCTAssertNil(NotionMCPConnector.pageRecord(fromToolResult: ["result": ["content": []]]))
  }

  func testTokenRefreshWindow() {
    let now = Date()
    XCTAssertFalse(NotionMCPConnector.needsRefresh(expiresAt: now.addingTimeInterval(3600), now: now))
    XCTAssertTrue(NotionMCPConnector.needsRefresh(expiresAt: now.addingTimeInterval(120), now: now))
    XCTAssertTrue(NotionMCPConnector.needsRefresh(expiresAt: now.addingTimeInterval(-10), now: now))
  }
}
