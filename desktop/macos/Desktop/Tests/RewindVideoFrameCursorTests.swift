import AVFoundation
import AppKit
import XCTest

@testable import Omi_Computer

/// Behavioural coverage for the sequential decode cursor `RewindStorage` now keeps parked on the
/// last chunk it read from.
///
/// A Rewind chunk is inter-frame compressed, so reaching frame *n* means decoding everything before
/// it. The reader used to be opened fresh per request and walked from frame 0 every time, which made
/// scrubbing a chunk quadratic in its length; keeping the reader alive makes a forward step cost one
/// sample buffer. That is a real change in how frames are produced, so the risk it introduces is
/// **correctness**, not speed: a cursor can only move forward, it can outlive the frames a chunk had
/// when it was opened, and the owning actor is reentrant. Every test below drives real decoded
/// pixels through `RewindStorage` for one of those three.
///
/// Frames are solid colours so a wrong frame is unambiguous rather than a subtle diff, and every
/// assertion reads the *decoded* centre pixel rather than any bookkeeping the cursor keeps.
final class RewindVideoFrameCursorTests: XCTestCase {
  private var testUserId: String!
  private var userDir: URL!

  /// Red, green, blue, red, green, blue — repeating so an off-by-one is visible as a wrong colour
  /// rather than accidentally matching its neighbour.
  private static let frameColors: [NSColor] = [
    .red, .green, .blue, .red, .green, .blue, .red, .green,
  ]
  private static let expectedNames = ["red", "green", "blue", "red", "green", "blue", "red", "green"]

  override func setUp() async throws {
    try await super.setUp()
    await RewindStorage.shared.reset()
    testUserId = "frame-cursor-test-\(UUID().uuidString)"
    RewindDatabase.currentUserId = testUserId
    try await RewindStorage.shared.initialize()

    userDir = FileManager.default
      .urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)
  }

  override func tearDown() async throws {
    if let userDir { try? FileManager.default.removeItem(at: userDir) }
    RewindDatabase.currentUserId = nil
    await RewindStorage.shared.reset()
    try await super.tearDown()
  }

  /// The move the cursor exists for: stepping forward one frame at a time through one chunk. Every
  /// step must produce its own frame, not the one the tape happened to be parked on.
  func testForwardScrubReturnsEveryFrameInOrder() async throws {
    let path = try await Self.makeChunk("forward")

    for offset in Self.frameColors.indices {
      let colour = try await Self.colourName(path: path, offset: offset)
      XCTAssertEqual(colour, Self.expectedNames[offset], "forward step to offset \(offset)")
    }
  }

  /// A cursor is a one-way tape, so every backward step has to retire it and reopen. This is the
  /// case that silently returns a stale frame if the rewind check is wrong.
  func testBackwardScrubReturnsEveryFrameInOrder() async throws {
    let path = try await Self.makeChunk("backward")
    await RewindStorage.shared.clearCache()

    for offset in Self.frameColors.indices.reversed() {
      let colour = try await Self.colourName(path: path, offset: offset)
      XCTAssertEqual(colour, Self.expectedNames[offset], "backward step to offset \(offset)")
    }
  }

  /// Jumping around — which is what clicking on the timeline does, as opposed to arrowing through it
  /// — mixes forward reuse and backward reopen in one sequence.
  func testOutOfOrderSeeksStayCorrect() async throws {
    let path = try await Self.makeChunk("out-of-order")
    await RewindStorage.shared.clearCache()

    for offset in [5, 2, 7, 0, 3, 3, 6, 1] {
      let colour = try await Self.colourName(path: path, offset: offset)
      XCTAssertEqual(colour, Self.expectedNames[offset], "seek to offset \(offset)")
    }
  }

  /// The owning actor suspends while opening a reader, so a second load arriving in that window must
  /// not share a half-advanced tape. Concurrent loads must each get their own frame.
  func testConcurrentLoadsEachGetTheirOwnFrame() async throws {
    let path = try await Self.makeChunk("concurrent")
    await RewindStorage.shared.clearCache()

    async let a = Self.colourName(path: path, offset: 0)
    async let b = Self.colourName(path: path, offset: 4)
    async let c = Self.colourName(path: path, offset: 2)
    async let d = Self.colourName(path: path, offset: 7)

    let results = try await [a, b, c, d]
    XCTAssertEqual(
      results,
      [Self.expectedNames[0], Self.expectedNames[4], Self.expectedNames[2], Self.expectedNames[7]])
  }

  /// The cursor must not turn "past the end" into a stale frame from the tape it is parked on. It is
  /// still an absence, reported the same way it was before the cursor existed.
  func testOffsetPastTheEndIsStillReportedAsMissing() async throws {
    let path = try await Self.makeChunk("past-end")
    _ = try await Self.colourName(path: path, offset: 3)  // park the cursor mid-chunk

    do {
      _ = try await RewindStorage.shared.videoFrameCenterPixel(videoPath: path, frameOffset: 99)
      XCTFail("expected a frame past the end of the chunk to be reported as missing")
    } catch RewindError.screenshotNotFound {
      // Expected.
    }
  }

  /// The main-actor image path no longer re-encodes the decoded frame to JPEG and decodes it again,
  /// so this asserts the pixels that reach the UI are the frame's own, at the frame's own size.
  @MainActor
  func testMainActorImageLoadReturnsTheDecodedFramePixels() async throws {
    let path = try await Self.makeChunk("image-load")
    let screenshot = Screenshot(
      timestamp: Date(),
      appName: "Cursor Test",
      windowTitle: "frame 4",
      imagePath: nil,
      videoChunkPath: path,
      frameOffset: 4
    )

    let image = try await RewindStorage.shared.loadScreenshotImage(for: screenshot)
    let cgImage = try XCTUnwrap(image.cgImage(forProposedRect: nil, context: nil, hints: nil))
    XCTAssertEqual(cgImage.width, 96)
    XCTAssertEqual(cgImage.height, 64)

    let bitmap = NSBitmapImageRep(cgImage: cgImage)
    let sample = try XCTUnwrap(
      bitmap.colorAt(x: bitmap.pixelsWide / 2, y: bitmap.pixelsHigh / 2)?.usingColorSpace(.deviceRGB))
    XCTAssertEqual(
      Self.dominantChannel(
        red: Int(sample.redComponent * 255),
        green: Int(sample.greenComponent * 255),
        blue: Int(sample.blueComponent * 255)),
      Self.expectedNames[4])
  }

  // MARK: - Helpers

  // Static so a concurrent test can start several of these at once: an `async let` on an
  // instance method would send task-isolated `self` across, which Swift 6 rejects.
  private static func colourName(path: String, offset: Int) async throws -> String {
    let pixel = try await RewindStorage.shared.videoFrameCenterPixel(videoPath: path, frameOffset: offset)
    return Self.dominantChannel(red: pixel.red, green: pixel.green, blue: pixel.blue)
  }

  private static func dominantChannel(red: Int, green: Int, blue: Int) -> String {
    let r = Double(red)
    let g = Double(green)
    let b = Double(blue)
    if r > g * 1.5, r > b * 1.5 { return "red" }
    if g > r * 1.5, g > b * 1.5 { return "green" }
    if b > r * 1.5, b > g * 1.5 { return "blue" }
    return "other(\(red),\(green),\(blue))"
  }

  private static func makeChunk(_ label: String) async throws -> String {
    let relativePath = "2026-07-04/chunk_cursor_\(label).mp4"
    let maybeVideosDir = await RewindStorage.shared.getVideosDirectory()
    let videosDir = try XCTUnwrap(maybeVideosDir)
    let outputURL = videosDir.appendingPathComponent(relativePath)
    try FileManager.default.createDirectory(
      at: outputURL.deletingLastPathComponent(), withIntermediateDirectories: true)

    let width = 96
    let height = 64
    let writer = try AVAssetWriter(outputURL: outputURL, fileType: .mp4)
    let input = AVAssetWriterInput(
      mediaType: .video,
      outputSettings: [
        AVVideoCodecKey: AVVideoCodecType.hevc,
        AVVideoWidthKey: width,
        AVVideoHeightKey: height,
        AVVideoCompressionPropertiesKey: [
          AVVideoExpectedSourceFrameRateKey: 1,
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
      ])

    guard writer.startWriting() else {
      throw RewindError.storageError("Failed to start test writer")
    }
    writer.startSession(atSourceTime: .zero)

    for (index, color) in Self.frameColors.enumerated() {
      while !input.isReadyForMoreMediaData {
        try await Task.sleep(nanoseconds: 10_000_000)
      }
      let buffer = try Self.makePixelBuffer(width: width, height: height, color: color, adaptor: adaptor)
      let time = CMTime(seconds: Double(index), preferredTimescale: 600)
      guard adaptor.append(buffer, withPresentationTime: time) else {
        throw RewindError.storageError("Failed to append test frame \(index)")
      }
    }

    input.markAsFinished()
    let box = CursorTestWriterBox(writer)
    try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
      box.writer.finishWriting {
        if box.writer.status == .completed {
          continuation.resume()
        } else {
          continuation.resume(throwing: RewindError.storageError("Failed to finish test writer"))
        }
      }
    }

    return relativePath
  }

  private static func makePixelBuffer(
    width: Int, height: Int, color: NSColor, adaptor: AVAssetWriterInputPixelBufferAdaptor
  ) throws -> CVPixelBuffer {
    guard let pool = adaptor.pixelBufferPool else {
      throw RewindError.storageError("Test pixel buffer pool unavailable")
    }
    var buffer: CVPixelBuffer?
    guard CVPixelBufferPoolCreatePixelBuffer(nil, pool, &buffer) == kCVReturnSuccess,
      let pixelBuffer = buffer
    else {
      throw RewindError.storageError("Failed to create test pixel buffer")
    }

    CVPixelBufferLockBaseAddress(pixelBuffer, [])
    defer { CVPixelBufferUnlockBaseAddress(pixelBuffer, []) }
    guard let base = CVPixelBufferGetBaseAddress(pixelBuffer),
      let rgb = color.usingColorSpace(.deviceRGB)
    else {
      throw RewindError.storageError("Failed to address test pixel buffer")
    }

    let bytesPerRow = CVPixelBufferGetBytesPerRow(pixelBuffer)
    let blue = UInt8(rgb.blueComponent * 255)
    let green = UInt8(rgb.greenComponent * 255)
    let red = UInt8(rgb.redComponent * 255)
    let pixels = base.assumingMemoryBound(to: UInt8.self)
    for y in 0..<height {
      for x in 0..<width {
        let index = y * bytesPerRow + x * 4
        pixels[index] = blue
        pixels[index + 1] = green
        pixels[index + 2] = red
        pixels[index + 3] = 255
      }
    }
    return pixelBuffer
  }
}

private final class CursorTestWriterBox: @unchecked Sendable {
  let writer: AVAssetWriter
  init(_ writer: AVAssetWriter) { self.writer = writer }
}
