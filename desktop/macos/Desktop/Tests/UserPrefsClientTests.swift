import XCTest

@testable import Omi_Computer

/// Tests for the desktop `UserPrefsClient` (v5 port of v3's design — v3
/// committed the design but the file was never landed, so v5 creates it).
///
/// Covers the testable surface:
/// - URL building (trailing slash, no slash, port)
/// - UserPrefs data type (empty, equality, Codable roundtrip)
/// - TaskWeights data type (validation, approximatelyEquals tolerance)
/// - PrefsError equality
///
/// End-to-end HTTP tests are out of scope (would require URLProtocol
/// mocking or a running local backend; both belong in integration tests).
@MainActor
final class UserPrefsClientTests: XCTestCase {

    // MARK: - URL building

    func testEndpointURL_stripsTrailingSlash() {
        let url = UserPrefsClient.endpointURL(base: "http://localhost:8080/")
        XCTAssertEqual(url?.absoluteString, "http://localhost:8080/v1/auto-router/prefs")
    }

    func testEndpointURL_keepsBaseWithoutTrailingSlash() {
        let url = UserPrefsClient.endpointURL(base: "http://localhost:8080")
        XCTAssertEqual(url?.absoluteString, "http://localhost:8080/v1/auto-router/prefs")
    }

    func testEndpointURL_preservesPort() {
        let url = UserPrefsClient.endpointURL(base: "https://example.com:1234")
        XCTAssertEqual(url?.absoluteString, "https://example.com:1234/v1/auto-router/prefs")
    }

    func testEndpointURL_acceptsExplicitPath() {
        // The static also accepts an explicit path override (used by tests).
        let url = UserPrefsClient.endpointURL(base: "http://localhost", path: "/v1/auto-router/prefs")
        XCTAssertEqual(url?.absoluteString, "http://localhost/v1/auto-router/prefs")
    }

    func testEndpointURL_acceptsPathWithoutLeadingSlash() {
        // The endpointPath constant starts with "/" so this is just defensive.
        let url = UserPrefsClient.endpointURL(base: "http://localhost", path: "v1/auto-router/prefs")
        XCTAssertEqual(url?.absoluteString, "http://localhost/v1/auto-router/prefs")
    }

    // MARK: - UserPrefs data type

    func testUserPrefs_emptyByDefault() {
        let prefs = UserPrefs()
        XCTAssertTrue(prefs.overrides.isEmpty)
    }

    func testUserPrefs_emptyConstantIsIdentical() {
        XCTAssertEqual(UserPrefs(), UserPrefs.empty)
        XCTAssertEqual(UserPrefs.empty.overrides.count, 0)
    }

    func testUserPrefs_equalityByContent() {
        let a = UserPrefs(overrides: ["ptt_response": TaskWeights.balanced])
        let b = UserPrefs(overrides: ["ptt_response": TaskWeights.balanced])
        XCTAssertEqual(a, b)
    }

    func testUserPrefs_codableRoundtripWithMultipleOverrides() throws {
        let ptt = try TaskWeights(quality: 0.4, latency: 0.5, cost: 0.1)
        let emb = try TaskWeights(quality: 0.2, latency: 0.3, cost: 0.5)
        let prefs = UserPrefs(overrides: ["ptt_response": ptt, "screenshot_embedding": emb])
        let data = try JSONEncoder().encode(prefs)
        let decoded = try JSONDecoder().decode(UserPrefs.self, from: data)
        XCTAssertEqual(prefs, decoded)
    }

    // MARK: - UserPrefs.from / toRawDict

    func testUserPrefs_fromEmptyRaw() {
        let prefs = UserPrefs.from([:])
        XCTAssertTrue(prefs.overrides.isEmpty)
    }

    func testUserPrefs_fromValidRaw() {
        let raw: [String: [String: Double]] = [
            "ptt_response": ["quality": 0.4, "latency": 0.5, "cost": 0.1]
        ]
        let prefs = UserPrefs.from(raw)
        XCTAssertEqual(prefs.overrides.count, 1)
        // 0.4 + 0.5 + 0.1 = 1.0 ✓ (within tolerance)
        let weights = prefs.overrides["ptt_response"]!
        XCTAssertEqual(weights.quality, 0.4, accuracy: 1e-9)
        XCTAssertEqual(weights.latency, 0.5, accuracy: 1e-9)
        XCTAssertEqual(weights.cost, 0.1, accuracy: 1e-9)
    }

    func testUserPrefs_toRawDictRoundtrip() {
        let raw: [String: [String: Double]] = [
            "transcription": ["quality": 0.3, "latency": 0.6, "cost": 0.1]
        ]
        let prefs = UserPrefs.from(raw)
        XCTAssertEqual(prefs.toRawDict(), raw)
    }

    func testUserPrefs_fromDropsInvalidWeights() {
        // Sum != 1.0 → invalid → dropped.
        let raw: [String: [String: Double]] = [
            "ptt_response": ["quality": 0.5, "latency": 0.5, "cost": 0.5],  // sum 1.5
            "transcription": ["quality": 0.3, "latency": 0.6, "cost": 0.1],  // valid
        ]
        let prefs = UserPrefs.from(raw)
        XCTAssertNil(prefs.overrides["ptt_response"], "Invalid weights should be dropped")
        XCTAssertNotNil(prefs.overrides["transcription"])
    }

    func testUserPrefs_fromDropsMissingFields() {
        // Missing latency → not a TaskWeights → dropped.
        let raw: [String: [String: Double]] = [
            "ptt_response": ["quality": 0.5, "cost": 0.5],  // no latency
        ]
        let prefs = UserPrefs.from(raw)
        XCTAssertTrue(prefs.overrides.isEmpty)
    }

    // MARK: - TaskWeights validation

    func testTaskWeights_balancedSumsToOne() throws {
        let w = try TaskWeights(quality: 1.0 / 3.0, latency: 1.0 / 3.0, cost: 1.0 / 3.0)
        XCTAssertEqual(w.quality, 1.0 / 3.0, accuracy: 1e-9)
        XCTAssertEqual(w.latency, 1.0 / 3.0, accuracy: 1e-9)
        XCTAssertEqual(w.cost, 1.0 / 3.0, accuracy: 1e-9)
    }

    func testTaskWeights_valid() throws {
        let w = try TaskWeights(quality: 0.4, latency: 0.5, cost: 0.1)
        XCTAssertEqual(w.quality, 0.4)
        XCTAssertEqual(w.latency, 0.5)
        XCTAssertEqual(w.cost, 0.1)
    }

    func testTaskWeights_extremeValues() throws {
        // All weight on quality.
        let w = try TaskWeights(quality: 1.0, latency: 0.0, cost: 0.0)
        XCTAssertEqual(w.quality, 1.0)
    }

    func testTaskWeights_toleranceAccepted() throws {
        // Sum = 1.0005 — within tolerance 1e-3 (abs(diff) < 0.001).
        let w = try TaskWeights(quality: 0.4, latency: 0.5, cost: 0.1005)
        XCTAssertEqual(w.cost, 0.1005, accuracy: 1e-9)
    }

    func testTaskWeights_sumTooFarFromOne_rejected() {
        XCTAssertThrowsError(try TaskWeights(quality: 0.5, latency: 0.5, cost: 0.5))  // sum 1.5
        XCTAssertThrowsError(try TaskWeights(quality: 0.0, latency: 0.0, cost: 0.0))  // sum 0.0
    }

    func testTaskWeights_outOfRange_rejected() {
        XCTAssertThrowsError(try TaskWeights(quality: -0.1, latency: 0.6, cost: 0.5))
        XCTAssertThrowsError(try TaskWeights(quality: 1.1, latency: -0.05, cost: -0.05))
    }

    func testTaskWeights_nonFinite_rejected() {
        XCTAssertThrowsError(try TaskWeights(quality: .nan, latency: 0.5, cost: 0.5))
        XCTAssertThrowsError(try TaskWeights(quality: .infinity, latency: 0.5, cost: 0.5))
    }

    // MARK: - TaskWeights approximatelyEquals

    func TaskWeights_approximatelyEquals_toleranceWorks() throws {
        let a = try TaskWeights(quality: 0.4, latency: 0.5, cost: 0.1)
        let b = try TaskWeights(quality: 0.4001, latency: 0.5, cost: 0.0999)
        XCTAssertTrue(a.approximatelyEquals(b))
    }

    func TaskWeights_approximatelyEquals_strictDifferencesRejected() throws {
        let a = try TaskWeights(quality: 0.4, latency: 0.5, cost: 0.1)
        let b = try TaskWeights(quality: 0.5, latency: 0.4, cost: 0.1)
        XCTAssertFalse(a.approximatelyEquals(b))
    }

    // MARK: - PrefsError equality

    func testPrefsError_equalityByCase() {
        XCTAssertEqual(PrefsError.unauthorized, PrefsError.unauthorized)
        XCTAssertEqual(PrefsError.serverError(status: 500), PrefsError.serverError(status: 500))
        XCTAssertNotEqual(PrefsError.serverError(status: 500), PrefsError.serverError(status: 503))
        XCTAssertEqual(
            PrefsError.transport(underlying: "offline"),
            PrefsError.transport(underlying: "offline")
        )
        XCTAssertNotEqual(PrefsError.unauthorized, PrefsError.unavailable)
    }

    // MARK: - PrefsError userMessage

    func testPrefsError_userMessage_unauthorized() {
        XCTAssertTrue(PrefsError.unauthorized.userMessage.contains("Sign in"))
    }

    func testPrefsError_userMessage_invalidWeights() {
        XCTAssertTrue(PrefsError.invalidWeights.userMessage.contains("rejected"))
    }

    func testPrefsError_userMessage_invalidWeight_local() {
        // Local validation (different from server-side invalidWeights).
        XCTAssertTrue(PrefsError.invalidWeight(reason: "sum != 1.0").userMessage.contains("invalid"))
    }

    func testPrefsError_userMessage_unavailable() {
        XCTAssertTrue(PrefsError.unavailable.userMessage.contains("unavailable"))
    }

    func testPrefsError_userMessage_transport() {
        XCTAssertTrue(PrefsError.transport(underlying: "offline").userMessage.contains("Network"))
    }

    func testPrefsError_userMessage_invalidURL() {
        XCTAssertTrue(PrefsError.invalidURL(base: "x").userMessage.contains("misconfigured"))
    }

    func testPrefsError_userMessage_invalidResponse() {
        XCTAssertTrue(PrefsError.invalidResponse.userMessage.contains("unexpected"))
    }

    func testPrefsError_userMessage_decodingFailed() {
        XCTAssertTrue(PrefsError.decodingFailed.userMessage.contains("read the server response"))
    }

    func testPrefsError_userMessage_serverError_includesStatus() {
        // The status code should be in the user-facing message so users can
        // report it when filing a bug.
        let msg = PrefsError.serverError(status: 503).userMessage
        XCTAssertTrue(msg.contains("503"), "server message should include status: \(msg)")
    }
}
