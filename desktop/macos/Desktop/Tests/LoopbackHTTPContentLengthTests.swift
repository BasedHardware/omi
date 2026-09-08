import XCTest

@testable import Omi_Computer

/// Regression coverage for the loopback HTTP servers' Content-Length parsing.
/// A negative or absurd length reaching the body-slice math traps the whole app
/// on an unauthenticated request; the shared parser must fail closed instead.
final class LoopbackHTTPContentLengthTests: XCTestCase {

  func testRejectsNegativeContentLength() {
    // The historical crash: `Content-Length: -5` produced an invalid body-slice
    // range that trapped. It must now be rejected (nil), never returned as -5.
    XCTAssertNil(LoopbackHTTPParsing.parseContentLength("-5", maxBytes: 1024 * 1024))
    XCTAssertNil(LoopbackHTTPParsing.parseContentLength("-1", maxBytes: 1024 * 1024))
  }

  func testRejectsOverLargeContentLength() {
    // A huge value overflowed the `distance + contentLength` Int addition.
    XCTAssertNil(
      LoopbackHTTPParsing.parseContentLength("9223372036854775807", maxBytes: 8 * 1024 * 1024))
    XCTAssertNil(LoopbackHTTPParsing.parseContentLength("1048577", maxBytes: 1024 * 1024))
  }

  func testRejectsMalformedContentLength() {
    XCTAssertNil(LoopbackHTTPParsing.parseContentLength("", maxBytes: 1024 * 1024))
    XCTAssertNil(LoopbackHTTPParsing.parseContentLength("abc", maxBytes: 1024 * 1024))
    XCTAssertNil(LoopbackHTTPParsing.parseContentLength("12x", maxBytes: 1024 * 1024))
  }

  func testAcceptsValidContentLength() {
    XCTAssertEqual(LoopbackHTTPParsing.parseContentLength("0", maxBytes: 1024 * 1024), 0)
    XCTAssertEqual(LoopbackHTTPParsing.parseContentLength("512", maxBytes: 1024 * 1024), 512)
    XCTAssertEqual(
      LoopbackHTTPParsing.parseContentLength("1048576", maxBytes: 1024 * 1024), 1_048_576)
  }
}
