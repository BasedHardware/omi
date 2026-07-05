import XCTest

final class RewindEncoderDiagnosticsSourceTests: XCTestCase {
  func testEncoderStatusExposesBoundedLifecycleCounters() throws {
    let source = try readSource("Sources/Rewind/Core/VideoChunkEncoder.swift")

    XCTAssertTrue(source.contains("struct EncoderStatus"))
    XCTAssertTrue(source.contains("maxBufferFrames"))
    XCTAssertTrue(source.contains("encoderRestartCount"))
    XCTAssertTrue(source.contains("emergencyResetCount"))
    XCTAssertTrue(source.contains("ffmpegNotReadyCount"))
    XCTAssertTrue(source.contains("maxConsecutiveNotReadyFailures"))
    XCTAssertTrue(source.contains("ffmpeg_not_ready_loop"))
    XCTAssertTrue(source.contains("buffer_overflow"))
    XCTAssertTrue(source.contains("ffmpeg_start_failure"))
    XCTAssertTrue(source.contains("write_failure"))
  }

  func testResourceMonitorPublishesRewindAndEncoderDiagnostics() throws {
    let source = try readSource("Sources/ResourceMonitor.swift")

    XCTAssertTrue(source.contains("videoEncoder_maxBufferFrames"))
    XCTAssertTrue(source.contains("videoEncoder_isFFmpegRunning"))
    XCTAssertTrue(source.contains("videoEncoder_restartCount"))
    XCTAssertTrue(source.contains("videoEncoder_emergencyResetCount"))
    XCTAssertTrue(source.contains("videoEncoder_ffmpegNotReadyCount"))
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
