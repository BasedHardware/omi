import CoreGraphics
import Foundation
import ImageIO

struct CapturedFrame: @unchecked Sendable {
  var jpegData: Data { lazyData.value }

  let appName: String
  let windowTitle: String?
  let frameNumber: Int
  let captureTime: Date
  let capturedUptime: TimeInterval
  let screenshotId: Int64?
  let taskBinding: ScreenTaskFrameBinding?

  private let lazyData: LazyJPEGData

  init(
    jpegData: Data,
    appName: String,
    windowTitle: String? = nil,
    frameNumber: Int,
    captureTime: Date = Date(),
    capturedUptime: TimeInterval = ProcessInfo.processInfo.systemUptime,
    screenshotId: Int64? = nil,
    taskBinding: ScreenTaskFrameBinding? = nil
  ) {
    self.lazyData = LazyJPEGData(jpegData: jpegData)
    self.appName = appName
    self.windowTitle = windowTitle
    self.frameNumber = frameNumber
    self.captureTime = captureTime
    self.capturedUptime = capturedUptime
    self.screenshotId = screenshotId
    self.taskBinding = taskBinding
  }

  init(
    cgImage: CGImage,
    jpegQuality: CGFloat,
    appName: String,
    windowTitle: String? = nil,
    frameNumber: Int,
    captureTime: Date = Date(),
    capturedUptime: TimeInterval = ProcessInfo.processInfo.systemUptime,
    screenshotId: Int64? = nil,
    taskBinding: ScreenTaskFrameBinding? = nil
  ) {
    self.lazyData = LazyJPEGData(cgImage: cgImage, quality: jpegQuality)
    self.appName = appName
    self.windowTitle = windowTitle
    self.frameNumber = frameNumber
    self.captureTime = captureTime
    self.capturedUptime = capturedUptime
    self.screenshotId = screenshotId
    self.taskBinding = taskBinding
  }

  private final class LazyJPEGData: @unchecked Sendable {
    private var cgImage: CGImage?
    private let quality: CGFloat
    private var cached: Data?
    private let lock = NSLock()

    init(jpegData: Data) {
      self.cached = jpegData
      self.quality = 0
    }

    init(cgImage: CGImage, quality: CGFloat) {
      self.cgImage = cgImage
      self.quality = quality
    }

    var value: Data {
      lock.lock()
      defer { lock.unlock() }
      if let cached { return cached }
      guard let cgImage else { return Data() }
      let data = Self.encode(cgImage: cgImage, quality: quality)
      self.cgImage = nil
      self.cached = data
      return data
    }

    private static func encode(cgImage: CGImage, quality: CGFloat) -> Data {
      autoreleasepool {
        let data = NSMutableData()
        guard
          let destination = CGImageDestinationCreateWithData(
            data as CFMutableData, "public.jpeg" as CFString, 1, nil)
        else {
          return Data()
        }
        let options: [CFString: Any] = [kCGImageDestinationLossyCompressionQuality: quality]
        CGImageDestinationAddImage(destination, cgImage, options as CFDictionary)
        guard CGImageDestinationFinalize(destination) else { return Data() }
        return data as Data
      }
    }
  }
}
