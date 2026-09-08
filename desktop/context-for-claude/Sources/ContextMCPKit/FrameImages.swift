import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers

/// Turning a stored screen capture into something a model can actually look at.
///
/// Capture writes HEIC at up to 1600 px and as low as quality 0.10, because for two years nothing
/// decoded those files: every tool returned text and the uploader sent text. `look` decodes them,
/// and that changes what the stored picture has to survive — a tile tuned purely for bytes-on-disk
/// is now also the ceiling on what Claude can read, so anyone re-tuning `CaptureQuality` is tuning
/// legibility too.
///
/// Two conversions happen here and both are mandatory:
///
/// - **HEIC to JPEG.** No Claude surface accepts `image/heic`. A frame handed over in its stored
///   format is not a slightly worse image, it is a rejected request.
/// - **Down to a size that fits in a reply.** A tool result is inlined into the conversation, so
///   the budget is small and shared with the prose. `longestSide` is Claude's own no-loss ceiling:
///   larger images are scaled down before the model sees them anyway, so the bytes above it buy
///   nothing and cost the reply.
enum FrameImages {
    /// The longest edge, in pixels, of the image actually sent.
    ///
    /// 1568 is where Claude stops gaining detail — an image larger than this is resized down before
    /// it reaches the model regardless — and capture already tops out at 1600, so in practice this
    /// is a trim rather than a downscale. Below ~1000 px, UI text in a full-screen capture stops
    /// being reliably readable, which is the failure mode that matters for the tool's main job.
    static let longestSide = 1568

    /// JPEG quality for the sent image. Above the stored HEIC's own fidelity on purpose: re-encoding
    /// lossy pixels at low quality compounds the two artefact sets, and text is what suffers first.
    static let quality: CGFloat = 0.72

    /// The most encoded bytes one image may spend, before base64 inflates it by a third.
    ///
    /// A ceiling rather than a target: at `longestSide` a typical desktop frame lands near 200 KB,
    /// and only a dense photographic screen approaches this. When one does, it is re-encoded
    /// smaller rather than sent — a request rejected for size answers nothing at all.
    static let maxEncodedBytes = 700_000

    /// The mime type of every image this type produces.
    static let mimeType = "image/jpeg"

    /// The stored frame at `path`, decoded and re-encoded as a JPEG a model can read.
    ///
    /// Nil when the file is gone or unreadable — which is normal rather than exceptional: retention
    /// pruning deletes frame files while their rows survive, so a row from outside the retention
    /// window points at nothing. The caller says so in prose instead of failing the call.
    static func modelImage(atPath path: String) -> ToolImage? {
        let url = URL(fileURLWithPath: path)
        guard let source = CGImageSourceCreateWithURL(url as CFURL, nil) else { return nil }

        // Decode and downscale in one pass. `CGImageSourceCreateThumbnailAtIndex` is the only route
        // that never materialises the full-size bitmap, which matters because this runs inside a
        // short-lived MCP process answering a request the user is waiting on.
        let options: [CFString: Any] = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceThumbnailMaxPixelSize: longestSide,
            // Rotation is baked in here or not at all — a JPEG re-encode drops the EXIF orientation
            // the source carried, so a frame that was upright on disk would arrive on its side.
            kCGImageSourceCreateThumbnailWithTransform: true,
        ]
        guard let image = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary) else {
            return nil
        }

        guard var data = jpeg(from: image, quality: quality) else { return nil }
        if data.count > maxEncodedBytes {
            // One retry, at half the edge and lower quality: that is a ~4x pixel reduction, which
            // clears the ceiling from anywhere a screen capture can realistically land. Looping to
            // convergence would trade an unbounded number of encodes for the same outcome.
            let smaller = CGImageSourceCreateThumbnailAtIndex(
                source,
                0,
                options.merging([kCGImageSourceThumbnailMaxPixelSize: longestSide / 2]) { _, new in new }
                    as CFDictionary)
            guard let smaller, let retried = jpeg(from: smaller, quality: 0.6),
                  retried.count <= maxEncodedBytes
            else { return nil }
            data = retried
        }
        return ToolImage(base64: data.base64EncodedString(), mimeType: mimeType)
    }

    private static func jpeg(from image: CGImage, quality: CGFloat) -> Data? {
        let out = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(
            out as CFMutableData, UTType.jpeg.identifier as CFString, 1, nil)
        else { return nil }
        CGImageDestinationAddImage(
            destination, image, [kCGImageDestinationLossyCompressionQuality: quality] as CFDictionary)
        guard CGImageDestinationFinalize(destination) else { return nil }
        return out as Data
    }
}
