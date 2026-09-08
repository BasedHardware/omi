import XCTest

/// Sentinel: proves `BareSlashRegexLiterals` is active by using a bare-slash
/// regex literal.  If the feature is removed or misspelled in Package.swift,
/// this file fails to compile — the regex literal is a syntax error without it.
final class BareSlashRegexSentinelTests: XCTestCase {
  func testBareSlashRegexCompiles() throws {
    let pattern = /\d+/
    let input = "42"
    XCTAssertNotNil(try pattern.wholeMatch(in: input))
  }
}
