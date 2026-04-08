import Foundation
import os
import QuartzCore

// CRITICAL LIMITATION:
//
// This property wrapper ONLY protects reference replacement, NOT compound operations.
//
// NOT thread-safe (race condition):
//    @OmiAudioLock var counter = 0
//    counter += 1  // Expands to: temp = get(); set(temp + 1) - RACE WINDOW
//
// Thread-safe (atomic replacement):
//    counter = 5
//    context = nil
//
// For compound operations, use withLock:
//    $counter.withLock { $0 += 1 }

/// Thread-safe property wrapper using os_unfair_lock for audio device state
/// accessed from Core Audio real-time threads (~100 callbacks/sec).
///
/// os_unfair_lock: 5-10ns per acquisition vs 50-200ns for DispatchQueue.sync.
/// Only protects whole-value replacement. See header for limitations.
@propertyWrapper
final class OmiAudioLock<T>: @unchecked Sendable {
    private var value: T
    private var lock = os_unfair_lock()

    #if DEBUG
    private var maxLockWaitTime: TimeInterval = 0
    private var lockAcquisitionCount: Int64 = 0
    #endif

    init(wrappedValue: T) {
        self.value = wrappedValue
    }

    var wrappedValue: T {
        get {
            #if DEBUG
            let startTime = CACurrentMediaTime()
            #endif

            os_unfair_lock_lock(&lock)
            defer {
                os_unfair_lock_unlock(&lock)

                #if DEBUG
                let elapsed = CACurrentMediaTime() - startTime
                if elapsed > maxLockWaitTime {
                    maxLockWaitTime = elapsed
                }
                lockAcquisitionCount += 1
                if elapsed > 0.001 {
                    print("[OmiAudioLock] lock held for \(elapsed * 1000)ms")
                }
                #endif
            }
            return value
        }
        set {
            #if DEBUG
            let startTime = CACurrentMediaTime()
            #endif

            os_unfair_lock_lock(&lock)
            defer {
                os_unfair_lock_unlock(&lock)

                #if DEBUG
                let elapsed = CACurrentMediaTime() - startTime
                if elapsed > maxLockWaitTime {
                    maxLockWaitTime = elapsed
                }
                lockAcquisitionCount += 1
                #endif
            }
            value = newValue
        }
    }

    var projectedValue: OmiAudioLock<T> {
        return self
    }

    /// Non-blocking read for real-time threads that cannot afford to wait.
    func tryRead() -> T? {
        guard os_unfair_lock_trylock(&lock) else { return nil }
        defer { os_unfair_lock_unlock(&lock) }
        return value
    }

    /// Execute a block with the lock held for compound operations.
    /// Keep blocks short to avoid blocking audio threads.
    func withLock<R>(_ block: (inout T) throws -> R) rethrows -> R {
        os_unfair_lock_lock(&lock)
        defer { os_unfair_lock_unlock(&lock) }
        return try block(&value)
    }

    /// Force set without locking. Only use during initialization when no other thread can access.
    func unsafeSet(_ newValue: T) {
        value = newValue
    }

    #if DEBUG
    var diagnostics: (maxWaitTime: TimeInterval, acquisitionCount: Int64) {
        os_unfair_lock_lock(&lock)
        defer { os_unfair_lock_unlock(&lock) }
        return (maxLockWaitTime, lockAcquisitionCount)
    }

    func resetDiagnostics() {
        os_unfair_lock_lock(&lock)
        defer { os_unfair_lock_unlock(&lock) }
        maxLockWaitTime = 0
        lockAcquisitionCount = 0
    }
    #endif
}

// MARK: - Convenience Extensions

extension OmiAudioLock where T: Equatable {
    func isEqual(to other: T) -> Bool {
        return wrappedValue == other
    }
}

extension OmiAudioLock {
    var isNil: Bool {
        if let optional = wrappedValue as? any OmiOptionalCheck {
            return optional.isNil
        }
        return false
    }

    var isNotNil: Bool {
        return !isNil
    }
}

private protocol OmiOptionalCheck {
    var isNil: Bool { get }
}

extension Optional: OmiOptionalCheck {
    var isNil: Bool {
        return self == nil
    }
}
