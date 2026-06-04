import AppKit
import CWebP

class ScreenCaptureManager {
    /// Longest-edge cap for screenshots sent to the model. Claude downscales
    /// vision input to ~1568px on its longest side anyway, so capturing/encoding
    /// at native Retina resolution (often 3-5K) just wastes encode time, upload
    /// bandwidth, vision tokens (cost), and server-side processing — with zero
    /// quality gain. Cap here so every floating-bar query stays cheap and fast.
    static let maxLongestEdge = 1568

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
        let startedAt = CFAbsoluteTimeGetCurrent()
        guard let image = captureScreenImage() else { return nil }

        let nativeWidth = image.width
        let nativeHeight = image.height

        // Downscale so the longest edge is at most `maxLongestEdge`. Drawing the
        // CGImage into a smaller context scales it for us; for screens already
        // below the cap this is a no-op (scale == 1).
        let scale = min(1.0, Double(maxLongestEdge) / Double(max(nativeWidth, nativeHeight)))
        let width = max(1, Int((Double(nativeWidth) * scale).rounded()))
        let height = max(1, Int((Double(nativeHeight) * scale).rounded()))

        // Render CGImage into an RGBA bitmap context (at the downscaled size)
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
        context.interpolationQuality = .medium
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

        let elapsedMs = Int((CFAbsoluteTimeGetCurrent() - startedAt) * 1000)
        log("ScreenCaptureManager: captured \(nativeWidth)x\(nativeHeight) → \(width)x\(height), WebP \(data.count / 1024) KB in \(elapsedMs)ms")
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
