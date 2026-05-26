import AppKit
import Foundation

/// A user-selected file staged for attachment to a chat message.
///
/// Lifecycle:
///   1. User selects a file (NSOpenPanel or drag-drop) → init with local URL/data.
///   2. ChatProvider uploads it via APIClient.uploadChatFiles → server fills
///      `serverId`, `thumbnailURL`, `mimeType`, sets `state = .uploaded`.
///   3. On send, the first image's raw `data` is passed to the agent bridge as
///      `imageBase64`; all uploaded `serverId`s are persisted in message metadata
///      so the bubble can re-render thumbnails after a reload.
struct ChatAttachment: Identifiable, Equatable {
    enum State: Equatable {
        case uploading
        case uploaded
        case failed(String)
    }

    let id: String
    var fileName: String
    var mimeType: String
    /// Local image bytes — populated for images so the agent bridge can see them
    /// and so the user gets an instant thumbnail without waiting for upload.
    var data: Data?
    /// Server-assigned file id (matches Flutter's MessageFile.id).
    var serverId: String?
    /// Public thumbnail URL returned by /v2/files (only set for images).
    var thumbnailURL: String?
    var state: State

    init(
        id: String = UUID().uuidString,
        fileName: String,
        mimeType: String,
        data: Data? = nil,
        serverId: String? = nil,
        thumbnailURL: String? = nil,
        state: State = .uploading
    ) {
        self.id = id
        self.fileName = fileName
        self.mimeType = mimeType
        self.data = data
        self.serverId = serverId
        self.thumbnailURL = thumbnailURL
        self.state = state
    }

    var isImage: Bool {
        mimeType.hasPrefix("image/")
    }

    /// True once the backend has accepted the upload and returned an id.
    var isUploaded: Bool {
        if case .uploaded = state { return true }
        return false
    }

    /// Build a ChatAttachment from a local file URL, reading bytes if it's a
    /// reasonably-sized image so we can show an instant thumbnail.
    static func from(url: URL) -> ChatAttachment? {
        guard url.isFileURL else { return nil }
        let name = url.lastPathComponent
        let mime = mimeType(for: url)
        var bytes: Data? = nil
        if mime.hasPrefix("image/") {
            // Cap at 25 MB to avoid copying huge files into memory; backend limit
            // is enforced server-side anyway.
            if let attrs = try? FileManager.default.attributesOfItem(atPath: url.path),
                let size = attrs[.size] as? NSNumber, size.intValue <= 25 * 1024 * 1024
            {
                bytes = try? Data(contentsOf: url)
            }
        }
        return ChatAttachment(fileName: name, mimeType: mime, data: bytes)
    }

    /// Build a ChatAttachment from raw in-memory image bytes (e.g. a screenshot).
    static func fromImageData(_ data: Data, suggestedName: String = "screenshot.png") -> ChatAttachment
    {
        let mime = detectImageMime(data: data) ?? "image/png"
        return ChatAttachment(fileName: suggestedName, mimeType: mime, data: data)
    }

    // MARK: - Helpers

    private static func mimeType(for url: URL) -> String {
        let ext = url.pathExtension.lowercased()
        switch ext {
        case "png": return "image/png"
        case "jpg", "jpeg": return "image/jpeg"
        case "gif": return "image/gif"
        case "webp": return "image/webp"
        case "heic": return "image/heic"
        case "heif": return "image/heif"
        case "bmp": return "image/bmp"
        case "tiff", "tif": return "image/tiff"
        case "pdf": return "application/pdf"
        case "txt", "md", "log": return "text/plain"
        case "json": return "application/json"
        case "csv": return "text/csv"
        case "html", "htm": return "text/html"
        case "doc": return "application/msword"
        case "docx":
            return
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        case "xls": return "application/vnd.ms-excel"
        case "xlsx":
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        case "zip": return "application/zip"
        default: return "application/octet-stream"
        }
    }

    /// Sniff first bytes to detect image type when name/ext is unavailable.
    private static func detectImageMime(data: Data) -> String? {
        guard data.count >= 4 else { return nil }
        let b = [UInt8](data.prefix(12))
        if b.starts(with: [0x89, 0x50, 0x4E, 0x47]) { return "image/png" }
        if b.starts(with: [0xFF, 0xD8, 0xFF]) { return "image/jpeg" }
        if b.starts(with: [0x47, 0x49, 0x46]) { return "image/gif" }
        if b.count >= 12, b[0] == 0x52, b[1] == 0x49, b[2] == 0x46, b[3] == 0x46,
            b[8] == 0x57, b[9] == 0x45, b[10] == 0x42, b[11] == 0x50
        {
            return "image/webp"
        }
        return nil
    }
}

/// Maximum simultaneous attachments per message — matches the Flutter app
/// (`message_provider.dart:144`).
let kMaxChatAttachments = 4
