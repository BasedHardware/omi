import Foundation
import AppIntents
import CoreSpotlight
import GeoToolbox

@available(iOS 27.0, *)
@AppEntity(schema: .notes.folder)
struct OmiFolderEntity: IndexedEntity {
    static let defaultQuery = OmiFolderQuery()
    static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Omi folder")
    let id: String
    var name: String
    var parentFolder: OmiFolderEntity?
    var account: OmiAccountEntity?
    var displayRepresentation: DisplayRepresentation { DisplayRepresentation(title: "\(name)") }
    init(id: String, name: String) { self.id = id; self.name = name; parentFolder = nil; account = nil }
    static let conversations = OmiFolderEntity(id: "conversations", name: "Conversations")
    static let memories = OmiFolderEntity(id: "memories", name: "Memories")
    var attributeSet: CSSearchableItemAttributeSet {
        let attributes = defaultAttributeSet
        attributes.title = name
        attributes.relatedUniqueIdentifier = "omi://folder/\(id)"
        return attributes
    }
}

@available(iOS 27.0, *)
@AppEntity(schema: .notes.account)
struct OmiAccountEntity: AppEntity {
    static let defaultQuery = OmiAccountQuery()
    static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Omi account")
    let id: String
    var name: String
    var displayRepresentation: DisplayRepresentation { DisplayRepresentation(title: "\(name)") }
}

@available(iOS 27.0, *)
@AppEntity(schema: .notes.note)
struct ConversationEntity: IndexedEntity {
    static let defaultQuery = ConversationQuery()
    static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Omi conversation")
    let id: String
    var name: AttributedString
    var content: AttributedString?
    var attachments: [IntentFile]
    var isPinned: Bool
    var creationDate: Date?
    var modificationDate: Date?
    var folder: OmiFolderEntity?
    var displayRepresentation: DisplayRepresentation { DisplayRepresentation(title: "\(String(name.characters))") }
    init(id: String, name: String, content: String, creationDate: Date, modificationDate: Date) {
        self.id = id
        self.name = AttributedString(name)
        self.content = AttributedString(content)
        self.attachments = []
        self.isPinned = false
        self.creationDate = creationDate
        self.modificationDate = modificationDate
        self.folder = .conversations
    }
    init(memoryId: String, content: String, creationDate: Date) {
        self.id = memoryId
        self.name = AttributedString(String(content.prefix(60)))
        self.content = AttributedString(content)
        self.attachments = []
        self.isPinned = false
        self.creationDate = creationDate
        self.modificationDate = creationDate
        self.folder = .memories
    }
    var attributeSet: CSSearchableItemAttributeSet {
        let attributes = defaultAttributeSet
        attributes.title = String(name.characters)
        attributes.contentDescription = content.map { String($0.characters) }
        attributes.contentCreationDate = creationDate
        attributes.contentModificationDate = modificationDate
        attributes.relatedUniqueIdentifier = folder?.id == "memories" ? "omi://memory/\(id)" : "omi://conversation/\(id)"
        return attributes
    }
}

@available(iOS 27.0, *)
struct MemoryEntity: IndexedEntity {
    static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Omi memory")
    static let defaultQuery = MemoryQuery()
    let id: String
    @Property(title: "Name", indexingKey: \.displayName) var name: String
    @Property(title: "Content", indexingKey: \.contentDescription) var content: String
    @Property(title: "Created", indexingKey: \.contentCreationDate) var creationDate: Date
    var displayRepresentation: DisplayRepresentation { DisplayRepresentation(title: "\(name)") }
    init(id: String, content: String, creationDate: Date) {
        self.id = id
        self.name = String(content.prefix(60))
        self.content = content
        self.creationDate = creationDate
    }
    var attributeSet: CSSearchableItemAttributeSet {
        let attributes = defaultAttributeSet
        attributes.title = name
        attributes.contentDescription = content
        attributes.contentCreationDate = creationDate
        attributes.relatedUniqueIdentifier = "omi://memory/\(id)"
        return attributes
    }
}

@available(iOS 27.0, *)
@AppEntity(schema: .reminders.list)
struct OmiListEntity: IndexedEntity {
    static let defaultQuery = OmiListQuery()
    static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Omi task list")
    let id: String
    var name: String
    var type: OmiReminderListType
    var displayRepresentation: DisplayRepresentation { DisplayRepresentation(title: "\(name)") }
    init(id: String, name: String) { self.id = id; self.name = name; self.type = .standard }
    static let omi = OmiListEntity(id: "omi", name: "Omi")
    var attributeSet: CSSearchableItemAttributeSet {
        let attributes = defaultAttributeSet
        attributes.title = name
        attributes.relatedUniqueIdentifier = "omi://list/\(id)"
        return attributes
    }
}

@available(iOS 27.0, *)
@AppEnum(schema: .reminders.listType)
enum OmiReminderListType: String, AppEnum {
    case standard
    static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "List type")
    static let caseDisplayRepresentations: [Self: DisplayRepresentation] = [.standard: "Standard"]
}

@available(iOS 27.0, *)
@AppEntity(schema: .reminders.locationTrigger)
struct OmiLocationTriggerEntity: IndexedEntity {
    static let defaultQuery = OmiLocationTriggerQuery()
    static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Location trigger")
    let id: String
    var place: GeoToolbox.PlaceDescriptor
    var event: OmiLocationTriggerEvent
    var displayRepresentation: DisplayRepresentation { DisplayRepresentation(title: "Location") }
}

@available(iOS 27.0, *)
@AppEntity(schema: .reminders.section)
struct OmiSectionEntity: IndexedEntity {
    static let defaultQuery = OmiSectionQuery()
    static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Omi section")
    let id: String
    var name: String
    var list: OmiListEntity
    var displayRepresentation: DisplayRepresentation { DisplayRepresentation(title: "\(name)") }
}

@available(iOS 27.0, *)
@AppEnum(schema: .reminders.locationTriggerEvent)
enum OmiLocationTriggerEvent: String, AppEnum {
    case arrive, depart
    static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Location event")
    static let caseDisplayRepresentations: [Self: DisplayRepresentation] = [.arrive: "Arrive", .depart: "Depart"]
}

@available(iOS 27.0, *)
@AppEntity(schema: .reminders.reminder)
struct TaskEntity: IndexedEntity {
    static let defaultQuery = TaskQuery()
    static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Omi task")
    let id: String
    var title: String
    var note: AttributedString?
    var tags: Set<String>
    var urls: [URL]
    var dueDate: DateComponents?
    var recurrence: Calendar.RecurrenceRule?
    var isCompleted: Bool
    var isFlagged: Bool?
    var creationDate: Date?
    var completionDate: Date?
    var list: OmiListEntity
    var locationTrigger: OmiLocationTriggerEntity?
    var displayRepresentation: DisplayRepresentation { DisplayRepresentation(title: "\(title)") }
    init(id: String, title: String, isCompleted: Bool, creationDate: Date, dueDate: Date?, completionDate: Date?) {
        self.id = id
        self.title = title
        self.note = nil
        self.tags = []
        self.urls = []
        self.dueDate = dueDate.map { Calendar.current.dateComponents([.year, .month, .day, .hour, .minute], from: $0) }
        self.recurrence = nil
        self.isCompleted = isCompleted
        self.isFlagged = nil
        self.creationDate = creationDate
        self.completionDate = completionDate
        self.list = .omi
        self.locationTrigger = nil
    }
    var attributeSet: CSSearchableItemAttributeSet {
        let attributes = defaultAttributeSet
        attributes.title = title
        attributes.contentCreationDate = creationDate
        attributes.dueDate = dueDate.flatMap { Calendar.current.date(from: $0) }
        attributes.completionDate = completionDate
        attributes.relatedUniqueIdentifier = "omi://task/\(id)"
        return attributes
    }
}

@available(iOS 27.0, *)
struct OmiFolderQuery: EntityQuery {
    func entities(for identifiers: [String]) async throws -> [OmiFolderEntity] {
        [OmiFolderEntity.conversations, .memories].filter { identifiers.contains($0.id) }
    }
}
@available(iOS 27.0, *)
struct OmiAccountQuery: EntityQuery {
    func entities(for identifiers: [String]) async throws -> [OmiAccountEntity] { [] }
}
@available(iOS 27.0, *)
struct OmiListQuery: EntityQuery {
    func entities(for identifiers: [String]) async throws -> [OmiListEntity] { identifiers.contains("omi") ? [.omi] : [] }
}
@available(iOS 27.0, *)
struct OmiLocationTriggerQuery: EntityQuery {
    func entities(for identifiers: [String]) async throws -> [OmiLocationTriggerEntity] { [] }
}
@available(iOS 27.0, *)
struct OmiSectionQuery: EntityQuery {
    func entities(for identifiers: [String]) async throws -> [OmiSectionEntity] { [] }
}

@available(iOS 27.0, *)
struct ConversationQuery: IndexedEntityQuery {
    func entities(for identifiers: [String]) async throws -> [ConversationEntity] {
        SiriSnapshotStore.shared.conversations(ids: identifiers) + SiriSnapshotStore.shared.memoryNotes(ids: identifiers)
    }
    func suggestedEntities() async throws -> [ConversationEntity] { SiriSnapshotStore.shared.conversations(ids: nil) }
    func reindexEntities(for identifiers: [String], indexDescription: CSSearchableIndexDescription) async throws {
        guard let indexName = SiriSnapshotStore.shared.indexName else { return }
        try await CSSearchableIndex(name: indexName).indexAppEntities(try await entities(for: identifiers))
    }
    func reindexAllEntities(indexDescription: CSSearchableIndexDescription) async throws {
        try await SiriSnapshotStore.shared.rebuildIndex()
    }
}
@available(iOS 27.0, *)
struct MemoryQuery: IndexedEntityQuery {
    func entities(for identifiers: [String]) async throws -> [MemoryEntity] { SiriSnapshotStore.shared.memories(ids: identifiers) }
    func suggestedEntities() async throws -> [MemoryEntity] { SiriSnapshotStore.shared.memories(ids: nil) }
    func reindexEntities(for identifiers: [String], indexDescription: CSSearchableIndexDescription) async throws {
        guard let indexName = SiriSnapshotStore.shared.indexName else { return }
        try await CSSearchableIndex(name: indexName).indexAppEntities(try await entities(for: identifiers))
    }
    func reindexAllEntities(indexDescription: CSSearchableIndexDescription) async throws {
        try await SiriSnapshotStore.shared.rebuildIndex()
    }
}
@available(iOS 27.0, *)
struct TaskQuery: IndexedEntityQuery {
    func entities(for identifiers: [String]) async throws -> [TaskEntity] { SiriSnapshotStore.shared.tasks(ids: identifiers) }
    func suggestedEntities() async throws -> [TaskEntity] { SiriSnapshotStore.shared.tasks(ids: nil) }
    func reindexEntities(for identifiers: [String], indexDescription: CSSearchableIndexDescription) async throws {
        guard let indexName = SiriSnapshotStore.shared.indexName else { return }
        try await CSSearchableIndex(name: indexName).indexAppEntities(try await entities(for: identifiers))
    }
    func reindexAllEntities(indexDescription: CSSearchableIndexDescription) async throws {
        try await SiriSnapshotStore.shared.rebuildIndex()
    }
}
