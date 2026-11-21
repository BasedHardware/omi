import Foundation
import ImageIO
import UniformTypeIdentifiers

/// Photos for the chat travel as JPEG: the backend's `v2/files` rejects HEIC (the iPhone's camera
/// format), and a 12 MP photo is more than the model needs. ImageIO decodes whatever the photo
/// library, Files or the pasteboard hand over (HEIC, PNG, JPEG …), applies the orientation and
/// scales it down.
public enum ChatImageEncoder {
    /// The long side of a photo sent with a message.
    public static let maxSide = 2048
    /// The long side of the composer's thumbnail.
    public static let thumbnailSide = 240

    /// JPEG of `data` at most `maxSide` pixels on its long side, or nil when it is not an image.
    public static func jpeg(from data: Data, maxSide: Int = maxSide, quality: Double = 0.85) -> Data? {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil), CGImageSourceGetCount(source) > 0 else { return nil }
        let options: [CFString: Any] = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceThumbnailMaxPixelSize: maxSide,
            kCGImageSourceShouldCacheImmediately: true,
        ]
        guard let image = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary) else { return nil }
        let output = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(output, UTType.jpeg.identifier as CFString, 1, nil) else { return nil }
        CGImageDestinationAddImage(destination, image, [kCGImageDestinationLossyCompressionQuality: quality] as CFDictionary)
        guard CGImageDestinationFinalize(destination) else { return nil }
        return output as Data
    }

    /// Whether `data` is a HEIC/HEIF image (what the backend would refuse).
    public static func isHEIC(_ data: Data) -> Bool {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil),
              let type = CGImageSourceGetType(source) as String?,
              let utType = UTType(type) else { return false }
        return utType.conforms(to: .heic) || utType.conforms(to: .heif)
    }

    /// A photo's file name with the `.jpg` it now is ("IMG_0042.HEIC" → "IMG_0042.jpg").
    public static func jpegName(for name: String?) -> String {
        let base = (name.map { ($0 as NSString).deletingPathExtension } ?? "").trimmingCharacters(in: .whitespaces)
        return (base.isEmpty ? "photo-\(UUID().uuidString.prefix(8).lowercased())" : base) + ".jpg"
    }
}

public extension ChatStore {
    /// Attaches a photo from any source as JPEG (HEIC converted). False when it is no image.
    @discardableResult
    func attachImage(data: Data, filename: String? = nil) -> Bool {
        guard let jpeg = ChatImageEncoder.jpeg(from: data) else { return false }
        let preview = ChatImageEncoder.jpeg(from: jpeg, maxSide: ChatImageEncoder.thumbnailSide, quality: 0.7)
        attach(data: jpeg, filename: ChatImageEncoder.jpegName(for: filename), mimeType: "image/jpeg", preview: preview)
        return true
    }
}
