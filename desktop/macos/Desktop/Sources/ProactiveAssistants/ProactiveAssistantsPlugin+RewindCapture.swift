import CoreGraphics
import Foundation

extension ProactiveAssistantsPlugin {
  func enqueueRewindFrame(
    cgImage: CGImage,
    appName: String,
    windowTitle: String?,
    captureTime: Date,
    exclusionSnapshot: RewindCaptureExclusionSnapshot
  ) {
    Task { [weak self] in
      await RewindIndexer.shared.processFrame(
        cgImage: cgImage,
        appName: appName,
        windowTitle: windowTitle,
        captureTime: captureTime,
        exclusionSnapshot: exclusionSnapshot)
      await MainActor.run {
        self?.finishRewindFrameProcessing()
      }
    }
  }

  func enqueueRewindFrame(
    _ frame: CapturedFrame,
    exclusionSnapshot: RewindCaptureExclusionSnapshot
  ) {
    Task { [weak self] in
      await RewindIndexer.shared.processFrame(frame, exclusionSnapshot: exclusionSnapshot)
      await MainActor.run {
        self?.finishRewindFrameProcessing()
      }
    }
  }
}
