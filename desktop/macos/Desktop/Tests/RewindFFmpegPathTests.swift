import Foundation
import XCTest

@testable import Omi_Computer

final class RewindFFmpegPathTests: XCTestCase {
  func testStructuredSwiftPMBundleTakesPriorityOverFlatBundle() throws {
    let app = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".app")
    defer { try? FileManager.default.removeItem(at: app) }
    let structured = app.appendingPathComponent(
      "Contents/Resources/Omi Computer_Omi Computer.bundle/Contents/Resources/ffmpeg")
    let flat = app.appendingPathComponent("Contents/Resources/Omi Computer_Omi Computer.bundle/ffmpeg")
    try FileManager.default.createDirectory(
      at: structured.deletingLastPathComponent(), withIntermediateDirectories: true)
    FileManager.default.createFile(atPath: structured.path, contents: Data())
    FileManager.default.createFile(atPath: flat.path, contents: Data())

    XCTAssertEqual(RewindStorage.findFFmpegPath(in: app, fallbackPaths: []), structured.path)
  }

  func testFlatSwiftPMBundleRemainsSupported() throws {
    let app = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".app")
    defer { try? FileManager.default.removeItem(at: app) }
    let flat = app.appendingPathComponent("Contents/Resources/Omi Computer_Omi Computer.bundle/ffmpeg")
    try FileManager.default.createDirectory(at: flat.deletingLastPathComponent(), withIntermediateDirectories: true)
    FileManager.default.createFile(atPath: flat.path, contents: Data())

    XCTAssertEqual(RewindStorage.findFFmpegPath(in: app, fallbackPaths: []), flat.path)
  }

  func testAssembledReleaseBundleResolvesBundledFFmpeg() throws {
    guard let appPath = ProcessInfo.processInfo.environment["OMI_FFMPEG_PROOF_APP"] else {
      throw XCTSkip("Set OMI_FFMPEG_PROOF_APP for a locally assembled release bundle")
    }
    let app = URL(fileURLWithPath: appPath)
    let ffmpeg = app.appendingPathComponent(
      "Contents/Resources/Omi Computer_Omi Computer.bundle/Contents/Resources/ffmpeg")
    XCTAssertTrue(FileManager.default.isExecutableFile(atPath: ffmpeg.path))
    XCTAssertEqual(RewindStorage.findFFmpegPath(in: app, fallbackPaths: []), ffmpeg.path)
  }
}
