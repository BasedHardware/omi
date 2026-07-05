import AppKit
import Foundation

/// Shared helper to prepare inline image attachments for the reply-draft backend's
/// vision step: downscale + JPEG-encode to base64, bounded in dimension and bytes
/// so the draft request stays small. Used by all three inboxes' `draftContext`.
enum MessagingMedia {
  /// Returns a base64 JPEG for the image at `path`, or nil for unreadable /
  /// non-image files. Downscaled to `maxDimension` and re-compressed until under
  /// `maxBytes` so we never send a multi-MB photo.
  /// Cache of encoded results keyed by (path + params). Attachment files are immutable
  /// (Messages/WhatsApp/Telegram store them content-addressed), so a path maps to a
  /// stable encoding. This avoids re-decoding/resizing/encoding the same photo every
  /// time `draftContext()` runs (re-renders, repeated predraft/auto-reply) — the main
  /// source of the main-thread churn. (NSCache is thread-safe.)
  private static let cache: NSCache<NSString, NSString> = {
    let c = NSCache<NSString, NSString>()
    c.countLimit = 256
    // Also bound by bytes, not just entry count: each value is a base64 JPEG up to a
    // couple MB, so 256 entries could otherwise retain hundreds of MB. Matches the
    // InboxAttachmentImageCache 100 MB ceiling.
    c.totalCostLimit = 100 * 1024 * 1024
    return c
  }()

  static func base64JPEG(
    path: String, maxDimension: CGFloat = 1024, quality: CGFloat = 0.6, maxBytes: Int = 1_500_000
  ) -> String? {
    let cacheKey = "\(path)|\(maxDimension)|\(quality)|\(maxBytes)" as NSString
    if let cached = cache.object(forKey: cacheKey) { return cached as String }
    guard let image = NSImage(contentsOfFile: path) else { return nil }
    let size = image.size
    guard size.width > 0, size.height > 0 else { return nil }

    let scale = min(1, maxDimension / max(size.width, size.height))
    let target = NSSize(width: size.width * scale, height: size.height * scale)
    let resized = NSImage(size: target)
    resized.lockFocus()
    image.draw(
      in: NSRect(origin: .zero, size: target),
      from: NSRect(origin: .zero, size: size), operation: .copy, fraction: 1)
    resized.unlockFocus()

    guard let tiff = resized.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff) else { return nil }
    var q = quality
    var data = rep.representation(using: .jpeg, properties: [.compressionFactor: q])
    while let d = data, d.count > maxBytes, q > 0.2 {
      q -= 0.15
      data = rep.representation(using: .jpeg, properties: [.compressionFactor: q])
    }
    guard let final = data, final.count <= maxBytes else { return nil }
    let b64 = final.base64EncodedString()
    cache.setObject(b64 as NSString, forKey: cacheKey, cost: b64.utf8.count)
    return b64
  }
}
