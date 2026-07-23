import AVFoundation
import CoreGraphics
import Foundation
import XCTest

@testable import Omi_Computer

/// Regression coverage for the writer settings that reach `AVAssetWriterInput`.
/// Intel macOS 15 rejects the duration-based keyframe setting for HEVC/hvc1
/// while constructing the input, so this test pins the supported configuration
/// and exercises the real `VideoChunkEncoder` start, append, and finalization
/// path that uses it.
final class VideoChunkEncoderHEVCWriterTests: XCTestCase {
  private var fixture: RewindStorageTestIsolation.Fixture?

  override func setUp() async throws {
    try await super.setUp()
    await RewindStorage.shared.reset()
    fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "rewind-hevc-writer")
    try await RewindStorage.shared.initialize()
  }

  override func tearDown() async throws {
    await VideoChunkEncoder.shared.cancel()
    await RewindStorage.shared.reset()
    await RewindStorageTestIsolation.tearDown(userDir: fixture?.userDir)
    fixture = nil
    try await super.tearDown()
  }

  func testHEVCWriterSettingsOmitUnsupportedDurationKey() throws {
    let settings = VideoChunkEncoder.hevcVideoSettings(
      width: 96,
      height: 64,
      bitrate: 128_000,
      frameRate: 1.0 / 3.0
    )
    let compressionProperties = try XCTUnwrap(settings[AVVideoCompressionPropertiesKey] as? [String: Any])

    XCTAssertEqual(settings[AVVideoCodecKey] as? AVVideoCodecType, .hevc)
    XCTAssertEqual(compressionProperties[AVVideoAverageBitRateKey] as? Int, 128_000)
    XCTAssertEqual(compressionProperties[AVVideoExpectedSourceFrameRateKey] as? Int, 1)
    XCTAssertEqual(compressionProperties[AVVideoAllowFrameReorderingKey] as? Bool, false)
    XCTAssertNil(compressionProperties[AVVideoMaxKeyFrameIntervalDurationKey])
  }

  func testHEVCWriterStartsAppendsAndFinalizesAChunk() async throws {
    let encoder = VideoChunkEncoder.shared
    let image = try solidRedImage()
    let startedAt = Date()

    let idleStatus = await encoder.getBufferStatus()
    XCTAssertEqual(idleStatus.lifecyclePhase, "idle")
    XCTAssertEqual(idleStatus.queueBucket, "none")
    XCTAssertTrue(idleStatus.isInitialized)

    let firstFrame = try await encoder.addFrame(image: image, timestamp: startedAt)
    let secondFrame = try await encoder.addFrame(image: image, timestamp: startedAt.addingTimeInterval(3))
    XCTAssertNotNil(firstFrame)
    XCTAssertNotNil(secondFrame)

    let writingStatus = await encoder.getBufferStatus()
    XCTAssertEqual(writingStatus.lifecyclePhase, "writing")
    XCTAssertEqual(writingStatus.queueBucket, "few")
    XCTAssertTrue(writingStatus.hasStalenessTimer)

    let flushResult = try await encoder.flushCurrentChunk()
    let result = try XCTUnwrap(flushResult)
    XCTAssertEqual(result.frames.map(\.frameOffset), [0, 1])

    let finalizedStatus = await encoder.getBufferStatus()
    XCTAssertEqual(finalizedStatus.lifecyclePhase, "idle")
    XCTAssertEqual(finalizedStatus.queueBucket, "none")
    XCTAssertFalse(finalizedStatus.hasStalenessTimer)
    XCTAssertEqual(finalizedStatus.finalizationWaiterBucket, "none")

    let maybeVideosDirectory = await RewindStorage.shared.getVideosDirectory()
    let videosDirectory = try XCTUnwrap(maybeVideosDirectory)
    let videoURL = videosDirectory.appendingPathComponent(result.videoChunkPath)
    XCTAssertTrue(FileManager.default.fileExists(atPath: videoURL.path))

    let center = try await RewindStorage.shared.videoFrameCenterPixel(
      videoPath: result.videoChunkPath,
      frameOffset: 0
    )
    XCTAssertGreaterThan(center.red, center.green)
    XCTAssertGreaterThan(center.red, center.blue)
  }

  private func solidRedImage() throws -> CGImage {
    let width = 96
    let height = 64
    let colorSpace = CGColorSpaceCreateDeviceRGB()
    let context = try XCTUnwrap(
      CGContext(
        data: nil,
        width: width,
        height: height,
        bitsPerComponent: 8,
        bytesPerRow: 0,
        space: colorSpace,
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
      ))
    context.setFillColor(red: 1, green: 0, blue: 0, alpha: 1)
    context.fill(CGRect(x: 0, y: 0, width: width, height: height))
    return try XCTUnwrap(context.makeImage())
  }
}
