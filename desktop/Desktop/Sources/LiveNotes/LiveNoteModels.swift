import Foundation
import GRDB

// MARK: - Live Note

/// A note generated during a live recording session
struct LiveNote: Identifiable, Equatable, Sendable {
    let id: Int64
    let sessionId: Int64
    var text: String
    let timestamp: Date
    let isAiGenerated: Bool
    let segmentStartOrder: Int?
    let segmentEndOrder: Int?
    let createdAt: Date
    var updatedAt: Date
}

// MARK: - Live Note Record

/// Database record for live notes
/// Stores AI-generated or manual notes during recording sessions
struct LiveNoteRecord: Codable, FetchableRecord, PersistableRecord, Identifiable {
    var id: Int64?
    var sessionId: Int64
    var text: String
    var timestamp: Date
    var isAiGenerated: Bool
    var segmentStartOrder: Int?
    var segmentEndOrder: Int?
    var createdAt: Date
    var updatedAt: Date

    static let databaseTableName = "live_notes"

    // MARK: - Initialization

    init(
        id: Int64? = nil,
        sessionId: Int64,
        text: String,
        timestamp: Date = Date(),
        isAiGenerated: Bool = true,
        segmentStartOrder: Int? = nil,
        segmentEndOrder: Int? = nil,
        createdAt: Date = Date(),
        updatedAt: Date = Date()
    ) {
        self.id = id
        self.sessionId = sessionId
        self.text = text
        self.timestamp = timestamp
        self.isAiGenerated = isAiGenerated
        self.segmentStartOrder = segmentStartOrder
        self.segmentEndOrder = segmentEndOrder
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }

    // MARK: - Persistence Callbacks

    mutating func didInsert(_ inserted: InsertionSuccess) {
        id = inserted.rowID
    }

    // MARK: - Relationships

    static let session = belongsTo(TranscriptionSessionRecord.self)

    var session: QueryInterfaceRequest<TranscriptionSessionRecord> {
        request(for: LiveNoteRecord.session)
    }

    // MARK: - Conversion

    /// Convert to LiveNote for UI consumption
    func toLiveNote() -> LiveNote? {
        guard let id = id else { return nil }
        return LiveNote(
            id: id,
            sessionId: sessionId,
            text: text,
            timestamp: timestamp,
            isAiGenerated: isAiGenerated,
            segmentStartOrder: segmentStartOrder,
            segmentEndOrder: segmentEndOrder,
            createdAt: createdAt,
            updatedAt: updatedAt
        )
    }
}

// MARK: - TableDocumented

extension LiveNoteRecord: TableDocumented {
    static var tableDescription: String { ChatPrompts.tableAnnotations["live_notes"]! }
    static var columnDescriptions: [String: String] { ChatPrompts.columnAnnotations["live_notes"] ?? [:] }
}

// MARK: - Live Note Error

/// Errors for LiveNote operations
enum LiveNoteError: LocalizedError {
    case databaseNotInitialized
    case sessionNotFound
    case noteNotFound
    case generationFailed(String)

    var errorDescription: String? {
        switch self {
        case .databaseNotInitialized:
            return "Live notes database is not initialized"
        case .sessionNotFound:
            return "Recording session not found"
        case .noteNotFound:
            return "Note not found"
        case .generationFailed(let message):
            return "Note generation failed: \(message)"
        }
    }
}
