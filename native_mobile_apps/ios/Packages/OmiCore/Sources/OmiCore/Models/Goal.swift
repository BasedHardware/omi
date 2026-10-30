import Foundation

/// Something the user works toward, with a number to track (`GoalResponse`, numeric goals as in
/// Flutter's goals widget: current of target).
public struct Goal: Identifiable, Hashable, Sendable {
    public let id: String
    public var title: String
    public var current: Double
    public var target: Double
    public var unit: String?
    public let createdAt: Date?

    public init(id: String, title: String, current: Double, target: Double, unit: String? = nil, createdAt: Date? = nil) {
        self.id = id
        self.title = title
        self.current = current
        self.target = target
        self.unit = unit
        self.createdAt = createdAt
    }

    /// 0...1, as Flutter's `progressPercentage`: a goal without a target is done once it has any progress.
    public var progress: Double {
        guard target > 0 else { return current > 0 ? 1 : 0 }
        return min(max(current / target, 0), 1)
    }
}
