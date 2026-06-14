import Foundation

/// Tiny time-to-live cache. Stops thrashing the network for data that only
/// changes on the order of seconds (chat quota, plan info, etc.).
///
/// Pure value type — no I/O, no actors, no global state. The caller decides
/// what "now" means (production uses `Date()`; tests use a fixed instant) so
/// the freshness check is fully deterministic.
///
/// Use the `get(now:)` / `set(_:now:)` entry points for the typical pattern;
/// `isFresh(now:)` is exposed for cases where the caller already has the
/// cached value and just wants to know whether to refetch.
public struct TTLCache<Value: Sendable>: Sendable {
    /// The current cached value, if any, and the wall-clock time it was
    /// stored. `value` is nil when the cache is empty.
    public private(set) var entry: (value: Value, storedAt: Date)?

    /// How long an entry is considered fresh. Once `now - storedAt > ttl`,
    /// `get(now:)` returns nil and `isFresh(now:)` returns false.
    public let ttl: TimeInterval

    public init(ttl: TimeInterval) {
        precondition(ttl >= 0, "TTLCache.ttl must be non-negative")
        self.ttl = ttl
        self.entry = nil
    }

    /// Returns the cached value if it's still fresh, otherwise nil.
    /// `now` is injectable so tests don't depend on wall-clock time.
    public func get(now: Date) -> Value? {
        guard let entry = entry else { return nil }
        let age = now.timeIntervalSince(entry.storedAt)
        return age <= ttl ? entry.value : nil
    }

    /// Stores `value` at `now`, overwriting any previous entry. Stale values
    /// are silently overwritten — callers don't need to invalidate manually.
    public mutating func set(_ value: Value, now: Date) {
        entry = (value: value, storedAt: now)
    }

    /// Removes the cached entry. Use when the underlying source-of-truth has
    /// changed in a way the TTL can't detect (e.g. user upgraded plan via
    /// Settings; checkout completed; sign-out).
    public mutating func invalidate() {
        entry = nil
    }

    /// True if there is an entry AND it hasn't expired.
    public func isFresh(now: Date) -> Bool {
        get(now: now) != nil
    }
}
