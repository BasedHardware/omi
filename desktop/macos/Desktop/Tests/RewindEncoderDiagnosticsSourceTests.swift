import XCTest

final class RewindEncoderDiagnosticsSourceTests: XCTestCase {
  func testEncoderStatusExposesBoundedLifecycleCounters() throws {
    let source = try readSource("Sources/Rewind/Core/VideoChunkEncoder.swift")

    XCTAssertTrue(source.contains("struct EncoderStatus"))
    XCTAssertTrue(source.contains("maxBufferFrames"))
    XCTAssertTrue(source.contains("encoderRestartCount"))
    XCTAssertTrue(source.contains("emergencyResetCount"))
    // Encoder diagnostics were renamed ffmpeg* -> writer* (AVAssetWriter-based encoder).
    XCTAssertTrue(source.contains("writerNotReadyCount"))
    XCTAssertTrue(source.contains("maxConsecutiveNotReadyFailures"))
    XCTAssertTrue(source.contains("writer_not_ready_loop"))
    XCTAssertTrue(source.contains("buffer_overflow"))
    XCTAssertTrue(source.contains("writer_start_failure"))
    XCTAssertTrue(source.contains("write_failure"))
  }

  func testResourceMonitorPublishesRewindAndEncoderDiagnostics() throws {
    let source = try readSource("Sources/ResourceMonitor.swift")

    XCTAssertTrue(source.contains("videoEncoder_maxBufferFrames"))
    XCTAssertTrue(source.contains("videoEncoder_isEncoderRunning"))
    XCTAssertTrue(source.contains("videoEncoder_restartCount"))
    XCTAssertTrue(source.contains("videoEncoder_emergencyResetCount"))
    XCTAssertTrue(source.contains("videoEncoder_writerNotReadyCount"))
    XCTAssertTrue(source.contains("rewind_isMonitoring"))
    XCTAssertTrue(source.contains("rewind_effectiveCaptureIntervalSec"))
    XCTAssertTrue(source.contains("system_memoryPressurePercent"))
  }

  private func readSource(_ relativePath: String) throws -> String {
    let testFile = URL(fileURLWithPath: #filePath)
    let desktopDir = testFile.deletingLastPathComponent().deletingLastPathComponent()
    let file = desktopDir.appendingPathComponent(relativePath)
    return try String(contentsOf: file, encoding: .utf8)
  }
}
