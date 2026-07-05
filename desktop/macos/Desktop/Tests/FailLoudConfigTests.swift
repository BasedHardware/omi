import XCTest

@testable import Omi_Computer

/// S-08 — Fail-loud config (BL-019, BL-020).
/// Behavioral tests where the type is constructible; source-scrape guards
/// (same pattern as `TranscriptionTransportTests`/`PTTAudioCaptureRaceTests`)
/// for the private auth internals and the AppState permission path that can't
/// be driven without a real signed-in session or a live TCC grant.
final class FailLoudConfigTests: XCTestCase {

  // MARK: BL-019 — empty firebaseApiKey must fail loud, not silently produce ""

  /// A dedicated, user-visible error exists for the missing-key case (so the
  /// failure surfaces as an actionable message instead of an opaque HTTP 400).
  func testMissingFirebaseApiKeyErrorIsUserVisible() {
    let message = AuthError.missingFirebaseApiKey.errorDescription
    XCTAssertNotNil(message)
    let lowered = (message ?? "").lowercased()
    XCTAssertTrue(
      lowered.contains("firebase") || lowered.contains("api key"),
      "the missing-key error must name the cause; got: \(message ?? "nil")")
  }

  /// Every Firebase REST URL builder resolves the key through the throwing
  /// `requireFirebaseApiKey()` helper — the raw `?key=\(firebaseApiKey)`
  /// interpolation (which silently emits `?key=` when unset) must be gone.
  func testFirebaseRequestsResolveKeyThroughThrowingHelper() throws {
    let src = try source(relativePath: "Sources/AuthService.swift")

    XCTAssertTrue(
      src.contains("func requireFirebaseApiKey() throws -> String"),
      "a throwing key accessor must exist")
    XCTAssertTrue(
      src.contains("throw AuthError.missingFirebaseApiKey"),
      "the helper must fail loud on an empty/missing key")

    // The silent path — interpolating the raw computed property straight into a
    // request URL — must no longer exist at any call site.
    XCTAssertFalse(
      src.contains("?key=\\(firebaseApiKey)"),
      "auth request URLs must use the guarded key (try requireFirebaseApiKey()), not the raw property")

    // Each of the three Firebase endpoints must go through the helper.
    XCTAssertTrue(src.contains("signInWithCustomToken?key=\\(apiKey)"))
    XCTAssertTrue(src.contains("securetoken.googleapis.com/v1/token?key=\\(apiKey)"))
    XCTAssertTrue(src.contains("signInWithIdp?key=\\(apiKey)"))
  }

  // MARK: Helper

  private func source(relativePath: String) throws -> String {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent(relativePath)
    return try String(contentsOf: url, encoding: .utf8)
  }
}
