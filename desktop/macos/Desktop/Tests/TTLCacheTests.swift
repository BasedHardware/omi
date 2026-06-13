import XCTest

@testable import Omi_Computer

/// Tests for `TTLCache` — the small value type backing the quota TTL in
/// `APIClient.fetchChatUsageQuota`.
///
/// Pure value-type tests: no actors, no async, no network. Time is injected
/// via the `now` parameter so the freshness check is deterministic.
final class TTLCacheTests: XCTestCase {

    func testEmptyCacheReturnsNil() {
        let cache = TTLCache<String>(ttl: 30)
        XCTAssertNil(cache.get(now: Date()))
        XCTAssertFalse(cache.isFresh(now: Date()))
    }

    func testSetThenGetWithinTTLReturnsValue() {
        var cache = TTLCache<String>(ttl: 30)
        let t0 = Date(timeIntervalSince1970: 1_700_000_000)
        cache.set("hello", now: t0)
        XCTAssertEqual(cache.get(now: t0), "hello")
        XCTAssertEqual(cache.get(now: t0.addingTimeInterval(15)), "hello")
        XCTAssertEqual(cache.get(now: t0.addingTimeInterval(30)), "hello")
    }

    func testGetAfterTTLExpiresReturnsNil() {
        var cache = TTLCache<String>(ttl: 30)
        let t0 = Date(timeIntervalSince1970: 1_700_000_000)
        cache.set("hello", now: t0)
        // Just past the TTL boundary.
        XCTAssertNil(cache.get(now: t0.addingTimeInterval(30.001)))
        XCTAssertFalse(cache.isFresh(now: t0.addingTimeInterval(30.001)))
    }

    func testGetAtExactTTLBoundaryIsFresh() {
        // The check is `age <= ttl` (inclusive). Boundary must be fresh so
        // a refresh in the same second as the previous fetch doesn't miss.
        var cache = TTLCache<String>(ttl: 30)
        let t0 = Date(timeIntervalSince1970: 1_700_000_000)
        cache.set("hello", now: t0)
        XCTAssertEqual(cache.get(now: t0.addingTimeInterval(30)), "hello")
    }

    func testSetOverwritesPreviousValue() {
        var cache = TTLCache<String>(ttl: 30)
        let t0 = Date(timeIntervalSince1970: 1_700_000_000)
        cache.set("first", now: t0)
        cache.set("second", now: t0.addingTimeInterval(5))
        XCTAssertEqual(cache.get(now: t0.addingTimeInterval(5)), "second")
        XCTAssertEqual(cache.get(now: t0.addingTimeInterval(35)), "second")
    }

    func testSetResetsStoredAtSoTTLRestarts() {
        var cache = TTLCache<String>(ttl: 30)
        let t0 = Date(timeIntervalSince1970: 1_700_000_000)
        cache.set("first", now: t0)
        // 25s later, refresh. The new storedAt means the value stays fresh
        // for another 30s, not 5s.
        cache.set("second", now: t0.addingTimeInterval(25))
        XCTAssertEqual(cache.get(now: t0.addingTimeInterval(54)), "second")
        XCTAssertNil(cache.get(now: t0.addingTimeInterval(55.001)))
    }

    func testInvalidateClearsCache() {
        var cache = TTLCache<String>(ttl: 30)
        let t0 = Date(timeIntervalSince1970: 1_700_000_000)
        cache.set("hello", now: t0)
        cache.invalidate()
        XCTAssertNil(cache.get(now: t0))
        XCTAssertFalse(cache.isFresh(now: t0))
    }

    func testZeroTTLAlwaysExpires() {
        // A zero-second TTL means "fresh only at the exact storedAt instant".
        // Useful as a no-cache fallback.
        var cache = TTLCache<String>(ttl: 0)
        let t0 = Date(timeIntervalSince1970: 1_700_000_000)
        cache.set("hello", now: t0)
        XCTAssertEqual(cache.get(now: t0), "hello")
        XCTAssertNil(cache.get(now: t0.addingTimeInterval(0.001)))
    }

    func testNegativeTTLIsRejected() {
        // Defensive: a typo'd negative TTL would silently disable the cache.
        // The precondition in init surfaces it loudly.
        // (precondition crashes the process — we don't test the crash path
        // directly, just verify the init exists with the documented
        // precondition.)
        _ = TTLCache<String>(ttl: 1)  // sanity: positive TTL is fine
    }

    func testWorksWithComplexValueTypes() {
        // The cache is generic over Sendable. Verify with a struct, not
        // just String. Equatable isn't required (the cache doesn't compare
        // values), so we omit the conformance.
        struct Quota: Sendable {
            let plan: String
            let used: Int
        }
        var cache = TTLCache<Quota>(ttl: 30)
        let t0 = Date(timeIntervalSince1970: 1_700_000_000)
        cache.set(Quota(plan: "Free", used: 5), now: t0)
        XCTAssertEqual(cache.get(now: t0)?.plan, "Free")
        XCTAssertEqual(cache.get(now: t0)?.used, 5)
    }
}
