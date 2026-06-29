import XCTest
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
            credentialForAuth: "TELEGRAM_TOKEN"
        )
        XCTAssertEqual(body["chat_id"] as? String, "12345")
        XCTAssertEqual(body["bot_token"] as? String, "TELEGRAM_TOKEN")
        XCTAssertEqual(body["enabled"] as? Bool, true)
    }

    func testWhatsAppToggleBodyUsesAccessTokenForAuth() {
        let body = AIPlugin.whatsapp.toggleRequestBody(
            chatId: "15550001111",
            credentialForAuth: "WA_TOKEN"
        )
        XCTAssertEqual(body["phone"] as? String, "15550001111")
        XCTAssertEqual(body["access_token"] as? String, "WA_TOKEN")
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