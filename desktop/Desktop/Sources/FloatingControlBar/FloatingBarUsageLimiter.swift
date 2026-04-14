import Foundation

/// Tracks AI chat/query usage and enforces a shared monthly limit for free users.
///
/// Shared between the floating bar (Ask omi / PTT queries) and the main chat page
/// (ChatProvider.sendMessage). A single 30-message monthly pool is counted against
/// both surfaces so the free tier can't be stretched by bouncing between the two.
@MainActor
final class FloatingBarUsageLimiter: ObservableObject {
    static let shared = FloatingBarUsageLimiter()

    /// Monthly free cap, shared across floating bar + main chat.
    static let monthlyFreeLimit = 30

    /// Rolling window in seconds (30 days).
    static let windowSeconds: Double = 30 * 24 * 3600

    private static let queryTimestampsKey = "floatingBar_queryTimestamps"
    private static let cachedPlanKey = "floatingBar_cachedPlan"

    @Published private(set) var monthlyQueriesUsed: Int = 0
    @Published private(set) var hasPaidPlan: Bool = false
    private var planFetched = false

    private init() {
        hasPaidPlan = UserDefaults.standard.string(forKey: Self.cachedPlanKey).map { $0 != "basic" } ?? false
        pruneAndCount()
    }

    /// Fetch the user's subscription plan from the backend (call on app launch / sign-in).
    func fetchPlan() async {
        do {
            let response = try await APIClient.shared.getUserSubscription()
            applyPlan(plan: response.subscription.plan, status: response.subscription.status)
        } catch {
            log("FloatingBarUsageLimiter: failed to fetch plan: \(error.localizedDescription)")
        }
    }

    /// Update cached plan directly from an already-fetched subscription (no extra API call).
    func applyPlan(plan: SubscriptionPlanType, status: SubscriptionStatusType) {
        hasPaidPlan = plan != .basic && status == .active
        UserDefaults.standard.set(plan.rawValue, forKey: Self.cachedPlanKey)
        planFetched = true
    }

    var isLimitReached: Bool {
        !hasPaidPlan && monthlyQueriesUsed >= Self.monthlyFreeLimit
    }

    var remainingQueries: Int {
        hasPaidPlan ? .max : max(0, Self.monthlyFreeLimit - monthlyQueriesUsed)
    }

    /// Record a query. Call after successfully sending a query from the floating bar
    /// OR the main chat page — both surfaces share this pool.
    func recordQuery() {
        var timestamps = loadTimestamps()
        timestamps.append(Date().timeIntervalSince1970)
        UserDefaults.standard.set(timestamps, forKey: Self.queryTimestampsKey)
        pruneAndCount()
    }

    private func pruneAndCount() {
        let cutoff = Date().timeIntervalSince1970 - Self.windowSeconds
        var timestamps = loadTimestamps()
        timestamps.removeAll { $0 < cutoff }
        UserDefaults.standard.set(timestamps, forKey: Self.queryTimestampsKey)
        monthlyQueriesUsed = timestamps.count
    }

    private func loadTimestamps() -> [Double] {
        UserDefaults.standard.array(forKey: Self.queryTimestampsKey) as? [Double] ?? []
    }
}
