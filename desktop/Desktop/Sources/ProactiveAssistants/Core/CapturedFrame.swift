import Foundation

/// Represents a captured screen frame that can be analyzed by assistants
struct CapturedFrame {
    /// JPEG-encoded image data
    let jpegData: Data

    /// Name of the active application
    let appName: String

    /// Title of the active window (if available)
    let windowTitle: String?

    /// Sequential frame number for ordering
    let frameNumber: Int

    /// Timestamp when the frame was captured
    let captureTime: Date

    /// Optional reference to the screenshot in the Rewind database
    /// Used to link proactive extractions back to their source screenshot
    let screenshotId: Int64?

    init(
        jpegData: Data,
        appName: String,
        windowTitle: String? = nil,
        frameNumber: Int,
        captureTime: Date = Date(),
        screenshotId: Int64? = nil
    ) {
        self.jpegData = jpegData
        self.appName = appName
        self.windowTitle = windowTitle
        self.frameNumber = frameNumber
        self.captureTime = captureTime
        self.screenshotId = screenshotId
    }
}
