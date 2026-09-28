import Foundation

/// A minimal mutex-protected value box, used where the TypeScript closures
/// captured mutable parser state across stream callbacks.
public final class LockedBox<T>: @unchecked Sendable {
    private var value: T
    private let lock = NSLock()

    public init(_ value: T) {
        self.value = value
    }

    public func withLock<R>(_ body: (inout T) throws -> R) rethrows -> R {
        lock.lock()
        defer { lock.unlock() }
        return try body(&value)
    }

    public func set(_ newValue: T) {
        lock.lock()
        value = newValue
        lock.unlock()
    }

    public func get() -> T {
        lock.lock()
        defer { lock.unlock() }
        return value
    }
}
