import XCTest

@testable import Omi_Computer

#if DEBUG
  // omi-release-compile: this suite drives DEBUG-only test seams; the release-mode
  // notification regression step must compile the bundle without them.

  final class BleAudioProcessorTests: XCTestCase {
    override func setUp() {
      super.setUp()
      DesktopDiagnosticsManager.shared.resetForTests()
    }

    override func tearDown() {
      DesktopDiagnosticsManager.shared.resetForTests()
      super.tearDown()
    }

    func testDecodeFailureThresholdRecordsHealthAndNotifiesDelegate() throws {
      let processor = BleAudioProcessor(codec: .opusFS320)
      let delegate = DecodeFailureDelegate()
      processor.delegate = delegate

      for _ in 0..<10 {
        processor.processFrame(Data([0x00, 0x01, 0x02]))
      }

      XCTAssertEqual(delegate.failureCount, 1)

      let snapshot = try latestHealthSnapshot()
      XCTAssertEqual(snapshot["event"] as? String, "fallback_triggered")
      XCTAssertEqual(snapshot["area"] as? String, "ble_audio")
      XCTAssertEqual(snapshot["recovery_action"] as? String, "continue_raw_capture")
    }

    private func latestHealthSnapshot() throws -> [String: Any] {
      let url = try XCTUnwrap(DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment())
      defer { try? FileManager.default.removeItem(at: url) }
      let data = try Data(contentsOf: url)
      let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
      let snapshots = try XCTUnwrap(root["snapshots"] as? [[String: Any]])
      return try XCTUnwrap(snapshots.last)
    }
  }

  private final class DecodeFailureDelegate: BleAudioProcessor.Delegate {
    var failureCount = 0

    func bleAudioProcessor(_ processor: BleAudioProcessor, didDecodeSamples samples: [Int16]) {}

    func bleAudioProcessor(_ processor: BleAudioProcessor, didFailWithError error: Error) {
      failureCount += 1
    }
  }
#endif
