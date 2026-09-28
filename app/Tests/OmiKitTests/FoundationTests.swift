import XCTest

@testable import OmiKit

final class FoundationTests: XCTestCase {
    func testParseOriginAcceptsStampedV5Origins() {
        XCTAssertEqual(
            parseOrigin("https://api.omi.me"),
            BackendOrigin(
                hostname: "api.omi.me", origin: "https://api.omi.me", port: "",
                isSecure: true
            )
        )
        XCTAssertEqual(
            parseOrigin("HTTP://Example.COM:8787/"),
            BackendOrigin(
                hostname: "example.com", origin: "http://example.com:8787",
                port: "8787", isSecure: false
            )
        )
        // Default ports are elided.
        XCTAssertEqual(
            parseOrigin("https://example.com:443")?.origin,
            "https://example.com"
        )
        XCTAssertEqual(
            parseOrigin("http://example.com:80")?.origin, "http://example.com"
        )
        // Loopback IPv6.
        XCTAssertEqual(
            parseOrigin("http://[::1]:8787"),
            BackendOrigin(
                hostname: "::1", origin: "http://[::1]:8787", port: "8787",
                isSecure: false
            )
        )
    }

    func testParseOriginRejectsInvalidValues() {
        XCTAssertNil(parseOrigin("https://"))
        XCTAssertNil(parseOrigin("https://example.com/path"))
        XCTAssertNil(parseOrigin("https://example.com?q=1"))
        XCTAssertNil(parseOrigin("https://example.com#frag"))
        XCTAssertNil(parseOrigin("https://[::2]:8787"))
        XCTAssertNil(parseOrigin("https://[::1]:0"))
        XCTAssertNil(parseOrigin("https://example.com:65536"))
        XCTAssertNil(parseOrigin("https://exa_mple.com"))
        XCTAssertNil(parseOrigin("example.com"))
        XCTAssertNil(parseOrigin("https://user@example.com"))
    }

    func testLoopbackHostname() {
        XCTAssertTrue(isLoopbackHostname("localhost"))
        XCTAssertTrue(isLoopbackHostname("[::1]"))
        XCTAssertTrue(isLoopbackHostname("127.0.0.1"))
        XCTAssertFalse(isLoopbackHostname("api.omi.me"))
    }

    func testRouteResolution() {
        XCTAssertEqual(Route.resolve("Tasks"), .Tasks)
        XCTAssertEqual(Route.resolve("nope"), .Home)
        XCTAssertEqual(Route.resolve(nil), .Home)
        // Paired maps must agree in both directions — except Memories,
        // which deliberately lands on the mobile home route.
        for route in Route.allCases {
            if route == .Memories {
                XCTAssertEqual(route.mobileRoute, .home, route.rawValue)
            } else {
                XCTAssertEqual(route.mobileRoute.route, route, route.rawValue)
            }
        }
        for mobile in MobileRoute.allCases {
            XCTAssertEqual(mobile.route.mobileRoute, mobile, mobile.rawValue)
        }
    }

    func testTaskGrouping() {
        let now: Int64 = 1_789_000_000_000
        XCTAssertEqual(taskGroup(dueAt: nil, nowMilliseconds: now), .later)
        XCTAssertEqual(taskGroup(dueAt: now, nowMilliseconds: now), .today)
        XCTAssertEqual(taskGroup(dueAt: now - 86_400_000, nowMilliseconds: now), .today)
        XCTAssertEqual(
            taskGroup(dueAt: now + 86_400_000, nowMilliseconds: now), .tomorrow
        )
        XCTAssertEqual(
            taskGroup(dueAt: now + 5 * 86_400_000, nowMilliseconds: now), .later
        )
    }

    func testConversationGroupLabel() {
        // 2026-09-13T01:00:00Z
        let now: Int64 = 1_789_261_200_000
        XCTAssertEqual(
            conversationGroupLabel("2026-09-13T10:20:00Z", nowEpochMilliseconds: now),
            "Today"
        )
        XCTAssertEqual(
            conversationGroupLabel("2026-09-12T23:00:00Z", nowEpochMilliseconds: now),
            "Yesterday"
        )
    }

    func testISOReader() {
        XCTAssertEqual(ISO8601Reader.epochSeconds("1970-01-01T00:00:20Z"), 20)
        XCTAssertEqual(
            ISO8601Reader.epochSeconds("2026-01-01T00:00:00Z").map { Int($0) },
            1_767_225_600
        )
        XCTAssertNil(ISO8601Reader.epochSeconds("not-a-date"))
    }

    // MARK: C++ middleware binding (the shared native-core policy)

    func testMiddlewarePolicyCapturePathAllowlist() {
        XCTAssertTrue(Policy.isCapturePath("/v1/live/sessions?retry=1"))
        XCTAssertTrue(Policy.isCapturePath("/v1/chat-messages"))
        XCTAssertTrue(Policy.isCapturePath("/v1/device-sessions/abc/audio"))
        XCTAssertTrue(Policy.isCapturePath("/v1/conversations"))
        XCTAssertFalse(Policy.isCapturePath("/v1/live/sessions-extra"))
        XCTAssertFalse(Policy.isCapturePath("/v1/device-sessions-extra"))
        XCTAssertFalse(Policy.isCapturePath("/nonexistent"))
    }

    func testMiddlewarePolicyTimeoutTable() {
        XCTAssertEqual(
            Policy.requestTimeoutSeconds(
                method: "POST", path: "/v1/device-sessions/abc/transcribe"
            ),
            150
        )
        XCTAssertEqual(
            Policy.requestTimeoutSeconds(method: "GET", path: "/v1/tasks"), 60
        )
    }

    func testMiddlewarePolicyHostnameClasses() {
        XCTAssertTrue(Policy.isLoopbackHostname("LOCALHOST"))
        XCTAssertTrue(Policy.isLoopbackHostname("[::1]"))
        XCTAssertTrue(Policy.isCloudHostname("api.omi.me"))
        XCTAssertFalse(Policy.isCloudHostname("example.invalid"))
    }

    func testMiddlewareCodec() {
        // Framed packet normalization round trip through the C++ codec.
        let empty = Policy.normalizePacket([])
        XCTAssertNotEqual(empty.status, 0)
        let capabilities = Policy.nativeCapabilities()
        XCTAssertNotNil(capabilities)
        XCTAssertTrue(capabilities?.hasPrefix("{") == true)
    }

    func testMiddlewareSoftwarePlane() {
        // Stored preference wins ("new" only); otherwise stamped origin decides.
        XCTAssertTrue(Policy.softwarePlaneIsNew(stored: "new", stampedValid: false))
        XCTAssertFalse(Policy.softwarePlaneIsNew(stored: "old", stampedValid: true))
        XCTAssertTrue(Policy.softwarePlaneIsNew(stored: nil, stampedValid: true))
        XCTAssertFalse(Policy.softwarePlaneIsNew(stored: nil, stampedValid: false))
    }
}
