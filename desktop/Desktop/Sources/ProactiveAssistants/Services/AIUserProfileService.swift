import Foundation
import GRDB

// MARK: - Database Record

/// Database record for AI-generated user profile history
struct AIUserProfileRecord: Codable, FetchableRecord, PersistableRecord, Identifiable {
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

    private var backendService: BackendProactiveService?
    private let maxProfileLength = 10000

    /// Whether profile generation is currently in progress
    private var isGenerating = false

    /// Cached database pool
    private var _dbQueue: DatabasePool?

    /// Invalidate cached DB queue (called on user switch / sign-out)
    func invalidateCache() {
        _dbQueue = nil
    }

    /// Set the backend service for Phase 2 server-side profile generation.
    func configure(backendService: BackendProactiveService) {
        self.backendService = backendService
    }

    // MARK: - Database Access

    private func ensureDB() async throws -> DatabasePool {
        if let db = _dbQueue { return db }
        try await RewindDatabase.shared.initialize()
        guard let db = await RewindDatabase.shared.getDatabaseQueue() else {
            throw ProfileError.databaseNotAvailable
        }
        _dbQueue = db
        return db
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
            guard let latest else { return true } // Never generated
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
        guard let db = try? await ensureDB() else {
            log("AIUserProfileService: DB not available for saving exploration profile")
            return false
        }
        let generatedAt = Date()
        let record = AIUserProfileRecord(
            profileText: String(text.prefix(maxProfileLength)),
            dataSourcesUsed: 1,
            backendSynced: false,
            generatedAt: generatedAt
        )
        do {
            let insertedId = try await db.write { database -> Int64? in
                let mutableRecord = record
                try mutableRecord.insert(database)
                return mutableRecord.id
            }
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
        return (try? await db.read { database in
            try AIUserProfileRecord
                .order(Column("generatedAt").desc)
                .limit(limit)
                .fetchAll(database)
        }) ?? []
    }

    /// Generate a new AI user profile via backend WebSocket.
    /// The backend fetches all user data from Firestore and generates the profile server-side.
    func generateProfile() async throws -> AIUserProfileRecord {
        guard !isGenerating else {
            throw ProfileError.alreadyGenerating
        }
        guard let service = backendService else {
            throw ProfileError.databaseNotAvailable
        }
        isGenerating = true
        defer { isGenerating = false }

        log("AIUserProfileService: Requesting server-side profile generation")

        let profileText = try await service.requestProfile()
        let truncated = String(profileText.prefix(maxProfileLength))
        let generatedAt = Date()

        log("AIUserProfileService: Received profile from backend (\(truncated.count) chars)")

        // Save to local database
        let db = try await ensureDB()
        let record = AIUserProfileRecord(
            profileText: truncated,
            dataSourcesUsed: 0,
            backendSynced: true,  // Backend already has it
            generatedAt: generatedAt
        )
        try await db.write { database in
            try record.insert(database)
        }

        log("AIUserProfileService: Profile saved to local DB")
        return record
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
