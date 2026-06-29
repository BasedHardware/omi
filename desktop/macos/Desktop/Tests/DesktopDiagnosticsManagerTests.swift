import XCTest

@testable import Omi_Computer

final class DesktopDiagnosticsManagerTests: XCTestCase {
  func testDiagnosticsAttachmentUsesSafeOperationalFields() throws {
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

    let url = try XCTUnwrap(DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment())
    defer { try? FileManager.default.removeItem(at: url) }

    let data = try Data(contentsOf: url)
    let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    let snapshots = try XCTUnwrap(root["snapshots"] as? [[String: Any]])
    let snapshot = try XCTUnwrap(snapshots.last)

    XCTAssertEqual(snapshot["event"] as? String, "ptt_audio_capture_silent_turn")
    XCTAssertEqual(snapshot["input_device_class"] as? String, "built_in_mic")
    XCTAssertEqual(snapshot["peak"] as? Int, 0)
    XCTAssertEqual(snapshot["rms"] as? Int, 0)

    let json = String(data: data, encoding: .utf8) ?? ""
    XCTAssertFalse(json.contains("Alice"))
    XCTAssertFalse(json.contains("private microphone"))
    XCTAssertFalse(json.contains("id=123"))
  }
}
