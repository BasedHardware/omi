import AppKit
import CWebP

class ScreenCaptureManager {
    /// Returns a CGImage for the screen under the mouse cursor.
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

    /// Returns WebP data for the screen under the mouse cursor at full Retina
    /// resolution, compressed in memory via libwebp. No disk I/O.
    static func captureScreenData() -> Data? {
        guard let image = captureScreenImage() else { return nil }

        let width = image.width
        let height = image.height

        // Render CGImage into an RGBA bitmap context
        guard let context = CGContext(
            data: nil,
            width: width,
            height: height,
            bitsPerComponent: 8,
            bytesPerRow: width * 4,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue
        ) else {
            log("ScreenCaptureManager: Could not create bitmap context")
            return nil
        }
        context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))

        guard let pixelData = context.data else {
            log("ScreenCaptureManager: Could not get pixel data from context")
            return nil
        }

        // Encode to WebP via libwebp at quality 70
        let rgba = pixelData.assumingMemoryBound(to: UInt8.self)
        var output: UnsafeMutablePointer<UInt8>?
        let size = WebPEncodeRGBA(rgba, Int32(width), Int32(height), Int32(width * 4), 70.0, &output)

        guard size > 0, let webpPtr = output else {
            log("ScreenCaptureManager: WebP encoding failed")
            return nil
        }

        let data = Data(bytes: webpPtr, count: size)
        WebPFree(webpPtr)

        log("ScreenCaptureManager: Screenshot captured \(width)x\(height), WebP \(data.count / 1024) KB")
        return data
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

    /// Legacy file-based capture (kept for callers that need a URL).
    static func captureScreen() -> URL? {
        guard let data = captureScreenData() else { return nil }

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
        let fileURL = screenshotsDirectory.appendingPathComponent("screenshot-\(timestamp).webp")

        do {
            try data.write(to: fileURL)
            return fileURL
        } catch {
            log("ScreenCaptureManager: Could not save screenshot: \(error)")
            return nil
        }
    }
}
