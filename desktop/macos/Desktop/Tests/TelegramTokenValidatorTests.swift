import XCTest
@testable import Omi_Computer

/// Tests for the client-side Telegram bot-token validator.
///
/// Covers the matrix from the onboarding UX plan:
/// - valid token
/// - invalid token (typo, wrong chars)
/// - missing colon
/// - short token
/// - invalid characters
/// - nil / empty / whitespace-only
/// - state() classification
final class TelegramTokenValidatorTests: XCTestCase {

    func testValidToken() {
        let token = "123456789:AAEhBP7fWqu7vK3HbZGE-vJRq4YH9k5m7XQ"
        XCTAssertTrue(TelegramTokenValidator.isValid(token))
        XCTAssertEqual(TelegramTokenValidator.state(token), .valid)
    }

    func testValidTokenWithUnderscoresAndDashes() {
        // Real Telegram tokens mix A-Z, a-z, 0-9, _, -. 35+ chars after colon.
        XCTAssertTrue(TelegramTokenValidator.isValid("987654321:abc_def-ghi_jkl_mno_pqr_stu_vwx_yz1"))
        XCTAssertTrue(TelegramTokenValidator.isValid("123:_-_-_-_-_-_-_-_-_-_-_-_-_-_-_-_-_-_"))
    }

    func testMissingColon() {
        XCTAssertFalse(TelegramTokenValidator.isValid("123456789AAEhBP7fWqu7vK3HbZGE"))
    }

    func testShortToken() {
        // < 30 chars after the colon → rejected.
        XCTAssertFalse(TelegramTokenValidator.isValid("123:abc"))
        XCTAssertFalse(TelegramTokenValidator.isValid("123:abcdefghij"))
    }

    func testInvalidCharacters() {
        // Real Telegram tokens use only [A-Za-z0-9_-]. Anything else (slashes,
        // dots, spaces, etc.) should be rejected client-side.
        XCTAssertFalse(TelegramTokenValidator.isValid("123456789:abc def.ghi+123"))
        XCTAssertFalse(TelegramTokenValidator.isValid("123456789:abcdef/ghijklmn"))
    }

    func testEmptyAndNil() {
        XCTAssertFalse(TelegramTokenValidator.isValid(""))
        XCTAssertFalse(TelegramTokenValidator.isValid(nil))
        XCTAssertEqual(TelegramTokenValidator.state(""), .empty)
        XCTAssertEqual(TelegramTokenValidator.state(nil), .empty)
    }

    func testWhitespaceOnlyIsEmpty() {
        XCTAssertEqual(TelegramTokenValidator.state("   "), .empty)
        XCTAssertEqual(TelegramTokenValidator.state("\n\t"), .empty)
    }

    func testTrailingWhitespaceTrimmed() {
        // "valid " (with trailing space) should still validate after trimming.
        let token = "  123456789:AAEhBP7fWqu7vK3HbZGE-vJRq4YH9k5m7XQ  \n"
        XCTAssertEqual(TelegramTokenValidator.state(token), .valid)
    }

    func testInvalidStateClassification() {
        XCTAssertEqual(TelegramTokenValidator.state("123"), .invalid)
        XCTAssertEqual(TelegramTokenValidator.state("not-a-token"), .invalid)
        XCTAssertEqual(TelegramTokenValidator.state("123:short"), .invalid)
    }

    func testStateBoundaryAt30Chars() {
        // Pattern is `^{30,}$` for the suffix. 29 chars should fail, 30+ pass.
        let numericPrefix = "1"
        let shortToken = "\(numericPrefix):" + String(repeating: "a", count: 29)
        let validToken = "\(numericPrefix):" + String(repeating: "a", count: 30)
        XCTAssertFalse(TelegramTokenValidator.isValid(shortToken))
        XCTAssertTrue(TelegramTokenValidator.isValid(validToken))
    }
}