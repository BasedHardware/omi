import XCTest

@testable import Omi_Computer

#if DEBUG
  // omi-release-compile: this suite drives DEBUG-only test seams; the release-mode
  // notification regression step must compile the bundle without them.

  /// SET-02: the feedback dry-run bridge action must let a harness inspect the exact
  /// payload `FeedbackView.submitFeedback()` would attach — WITHOUT firing a Sentry
  /// event — so the diagnostics JSON can be scanned for secrets.
  ///
  /// The redaction guarantee of the diagnostics attachment itself is already covered
  /// by `DesktopDiagnosticsManagerTests`. These tests instead pin the *dry-run seam*:
  /// that the action is registered, derives its payload from the same builders the
  /// real submit uses (so it can't silently drift), and never touches Sentry.
  final class FeedbackPayloadDryRunTests: XCTestCase {
    private let actionName = "dump_feedback_payload_dryrun"

    // MARK: - Source-invariant guards on the dry-run seam

    func testActionIsRegisteredAndNonProdGated() throws {
      // Assert presence against the FULL source and FAIL (not XCTSkip) if the action
      // is ever deleted/renamed. `dryRunActionBlock()` skips when the marker is
      // absent, so without this hard check every source-invariant test in this file
      // would skip silently and CI would stay green on a removed action.
      let source = try bridgeSource()
      XCTAssertTrue(
        source.contains("name: \"\(actionName)\""),
        "dry-run action must be registered under its stable name")

      let block = try dryRunActionBlock()
      XCTAssertTrue(
        block.contains("guard AppBuild.isNonProduction"),
        "dry-run action must refuse to run on production bundles")
    }

    func testDryRunUsesTheSameBuildersAsTheRealSubmit() throws {
      let block = try dryRunActionBlock()
      // Same diagnostics builder the real Sentry attachment uses — the dry-run
      // returns the identical JSON, not a parallel reimplementation.
      XCTAssertTrue(
        block.contains("DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment()"),
        "dry-run must build the diagnostics JSON via the shared attachment builder")
      // Same title builder the real submit uses.
      XCTAssertTrue(
        block.contains("feedbackReportTitle(for:"),
        "dry-run must derive the report title from the shared builder")
      XCTAssertTrue(
        block.contains("feedbackDiagnosticsAttachmentFilename"),
        "dry-run must report the shared diagnostics attachment filename")
    }

    func testDryRunNeverSubmitsToSentry() throws {
      let block = try dryRunActionBlock()
      XCTAssertFalse(
        block.contains("SentrySDK"),
        "dry-run must not invoke Sentry — that is the whole point of a dry run")
      XCTAssertTrue(
        block.contains("\"sentry_capture_invoked\": \"false\""),
        "dry-run must declare that no Sentry capture happened")
    }

    func testDryRunReturnsLogMetadataOnlyNotContents() throws {
      let block = try dryRunActionBlock()
      // The raw log is attached unredacted to Sentry by design; the dry-run must
      // surface only metadata so the bridge response can't leak the log itself.
      XCTAssertTrue(block.contains("log_attachment_filename"))
      XCTAssertTrue(block.contains("log_attachment_exists"))
      // Targeted guard: reject the common ways of reading the log *contents* keyed
      // on logPath. Not exhaustive (a FileHandle read would slip past), but paired
      // with the positive metadata-only assertions above it pins the intent.
      XCTAssertFalse(
        block.contains("contentsOfFile: logPath"),
        "dry-run must not read the raw log contents into its response")
      XCTAssertFalse(
        block.contains("contentsOf: URL(fileURLWithPath: logPath)"),
        "dry-run must not read the raw log contents into its response")
    }

    func testRealSubmitSharesTheSameBuilders() throws {
      // If submitFeedback stopped using the shared builders, the dry-run would no
      // longer reflect what actually ships — pin that both sides share them.
      let source = try feedbackViewSource()
      XCTAssertTrue(
        source.contains("let sentryMessage = feedbackReportTitle(for: message)"),
        "submitFeedback must build its Sentry title via the shared builder")
      XCTAssertTrue(
        source.contains("filename: feedbackDiagnosticsAttachmentFilename"),
        "submitFeedback must attach the diagnostics JSON under the shared filename")
    }

    // MARK: - Behavioral: shared title builder + payload shape

    func testReportTitleBuilderMatchesTheShippedStrings() {
      XCTAssertEqual(feedbackReportTitle(for: ""), "User Report (logs only)")
      XCTAssertEqual(feedbackReportTitle(for: "mic dropped"), "User Report: mic dropped")
    }

    func testDiagnosticsPayloadIsParseableAndCarriesPrivacyMarker() throws {
      DesktopDiagnosticsManager.shared.resetForTests()
      defer { DesktopDiagnosticsManager.shared.resetForTests() }
      DesktopDiagnosticsManager.shared.recordPTTSilentTurn(
        source: "hub",
        mode: "hold",
        audioSeconds: 2.0,
        voicedSeconds: nil,
        peak: 0,
        rms: 0,
        deviceDescription: "built-in microphone",
        micPermissionGranted: true,
        hubActive: true)

      let url = try XCTUnwrap(DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment())
      defer { try? FileManager.default.removeItem(at: url) }
      let data = try Data(contentsOf: url)
      let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])

      // This is exactly the JSON the dry-run returns as `diagnostics_json`: valid,
      // shaped, and flagged as operational-only so a secret-scan has a clean target.
      XCTAssertEqual(root["privacy"] as? String, "safe_operational_fields_only")
      XCTAssertNotNil(root["snapshots"] as? [[String: Any]])
    }

    // MARK: - Helpers

    private func dryRunActionBlock() throws -> String {
      let source = try bridgeSource()
      guard let start = source.range(of: "name: \"\(actionName)\"") else {
        throw XCTSkip("\(actionName) registration not found")
      }
      let tail = source[start.lowerBound...]
      // The dry-run action is the last register() in registerBuiltins(); slice to
      // the next register() if one is ever added after it, else take the rest.
      if let next = tail.dropFirst().range(of: "\n    register(") {
        return String(tail[..<next.lowerBound])
      }
      return String(tail)
    }

    private func bridgeSource() throws -> String {
      try sourceFile(named: "DesktopAutomationBridge.swift")
    }

    private func feedbackViewSource() throws -> String {
      try sourceFile(named: "FeedbackView.swift")
    }

    private func sourceFile(named name: String) throws -> String {
      let url = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .appendingPathComponent("Sources/\(name)")
      return try String(contentsOf: url, encoding: .utf8)
    }
  }
#endif
