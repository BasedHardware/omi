import AppKit

class ScreenCaptureManager {
    /// Returns a CGImage for the screen under the mouse cursor.
    /// Used by PushToTalkManager for context capture and ScreenContextPipeline.
    static func captureScreenImage() -> CGImage? {
        guard CGPreflightScreenCaptureAccess() else {
            log("ScreenCaptureManager: Screen recording permission not granted, skipping capture")
            return nil
        }

        let displayID = displayIDUnderMouse()
        guard let image = CGDisplayCreateImage(displayID) else {
            log("ScreenCaptureManager: Could not capture screen (display \(displayID))")
            return nil
        }

        return image
    }

    /// Returns a lightweight JPEG thumbnail of the screen (max 512px, quality 0.4).
    /// Used as a visual fallback for screen-aware queries. No WebP dependency.
    static func captureThumbnail() -> Data? {
        guard let image = captureScreenImage() else { return nil }
        return encodeJPEGThumbnail(image)
    }

    /// Encode a CGImage as a lightweight JPEG thumbnail (max 512px on longest side).
    private static func encodeJPEGThumbnail(_ image: CGImage) -> Data? {
        let maxDimension: CGFloat = 512
        let width = CGFloat(image.width)
        let height = CGFloat(image.height)

        let scale = min(maxDimension / max(width, height), 1.0)
        let newWidth = Int(width * scale)
        let newHeight = Int(height * scale)

        guard let ctx = CGContext(
            data: nil,
            width: newWidth,
            height: newHeight,
            bitsPerComponent: 8,
            bytesPerRow: 0,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ) else { return nil }

        ctx.interpolationQuality = .high
        ctx.draw(image, in: CGRect(x: 0, y: 0, width: newWidth, height: newHeight))

        guard let resizedImage = ctx.makeImage() else { return nil }

        let data = NSMutableData()
        guard let dest = CGImageDestinationCreateWithData(
            data as CFMutableData, "public.jpeg" as CFString, 1, nil)
        else { return nil }

        let options: [CFString: Any] = [kCGImageDestinationLossyCompressionQuality: 0.4]
        CGImageDestinationAddImage(dest, resizedImage, options as CFDictionary)
        guard CGImageDestinationFinalize(dest) else { return nil }

        return data as Data
    }

    private static func displayIDUnderMouse() -> CGDirectDisplayID {
        let mouseLocation = NSEvent.mouseLocation
        for screen in NSScreen.screens {
            if screen.frame.contains(mouseLocation),
               let screenNumber = screen.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? CGDirectDisplayID {
                return screenNumber
            }
        }
        return CGMainDisplayID()
    }

    /// Lightweight screen capture that writes a JPEG thumbnail to disk for tool executors.
    static func captureScreen() -> URL? {
        guard let data = captureThumbnail() else { return nil }

        let fileManager = FileManager.default
        guard let documentsDirectory = fileManager.urls(for: .documentDirectory, in: .userDomainMask).first else {
            return nil
        }
        let screenshotsDirectory = documentsDirectory
            .appendingPathComponent("Omi")
            .appendingPathComponent("Screenshots")
        try? fileManager.createDirectory(at: screenshotsDirectory, withIntermediateDirectories: true, attributes: nil)

        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd_HH-mm-ss"
        let timestamp = formatter.string(from: Date())
        let fileURL = screenshotsDirectory.appendingPathComponent("screenshot-\(timestamp).jpg")

        do {
            try data.write(to: fileURL)
            return fileURL
        } catch {
            log("ScreenCaptureManager: Could not save screenshot: \(error)")
            return nil
        }
    }
}
