import GRDB

/// Forward-only retirement of the local AI user profile history.
///
/// The backend owns the profile (`GET /v1/users/ai-profile`) and keeps no history, so the
/// `ai_user_profiles` table has no reader or writer. Dropping it removes stale profile text
/// from disk and from the schema the chat SQL tool exposes. The historical
/// `createAIUserProfiles` registration stays so installed databases keep their ledger.
enum LocalProfileHistoryRetirementMigration {
  static let retiredTable = "ai_user_profiles"

  static func registerMigration(on migrator: inout DatabaseMigrator) {
    migrator.registerMigration("retireAIUserProfileHistory") { db in
      try db.execute(sql: "DROP TABLE IF EXISTS \(retiredTable)")
    }
  }
}
