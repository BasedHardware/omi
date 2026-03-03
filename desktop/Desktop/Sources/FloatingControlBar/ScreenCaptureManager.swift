import AppKit
import ImageIO

class ScreenCaptureManager {
    static func captureScreen() -> URL? {
        let fileManager = FileManager.default
        guard let documentsDirectory = fileManager.urls(for: .documentDirectory, in: .userDomainMask).first else {
            log("ScreenCaptureManager: Could not find documents directory")
            return nil
        }
        let screenshotsDirectory = documentsDirectory
            .appendingPathComponent("Omi")
            .appendingPathComponent("Screenshots")

        do {
            try fileManager.createDirectory(at: screenshotsDirectory, withIntermediateDirectories: true, attributes: nil)
        } catch {
            log("ScreenCaptureManager: Error creating directory: \(error)")
            return nil
        }

        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd_HH-mm-ss"
        let timestamp = formatter.string(from: Date())
        let fileName = "screenshot-\(timestamp).jpg"
        let fileURL = screenshotsDirectory.appendingPathComponent(fileName)

        guard let image = CGDisplayCreateImage(CGMainDisplayID()) else {
            log("ScreenCaptureManager: Could not capture screen")
            return nil
        }

        guard let destination = CGImageDestinationCreateWithURL(fileURL as CFURL, "public.jpeg" as CFString, 1, nil) else {
            log("ScreenCaptureManager: Could not create image destination")
            return nil
        }

        // JPEG at 0.75 quality keeps file size ~400–800 KB vs 5+ MB for PNG,
        // staying well under the Claude API's 5 MB base64 limit.
        let options: [CFString: Any] = [kCGImageDestinationLossyCompressionQuality: 0.75]
        CGImageDestinationAddImage(destination, image, options as CFDictionary)

        if !CGImageDestinationFinalize(destination) {
            log("ScreenCaptureManager: Could not save image")
            return nil
        }

        log("ScreenCaptureManager: Screenshot saved to \(fileURL.path) (\(image.width)×\(image.height))")
        return fileURL
    }
}
