import Foundation
@preconcurrency import GRDB

// MARK: - Database Record

/// Database record for AI-generated user profile history
// `MutablePersistableRecord` — not `PersistableRecord` — because the rowid is
// captured by a `mutating didInsert`. `PersistableRecord`'s requirement is
// non-mutating, so a mutating declaration silently witnesses nothing and the
// empty default runs instead, leaving `id` nil after every insert.
struct AIUserProfileRecord: Codable, FetchableRecord, MutablePersistableRecord, Identifiable {
  var id: Int64?
  var profileText: String
  var dataSourcesUsed: Int
  var backendSynced: Bool
  var generatedAt: Date

  static let databaseTableName = "ai_user_profiles"

  mutating func didInsert(_ inserted: InsertionSuccess) {
    id = inserted.rowID
  }
}

// MARK: - TableDocumented

extension AIUserProfileRecord: TableDocumented {
  static var tableDescription: String { ChatPrompts.tableAnnotations["ai_user_profiles"]! }
  static var columnDescriptions: [String: String] { ChatPrompts.columnAnnotations["ai_user_profiles"] ?? [:] }
}

// MARK: - Service

/// Service that generates and maintains an AI-generated user profile.
/// Inspired by the ContextAgent paper (arXiv:2505.14668).
/// Runs once daily, fetches data from multiple sources, and calls Gemini to synthesize a concise profile.
/// All generated profiles are stored in the local database for history tracking.
actor AIUserProfileService {
  static let shared = AIUserProfileService()

  private let maxProfileLength = 10000

  /// Whether profile generation is currently in progress
  private var isGenerating = false

  /// Cached database pool
  private var _dbQueue: DatabasePool?
  private var _dbGeneration = -1

  /// Invalidate cached DB queue (called on user switch / sign-out)
  func invalidateCache() {
    _dbQueue = nil
  }

  // MARK: - Database Access

  private func ensureDB() async throws -> DatabasePool {
    if let db = _dbQueue, await RewindDatabase.shared.poolGeneration() == _dbGeneration { return db }
    try await RewindDatabase.shared.initialize()
    let (queue, generation) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let db = queue else {
      throw ProfileError.databaseNotAvailable
    }
    _dbQueue = db
    _dbGeneration = generation
    return db
  }

  /// Insert a profile row and return it carrying its persisted rowid.
  ///
  /// Every caller hands the returned record's `id` to a `WHERE id = ?` consumer
  /// (the backend-sync flag update, Settings edit/delete), so the insert must go
  /// through the mutating path that runs `didInsert`.
  func insertProfile(_ record: AIUserProfileRecord) async throws -> AIUserProfileRecord {
    let db = try await ensureDB()
    return try await db.write { database in
      try record.inserted(database)
    }
  }

  // MARK: - Public Interface

  /// Check if we should generate a new profile (>24h since last generation)
  func shouldGenerate() async -> Bool {
    guard let db = try? await ensureDB() else { return false }
    do {
      let latest = try await db.read { database in
        try AIUserProfileRecord
          .order(Column("generatedAt").desc)
          .fetchOne(database)
      }
      guard let latest else { return true }  // Never generated
      return Date().timeIntervalSince(latest.generatedAt) > 86400
    } catch {
      return true
    }
  }

  /// Get the latest stored profile
  func getLatestProfile() async -> AIUserProfileRecord? {
    guard let db = try? await ensureDB() else { return nil }
    return try? await db.read { database in
      try AIUserProfileRecord
        .order(Column("generatedAt").desc)
        .fetchOne(database)
    }
  }

  /// Delete a profile by ID and return the next latest profile
  func deleteProfile(id: Int64) async -> AIUserProfileRecord? {
    guard let db = try? await ensureDB() else { return nil }
    _ = try? await db.write { database in
      try database.execute(
        sql: "DELETE FROM ai_user_profiles WHERE id = ?",
        arguments: [id]
      )
    }
    return await getLatestProfile()
  }

  /// Update the profile text of an existing record and sync to backend
  func updateProfileText(id: Int64, newText: String) async -> Bool {
    guard let db = try? await ensureDB() else { return false }
    do {
      try await db.write { database in
        try database.execute(
          sql: "UPDATE ai_user_profiles SET profileText = ? WHERE id = ?",
          arguments: [newText, id]
        )
      }
      // Sync updated profile to backend (fire-and-forget)
      let text = newText
      Task {
        do {
          // Fetch the record to get generatedAt and dataSourcesUsed
          let record = try? await db.read { database in
            try AIUserProfileRecord.fetchOne(database, key: id)
          }
          try await APIClient.shared.syncAIUserProfile(
            profileText: text,
            generatedAt: record?.generatedAt ?? Date(),
            dataSourcesUsed: record?.dataSourcesUsed ?? 0
          )
          _ = try? await db.write { database in
            try database.execute(
              sql: "UPDATE ai_user_profiles SET backendSynced = 1 WHERE id = ?",
              arguments: [id]
            )
          }
          log("AIUserProfileService: Synced updated profile to backend")
        } catch {
          log("AIUserProfileService: Failed to sync updated profile to backend: \(error.localizedDescription)")
        }
      }
      return true
    } catch {
      log("AIUserProfileService: Failed to update profile text: \(error.localizedDescription)")
      return false
    }
  }

  /// Save exploration text as a new profile record (when no profile exists yet)
  func saveExplorationAsProfile(text: String) async -> Bool {
    let generatedAt = Date()
    let record = AIUserProfileRecord(
      profileText: String(text.prefix(maxProfileLength)),
      dataSourcesUsed: 1,
      backendSynced: false,
      generatedAt: generatedAt
    )
    do {
      let insertedId = try await insertProfile(record).id
      log("AIUserProfileService: Saved exploration as new profile (\(record.profileText.count) chars)")

      // Sync to backend (fire-and-forget)
      let profileText = record.profileText
      let recordId = insertedId
      Task {
        do {
          try await APIClient.shared.syncAIUserProfile(
            profileText: profileText,
            generatedAt: generatedAt,
            dataSourcesUsed: 1
          )
          if let id = recordId, let db = try? await self.ensureDB() {
            _ = try? await db.write { database in
              try database.execute(
                sql: "UPDATE ai_user_profiles SET backendSynced = 1 WHERE id = ?",
                arguments: [id]
              )
            }
          }
          log("AIUserProfileService: Synced exploration profile to backend")
        } catch {
          log("AIUserProfileService: Failed to sync exploration profile to backend: \(error.localizedDescription)")
        }
      }
      return true
    } catch {
      log("AIUserProfileService: Failed to save exploration profile: \(error.localizedDescription)")
      return false
    }
  }

  /// Delete all stored profiles
  func deleteAllProfiles() async {
    guard let db = try? await ensureDB() else { return }
    _ = try? await db.write { database in
      try database.execute(sql: "DELETE FROM ai_user_profiles")
    }
  }

  /// Get all stored profiles (newest first)
  func getAllProfiles(limit: Int = 30) async -> [AIUserProfileRecord] {
    guard let db = try? await ensureDB() else { return [] }
    return
      (try? await db.read { database in
        try AIUserProfileRecord
          .order(Column("generatedAt").desc)
          .limit(limit)
          .fetchAll(database)
      }) ?? []
  }

  /// Generate a new AI user profile from all available data sources
  func generateProfile() async throws -> AIUserProfileRecord {
    guard !isGenerating else {
      throw ProfileError.alreadyGenerating
    }
    isGenerating = true
    defer { isGenerating = false }

    log("AIUserProfileService: Starting profile generation")

    // 1. Fetch all data sources in parallel
    let (memories, tasks, goals, conversations, messages) = await fetchDataSources()

    // 2. Count total data items
    let dataSourcesUsed = memories.count + tasks.count + goals.count + conversations.count + messages.count
    log(
      "AIUserProfileService: Fetched \(dataSourcesUsed) data items (memories=\(memories.count), tasks=\(tasks.count), goals=\(goals.count), convos=\(conversations.count), messages=\(messages.count))"
    )

    guard dataSourcesUsed > 0 else {
      throw ProfileError.insufficientData
    }

    // 3. Synthesize through the backend SSOT. The prompts, the model and the
    // stage-2 consolidation with past profiles all live behind
    // POST /v1/users/ai-profile/synthesize; this only ships the source lines.
    // Stored newest-first, sent oldest-first for the consolidation stage.
    let pastProfiles = await getAllProfiles(limit: 5)
    let synthesis = try await APIClient.shared.synthesizeAIUserProfile(
      memories: memories,
      tasks: tasks,
      goals: goals,
      conversations: conversations,
      messages: messages,
      pastProfilesOldestFirst: pastProfiles.reversed().map { $0.profileText }
    )
    let finalText = synthesis.profileText
    log(
      "AIUserProfileService: Synthesis complete (\(finalText.count) chars, \(pastProfiles.count) past profiles)"
    )

    // 4. Truncate if needed
    let truncated = String(finalText.prefix(maxProfileLength))
    let generatedAt = Date()

    // 5. Save to database
    let record = try await insertProfile(
      AIUserProfileRecord(
        profileText: truncated,
        dataSourcesUsed: dataSourcesUsed,
        backendSynced: false,
        generatedAt: generatedAt
      ))

    // 6. Sync to backend (fire-and-forget)
    let recordId = record.id
    Task {
      do {
        try await APIClient.shared.syncAIUserProfile(
          profileText: truncated,
          generatedAt: generatedAt,
          dataSourcesUsed: dataSourcesUsed
        )
        // Mark as synced
        if let id = recordId, let db = try? await self.ensureDB() {
          _ = try? await db.write { database in
            try database.execute(
              sql: "UPDATE ai_user_profiles SET backendSynced = 1 WHERE id = ?",
              arguments: [id]
            )
          }
        }
        log("AIUserProfileService: Synced profile to backend")
      } catch {
        log("AIUserProfileService: Failed to sync profile to backend: \(error.localizedDescription)")
      }
    }

    log(
      "AIUserProfileService: Profile generated successfully (\(truncated.count) chars, \(dataSourcesUsed) data items)")
    return record
  }

  // MARK: - Data Fetching

  private func fetchDataSources() async -> (
    memories: [String],
    tasks: [String],
    goals: [String],
    conversations: [String],
    messages: [String]
  ) {
    async let memoriesTask = fetchMemories()
    async let tasksTask = fetchTasks()
    async let goalsTask = fetchGoals()
    async let conversationsTask = fetchConversations()
    async let messagesTask = fetchMessages()

    let memories = await memoriesTask
    let tasks = await tasksTask
    let goals = await goalsTask
    let conversations = await conversationsTask
    let messages = await messagesTask

    return (memories, tasks, goals, conversations, messages)
  }

  private func fetchMemories() async -> [String] {
    do {
      let memories = try await APIClient.shared.getMemories(limit: 100)
      return memories.map { "[\($0.category.rawValue)] \($0.content)" }
    } catch {
      log("AIUserProfileService: Failed to fetch memories: \(error.localizedDescription)")
      return []
    }
  }

  private func fetchTasks() async -> [String] {
    do {
      let response = try await APIClient.shared.getActionItems(limit: 50)
      return response.items.map { item in
        let status = item.completed ? "done" : "todo"
        let priority = item.priority ?? "medium"
        return "[\(status)/\(priority)] \(item.description)"
      }
    } catch {
      log("AIUserProfileService: Failed to fetch tasks: \(error.localizedDescription)")
      return []
    }
  }

  private func fetchGoals() async -> [String] {
    do {
      let goals = try await APIClient.shared.getGoals()
      return goals.filter { $0.isActive }.map { goal in
        let progress = goal.targetValue > 0 ? Int((goal.currentValue / goal.targetValue) * 100) : 0
        return "\(goal.title) (\(progress)% complete)"
      }
    } catch {
      log("AIUserProfileService: Failed to fetch goals: \(error.localizedDescription)")
      return []
    }
  }

  private func fetchConversations() async -> [String] {
    do {
      let sevenDaysAgo = Calendar.current.date(byAdding: .day, value: -7, to: Date())
      let conversations = try await APIClient.shared.getConversations(
        limit: 20,
        startDate: sevenDaysAgo
      )
      return conversations.compactMap { convo in
        let title = convo.structured.title
        let summary = convo.structured.overview
        guard !title.isEmpty else { return nil }
        return "\(title): \(summary)"
      }
    } catch {
      log("AIUserProfileService: Failed to fetch conversations: \(error.localizedDescription)")
      return []
    }
  }

  private func fetchMessages() async -> [String] {
    do {
      let messages = try await APIClient.shared.getMessages(limit: 30)
      return messages.map { "[\($0.sender)] \($0.text)" }
    } catch {
      log("AIUserProfileService: Failed to fetch messages: \(error.localizedDescription)")
      return []
    }
  }

  // MARK: - Errors

  enum ProfileError: LocalizedError {
    case alreadyGenerating
    case insufficientData
    case databaseNotAvailable

    var errorDescription: String? {
      switch self {
      case .alreadyGenerating:
        return "Profile generation is already in progress"
      case .insufficientData:
        return "Not enough data to generate a profile"
      case .databaseNotAvailable:
        return "Database is not available"
      }
    }
  }
}
