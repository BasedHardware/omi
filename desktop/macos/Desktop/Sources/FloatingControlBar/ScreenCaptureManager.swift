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

    /// Returns WebP data for the screen under the mouse cursor at full Retina
    /// resolution, compressed in memory via libwebp. No disk I/O.
    static func captureScreenData() -> Data? {
        guard let image = captureScreenImage() else { return nil }
        guard let data = encodeWebP(image) else { return nil }
        log("ScreenCaptureManager: Screenshot captured \(image.width)x\(image.height), WebP \(data.count / 1024) KB")
        return data
    }

    /// Encode a CGImage to WebP (quality 70) via libwebp, in memory.
    private static func encodeWebP(_ image: CGImage) -> Data? {
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
        return data
    }

    // MARK: - Detail tiles (vision legibility)

    /// A native-resolution sub-region of a screenshot, sized so a vision model
    /// receives it without provider-side downscaling.
    struct DetailTile: Equatable {
        let label: String
        let rect: CGRect
    }

    /// Vision APIs downscale images whose long edge exceeds ~1568 px. A full-Retina
    /// screenshot (5+ MP) squeezed to ~1.15 MP makes dense UI text — product titles,
    /// prices, labels — illegible, so the model guesses instead of reading (e.g.
    /// conflating two similar listings). Tiles at or under this edge arrive at
    /// native sharpness.
    static let maxVisionTileLongEdge = 1568

    /// Grid-partition a width×height image into native-resolution tiles whose long
    /// edge stays ≤ `maxLongEdge`. The tiles exactly cover the image with no gaps or
    /// overlaps. Returns [] when the full image already fits (no tiling needed).
    /// Pure math — no capture, no I/O — so it is unit-testable.
    static func detailTileRects(
        width: Int, height: Int, maxLongEdge: Int = ScreenCaptureManager.maxVisionTileLongEdge
    ) -> [DetailTile] {
        guard width > 0, height > 0, maxLongEdge > 0 else { return [] }
        guard max(width, height) > maxLongEdge else { return [] }

        let cols = (width + maxLongEdge - 1) / maxLongEdge
        let rows = (height + maxLongEdge - 1) / maxLongEdge

        var tiles: [DetailTile] = []
        for row in 0..<rows {
            let y0 = row * height / rows
            let y1 = (row + 1) * height / rows
            for col in 0..<cols {
                let x0 = col * width / cols
                let x1 = (col + 1) * width / cols
                tiles.append(
                    DetailTile(
                        label: tileLabel(row: row, col: col, rows: rows, cols: cols),
                        rect: CGRect(x: x0, y: y0, width: x1 - x0, height: y1 - y0)
                    ))
            }
        }
        return tiles
    }

    /// Human-readable position label ("top-left", "right", "r2c3") the model can
    /// map to what the user described on screen.
    static func tileLabel(row: Int, col: Int, rows: Int, cols: Int) -> String {
        if rows <= 2 && cols <= 2 {
            let vertical = rows == 2 ? (row == 0 ? "top" : "bottom") : nil
            let horizontal = cols == 2 ? (col == 0 ? "left" : "right") : nil
            switch (vertical, horizontal) {
            case let (v?, h?): return "\(v)-\(h)"
            case let (v?, nil): return v
            case let (nil, h?): return h
            default: return "full"
            }
        }
        return "r\(row + 1)c\(col + 1)"
    }

    /// Result of a chat-tool screen capture: the full-screen file plus
    /// native-resolution detail tiles for large (Retina) displays.
    struct ChatScreenshotCapture {
        let fullImageURL: URL
        let tiles: [(label: String, rect: CGRect, url: URL)]
    }

    /// Capture the screen for the chat `capture_screen` tool: writes the full frame
    /// plus native-resolution detail tiles so the model can re-read small text
    /// (titles, prices, labels) at legible sharpness. Tiles are best-effort — the
    /// full-screen file is the contract.
    static func captureScreenWithDetailTiles() -> ChatScreenshotCapture? {
        guard let image = captureScreenImage() else { return nil }
        guard let directory = screenshotsDirectory() else { return nil }

        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd_HH-mm-ss"
        let timestamp = formatter.string(from: Date())

        guard let fullData = encodeWebP(image) else { return nil }
        let fullURL = directory.appendingPathComponent("screenshot-\(timestamp).webp")
        do {
            try fullData.write(to: fullURL)
        } catch {
            log("ScreenCaptureManager: Could not save screenshot: \(error)")
            return nil
        }
        log("ScreenCaptureManager: Screenshot captured \(image.width)x\(image.height), WebP \(fullData.count / 1024) KB")

        var tiles: [(label: String, rect: CGRect, url: URL)] = []
        for tile in detailTileRects(width: image.width, height: image.height) {
            guard let cropped = image.cropping(to: tile.rect), let tileData = encodeWebP(cropped) else {
                log("ScreenCaptureManager: Skipping detail tile \(tile.label) (crop/encode failed)")
                continue
            }
            let tileURL = directory.appendingPathComponent("screenshot-\(timestamp)-\(tile.label).webp")
            do {
                try tileData.write(to: tileURL)
                tiles.append((label: tile.label, rect: tile.rect, url: tileURL))
            } catch {
                log("ScreenCaptureManager: Could not save detail tile \(tile.label): \(error)")
            }
        }
        return ChatScreenshotCapture(fullImageURL: fullURL, tiles: tiles)
    }

    private static func screenshotsDirectory() -> URL? {
        let fileManager = FileManager.default
        guard let documentsDirectory = fileManager.urls(for: .documentDirectory, in: .userDomainMask).first else {
            return nil
        }
        let directory = documentsDirectory
            .appendingPathComponent("Omi")
            .appendingPathComponent("Screenshots")
        try? fileManager.createDirectory(at: directory, withIntermediateDirectories: true, attributes: nil)
        return directory
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
        guard let directory = screenshotsDirectory() else { return nil }

        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd_HH-mm-ss"
        let timestamp = formatter.string(from: Date())
        let fileURL = directory.appendingPathComponent("screenshot-\(timestamp).webp")

        do {
            try data.write(to: fileURL)
            return fileURL
        } catch {
            log("ScreenCaptureManager: Could not save screenshot: \(error)")
            return nil
        }
    }
}
