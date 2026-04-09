import Foundation

/// Tracks weekly floating bar query usage and enforces limits for free users.
@MainActor
final class FloatingBarUsageLimiter: ObservableObject {
    static let shared = FloatingBarUsageLimiter()

    static let weeklyFreeLimit = 50

    private static let queryTimestampsKey = "floatingBar_queryTimestamps"
    private static let cachedPlanKey = "floatingBar_cachedPlan"

    @Published private(set) var weeklyQueriesUsed: Int = 0
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
            let plan = response.subscription.plan
            hasPaidPlan = plan != .basic && response.subscription.status == .active
            UserDefaults.standard.set(plan.rawValue, forKey: Self.cachedPlanKey)
            planFetched = true
        } catch {
            log("FloatingBarUsageLimiter: failed to fetch plan: \(error.localizedDescription)")
        }
    }

    var isLimitReached: Bool {
        !hasPaidPlan && weeklyQueriesUsed >= Self.weeklyFreeLimit
    }

    var remainingQueries: Int {
        hasPaidPlan ? .max : max(0, Self.weeklyFreeLimit - weeklyQueriesUsed)
    }

    /// Record a query. Call after successfully sending a floating bar query.
    func recordQuery() {
        var timestamps = loadTimestamps()
        timestamps.append(Date().timeIntervalSince1970)
        UserDefaults.standard.set(timestamps, forKey: Self.queryTimestampsKey)
        pruneAndCount()
    }

    private func pruneAndCount() {
        let cutoff = Date().timeIntervalSince1970 - 7 * 24 * 3600
        var timestamps = loadTimestamps()
        timestamps.removeAll { $0 < cutoff }
        UserDefaults.standard.set(timestamps, forKey: Self.queryTimestampsKey)
        weeklyQueriesUsed = timestamps.count
    }

    private func loadTimestamps() -> [Double] {
        UserDefaults.standard.array(forKey: Self.queryTimestampsKey) as? [Double] ?? []
    }
}
