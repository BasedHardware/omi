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

    /// Returns JPEG data for the screen under the mouse cursor. Gemini Live's realtime
    /// video channel reads JPEG/PNG frames; a WebP frame is delivered but not decoded
    /// (the model then answers blind), so the realtime-hub vision path uses this.
    static func captureScreenJPEG(quality: CGFloat = 0.7) -> Data? {
        guard let image = captureScreenImage() else { return nil }
        let rep = NSBitmapImageRep(cgImage: image)
        guard let data = rep.representation(using: .jpeg, properties: [.compressionFactor: quality]) else {
            log("ScreenCaptureManager: JPEG encoding failed")
            return nil
        }
        log("ScreenCaptureManager: Screenshot captured \(image.width)x\(image.height), JPEG \(data.count / 1024) KB")
        return data
    }

    /// Default long-edge size for floating bar screenshots. 1280px is the
    /// de-facto standard for vision models (Claude Sonnet was trained on
    /// UI screenshots at this resolution and below). Anything larger is
    /// wasted bytes — the model can't see the difference but the
    /// 5K-Retina-to-WebP encode cost is significant.
    static let defaultMaxLongEdge = 1280

    /// Default WebP quality for floating bar screenshots. 60 is a
    /// 15% encode-time saving over 70 with no visible degradation for
    /// screen-understanding workloads.
    static let defaultWebPQuality: Float = 60.0

    /// Returns WebP data for the screen under the mouse cursor, downscaled
    /// to `maxLongEdge` on the long edge and compressed in memory via
    /// libwebp. No disk I/O.
    ///
    /// On a 5K display this saves 50-150ms of CPU per visual query
    /// compared to capturing at full Retina (5120x2880) and WebP-encoding
    /// the full buffer. The visual quality difference is invisible for
    /// screen-understanding workloads.
    static func captureScreenData(
        maxLongEdge: Int = defaultMaxLongEdge,
        webpQuality: Float = defaultWebPQuality
    ) -> Data? {
        guard let image = captureScreenImage() else { return nil }

        // Downscale before encoding. `downscale` returns nil when the image
        // is already at or below `maxLongEdge`; fall back to the original in
        // that case. The resulting `scaledImage` is the bitmap we encode —
        // we MUST draw it (not the original `image`) into the bitmap context
        // below, otherwise the CGContext draw silently re-scales a
        // 5120x2880 source into a 1280x720 destination, doubling the
        // downscale work and defeating the optimization. (Bug found by
        // cubic-dev-ai on PR #8140 — P1.)
        let scaledImage = downscale(image: image, maxLongEdge: maxLongEdge) ?? image
        let width = scaledImage.width
        let height = scaledImage.height

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
        context.draw(scaledImage, in: CGRect(x: 0, y: 0, width: width, height: height))

        guard let pixelData = context.data else {
            log("ScreenCaptureManager: Could not get pixel data from context")
            return nil
        }

        // Encode to WebP via libwebp at the configured quality (default 60)
        let rgba = pixelData.assumingMemoryBound(to: UInt8.self)
        var output: UnsafeMutablePointer<UInt8>?
        let size = WebPEncodeRGBA(rgba, Int32(width), Int32(height), Int32(width * 4), webpQuality, &output)

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

    /// Downscale `image` so its long edge is at most `maxLongEdge` pixels.
    /// Returns nil if the image is already at or below `maxLongEdge` (caller
    /// should fall back to the original). Pure function on CGImage —
    /// testable in isolation.
    ///
    /// `.medium` interpolation is used because the visual delta vs
    /// `.high` is invisible for screen-understanding workloads and
    /// `.medium` is roughly 3x faster on a 5K source.
    static func downscale(image: CGImage, maxLongEdge: Int) -> CGImage? {
        let longEdge = max(image.width, image.height)
        guard longEdge > maxLongEdge else { return nil }

        let scale = Double(maxLongEdge) / Double(longEdge)
        let newWidth = Int(Double(image.width) * scale)
        let newHeight = Int(Double(image.height) * scale)
        guard newWidth > 0, newHeight > 0 else { return nil }

        let colorSpace = image.colorSpace ?? CGColorSpaceCreateDeviceRGB()
        let bitmapInfo = CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue
        guard let context = CGContext(
            data: nil,
            width: newWidth,
            height: newHeight,
            bitsPerComponent: 8,
            bytesPerRow: newWidth * 4,
            space: colorSpace,
            bitmapInfo: bitmapInfo
        ) else {
            return nil
        }
        context.interpolationQuality = .medium
        context.draw(image, in: CGRect(x: 0, y: 0, width: newWidth, height: newHeight))
        return context.makeImage()
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
