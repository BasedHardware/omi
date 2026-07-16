import AVFoundation
import AppKit
import XCTest

@testable import Omi_Computer

@MainActor
final class RewindStorageVideoFrameExtractionTests: XCTestCase {
  private var testUserId: String!
  private var userDir: URL!

  override func setUp() async throws {

    testUserId = "video-frame-test-\(UUID().uuidString)"
    RewindDatabase.currentUserId = testUserId
    try await RewindStorage.shared.initialize()

    let appSupport = FileManager.default
      .urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
    userDir =
      appSupport
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)
  }

  override func tearDown() async throws {
    if let userDir { try? FileManager.default.removeItem(at: userDir) }
    RewindDatabase.currentUserId = nil
    await RewindStorage.shared.reset()
  }

  func testLoadVideoFrameExtractsRequestedFrameOffsetFromMP4Chunk() async throws {
    let relativePath = "2026-07-04/chunk_frame_selection.mp4"
    let fullPath = try await createChunk(relativePath: relativePath, colors: [.red, .green, .blue], frameRate: 2.0)

    XCTAssertTrue(FileManager.default.fileExists(atPath: fullPath.path), "precondition: MP4 chunk written")

    let frame = try await RewindStorage.shared.loadVideoFrame(videoPath: relativePath, frameOffset: 1)
    let center = try XCTUnwrap(centerPixel(in: frame))

    XCTAssertGreaterThan(center.green, center.red)
    XCTAssertGreaterThan(center.green, center.blue)
  }

  func testLoadVideoFrameUsesSampleOrdinalForLowCadenceChunks() async throws {
    let relativePath = "2026-07-04/chunk_low_cadence_frame_selection.mp4"
    let fullPath = try await createChunk(
      relativePath: relativePath, colors: [.red, .green, .blue], frameRate: 1.0 / 3.0)

    XCTAssertTrue(FileManager.default.fileExists(atPath: fullPath.path), "precondition: MP4 chunk written")

    let frame = try await RewindStorage.shared.loadVideoFrame(videoPath: relativePath, frameOffset: 1)
    let center = try XCTUnwrap(centerPixel(in: frame))

    XCTAssertGreaterThan(center.green, center.red)
    XCTAssertGreaterThan(center.green, center.blue)
  }

  func testRebuildUsesActualLowCadenceSamplePresentationTimes() async throws {
    let relativePath = "2026-07-04/chunk_120000.mp4"
    let presentationTimes: [TimeInterval] = [0, 3, 6]
    let fullPath = try await createChunk(
      relativePath: relativePath,
      colors: [.red, .green, .blue],
      presentationTimes: presentationTimes)

    let screenshots = try await RewindIndexer.reconstructedScreenshots(
      from: VideoChunkInfo(
        filename: fullPath.lastPathComponent,
        relativePath: relativePath,
        fullPath: fullPath))
    let chunkBase = try XCTUnwrap(RewindIndexer.parseChunkTimestamp(relativePath: relativePath))

    XCTAssertEqual(screenshots.count, 3)
    XCTAssertEqual(screenshots.compactMap(\.frameOffset), [0, 1, 2])
    for (screenshot, expectedPresentationTime) in zip(screenshots, presentationTimes) {
      XCTAssertEqual(
        screenshot.timestamp.timeIntervalSince(chunkBase),
        expectedPresentationTime,
        accuracy: 0.001)
      XCTAssertEqual(screenshot.appName, "Unknown")
      XCTAssertNil(screenshot.windowTitle)
      XCTAssertNil(screenshot.ocrText)
    }
  }

  func testRebuildTimelineValidationRejectsEmptyAndUnsafePresentationTimes() {
    assertTimelineRejected([], expected: .zeroFrames)
    assertTimelineRejected([.nan], expected: .invalidTimeline)
    assertTimelineRejected([-.infinity], expected: .invalidTimeline)
    assertTimelineRejected([-0.001], expected: .invalidTimeline)
    assertTimelineRejected([0, 0], expected: .invalidTimeline)
    assertTimelineRejected([0, 3, 2], expected: .invalidTimeline)
  }

  func testLoadVideoFrameReturnsNotFoundWhenFrameOffsetIsPastEnd() async throws {
    let relativePath = "2026-07-04/chunk_missing_frame.mp4"
    _ = try await createChunk(relativePath: relativePath, colors: [.red, .green, .blue], frameRate: 2.0)

    do {
      _ = try await RewindStorage.shared.loadVideoFrame(videoPath: relativePath, frameOffset: 99)
      XCTFail("Expected missing frame offset to be reported as screenshotNotFound")
    } catch RewindError.screenshotNotFound {
      // Expected: mirrors ffmpeg select=eq(n,offset) producing no frame.
    } catch {
      XCTFail("Expected screenshotNotFound, got \(error)")
    }
  }

  func testResetRebindsVideoEncoderToNextUserDirectory() async throws {
    let maybeFirstVideosDir = await VideoChunkEncoder.shared.videosDirectoryForTesting()
    let firstVideosDir = try XCTUnwrap(maybeFirstVideosDir)
    let nextUserId = "video-frame-test-next-\(UUID().uuidString)"
    let nextUserDir = FileManager.default
      .urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(nextUserId, isDirectory: true)
    defer { try? FileManager.default.removeItem(at: nextUserDir) }

    await RewindStorage.shared.reset()
    RewindDatabase.currentUserId = nextUserId
    try await RewindStorage.shared.initialize()

    let maybeReboundVideosDir = await VideoChunkEncoder.shared.videosDirectoryForTesting()
    let reboundVideosDir = try XCTUnwrap(maybeReboundVideosDir)
    XCTAssertNotEqual(reboundVideosDir.standardizedFileURL, firstVideosDir.standardizedFileURL)
    XCTAssertEqual(
      reboundVideosDir.standardizedFileURL,
      nextUserDir.appendingPathComponent("Videos", isDirectory: true).standardizedFileURL
    )
  }

  func testFinalizedChunkFilterExcludesActiveChunkAndKeepsFinalizedChunks() {
    let directory = URL(fileURLWithPath: "/tmp/rewind-finalized-filter", isDirectory: true)
    let finalizedPath = "2026-07-04/chunk_120000.mp4"
    let activePath = "2026-07-04/chunk_120100.mp4"
    let chunks = [
      VideoChunkInfo(
        filename: "chunk_120000.mp4",
        relativePath: finalizedPath,
        fullPath: directory.appendingPathComponent(finalizedPath)),
      VideoChunkInfo(
        filename: "chunk_120100.mp4",
        relativePath: activePath,
        fullPath: directory.appendingPathComponent(activePath)),
    ]

    let finalized = RewindStorage.filterFinalizedVideoChunks(chunks, excluding: activePath)

    XCTAssertEqual(finalized.map(\.relativePath), [finalizedPath])
  }

  private func createChunk(
    relativePath: String,
    colors: [NSColor],
    frameRate: Double
  ) async throws -> URL {
    let presentationTimes = colors.indices.map { Double($0) / frameRate }
    return try await createChunk(
      relativePath: relativePath,
      colors: colors,
      presentationTimes: presentationTimes,
      expectedSourceFrameRate: max(1, Int(ceil(frameRate))))
  }

  private func createChunk(
    relativePath: String,
    colors: [NSColor],
    presentationTimes: [TimeInterval],
    expectedSourceFrameRate: Int = 1
  ) async throws -> URL {
    guard colors.count == presentationTimes.count else {
      throw RewindError.storageError("Test video colors and presentation times must match")
    }

    let maybeVideosDir = await RewindStorage.shared.getVideosDirectory()
    let videosDir = try XCTUnwrap(maybeVideosDir)
    let outputURL = videosDir.appendingPathComponent(relativePath)
    try FileManager.default.createDirectory(
      at: outputURL.deletingLastPathComponent(),
      withIntermediateDirectories: true
    )

    let width = 96
    let height = 64
    let writer = try AVAssetWriter(outputURL: outputURL, fileType: .mp4)
    writer.shouldOptimizeForNetworkUse = true

    let input = AVAssetWriterInput(
      mediaType: .video,
      outputSettings: [
        AVVideoCodecKey: AVVideoCodecType.hevc,
        AVVideoWidthKey: width,
        AVVideoHeightKey: height,
        AVVideoCompressionPropertiesKey: [
          AVVideoExpectedSourceFrameRateKey: expectedSourceFrameRate,
          AVVideoAllowFrameReorderingKey: false,
        ],
      ])
    input.expectsMediaDataInRealTime = true

    guard writer.canAdd(input) else {
      throw XCTSkip("HEVC writer input is unavailable on this runner")
    }
    writer.add(input)

    let adaptor = AVAssetWriterInputPixelBufferAdaptor(
      assetWriterInput: input,
      sourcePixelBufferAttributes: [
        kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
        kCVPixelBufferWidthKey as String: width,
        kCVPixelBufferHeightKey as String: height,
        kCVPixelBufferIOSurfacePropertiesKey as String: [:],
      ]
    )

    guard writer.startWriting() else {
      throw RewindError.storageError("Failed to start test writer: \(writer.error?.localizedDescription ?? "unknown")")
    }
    writer.startSession(atSourceTime: .zero)

    for (index, color) in colors.enumerated() {
      while !input.isReadyForMoreMediaData {
        try await Task.sleep(nanoseconds: 10_000_000)
      }

      let pixelBuffer = try createPixelBuffer(
        width: width,
        height: height,
        color: color,
        adaptor: adaptor
      )
      let time = CMTime(seconds: presentationTimes[index], preferredTimescale: 600)
      guard adaptor.append(pixelBuffer, withPresentationTime: time) else {
        throw RewindError.storageError(
          "Failed to append test frame: \(writer.error?.localizedDescription ?? "unknown")")
      }
    }

    input.markAsFinished()
    let writerBox = TestAssetWriterBox(writer)
    try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
      writerBox.writer.finishWriting {
        if writerBox.writer.status == .completed {
          continuation.resume()
        } else {
          let error = writerBox.writer.error?.localizedDescription ?? "unknown"
          continuation.resume(throwing: RewindError.storageError("Failed to finish test writer: \(error)"))
        }
      }
    }

    return outputURL
  }

  private func assertTimelineRejected(
    _ presentationTimes: [TimeInterval],
    expected: RewindChunkExtractionError
  ) {
    do {
      _ = try RewindIndexer.validateVideoSampleTimeline(presentationTimes)
      XCTFail("unsafe video sample timeline should be rejected")
    } catch let error as RewindChunkExtractionError {
      XCTAssertEqual(error, expected)
    } catch {
      XCTFail("expected \(expected), got \(error)")
    }
  }

  private func createPixelBuffer(
    width: Int,
    height: Int,
    color: NSColor,
    adaptor: AVAssetWriterInputPixelBufferAdaptor
  ) throws -> CVPixelBuffer {
    var pixelBuffer: CVPixelBuffer?
    if let pool = adaptor.pixelBufferPool {
      CVPixelBufferPoolCreatePixelBuffer(nil, pool, &pixelBuffer)
    } else {
      CVPixelBufferCreate(
        nil,
        width,
        height,
        kCVPixelFormatType_32BGRA,
        [kCVPixelBufferIOSurfacePropertiesKey as String: [:]] as CFDictionary,
        &pixelBuffer
      )
    }

    let buffer = try XCTUnwrap(pixelBuffer)
    CVPixelBufferLockBaseAddress(buffer, [])
    defer { CVPixelBufferUnlockBaseAddress(buffer, []) }

    let context = try XCTUnwrap(
      CGContext(
        data: CVPixelBufferGetBaseAddress(buffer),
        width: width,
        height: height,
        bitsPerComponent: 8,
        bytesPerRow: CVPixelBufferGetBytesPerRow(buffer),
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGImageAlphaInfo.premultipliedFirst.rawValue | CGBitmapInfo.byteOrder32Little.rawValue
      ))

    context.setFillColor(color.cgColor)
    context.fill(CGRect(x: 0, y: 0, width: width, height: height))
    return buffer
  }

  private func centerPixel(in image: NSImage) -> (red: Int, green: Int, blue: Int)? {
    guard let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
      return nil
    }

    let bitmap = NSBitmapImageRep(cgImage: cgImage)
    let x = max(0, bitmap.pixelsWide / 2)
    let y = max(0, bitmap.pixelsHigh / 2)
    guard let color = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB) else {
      return nil
    }

    return (
      red: Int(color.redComponent * 255),
      green: Int(color.greenComponent * 255),
      blue: Int(color.blueComponent * 255)
    )
  }
}

private final class TestAssetWriterBox: @unchecked Sendable {
  let writer: AVAssetWriter

  init(_ writer: AVAssetWriter) {
    self.writer = writer
  }
}
