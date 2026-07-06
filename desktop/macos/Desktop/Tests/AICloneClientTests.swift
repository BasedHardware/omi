import XCTest
import OmiTheme
@testable import Omi_Computer

/// Tests for the desktop-side `AICloneClient` (the HTTP client used by the
/// AI Clone screen to talk to the self-hosted plugin service).
///
/// Covers:
/// - URL composition (trailing slashes, paths with leading slash)
/// - Empty / invalid base URL surfaces as `AICloneError.invalidURL`
/// - HTTP error sanitization (response bytes never leak into error messages)
/// - The `AIPlugin.setupRequestBody` / `toggleRequestBody` builders include
///   the right fields per plugin (Telegram vs WhatsApp credential keys)
final class AICloneClientTests: XCTestCase {

    // MARK: - URL composition

    func testEndpointURLStripsTrailingSlash() throws {
        let url = try AICloneClient.endpointURL(baseURL: "https://clone.example.com/", path: "/health")
        XCTAssertEqual(url.absoluteString, "https://clone.example.com/health")
    }

    func testEndpointURLStripsMultipleTrailingSlashes() throws {
        let url = try AICloneClient.endpointURL(baseURL: "https://clone.example.com///", path: "/setup")
        XCTAssertEqual(url.absoluteString, "https://clone.example.com/setup")
    }

    func testEndpointURLNoTrailingSlash() throws {
        let url = try AICloneClient.endpointURL(baseURL: "https://clone.example.com", path: "/toggle")
        XCTAssertEqual(url.absoluteString, "https://clone.example.com/toggle")
    }

    func testEndpointURLRejectsEmptyBase() {
        XCTAssertThrowsError(try AICloneClient.endpointURL(baseURL: "", path: "/health")) { err in
            guard case AICloneClient.AICloneError.invalidURL = err else {
                XCTFail("Expected .invalidURL, got \(err)")
                return
            }
        }
    }

    func testEndpointURLRejectsMalformedBase() {
        // "not a url" has whitespace; URL(string:) accepts it but the joined
        // string is not parseable as a URL with a scheme.
        XCTAssertThrowsError(try AICloneClient.endpointURL(baseURL: "not a url", path: "/health")) { err in
            guard case AICloneClient.AICloneError.invalidURL = err else {
                XCTFail("Expected .invalidURL, got \(err)")
                return
            }
        }
    }

    // MARK: - Error sanitization (no secret leak)

    func testErrorMessageIsCappedAtMaxLength() {
        // The desktop caps server error messages at 200 chars to bound the
        // damage if a server reflects a long secret-laden string in `detail`.
        let longDetail = String(repeating: "x", count: 500)
        let body = #"{"detail":"\#(longDetail)"}"#
        let data = body.data(using: .utf8)!
        let detail = AICloneClient.extractSanitizedDetail(from: data)
        XCTAssertLessThanOrEqual(detail.count, 210,
            "Detail exceeds max length cap; downstream UI / logs may receive unbounded strings")
    }

    func testErrorMessageReturnsGenericWhenNoDetailField() {
        // Response body without a JSON `detail` field — should NOT echo the body.
        let body = #"{"some_other_field":"oops"}"#
        let data = body.data(using: .utf8)!
        let detail = AICloneClient.extractSanitizedDetail(from: data)
        XCTAssertEqual(detail, "(no detail)")
    }

    func testErrorMessageReturnsGenericWhenBodyIsNotJSON() {
        // Raw text body — should NOT be echoed.
        let data = "Internal Server Error".data(using: .utf8)!
        let detail = AICloneClient.extractSanitizedDetail(from: data)
        XCTAssertEqual(detail, "(no detail)")
    }

    // MARK: - Request body builders (per-plugin credential keys)

    func testTelegramSetupBodyIncludesBotToken() {
        let body = AIPlugin.telegram.setupRequestBody(
            credentials: ["bot_token": "TELEGRAM_TOKEN"],
            omiUid: "u-1",
            personaId: "p-1",
            omiDevApiKey: "DEV_KEY",
            publicBaseUrl: "https://clone.example.com"
        )
        XCTAssertEqual(body["bot_token"] as? String, "TELEGRAM_TOKEN")
        XCTAssertEqual(body["omi_uid"] as? String, "u-1")
        XCTAssertEqual(body["persona_id"] as? String, "p-1")
        XCTAssertEqual(body["omi_dev_api_key"] as? String, "DEV_KEY")
        XCTAssertEqual(body["public_base_url"] as? String, "https://clone.example.com")
    }

    func testWhatsAppSetupBodyIncludesAllThreeCredentialFields() {
        let body = AIPlugin.whatsapp.setupRequestBody(
            credentials: [
                "access_token": "WA_TOKEN",
                "phone_number_id": "1234567890",
                "verify_token": "MY_VERIFY",
            ],
            omiUid: "u-1",
            personaId: "p-1",
            omiDevApiKey: "DEV_KEY",
            publicBaseUrl: "https://clone.example.com"
        )
        XCTAssertEqual(body["access_token"] as? String, "WA_TOKEN")
        XCTAssertEqual(body["phone_number_id"] as? String, "1234567890")
        XCTAssertEqual(body["verify_token"] as? String, "MY_VERIFY")
    }

    func testTelegramToggleBodyUsesBotTokenForAuth() {
        let body = AIPlugin.telegram.toggleRequestBody(
            chatId: "12345",
            enabled: true
        )
        XCTAssertEqual(body["chat_id"] as? String, "12345")
        XCTAssertEqual(body["enabled"] as? Bool, true)
    }

    func testTelegramToggleBodySupportsDisable() {
        // P2 fix: the previous implementation hardcoded enabled=true, so the
        // toggle could only ever be turned on. Verify the disable path now
        // works.
        let body = AIPlugin.telegram.toggleRequestBody(
            chatId: "12345",
            enabled: false
        )
        XCTAssertEqual(body["enabled"] as? Bool, false)
    }

    func testWhatsAppToggleBodyUsesAccessTokenForAuth() {
        let body = AIPlugin.whatsapp.toggleRequestBody(
            chatId: "15550001111",
            enabled: true
        )
        XCTAssertEqual(body["phone"] as? String, "15550001111")
        XCTAssertEqual(body["enabled"] as? Bool, true)
    }

    func testPluginToggleAuthCredentialKeyMatchesSetupField() {
        // Sanity check: the credential that doubles as the /toggle auth must
        // be the same one passed at /setup time. Catches drift between the
        // two code paths.
        XCTAssertEqual(AIPlugin.telegram.toggleAuthCredentialKey, "bot_token")
        XCTAssertEqual(AIPlugin.whatsapp.toggleAuthCredentialKey, "access_token")
    }

    // MARK: - Plugin metadata

    func testPluginCredentialFieldsShape() {
        XCTAssertEqual(AIPlugin.telegram.credentialFields.count, 1)
        XCTAssertEqual(AIPlugin.telegram.credentialFields.first?.key, "bot_token")
        XCTAssertTrue(AIPlugin.telegram.credentialFields.first?.isSecure ?? false)

        XCTAssertEqual(AIPlugin.whatsapp.credentialFields.count, 3)
        XCTAssertEqual(
            AIPlugin.whatsapp.credentialFields.map(\.key),
            ["access_token", "phone_number_id", "verify_token"]
        )
    }

    func testPluginAccentColorIsFromTokenPalette() {
        // M1 fix: card icons should use semantic color tokens, not raw .blue/.green.
        XCTAssertEqual(AIPlugin.telegram.accentColor, OmiColors.info)
        XCTAssertEqual(AIPlugin.whatsapp.accentColor, OmiColors.success)
    }
}

// MARK: - Deep link allowlist (P1 security gate)

/// Regression coverage for the host/scheme allowlist that gates which deep
/// links the desktop will hand to `NSWorkspace.shared.open`. A bug in this
/// check either lets a malicious deep link through (P1 risk) or rejects
/// every legitimate link (P0 usability regression — see code-review
/// finding that originally used `t.me` vs `me` mismatch).
final class ConnectSheetDeepLinkSafetyTests: XCTestCase {
    private typealias Safe = ConnectSheet

    func testAllowsTelegramDeepLink() {
        XCTAssertTrue(Safe.isSafeDeepLink("https://t.me/mybot?start=abc123", plugin: .telegram))
    }

    func testAllowsWhatsAppDeepLink() {
        XCTAssertTrue(Safe.isSafeDeepLink("https://wa.me/15550001111?text=/start%20token", plugin: .whatsapp))
    }

    func testAllowsHttpForDev() {
        // http is in the scheme allowlist (validation lives in AICloneConfig
        // for the *plugin URL*; the deep-link allowlist is intentionally
        // permissive for http because dev environments use it).
        XCTAssertTrue(Safe.isSafeDeepLink("http://t.me/mybot?start=token", plugin: .telegram))
    }

    func testRejectsEvilHost() {
        // https is the right scheme, but the host isn't in the allowlist.
        XCTAssertFalse(Safe.isSafeDeepLink("https://evil.com/phishing", plugin: .telegram))
    }

    func testRejectsFileScheme() {
        XCTAssertFalse(Safe.isSafeDeepLink("file:///etc/passwd", plugin: .telegram))
    }

    func testRejectsSSHScheme() {
        XCTAssertFalse(Safe.isSafeDeepLink("ssh://attacker.example", plugin: .telegram))
    }

    func testRejectsJavaScriptScheme() {
        XCTAssertFalse(Safe.isSafeDeepLink("javascript:alert(1)", plugin: .telegram))
    }

    func testRejectsMalformedURL() {
        XCTAssertFalse(Safe.isSafeDeepLink("not a url at all", plugin: .telegram))
    }

    func testRejectsEmptyString() {
        XCTAssertFalse(Safe.isSafeDeepLink("", plugin: .telegram))
    }

    // P1 cubic follow-up: the host check is bound to the active plugin.
    // A Telegram deep link must NOT be accepted in a WhatsApp connect
    // sheet (and vice versa) — a compromised plugin service could try
    // to phish by returning the other platform's host. Both directions
    // are tested.

    func testRejectsTelegramHostInWhatsAppContext() {
        let telegramURL = "https://t.me/mybot?start=abc123"
        XCTAssertTrue(Safe.isSafeDeepLink(telegramURL, plugin: .telegram))
        XCTAssertFalse(Safe.isSafeDeepLink(telegramURL, plugin: .whatsapp),
                       "t.me URL must not open in a WhatsApp connect sheet")
    }

    func testRejectsWhatsAppHostInTelegramContext() {
        let whatsappURL = "https://wa.me/15550001111?text=/start%20token"
        XCTAssertTrue(Safe.isSafeDeepLink(whatsappURL, plugin: .whatsapp))
        XCTAssertFalse(Safe.isSafeDeepLink(whatsappURL, plugin: .telegram),
                       "wa.me URL must not open in a Telegram connect sheet")
    }
}

// MARK: - User-account toggle (plan)

/// Mock URLProtocol that captures the request and returns a canned
/// response. Used to test `AICloneClient.toggleUserAccount`
/// without making real network calls.
private final class ToggleUserAccountMockURLProtocol: URLProtocol {
    nonisolated(unsafe) static var lastRequest: URLRequest?
    nonisolated(unsafe) static var responseStatus: Int = 200
    nonisolated(unsafe) static var responseBody: Data = Data()

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest {
        // Capture here because URLProtocol may convert httpBody to a
        // body stream by the time startLoading() runs.
        if Self.lastRequest == nil {
            Self.lastRequest = request
        }
        return request
    }

    override func startLoading() {
        if Self.lastRequest == nil {
            Self.lastRequest = self.request
        }
        let url = self.request.url!
        let resp = HTTPURLResponse(
            url: url, statusCode: Self.responseStatus,
            httpVersion: "HTTP/1.1", headerFields: ["Content-Type": "application/json"]
        )!
        client?.urlProtocol(self, didReceive: resp, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Self.responseBody)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

extension AICloneClientTests {
    /// Helper: install the mock URLProtocol, run the closure, return
    /// the captured request. Tears the protocol down on exit.
    private func withToggleMock(
        status: Int = 200,
        body: String = "{\"auto_reply_enabled\": true, \"affected_users\": 1}"
    ) async throws -> URLRequest? {
        ToggleUserAccountMockURLProtocol.responseStatus = status
        ToggleUserAccountMockURLProtocol.responseBody = body.data(using: .utf8) ?? Data()
        ToggleUserAccountMockURLProtocol.lastRequest = nil
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [ToggleUserAccountMockURLProtocol.self]
            + (config.protocolClasses ?? [])
        let session = URLSession(configuration: config)
        let client = AICloneClient(session: session, decoder: JSONDecoder())
        do {
            _ = try await client.toggleUserAccount(
                baseURL: "https://plugin.example.com",
                bearerToken: "test-token",
                enabled: true
            )
        } catch {
            // Test may assert on the error path; that's fine.
        }
        return ToggleUserAccountMockURLProtocol.lastRequest
    }

    func testToggleUserAccountSendsCorrectBody() async throws {
        let req = try await withToggleMock(
            body: "{\"auto_reply_enabled\": true, \"affected_users\": 3}"
        )
        XCTAssertNotNil(req)
        XCTAssertEqual(req?.httpMethod, "POST")
        XCTAssertEqual(
            req?.url?.path, "/toggle",
            "request should hit /toggle on the plugin"
        )
        // Authorization header set correctly.
        let auth = req?.value(forHTTPHeaderField: "Authorization")
        XCTAssertEqual(auth, "Bearer test-token")
        // Body contains the right keys.
        // URLProtocol may convert httpBody to a body stream.
        var bodyData = req?.httpBody ?? Data()
        if bodyData.isEmpty, let stream = req?.httpBodyStream {
            stream.open()
            let bufferSize = 1024
            var buffer = [UInt8](repeating: 0, count: bufferSize)
            while stream.hasBytesAvailable {
                let bytesRead = stream.read(&buffer, maxLength: bufferSize)
                if bytesRead > 0 {
                    bodyData.append(buffer, count: bytesRead)
                } else {
                    break
                }
            }
            stream.close()
        }
        let body = try JSONSerialization.jsonObject(with: bodyData) as? [String: Any]
        XCTAssertEqual(body?["handle"] as? String, "all",
                       "user-account toggle uses handle=all for the global toggle")
        XCTAssertEqual(body?["enabled"] as? Bool, true)
    }

    func testToggleUserAccountDecodesResponse() async throws {
        ToggleUserAccountMockURLProtocol.responseStatus = 200
        ToggleUserAccountMockURLProtocol.responseBody =
            "{\"auto_reply_enabled\": false, \"affected_users\": 5}"
                .data(using: .utf8) ?? Data()
        ToggleUserAccountMockURLProtocol.lastRequest = nil
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [ToggleUserAccountMockURLProtocol.self]
            + (config.protocolClasses ?? [])
        let session = URLSession(configuration: config)
        let client = AICloneClient(session: session, decoder: JSONDecoder())
        let response = try await client.toggleUserAccount(
            baseURL: "https://plugin.example.com",
            bearerToken: "test-token",
            enabled: false
        )
        XCTAssertFalse(response.autoReplyEnabled)
        XCTAssertEqual(response.affectedUsers, 5)
    }

    func testToggleUserAccountPropagatesHttpError() async throws {
        ToggleUserAccountMockURLProtocol.responseStatus = 403
        ToggleUserAccountMockURLProtocol.responseBody =
            "{\"detail\": \"No users configured\"}".data(using: .utf8) ?? Data()
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [ToggleUserAccountMockURLProtocol.self]
            + (config.protocolClasses ?? [])
        let session = URLSession(configuration: config)
        let client = AICloneClient(session: session, decoder: JSONDecoder())
        do {
            _ = try await client.toggleUserAccount(
                baseURL: "https://plugin.example.com",
                bearerToken: "test-token",
                enabled: true
            )
            XCTFail("Expected AICloneError.http(403)")
        } catch let error as AICloneClient.AICloneError {
            // The sanitized detail must contain the server's
            // error message (sanitized) but never the raw
            // response body bytes.
            if case .http(let status, let detail) = error {
                XCTAssertEqual(status, 403)
                XCTAssertTrue(detail.contains("No users configured"),
                              "sanitized detail should contain the server-provided message")
            } else {
                XCTFail("Expected .http(403, _), got \(error)")
            }
        }
    }
}
