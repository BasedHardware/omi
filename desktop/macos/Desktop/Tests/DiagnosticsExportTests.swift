import XCTest

@testable import Omi_Computer

/// BL-023 / SET-03: the local (offline) diagnostics export must produce a file
/// with app/OS metadata and a *redacted* log tail — no raw tokens.
final class DiagnosticsExportTests: XCTestCase {
  private var tempDir: URL!

  override func setUpWithError() throws {
    try super.setUpWithError()
    DesktopDiagnosticsManager.shared.resetForTests()
    tempDir = FileManager.default.temporaryDirectory
      .appendingPathComponent("diagnostics-export-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
  }

  override func tearDownWithError() throws {
    DesktopDiagnosticsManager.shared.resetForTests()
    if let tempDir { try? FileManager.default.removeItem(at: tempDir) }
    try super.tearDownWithError()
  }

  func testLocalBundleRedactsSecretsFromLogTailButKeepsBenignLines() throws {
    let logPath = tempDir.appendingPathComponent("omi-dev.log").path
    let jwt =
      "eyJhbGciOiJIUzI1NiJ9.eyJ1aWQiOiJhYmMifQ.s3cr3tSignatureValue_do_not_leak"
    let logContents = [
      "[10:00:00.000] [app] launched cleanly",
      "[10:00:01.000] [app] GET /v1/things?api_key=SUPERSECRETKEY123 status=200",
      "[10:00:02.000] [app] Authorization: Bearer BEARERTOKENabc123def456",
      "[10:00:03.000] [app] idToken=\(jwt)",
      "[10:00:03.500] [app] Authorization: Basic dXNlcjpwYXNzd29yZA==",
      "[10:00:03.750] [app] openai_key=sk-proj-1234567890abcdef1234567890abcdef",
      "[10:00:03.900] [app] raw key sk-1234567890abcdef1234567890abcdef",
      "[10:00:03.950] [app] applied basic settings for the user",
      "[10:00:04.000] [app] user tapped Report Issue",
    ].joined(separator: "\n")
    try logContents.write(toFile: logPath, atomically: true, encoding: .utf8)

    let text = DesktopDiagnosticsManager.shared.buildLocalDiagnosticsText(logPath: logPath)

    // Secrets are gone.
    XCTAssertFalse(text.contains("SUPERSECRETKEY123"), "api_key value leaked")
    XCTAssertFalse(text.contains("BEARERTOKENabc123def456"), "bearer token leaked")
    XCTAssertFalse(text.contains(jwt), "JWT leaked")
    XCTAssertFalse(text.contains("dXNlcjpwYXNzd29yZA=="), "basic auth leaked")
    XCTAssertFalse(text.contains("sk-proj-1234567890abcdef1234567890abcdef"), "OpenAI key leaked")
    XCTAssertFalse(text.contains("sk-1234567890abcdef1234567890abcdef"), "bare OpenAI key leaked")
    XCTAssertTrue(text.contains("[redacted"), "expected redaction markers")

    // Benign operational lines survive so the report stays useful — including
    // "basic settings", which the Basic-auth pattern must not over-redact.
    XCTAssertTrue(text.contains("launched cleanly"))
    XCTAssertTrue(text.contains("user tapped Report Issue"))
    XCTAssertTrue(text.contains("applied basic settings for the user"), "over-redacted benign 'basic'")

    // Metadata header is present and offline-safe.
    XCTAssertTrue(text.contains("# Omi Desktop Diagnostics"))
    XCTAssertTrue(text.contains("os_version:"))
    XCTAssertTrue(text.contains("privacy: redacted_local_export"))
  }

  func testWriteLocalDiagnosticsBundleCreatesFileOffline() throws {
    let logPath = tempDir.appendingPathComponent("omi-dev.log").path
    try "[10:00:00.000] [app] hello\n".write(toFile: logPath, atomically: true, encoding: .utf8)

    let outURL = tempDir.appendingPathComponent("omi-diagnostics.txt")
    XCTAssertTrue(
      DesktopDiagnosticsManager.shared.writeLocalDiagnosticsBundle(to: outURL, logPath: logPath))

    XCTAssertTrue(FileManager.default.fileExists(atPath: outURL.path))
    let written = try String(contentsOf: outURL, encoding: .utf8)
    XCTAssertTrue(written.contains("# Omi Desktop Diagnostics"))
    XCTAssertTrue(written.contains("hello"))
  }

  func testBundleIncludesSanitizedHealthSnapshots() throws {
    DesktopDiagnosticsManager.shared.recordPTTSilentTurn(
      source: "hub",
      mode: "hold",
      audioSeconds: 2.14,
      voicedSeconds: nil,
      peak: 0,
      rms: 0,
      deviceDescription: "built-in id=123 Alice private microphone",
      micPermissionGranted: true,
      hubActive: true)

    let logPath = tempDir.appendingPathComponent("omi-dev.log").path
    let text = DesktopDiagnosticsManager.shared.buildLocalDiagnosticsText(logPath: logPath)

    XCTAssertTrue(text.contains("ptt_audio_capture_silent_turn"))
    // The device-description PII must not survive into the snapshot section.
    XCTAssertFalse(text.contains("Alice"))
    XCTAssertFalse(text.contains("private microphone"))
  }

  func testMissingLogFileIsReportedNotCrashed() throws {
    let missing = tempDir.appendingPathComponent("does-not-exist.log").path
    let text = DesktopDiagnosticsManager.shared.buildLocalDiagnosticsText(logPath: missing)
    XCTAssertTrue(text.contains("no readable log file"))
  }

  func testLogTailReadsBoundedEndOfLargeLogFile() throws {
    let logPath = tempDir.appendingPathComponent("omi-dev.log").path
    // A log larger than the 512 KB bounded-read window: the head line falls
    // outside both the byte window and the requested line tail and must be
    // excluded, while the tail marker survives. Exercises the end-of-file seek
    // plus partial-first-line trim in redactedLogTail.
    var lines = ["[00:00:00.000] [app] HEAD_MARKER_beyond_window"]
    for i in 1...15000 {
      lines.append("[00:00:00.000] [app] filler operational line number \(i)")
    }
    lines.append("[23:59:59.999] [app] TAIL_MARKER_at_end")
    let body = lines.joined(separator: "\n")
    XCTAssertGreaterThan(
      body.utf8.count, 512 * 1024, "test log must exceed the bounded-read window")
    try body.write(toFile: logPath, atomically: true, encoding: .utf8)

    let text = DesktopDiagnosticsManager.shared.buildLocalDiagnosticsText(
      logPath: logPath, maxLogLines: 50)

    XCTAssertTrue(text.contains("TAIL_MARKER_at_end"), "tail line missing from export")
    XCTAssertFalse(
      text.contains("HEAD_MARKER_beyond_window"), "head line should be outside the bounded tail")
  }
}
