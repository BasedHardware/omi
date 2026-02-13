import Foundation

/// Manages automatic tier gating based on usage criteria.
///
/// Tiers are sequential — you must unlock tier N-1 before tier N:
/// - Tier 0: Show all features (manual override / existing users)
/// - Tier 1: Conversations + Rewind (base, always)
/// - Tier 2: + Memories (100 memories)
/// - Tier 3: + Tasks (100 tasks todo+done)
/// - Tier 4: + AI Chat (100 conversations)
/// - Tier 5: + Dashboard (200 conversations + 2,000 screenshots)
/// - Tier 6: + Apps (300 conversations)
///
/// Checks at most once per day. Never auto-downgrades if user manually set "Show All".
@MainActor
class TierManager {
    static let shared = TierManager()

    // UserDefaults keys
    private let lastTierCheckKey = "lastTierCheckDate"
    private let userShowAllKey = "userShowAllFeatures"     // true if user manually enabled "Show All Features"
    private let currentTierKey = "currentTierLevel"        // Int, 0-6

    // Thresholds (sequential)
    private let tier2MemoriesThreshold = 100
    private let tier3TasksThreshold = 100        // todo + done
    private let tier4ConversationsThreshold = 100
    private let tier5ConversationsThreshold = 200
    private let tier5ScreenshotsThreshold = 2_000
    private let tier6ConversationsThreshold = 300

    private init() {}

    /// Called on app launch (after auth). Checks tier at most once per day.
    func checkTierIfNeeded() async {
        // Skip if user manually set "Show All" (tier 0)
        let userShowAll = UserDefaults.standard.bool(forKey: userShowAllKey)
        if userShowAll { return }

        // Skip if checked today
        let lastCheck = UserDefaults.standard.object(forKey: lastTierCheckKey) as? Date ?? .distantPast
        if Calendar.current.isDateInToday(lastCheck) { return }

        // Mark checked
        UserDefaults.standard.set(Date(), forKey: lastTierCheckKey)

        // Compute and apply
        let newTier = await computeTierLevel()
        let currentTier = UserDefaults.standard.integer(forKey: currentTierKey)

        // Only upgrade, never downgrade automatically
        if newTier > currentTier {
            UserDefaults.standard.set(newTier, forKey: currentTierKey)
            AnalyticsManager.shared.tierChanged(tier: newTier, reason: "auto_upgrade")
            log("TierManager: Auto-upgraded from tier \(currentTier) to tier \(newTier)")
        }
    }

    /// Compute the highest tier the user qualifies for based on sequential criteria.
    private func computeTierLevel() async -> Int {
        do {
            // Fetch all stats in parallel
            async let memoryStats = MemoryStorage.shared.getStats()
            async let filterCounts = ActionItemStorage.shared.getFilterCounts()
            async let conversationsCount = APIClient.shared.getConversationsCount()

            let ms = try await memoryStats
            let filters = try await filterCounts
            let conversations = try await conversationsCount

            let screenshotCount: Int
            do {
                screenshotCount = try await RewindDatabase.shared.getScreenshotCount()
            } catch {
                screenshotCount = 0
            }

            let taskCount = filters.todo + filters.done

            log("TierManager: Stats - memories=\(ms.total), tasks=\(taskCount), conversations=\(conversations), screenshots=\(screenshotCount)")

            // Sequential check: must pass each tier before advancing
            // Tier 1 is always unlocked
            var tier = 1

            // Tier 2: 100 memories
            guard ms.total >= tier2MemoriesThreshold else { return tier }
            tier = 2

            // Tier 3: + 100 tasks
            guard taskCount >= tier3TasksThreshold else { return tier }
            tier = 3

            // Tier 4: + 100 conversations
            guard conversations >= tier4ConversationsThreshold else { return tier }
            tier = 4

            // Tier 5: + 200 conversations + 2,000 screenshots
            guard conversations >= tier5ConversationsThreshold && screenshotCount >= tier5ScreenshotsThreshold else { return tier }
            tier = 5

            // Tier 6: + 300 conversations
            guard conversations >= tier6ConversationsThreshold else { return tier }
            tier = 6

            return tier
        } catch {
            log("TierManager: Eligibility check failed: \(error)")
            return UserDefaults.standard.integer(forKey: currentTierKey).clamped(min: 1)
        }
    }

    /// Called when user manually selects a tier in Settings.
    func userDidSetTier(_ tier: Int) {
        let clamped = max(0, min(6, tier))
        UserDefaults.standard.set(clamped, forKey: currentTierKey)
        // Only lock out auto-check when user explicitly picks "Show All Features" (tier 0).
        // For other tiers, allow auto-upgrade to continue working.
        UserDefaults.standard.set(clamped == 0, forKey: userShowAllKey)
        AnalyticsManager.shared.tierChanged(tier: clamped, reason: "manual")
        log("TierManager: User manually set tier to \(clamped)")
    }

    /// One-time migration for existing users getting this update.
    /// Maps old boolean key to new integer tier:
    /// - `tierGatingEnabled=false` → tier 0 (preserve all features)
    /// - `tierGatingEnabled=true` → tier 1
    static func migrateExistingUsersIfNeeded() {
        let migrationKey = "didMigrateTierGatingV2"
        if !UserDefaults.standard.bool(forKey: migrationKey) {
            UserDefaults.standard.set(true, forKey: migrationKey)

            // Only for existing users (not first launch)
            if UserDefaults.standard.bool(forKey: "hasLaunchedBefore") {
                let oldGatingEnabled = UserDefaults.standard.bool(forKey: "tierGatingEnabled")
                let userOverrode = UserDefaults.standard.bool(forKey: "userOverrodeTier")

                if !oldGatingEnabled || userOverrode {
                    UserDefaults.standard.set(0, forKey: "currentTierLevel")
                    UserDefaults.standard.set(0, forKey: "lastSeenTierLevel")
                    UserDefaults.standard.set(true, forKey: "userShowAllFeatures")
                    log("TierManager: Migration V2 - existing user preserved at tier 0 (show all)")
                } else {
                    UserDefaults.standard.set(1, forKey: "currentTierLevel")
                    UserDefaults.standard.set(1, forKey: "lastSeenTierLevel")
                    log("TierManager: Migration V2 - existing user migrated to tier 1")
                }
            }
        }

        // V3: Fix V2 migration that incorrectly locked all existing users at tier 0.
        // V2 set userShowAllFeatures=true for everyone because tierGatingEnabled didn't
        // exist before tiers were introduced (defaulting to false). Clear the flag so
        // auto-evaluation can compute their actual tier. Only users who manually pick
        // "Show All Features" in Settings should be locked at tier 0.
        // Keep currentTierLevel at 0 (show all) so users don't flash to a reduced UI;
        // checkTierIfNeeded() will "upgrade" from 0 to their computed tier in one step.
        let v3Key = "didMigrateTierGatingV3"
        if !UserDefaults.standard.bool(forKey: v3Key) {
            UserDefaults.standard.set(true, forKey: v3Key)

            if UserDefaults.standard.bool(forKey: "userShowAllFeatures") {
                UserDefaults.standard.set(false, forKey: "userShowAllFeatures")
                // Clear last check date so checkTierIfNeeded() runs immediately
                UserDefaults.standard.removeObject(forKey: "lastTierCheckDate")
                log("TierManager: Migration V3 - cleared userShowAllFeatures, keeping tier 0 for seamless re-evaluation")
            }
        }
    }
}

// MARK: - Helpers
private extension Int {
    func clamped(min: Int) -> Int {
        return Swift.max(self, min)
    }
}
