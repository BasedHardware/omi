import AppIntents
import CoreLocation
import CoreSpotlight
import Foundation

@available(macOS 27, *)
@AppEntity(schema: .notes.folder)
struct OmiFolderEntity: IndexedEntity {
  static let defaultQuery = OmiFolderQuery()
  static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Omi Folder")
  let id: String
  var name: String
  var parentFolder: OmiFolderEntity?
  var account: OmiAccountEntity?
  var displayRepresentation: DisplayRepresentation { DisplayRepresentation(title: "\(name)") }

  init(id: String, name: String) {
    self.id = id
    self.name = name
    self.parentFolder = nil
    self.account = nil
  }

  static let conversations = OmiFolderEntity(id: "conversations", name: "Conversations")
  static let memories = OmiFolderEntity(id: "memories", name: "Memories")
}

@available(macOS 27, *)
@AppEntity(schema: .notes.account)
struct OmiAccountEntity: AppEntity {
  static let defaultQuery = OmiAccountQuery()
  static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Omi Account")
  let id: String
  var name: String
  var displayRepresentation: DisplayRepresentation { DisplayRepresentation(title: "\(name)") }

  init(id: String, name: String) {
    self.id = id
    self.name = name
  }
}

@available(macOS 27, *)
@AppEntity(schema: .notes.note)
struct ConversationEntity: IndexedEntity {
  static let defaultQuery = ConversationEntityQuery()
  static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Omi Conversation")
  let id: String
  var name: AttributedString
  var content: AttributedString?
  var attachments: [IntentFile]
  var isPinned: Bool
  var creationDate: Date?
  var modificationDate: Date?
  var folder: OmiFolderEntity?
  var displayRepresentation: DisplayRepresentation { DisplayRepresentation(title: "\(String(name.characters))") }

  init(_ record: TranscriptionSessionRecord) {
    id = record.backendId ?? ""
    name = AttributedString(record.title?.isEmpty == false ? record.title! : "Conversation")
    content = record.overview.map(AttributedString.init)
    attachments = []
    isPinned = false
    creationDate = record.startedAt
    modificationDate = record.serverUpdatedAt ?? record.updatedAt
    folder = .conversations
  }

  init(_ memory: ServerMemory) {
    id = memory.id
    name = AttributedString(String(memory.content.prefix(60)))
    content = AttributedString(memory.content)
    attachments = []
    isPinned = false
    creationDate = memory.createdAt
    modificationDate = memory.updatedAt
    folder = .memories
  }

  init(donationID: String) {
    id = donationID
    name = AttributedString("Omi Conversation")
    content = nil
    attachments = []
    isPinned = false
    creationDate = nil
    modificationDate = nil
    folder = .conversations
  }
}

@available(macOS 15.4, *)
struct MemoryEntity: IndexedEntity {
  static let defaultQuery = MemoryEntityQuery()
  static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Omi Memory")
  let id: String
  @Property(title: "Name", indexingKey: \.displayName) var name: String
  @Property(title: "Content", indexingKey: \.contentDescription) var content: String
  @Property(title: "Created", indexingKey: \.contentCreationDate) var creationDate: Date
  var expiresAt: Date?
  var displayRepresentation: DisplayRepresentation { DisplayRepresentation(title: "\(name)") }

  init(_ record: MemoryRecord) {
    id = record.backendId ?? ""
    name = String(record.content.prefix(60))
    content = record.content
    creationDate = record.createdAt
    expiresAt = record.expiresAt
  }

  init(_ memory: ServerMemory) {
    id = memory.id
    name = String(memory.content.prefix(60))
    content = memory.content
    creationDate = memory.createdAt
    expiresAt = memory.expiresAt
  }

  init(donationID: String) {
    id = donationID
    name = "Omi Memory"
    content = ""
    creationDate = .distantPast
    expiresAt = nil
  }
}

@available(macOS 27, *)
@AppEntity(schema: .reminders.list)
struct OmiListEntity: IndexedEntity {
  static let defaultQuery = OmiListQuery()
  static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Omi Task List")
  let id: String
  var name: String
  var type: OmiReminderListType
  var displayRepresentation: DisplayRepresentation { DisplayRepresentation(title: "\(name)") }
  init(id: String, name: String) {
    self.id = id
    self.name = name
    self.type = .standard
  }
  static let omi = OmiListEntity(id: "omi", name: "Omi")
}

@available(macOS 27, *)
@AppEnum(schema: .reminders.listType)
enum OmiReminderListType: String, AppEnum {
  case standard
  static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "List Type")
  static let caseDisplayRepresentations: [Self: DisplayRepresentation] = [.standard: "Standard"]
}

@available(macOS 27, *)
@AppEntity(schema: .reminders.reminder)
struct TaskEntity: IndexedEntity {
  static let defaultQuery = TaskEntityQuery()
  static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Omi Task")
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

  init(_ record: ActionItemRecord) {
    id = record.backendId ?? ""
    title = record.description
    note = nil
    tags = []
    urls = []
    dueDate = record.dueAt.map { Calendar.current.dateComponents([.year, .month, .day, .hour, .minute], from: $0) }
    recurrence = nil
    isCompleted = record.completed
    isFlagged = nil
    creationDate = record.createdAt
    completionDate = record.completedAt
    list = .omi
    locationTrigger = nil
  }

  init(_ task: TaskActionItem) {
    id = task.id
    title = task.description
    note = nil
    tags = []
    urls = []
    dueDate = task.dueAt.map { Calendar.current.dateComponents([.year, .month, .day, .hour, .minute], from: $0) }
    recurrence = nil
    isCompleted = task.completed
    isFlagged = nil
    creationDate = task.createdAt
    completionDate = task.completedAt
    list = .omi
    locationTrigger = nil
  }

  init(donationID: String) {
    id = donationID
    title = "Omi Task"
    note = nil
    tags = []
    urls = []
    dueDate = nil
    recurrence = nil
    isCompleted = false
    isFlagged = nil
    creationDate = nil
    completionDate = nil
    list = .omi
    locationTrigger = nil
  }
}

@available(macOS 27, *)
@AppEntity(schema: .reminders.locationTrigger)
struct OmiLocationTriggerEntity: IndexedEntity {
  static let defaultQuery = OmiLocationTriggerQuery()
  static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Location Trigger")
  let id: String
  var event: OmiLocationTriggerEvent
  var place: CLPlacemark
  var displayRepresentation: DisplayRepresentation { DisplayRepresentation(title: "Location") }
}

@available(macOS 27, *)
@AppEnum(schema: .reminders.locationTriggerEvent)
enum OmiLocationTriggerEvent: String, AppEnum {
  case arrive, depart
  static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Location Trigger Event")
  static let caseDisplayRepresentations: [Self: DisplayRepresentation] = [
    .arrive: "Arriving", .depart: "Leaving",
  ]
}

@available(macOS 27, *)
struct OmiFolderQuery: EntityQuery {
  func entities(for identifiers: [String]) async throws -> [OmiFolderEntity] {
    [OmiFolderEntity.conversations, .memories].filter { identifiers.contains($0.id) }
  }
}

@available(macOS 27, *)
struct OmiAccountQuery: EntityQuery {
  func entities(for identifiers: [String]) async throws -> [OmiAccountEntity] { [] }
}

@available(macOS 27, *)
struct OmiListQuery: EntityQuery {
  func entities(for identifiers: [String]) async throws -> [OmiListEntity] {
    identifiers.contains("omi") ? [.omi] : []
  }
}

@available(macOS 27, *)
struct OmiLocationTriggerQuery: EntityQuery {
  func entities(for identifiers: [String]) async throws -> [OmiLocationTriggerEntity] { [] }
}

@available(macOS 27, *)
struct ConversationEntityQuery: IndexedEntityQuery {
  func entities(for identifiers: [String]) async throws -> [ConversationEntity] {
    guard let owner = RuntimeOwnerIdentity.currentOwnerId() else { return [] }
    let result = try await withThrowingTaskGroup(of: ConversationEntity?.self) { group in
      for id in identifiers {
        group.addTask {
          guard let record = try await TranscriptionStorage.shared.getSessionByBackendId(id),
            SiriIndexScope.conversation(record, now: Date())
          else {
            guard let memory = try await MemoryStorage.shared.getMemoryByBackendId(id),
              SiriIndexScope.memory(
                backendId: memory.backendId, deleted: memory.deleted,
                dismissed: memory.isDismissed, expiresAt: memory.expiresAt, now: Date()),
              let value = memory.toServerMemory()
            else { return nil }
            return ConversationEntity(value)
          }
          return ConversationEntity(record)
        }
      }
      var found: [ConversationEntity] = []
      for try await entity in group { if let entity { found.append(entity) } }
      return found
    }
    return RuntimeOwnerIdentity.currentOwnerId() == owner ? result : []
  }

  func reindexEntities(for identifiers: [String], indexDescription: CSSearchableIndexDescription) async throws {
    guard let owner = RuntimeOwnerIdentity.currentOwnerId() else { return }
    try await SiriIndexer.shared.indexConversations(try await entities(for: identifiers), expectedOwner: owner)
  }

  func reindexAllEntities(indexDescription: CSSearchableIndexDescription) async throws {
    try await SiriIndexer.shared.rebuild()
  }
}

@available(macOS 15.4, *)
struct MemoryEntityQuery: IndexedEntityQuery {
  func entities(for identifiers: [String]) async throws -> [MemoryEntity] {
    guard let owner = RuntimeOwnerIdentity.currentOwnerId() else { return [] }
    let records = try await MemoryStorage.shared.getMemories(backendIds: identifiers)
    var found: [MemoryEntity] = []
    for memory in records {
      guard let record = try await MemoryStorage.shared.getMemoryByBackendId(memory.id),
        SiriIndexScope.memory(
          backendId: record.backendId, deleted: record.deleted,
          dismissed: record.isDismissed, expiresAt: record.expiresAt, now: Date())
      else { continue }
      found.append(MemoryEntity(record))
    }
    return RuntimeOwnerIdentity.currentOwnerId() == owner ? found : []
  }

  @available(macOS 27, *)
  func reindexEntities(for identifiers: [String], indexDescription: CSSearchableIndexDescription) async throws {
    guard let owner = RuntimeOwnerIdentity.currentOwnerId() else { return }
    try await SiriIndexer.shared.indexMemories(try await entities(for: identifiers), expectedOwner: owner)
  }

  @available(macOS 27, *)
  func reindexAllEntities(indexDescription: CSSearchableIndexDescription) async throws {
    try await SiriIndexer.shared.rebuild()
  }
}

@available(macOS 27, *)
struct TaskEntityQuery: IndexedEntityQuery {
  func entities(for identifiers: [String]) async throws -> [TaskEntity] {
    guard let owner = RuntimeOwnerIdentity.currentOwnerId() else { return [] }
    var found: [TaskEntity] = []
    for id in identifiers {
      guard let record = try await ActionItemStorage.shared.getActionItemByBackendId(id),
        SiriIndexScope.task(
          backendId: record.backendId, deleted: record.deleted,
          completed: record.completed, completedAt: record.completedAt,
          taskStatus: record.taskStatus, now: Date())
      else { continue }
      found.append(TaskEntity(record))
    }
    return RuntimeOwnerIdentity.currentOwnerId() == owner ? found : []
  }

  func reindexEntities(for identifiers: [String], indexDescription: CSSearchableIndexDescription) async throws {
    guard let owner = RuntimeOwnerIdentity.currentOwnerId() else { return }
    try await SiriIndexer.shared.indexTasks(try await entities(for: identifiers), expectedOwner: owner)
  }

  func reindexAllEntities(indexDescription: CSSearchableIndexDescription) async throws {
    try await SiriIndexer.shared.rebuild()
  }
}
