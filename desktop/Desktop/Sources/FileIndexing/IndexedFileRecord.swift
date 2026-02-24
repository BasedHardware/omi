import Foundation
import GRDB

// MARK: - File Type Category

enum FileTypeCategory: String, Codable, CaseIterable {
    case document
    case code
    case image
    case video
    case audio
    case spreadsheet
    case presentation
    case archive
    case data
    case other

    static func from(extension ext: String?) -> FileTypeCategory {
        guard let ext = ext?.lowercased() else { return .other }
        switch ext {
        case "pdf", "doc", "docx", "txt", "rtf", "md", "pages", "odt":
            return .document
        case "swift", "py", "js", "ts", "tsx", "jsx", "go", "rs", "java", "cpp", "c", "h", "rb", "php", "kt", "scala", "sh", "bash", "zsh", "r", "m", "mm", "lua", "pl", "ex", "exs", "hs", "clj", "dart", "vue", "svelte":
            return .code
        case "png", "jpg", "jpeg", "gif", "svg", "psd", "ai", "sketch", "webp", "ico", "tiff", "bmp", "heic", "raw":
            return .image
        case "mp4", "mov", "avi", "mkv", "webm", "flv", "wmv", "m4v":
            return .video
        case "mp3", "wav", "aac", "m4a", "flac", "ogg", "wma", "aiff":
            return .audio
        case "xlsx", "xls", "csv", "numbers", "tsv", "ods":
            return .spreadsheet
        case "pptx", "ppt", "key", "odp":
            return .presentation
        case "zip", "tar", "gz", "dmg", "rar", "7z", "bz2", "xz", "pkg", "iso":
            return .archive
        case "json", "xml", "yaml", "yml", "sql", "db", "sqlite", "plist", "toml", "ini", "cfg", "conf":
            return .data
        default:
            return .other
        }
    }
}

// MARK: - Indexed File Record

struct IndexedFileRecord: Codable, FetchableRecord, PersistableRecord, Identifiable {
    var id: Int64?
    var path: String              // Relative to home directory (~/...)
    var filename: String
    var fileExtension: String?
    var fileType: String          // FileTypeCategory raw value
    var sizeBytes: Int64
    var folder: String            // Top-level scanned folder: Downloads, Documents, Desktop
    var depth: Int                // 0 = root of scanned folder
    var createdAt: Date?          // File creation date
    var modifiedAt: Date?         // File modification date
    var indexedAt: Date           // When we indexed it

    static let databaseTableName = "indexed_files"

    // MARK: - Column mapping

    enum Columns {
        static let id = Column(CodingKeys.id)
        static let path = Column(CodingKeys.path)
        static let filename = Column(CodingKeys.filename)
        static let fileExtension = Column(CodingKeys.fileExtension)
        static let fileType = Column(CodingKeys.fileType)
        static let sizeBytes = Column(CodingKeys.sizeBytes)
        static let folder = Column(CodingKeys.folder)
        static let depth = Column(CodingKeys.depth)
        static let createdAt = Column(CodingKeys.createdAt)
        static let modifiedAt = Column(CodingKeys.modifiedAt)
        static let indexedAt = Column(CodingKeys.indexedAt)
    }

    // MARK: - Initialization

    init(
        id: Int64? = nil,
        path: String,
        filename: String,
        fileExtension: String? = nil,
        fileType: String,
        sizeBytes: Int64,
        folder: String,
        depth: Int,
        createdAt: Date? = nil,
        modifiedAt: Date? = nil,
        indexedAt: Date = Date()
    ) {
        self.id = id
        self.path = path
        self.filename = filename
        self.fileExtension = fileExtension
        self.fileType = fileType
        self.sizeBytes = sizeBytes
        self.folder = folder
        self.depth = depth
        self.createdAt = createdAt
        self.modifiedAt = modifiedAt
        self.indexedAt = indexedAt
    }

    // MARK: - Persistence Callbacks

    mutating func didInsert(_ inserted: InsertionSuccess) {
        id = inserted.rowID
    }
}

// MARK: - TableDocumented

extension IndexedFileRecord: TableDocumented {
    static var tableDescription: String { ChatPrompts.tableAnnotations["indexed_files"]! }
    static var columnDescriptions: [String: String] { ChatPrompts.columnAnnotations["indexed_files"] ?? [:] }
}
