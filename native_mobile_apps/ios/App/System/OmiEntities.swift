import AppIntents
import CoreSpotlight
import Foundation
import OmiCore
import OmiService

// Conversations, tasks, memories and folders as App Intents entities: Siri and Shortcuts pick them,
// Spotlight finds them (`SpotlightIndexer`), and "Open" intents show them in the app. Every query
// reads the app's stores through `SiriCatalog`.

struct ConversationEntity: IndexedEntity {
    static let typeDisplayRepresentation = TypeDisplayRepresentation(name: LocalizedStringResource("Conversation", table: "AppIntents"))
    static let defaultQuery = ConversationQuery()

    let id: String
    @Property(title: LocalizedStringResource("Title", table: "AppIntents")) var title: String
    @Property(title: LocalizedStringResource("Summary", table: "AppIntents")) var summary: String
    @Property(title: LocalizedStringResource("Date", table: "AppIntents")) var date: Date

    init(_ conversation: Conversation) {
        id = conversation.id
        title = conversation.title
        summary = String(conversation.overview.prefix(SpotlightRecord.textLimit))
        date = conversation.date
    }

    var displayRepresentation: DisplayRepresentation {
        DisplayRepresentation(title: "\(title)", subtitle: "\(summary)")
    }

    var attributeSet: CSSearchableItemAttributeSet {
        let attributes = CSSearchableItemAttributeSet(contentType: .text)
        attributes.title = title
        attributes.contentDescription = summary
        attributes.contentCreationDate = date
        return attributes
    }
}

struct ConversationQuery: EntityStringQuery {
    func entities(for identifiers: [String]) async throws -> [ConversationEntity] {
        try await AppIntentsBridge.catalog().conversations(ids: identifiers).map(ConversationEntity.init)
    }

    func entities(matching string: String) async throws -> [ConversationEntity] {
        try await AppIntentsBridge.catalog().conversations(matching: string)
            .prefix(SiriCatalog.suggestionLimit).map(ConversationEntity.init)
    }

    func suggestedEntities() async throws -> [ConversationEntity] {
        try await entities(matching: "")
    }
}

struct TaskEntity: IndexedEntity {
    static let typeDisplayRepresentation = TypeDisplayRepresentation(name: LocalizedStringResource("Task", table: "AppIntents"))
    static let defaultQuery = TaskQuery()

    let id: String
    @Property(title: LocalizedStringResource("Title", table: "AppIntents")) var title: String
    @Property(title: LocalizedStringResource("Done", table: "AppIntents")) var isCompleted: Bool
    @Property(title: LocalizedStringResource("Due", table: "AppIntents")) var dueDate: Date?

    init(_ task: ActionItem) {
        id = task.id
        title = task.description
        isCompleted = task.isCompleted
        dueDate = task.dueAt
    }

    var displayRepresentation: DisplayRepresentation {
        guard let dueDate else { return DisplayRepresentation(title: "\(title)") }
        return DisplayRepresentation(title: "\(title)", subtitle: "\(dueDate.formatted(date: .abbreviated, time: .shortened))")
    }

    var attributeSet: CSSearchableItemAttributeSet {
        let attributes = CSSearchableItemAttributeSet(contentType: .text)
        attributes.title = title
        attributes.dueDate = dueDate
        return attributes
    }
}

/// Picks among the user's open tasks (what "Complete task" needs); done ones still resolve by id.
struct TaskQuery: EntityStringQuery {
    func entities(for identifiers: [String]) async throws -> [TaskEntity] {
        try await AppIntentsBridge.catalog().tasks(ids: identifiers).map(TaskEntity.init)
    }

    func entities(matching string: String) async throws -> [TaskEntity] {
        try await AppIntentsBridge.catalog().tasks(matching: string).prefix(SiriCatalog.suggestionLimit).map(TaskEntity.init)
    }

    func suggestedEntities() async throws -> [TaskEntity] {
        try await entities(matching: "")
    }
}

struct MemoryEntity: IndexedEntity {
    static let typeDisplayRepresentation = TypeDisplayRepresentation(name: LocalizedStringResource("Memory", table: "AppIntents"))
    static let defaultQuery = MemoryQuery()

    let id: String
    @Property(title: LocalizedStringResource("Title", table: "AppIntents")) var title: String
    @Property(title: LocalizedStringResource("Content", table: "AppIntents")) var content: String

    init(_ memory: Memory) {
        id = memory.id
        title = SpotlightRecord.memoryTitle(memory)
        content = memory.content
    }

    var displayRepresentation: DisplayRepresentation {
        DisplayRepresentation(title: "\(title)")
    }

    var attributeSet: CSSearchableItemAttributeSet {
        let attributes = CSSearchableItemAttributeSet(contentType: .text)
        attributes.title = title
        attributes.contentDescription = String(content.prefix(SpotlightRecord.textLimit))
        return attributes
    }
}

struct MemoryQuery: EntityStringQuery {
    func entities(for identifiers: [String]) async throws -> [MemoryEntity] {
        try await AppIntentsBridge.catalog().memories(ids: identifiers).map(MemoryEntity.init)
    }

    func entities(matching string: String) async throws -> [MemoryEntity] {
        try await AppIntentsBridge.catalog().memories(matching: string).prefix(SiriCatalog.suggestionLimit).map(MemoryEntity.init)
    }

    func suggestedEntities() async throws -> [MemoryEntity] {
        try await entities(matching: "")
    }
}

struct FolderEntity: AppEntity {
    static let typeDisplayRepresentation = TypeDisplayRepresentation(name: LocalizedStringResource("Folder", table: "AppIntents"))
    static let defaultQuery = FolderQuery()

    let id: String
    @Property(title: LocalizedStringResource("Name", table: "AppIntents")) var name: String

    init(_ folder: Folder) {
        id = folder.id
        name = folder.name
    }

    var displayRepresentation: DisplayRepresentation {
        DisplayRepresentation(title: "\(name)")
    }
}

struct FolderQuery: EntityStringQuery {
    func entities(for identifiers: [String]) async throws -> [FolderEntity] {
        try await AppIntentsBridge.catalog().folders(ids: identifiers).map(FolderEntity.init)
    }

    func entities(matching string: String) async throws -> [FolderEntity] {
        try await AppIntentsBridge.catalog().folders(matching: string).map(FolderEntity.init)
    }

    func suggestedEntities() async throws -> [FolderEntity] {
        try await entities(matching: "")
    }
}
