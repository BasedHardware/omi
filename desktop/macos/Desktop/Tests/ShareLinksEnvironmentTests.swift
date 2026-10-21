import XCTest

@testable import Omi_Computer

final class ShareLinksEnvironmentTests: XCTestCase {
  func testShareBaseURLDefaultsToProduction() {
    XCTAssertEqual(
      DesktopBackendEnvironment.shareBaseURL(environmentValue: nil),
      "https://h.omi.me"
    )
    XCTAssertEqual(
      DesktopBackendEnvironment.conversationShareURL(
        id: "abc", environmentValue: nil, sid: "0123456789abcdef0123456789abcdef"),
      "https://h.omi.me/conversations/abc?s=mac&sid=0123456789abcdef0123456789abcdef"
    )
  }

  func testShareBaseURLHonorsOverride() {
    XCTAssertEqual(
      DesktopBackendEnvironment.shareBaseURL(environmentValue: "https://share.example.com/"),
      "https://share.example.com"
    )
    XCTAssertEqual(
      DesktopBackendEnvironment.shareBaseURL(environmentValue: "share.example.com"),
      "https://share.example.com"
    )
    XCTAssertEqual(
      DesktopBackendEnvironment.conversationShareURL(
        id: "abc",
        environmentValue: "https://share.example.com",
        sid: "0123456789abcdef0123456789abcdef"
      ),
      "https://share.example.com/conversations/abc?s=mac&sid=0123456789abcdef0123456789abcdef"
    )
  }

  func testTaggingPreservesExistingQueryAndMintsRandomIDs() {
    let first = DesktopBackendEnvironment.newShareID()
    let second = DesktopBackendEnvironment.newShareID()
    XCTAssertEqual(first.count, 32)
    XCTAssertNotEqual(first, second)
    let url = DesktopBackendEnvironment.tagShareURL("https://h.omi.me/chat/token?view=compact", sid: first)
    XCTAssertEqual(url, "https://h.omi.me/chat/token?view=compact&s=mac&sid=\(first)")
    XCTAssertEqual(DesktopBackendEnvironment.shareID(from: url), first)
    XCTAssertNil(DesktopBackendEnvironment.shareID(from: "https://h.omi.me/chat/token?sid=email@example.com"))
  }

  func testShareBaseURLFallsBackForMalformedOverride() {
    XCTAssertEqual(
      DesktopBackendEnvironment.shareBaseURL(environmentValue: "not a url"),
      "https://h.omi.me"
    )
    XCTAssertEqual(
      DesktopBackendEnvironment.shareBaseURL(environmentValue: "ftp://share.example.com"),
      "https://h.omi.me"
    )
  }
}
