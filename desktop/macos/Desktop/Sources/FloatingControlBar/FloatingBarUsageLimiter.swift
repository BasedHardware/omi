import Foundation

/// Tracks AI chat/query usage and enforces limits using the server-side quota.
///
/// Shared between the floating bar (Ask omi / PTT queries) and the main chat page
/// (ChatProvider.sendMessage). The server endpoint `/v1/users/me/usage-quota` is
/// the single source of truth for the current month's usage and plan limit.
@MainActor
final class FloatingBarUsageLimiter: ObservableObject {
    static let shared = FloatingBarUsageLimiter()

    private static let cachedPlanKey = "floatingBar_cachedPlan"

    @Published private(set) var hasPaidPlan: Bool = false

    /// True when the user is on Neo (unlimited) without desktop access — Neo is a
    /// mobile/web plan, so on desktop we surface a banner nudging them to Operator.
    /// Grandfathered Neo subscribers (desktopGrandfatherUntil set) are excluded.
    @Published private(set) var neoNeedsDesktopUpgrade: Bool = false

    /// Server-reported quota snapshot, plus an optimistic local delta for queries
    /// sent since the last server sync.
    private(set) var serverQuota: APIClient.ChatUsageQuota?
    private(set) var optimisticDelta: Int = 0

    init() {
        hasPaidPlan =
            UserDefaults.standard.string(forKey: Self.cachedPlanKey).map { $0 != "basic" } ?? false
    }

    /// Fetch the user's subscription plan and usage quota from the backend.
    /// Call on app launch, sign-in, and after checkout completes.
    func fetchPlan() async {
        do {
            let response = try await APIClient.shared.getUserSubscription()
            applyPlan(plan: response.subscription.plan, status: response.subscription.status)
            // Neo (unlimited) has no desktop entitlement; show the upgrade banner
            // unless this subscriber is grandfathered for the current period or is
            // BYOK-active (BYOK users pay their own LLM/STT bill and the backend
            // grants them desktop access, so the "upgrade to Operator" nudge would
            // be wrong for them).
            neoNeedsDesktopUpgrade =
                response.subscription.plan == .unlimited
                && response.desktopGrandfatherUntil == nil
                && !APIKeyService.isByokActive
        } catch {
            log("FloatingBarUsageLimiter: failed to fetch plan: \(error.localizedDescription)")
        }
        await syncQuota()
    }

    /// Sync quota from the server, resetting the optimistic delta.
    func syncQuota() async {
        if let quota = await APIClient.shared.fetchChatUsageQuota() {
            applyQuota(quota)
        }
    }

    /// Apply a quota snapshot directly (used by syncQuota and tests).
    func applyQuota(_ quota: APIClient.ChatUsageQuota) {
        serverQuota = quota
        optimisticDelta = 0
    }

    /// Update cached plan directly from an already-fetched subscription (no extra API call).
    func applyPlan(plan: SubscriptionPlanType, status: SubscriptionStatusType) {
        hasPaidPlan = plan != .basic && status == .active
        UserDefaults.standard.set(plan.rawValue, forKey: Self.cachedPlanKey)
    }

    /// Reset all quota state on sign-out so the next user starts clean.
    func reset() {
        serverQuota = nil
        optimisticDelta = 0
        hasPaidPlan = false
        neoNeedsDesktopUpgrade = false
        UserDefaults.standard.removeObject(forKey: Self.cachedPlanKey)
    }

    var isLimitReached: Bool {
        // BYOK users pay their own LLM bill and are never limited. Honor local
        // BYOK state so a heartbeat-lagged server quota (allowed=false right
        // after activation) can't block chat for a fully-configured BYOK user.
        if APIKeyService.isByokActive {
            return false
        }
        guard let quota = serverQuota else {
            // No server data yet — allow the query (server will enforce).
            return false
        }
        if quota.allowed {
            // Optimistic delta only applies to question-based quotas.
            // For cost_usd (Architect/Pro), we can't estimate cost per query
            // locally — rely on the server snapshot alone.
            guard quota.unit == "questions", let limit = quota.limit else { return false }
            return (quota.used + Double(optimisticDelta)) >= limit
        }
        return true
    }

    var remainingQueries: Int {
        guard let quota = serverQuota else { return .max }
        guard quota.unit == "questions", let limit = quota.limit else { return .max }
        return max(0, Int(limit - quota.used) - optimisticDelta)
    }

    /// Human-readable limit text for error messages.
    var limitDescription: String {
        guard let quota = serverQuota, let limit = quota.limit else {
            return "your monthly free message limit"
        }
        if quota.unit == "cost_usd" {
            return String(format: "your $%.0f %@ monthly spend limit", limit, quota.plan)
        }
        return "\(Int(limit)) \(quota.plan) messages this month"
    }

    /// Record a query. Call after successfully sending a query from the floating bar
    /// OR the main chat page — both surfaces share this pool.
    func recordQuery() {
        optimisticDelta += 1
    }
}
