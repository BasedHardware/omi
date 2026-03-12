import Foundation
import GRDB

/// Database record for screen observations captured during task extraction.
/// Every screenshot analysis produces an observation — whether or not a task was found.
struct ObservationRecord: Codable, FetchableRecord, PersistableRecord, Identifiable {
    var id: Int64?
    var screenshotId: Int64?
    var appName: String
    var contextSummary: String
    var currentActivity: String
    var hasTask: Bool
    var taskTitle: String?
    var sourceCategory: String?
    var sourceSubcategory: String?
    var metadataJson: String?
    var createdAt: Date

    static let databaseTableName = "observations"

    mutating func didInsert(_ inserted: InsertionSuccess) {
        id = inserted.rowID
    }
}

// MARK: - TableDocumented

extension ObservationRecord: TableDocumented {
    static var tableDescription: String { ChatPrompts.tableAnnotations["observations"]! }
    static var columnDescriptions: [String: String] { ChatPrompts.columnAnnotations["observations"] ?? [:] }
}
