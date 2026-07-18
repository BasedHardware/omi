@preconcurrency import AppKit
import CoreGraphics
import Foundation

/// Non-production Rewind artifact exercise used by the qualification harness.
///
/// It deliberately uses solid-color synthetic frames only. The normal frame is
/// admitted through the same Rewind privacy setting the capture loop consults,
/// then travels through the real indexer, HEVC encoder, SQLite store, and video
/// frame reader. A protected frame proves that the admission boundary blocks an
/// artifact before any persistence work begins. The database close/reopen step
/// models the recovery path used after local storage failures.
@MainActor
enum RewindArtifactGauntlet {
  struct Result: Equatable {
    let protectedFrameBlocked: Bool
    let protectedRowCount: Int
    let persistedFrameCount: Int
    let readbackColors: [String]
    let databaseReopened: Bool
    let rowsSurvivedReopen: Bool
    let cleanupRemovedRows: Int
    let artifactFileRemoved: Bool
  }

  private static let frameWidth = 96
  private static let frameHeight = 64

  static func run(nonce: String = UUID().uuidString) async throws -> Result {
    guard await VideoChunkEncoder.shared.currentChunkPath == nil else {
      throw RewindError.storageError("Rewind artifact gauntlet requires an idle video encoder")
    }

    try await RewindIndexer.shared.initialize()
    guard await VideoChunkEncoder.shared.currentChunkPath == nil else {
      throw RewindError.storageError("Rewind artifact gauntlet found an active video encoder after initialization")
    }

    let normalApp = "Omi Rewind Gauntlet \(nonce)"
    let protectedApp = "Omi Rewind Gauntlet Protected \(nonce)"
    let windowTitle = "synthetic artifact \(nonce)"
    let settings = RewindSettings.shared
    let originalExcludedApps = settings.excludedApps
    settings.includeApp(normalApp)
    settings.excludeApp(protectedApp)
    defer { settings.excludedApps = originalExcludedApps }

    var chunkPath: String?
    do {
      let protectedRowsBefore = try await rows(forApp: protectedApp, windowTitle: windowTitle)
      let protectedFrameBlocked =
        !(await admitSyntheticFrame(
          cgImage: try syntheticFrame(color: .systemBlue),
          appName: protectedApp,
          windowTitle: windowTitle,
          captureTime: Date()
        ))
      if !protectedFrameBlocked {
        throw RewindError.storageError("Rewind artifact gauntlet could not enable its protected-frame privacy gate")
      }

      // The protected frame reached the admission boundary but must never reach
      // either the indexer or local persistence.
      let protectedRowsAfter = try await rows(forApp: protectedApp, windowTitle: windowTitle)
      guard protectedRowsBefore.isEmpty, protectedRowsAfter.isEmpty else {
        throw RewindError.storageError("Protected Rewind frame unexpectedly reached local storage")
      }

      let startedAt = Date()
      let firstFrameAdmitted = await admitSyntheticFrame(
        cgImage: try syntheticFrame(color: .systemRed),
        appName: normalApp,
        windowTitle: windowTitle,
        captureTime: startedAt
      )
      let secondFrameAdmitted = await admitSyntheticFrame(
        cgImage: try syntheticFrame(color: .systemGreen),
        appName: normalApp,
        windowTitle: windowTitle,
        captureTime: startedAt.addingTimeInterval(1)
      )
      guard firstFrameAdmitted, secondFrameAdmitted else {
        throw RewindError.storageError("Rewind artifact gauntlet normal frame was unexpectedly privacy excluded")
      }

      let persistedRows = try await rows(forApp: normalApp, windowTitle: windowTitle)
      guard persistedRows.count == 2,
        let storedChunkPath = persistedRows.first?.videoChunkPath,
        persistedRows.allSatisfy({ $0.videoChunkPath == storedChunkPath })
      else {
        throw RewindError.storageError("Rewind artifact gauntlet did not persist two frames in one video chunk")
      }
      chunkPath = storedChunkPath

      let flush = try await VideoChunkEncoder.shared.flushCurrentChunk()
      guard let flush, flush.videoChunkPath == storedChunkPath, flush.frames.count == persistedRows.count else {
        throw RewindError.storageError("Rewind artifact gauntlet could not finalize its video chunk")
      }

      let videosDirectory = try await videosDirectory()
      let artifactURL = videosDirectory.appendingPathComponent(storedChunkPath)
      guard FileManager.default.fileExists(atPath: artifactURL.path) else {
        throw RewindError.storageError("Rewind artifact gauntlet finalized video file is missing")
      }

      var readbackColors: [String] = []
      for row in persistedRows.sorted(by: { ($0.frameOffset ?? -1) < ($1.frameOffset ?? -1) }) {
        guard let frameOffset = row.frameOffset else {
          throw RewindError.storageError("Rewind artifact gauntlet persisted a row without a frame offset")
        }
        let centerPixel = try await RewindStorage.shared.videoFrameCenterPixel(
          videoPath: storedChunkPath,
          frameOffset: frameOffset
        )
        readbackColors.append(dominantColor(in: centerPixel))
      }
      guard readbackColors == ["red", "green"] else {
        throw RewindError.storageError("Rewind artifact gauntlet video readback did not preserve frame order")
      }

      await RewindDatabase.shared.close()
      guard !(await RewindDatabase.shared.isInitialized) else {
        throw RewindError.storageError("Rewind artifact gauntlet could not close the database for recovery")
      }

      try await RewindIndexer.shared.initialize()
      let databaseReopened = await RewindDatabase.shared.isInitialized
      let rowsAfterReopen = try await rows(forApp: normalApp, windowTitle: windowTitle)
      let rowsSurvivedReopen =
        databaseReopened && rowsAfterReopen.count == persistedRows.count
        && rowsAfterReopen.allSatisfy { $0.videoChunkPath == storedChunkPath }
      guard rowsSurvivedReopen else {
        throw RewindError.storageError("Rewind artifact gauntlet rows did not survive database reopen")
      }

      let cleanupRemovedRows = try await RewindDatabase.shared.deleteScreenshotsFromVideoChunk(
        videoChunkPath: storedChunkPath)
      try FileManager.default.removeItem(at: artifactURL)
      let artifactFileRemoved = !FileManager.default.fileExists(atPath: artifactURL.path)

      return Result(
        protectedFrameBlocked: protectedFrameBlocked,
        protectedRowCount: protectedRowsAfter.count,
        persistedFrameCount: persistedRows.count,
        readbackColors: readbackColors,
        databaseReopened: databaseReopened,
        rowsSurvivedReopen: rowsSurvivedReopen,
        cleanupRemovedRows: cleanupRemovedRows,
        artifactFileRemoved: artifactFileRemoved
      )
    } catch {
      if !(await RewindDatabase.shared.isInitialized) {
        try? await RewindIndexer.shared.initialize()
      }
      if let chunkPath {
        await removeArtifact(chunkPath)
      }
      throw error
    }
  }

  private static func rows(forApp appName: String, windowTitle: String) async throws -> [Screenshot] {
    let allRows = try await RewindDatabase.shared.getRecentScreenshots(limit: 200)
    return allRows.filter { $0.appName == appName && $0.windowTitle == windowTitle }
  }

  private static func videosDirectory() async throws -> URL {
    guard let directory = await RewindStorage.shared.getVideosDirectory() else {
      throw RewindError.storageError("Rewind artifact gauntlet video storage is unavailable")
    }
    return directory
  }

  /// Mirrors the capture-loop admission point: privacy is checked immediately
  /// before the frame crosses into RewindIndexer. The gauntlet keeps the image
  /// entirely in memory when that check rejects it.
  private static func admitSyntheticFrame(
    cgImage: CGImage,
    appName: String,
    windowTitle: String,
    captureTime: Date
  ) async -> Bool {
    guard !RewindSettings.shared.isAppExcluded(appName) else { return false }
    await RewindIndexer.shared.processFrame(
      cgImage: cgImage,
      appName: appName,
      windowTitle: windowTitle,
      captureTime: captureTime
    )
    return true
  }

  private static func removeArtifact(_ chunkPath: String) async {
    _ = try? await RewindDatabase.shared.deleteScreenshotsFromVideoChunk(videoChunkPath: chunkPath)
    guard let directory = try? await videosDirectory() else { return }
    try? FileManager.default.removeItem(at: directory.appendingPathComponent(chunkPath))
  }

  private static func syntheticFrame(color: NSColor) throws -> CGImage {
    guard
      let context = CGContext(
        data: nil,
        width: frameWidth,
        height: frameHeight,
        bitsPerComponent: 8,
        bytesPerRow: frameWidth * 4,
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
      )
    else {
      throw RewindError.storageError("Rewind artifact gauntlet could not create a synthetic frame")
    }
    context.setFillColor(color.cgColor)
    context.fill(CGRect(x: 0, y: 0, width: frameWidth, height: frameHeight))
    guard let image = context.makeImage() else {
      throw RewindError.storageError("Rewind artifact gauntlet could not render a synthetic frame")
    }
    return image
  }

  private static func dominantColor(in centerPixel: RewindVideoFrameCenterPixel) -> String {
    let red = Double(centerPixel.red)
    let green = Double(centerPixel.green)
    let blue = Double(centerPixel.blue)
    if red > green * 1.5, red > blue * 1.5 { return "red" }
    if green > red * 1.5, green > blue * 1.5 { return "green" }
    return "other"
  }
}

@MainActor
extension DesktopAutomationActionRegistry {
  func registerRewindArtifactRecoveryGauntlet() {
    register(
      name: "rewind_artifact_recovery_gauntlet",
      summary:
        "Write safe synthetic Rewind frames through encoder, SQLite, and video readback; prove privacy exclusion and database reopen. Non-prod only.",
      category: "test",
      surfaces: ["rewind"],
      safety: "local_artifact",
      sideEffects: [
        "writes and removes a synthetic local video artifact", "closes and reopens the local Rewind database",
      ],
      examples: ["./scripts/omi-ctl action rewind_artifact_recovery_gauntlet"]
    ) { _ in
      guard AppBuild.isNonProduction else {
        return ["error": "rewind_artifact_recovery_gauntlet is disabled on production bundles"]
      }
      let result = try await RewindArtifactGauntlet.run()
      return [
        "protected_frame_blocked": result.protectedFrameBlocked ? "true" : "false",
        "protected_row_count": "\(result.protectedRowCount)",
        "persisted_frame_count": "\(result.persistedFrameCount)",
        "readback_colors": result.readbackColors.joined(separator: ","),
        "database_reopened": result.databaseReopened ? "true" : "false",
        "rows_survived_reopen": result.rowsSurvivedReopen ? "true" : "false",
        "cleanup_removed_rows": "\(result.cleanupRemovedRows)",
        "artifact_file_removed": result.artifactFileRemoved ? "true" : "false",
      ]
    }
  }
}
