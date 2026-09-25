import XCTest

@testable import ContextCore

/// Guards the one part of this app that can leak a credential.
///
/// Screen capture OCRs whatever is on screen into a plaintext database that an LLM then searches.
/// A dogfooding pass found complete OAuth callback URLs stored with their `code=` and `state=`
/// values intact — including this app's own sign-in callback. Those particular codes were
/// short-lived, but the same path will eventually catch an API key, a bearer token, or a password
/// field, and every one of them is served verbatim to any model that calls `recall`.
///
/// These tests exist because the redaction shipped without any, and an untested scrubber is
/// indistinguishable from no scrubber until the day it matters.
final class RedactionTests: XCTestCase {
    private func assertScrubbed(
        _ input: String, secret: String, file: StaticString = #filePath, line: UInt = #line
    ) {
        let out = Redaction.scrub(input)
        XCTAssertFalse(
            out.contains(secret),
            "the secret survived scrubbing: \(out)", file: file, line: line)
        XCTAssertTrue(
            out.contains(Redaction.marker),
            "nothing was marked as redacted: \(out)", file: file, line: line)
    }

    func testOAuthCallbackParametersAreRemoved() {
        // The exact shape that was found in the live database.
        assertScrubbed(
            "http://127.0.0.1:60617/callback?code=4/0AVGzR1BxQdLm9nT2wY&state=abc123def456",
            secret: "4/0AVGzR1BxQdLm9nT2wY")
        assertScrubbed(
            "http://127.0.0.1:60617/callback?code=4/0AVGzR1BxQdLm9nT2wY&state=abc123def456",
            secret: "abc123def456")
    }

    func testCommonCredentialParameterNamesAreRemoved() {
        let cases: [(String, String)] = [
            ("https://x.test/cb?access_token=ya29.aVeryLongLookingValue", "ya29.aVeryLongLookingValue"),
            ("https://x.test/cb?id_token=eyJhbGciOiJIUzI1NiJ9.payload.sig", "eyJhbGciOiJIUzI1NiJ9"),
            ("https://x.test/?api_key=abcdef0123456789abcdef", "abcdef0123456789abcdef"),
            ("https://x.test/?client_secret=s3cr3tValueHere12345", "s3cr3tValueHere12345"),
            ("password=hunter2butlongerthanthat", "hunter2butlongerthanthat"),
            ("refresh_token=1//04aLongRefreshTokenValue", "1//04aLongRefreshTokenValue"),
        ]
        for (input, secret) in cases {
            assertScrubbed(input, secret: secret)
        }
    }

    func testAuthorizationHeadersAreRemoved() {
        assertScrubbed(
            "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            secret: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9")
    }

    func testStandaloneKeysAreRemoved() {
        // Recognisable by prefix, so they are caught even with no surrounding parameter name —
        // which is how they appear when someone has one open in an editor or a terminal.
        assertScrubbed("sk-proj-0123456789abcdefghijklmnop", secret: "sk-proj-0123456789abcdefghijklmnop")
        assertScrubbed("ghp_0123456789abcdefghijklmnopqrstuv", secret: "ghp_0123456789abcdefghijklmnopqrstuv")
        assertScrubbed("omi_mcp_0123456789abcdef0123456789abcdef", secret: "omi_mcp_0123456789abcdef0123456789abcdef")
    }

    /// The other half of the contract. Over-redaction destroys the product: this text is the corpus
    /// `recall` searches, and a scrubber that eats ordinary prose makes real memories unfindable
    /// while `status` still tells the model the window was covered — the same false-negative-becomes-
    /// false-statement failure the redaction exists to avoid, arriving from the opposite direction.
    func testOrdinaryProseSurvives() {
        let untouched = [
            "I forgot my password again, can you reset it",
            "the code review is on Thursday",
            "we should check the state of the migration",
            "Sarah said the budget is $1,200 each for Lisbon",
            "git commit -m \"fix: handle the token bucket refill\"",
        ]
        for text in untouched {
            XCTAssertEqual(
                Redaction.scrub(text), text,
                "ordinary prose was altered — recall searches this text")
        }
    }

    func testSensitiveWindowsAreNeverCaptured() {
        XCTAssertTrue(Redaction.isSensitiveWindow(app: "1Password", title: "Personal"))
        XCTAssertTrue(Redaction.isSensitiveWindow(app: "Keychain Access", title: nil))
        XCTAssertFalse(Redaction.isSensitiveWindow(app: "Safari", title: "Flight deals to Lisbon"))
    }

    /// Scrubbing runs on every OCR pass, so it has to stay cheap relative to the 3 s capture cadence.
    func testScrubbingAFullScreenOfTextIsNotSlow() {
        let page = String(repeating: "the quick brown fox jumps over the lazy dog ", count: 400)
        let started = Date()
        _ = Redaction.scrub(page)
        XCTAssertLessThan(
            Date().timeIntervalSince(started), 0.5,
            "scrubbing a page of text must not approach the capture interval")
    }
}
