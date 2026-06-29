import AppKit
import CoreImage
import CoreImage.CIFilterBuiltins

/// Generates a QR code image from a string using CoreImage.
///
/// Used by the ConnectSheet to render the Telegram deep link so the
/// user can scan it with their phone (most Telegram use is mobile;
/// the existing \"Open\" button only works if Telegram is on the
/// same machine). Designed to be reusable across any future
/// onboarding flow that needs a QR display (WhatsApp, Discord, etc.).
enum QRCodeGenerator {

    /// Default size used by the onboarding UI. Tuned for the
    /// ConnectSheet's QR container (200pt square).
    private static let defaultSize: CGFloat = 200

    /// Render `text` as a QR code.
    ///
    /// - Parameter text: The string to encode. Empty / nil returns
    ///   nil so callers can render a placeholder instead.
    /// - Parameter size: Target output size in points. The output
    ///   is square; only the width is used.
    /// - Returns: NSImage suitable for SwiftUI Image(nsImage:).
    static func generate(_ text: String?, size: CGFloat = defaultSize) -> NSImage? {
        guard let text, !text.isEmpty else { return nil }
        guard let data = text.data(using: .utf8) else { return nil }

        let filter = CIFilter.qrCodeGenerator()
        filter.message = data
        // 'M' (Medium) is the default correction level. Handles ~15%
        // data loss \u2014 plenty for a phone scanner in good lighting.
        // Lower levels (L) produce simpler patterns but are fragile
        // when the screen is scratched or dirty.
        filter.correctionLevel = "M"

        guard let output = filter.outputImage else { return nil }

        // QR codes are tiny (typically ~30x30 pixels at M correction).
        // Scale up by nearest-neighbor so the squares stay crisp.
        let scale = size / output.extent.width
        let scaled = output.transformed(by: CGAffineTransform(scaleX: scale, y: scale))

        let context = CIContext()
        guard let cgImage = context.createCGImage(scaled, from: scaled.extent) else {
            return nil
        }
        return NSImage(cgImage: cgImage, size: NSSize(width: size, height: size))
    }
}