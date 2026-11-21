import XCTest

@testable import Omi_Computer

private final class SettingsOwnerRequestCapture: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private nonisolated(unsafe) static var paths: [String] = []
  private nonisolated(unsafe) static var payload = "{\"status\":\"ok\"}"

  static func reset() {
    lock.withLock {
      paths = []
      payload = "{\"status\":\"ok\"}"
    }
  }
  static func respond(with value: String) { lock.withLock { payload = value } }
  static func capturedPaths() -> [String] { lock.withLock { paths } }
  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
  override func startLoading() {
    Self.lock.withLock { Self.paths.append(request.url?.path ?? "") }
    guard let url = request.url,
      let response = HTTPURLResponse(
        url: url, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"])
    else {
      client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
      return
    }
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: Data(Self.lock.withLock { Self.payload }.utf8))
    client?.urlProtocolDidFinishLoading(self)
  }
  override func stopLoading() {}
}

@MainActor
final class APIClientSettingsOwnerRequestTests: XCTestCase {
  private var originalOwner: String?

  override func setUp() async throws {
    originalOwner = UserDefaults.standard.string(forKey: .authUserId)
    UserDefaults.standard.set("settings-request-owner", forKey: .authUserId)
    RuntimeOwnerAuthorizationAuthority.shared.beginTransition()
    RuntimeOwnerAuthorizationAuthority.shared.endTransition(ownerID: "settings-request-owner")
    SettingsOwnerRequestCapture.reset()
  }

  override func tearDown() async throws {
    UserDefaults.standard.set(originalOwner, forKey: .authUserId)
    RuntimeOwnerAuthorizationAuthority.shared.beginTransition()
    RuntimeOwnerAuthorizationAuthority.shared.endTransition(ownerID: originalOwner)
    SettingsOwnerRequestCapture.reset()
  }

  private func client() async -> APIClient {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [SettingsOwnerRequestCapture.self]
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setTestAuthHeader("Bearer synthetic-settings-owner")
    return client
  }

  func testCurrentSnapshotReachesBothSettingsRoutes() async throws {
    let api = await client()
    let snapshot = try XCTUnwrap(RuntimeOwnerIdentity.captureAuthorizationSnapshot())
    _ = try await api.getAssistantSettings(authorizationSnapshot: snapshot)
    _ = try await api.updateAssistantSettings(AssistantSettingsResponse(), authorizationSnapshot: snapshot)
    XCTAssertEqual(
      SettingsOwnerRequestCapture.capturedPaths(),
      [
        "/v1/users/assistant-settings", "/v1/users/assistant-settings",
      ])
  }

  func testRevokedSnapshotCannotEmitSettingsOrMemoryRequests() async throws {
    let api = await client()
    let snapshot = try XCTUnwrap(RuntimeOwnerIdentity.captureAuthorizationSnapshot())
    RuntimeOwnerAuthorizationAuthority.shared.beginTransition()
    RuntimeOwnerAuthorizationAuthority.shared.endTransition(ownerID: snapshot.ownerID)

    do {
      _ = try await api.getAssistantSettings(authorizationSnapshot: snapshot)
      XCTFail("Revoked settings read was accepted")
    } catch {}
    do {
      _ = try await api.updateAssistantSettings(AssistantSettingsResponse(), authorizationSnapshot: snapshot)
      XCTFail("Revoked settings write was accepted")
    } catch {}
    do {
      _ = try await api.editMemory(id: "original", content: "draft", authorizationSnapshot: snapshot)
      XCTFail("Revoked memory edit was accepted")
    } catch {}

    XCTAssertTrue(SettingsOwnerRequestCapture.capturedPaths().isEmpty)
  }

  func testUnsuccessfulEditResponseIsNotAcknowledgedAsSaved() async throws {
    let api = await client()
    let snapshot = try XCTUnwrap(RuntimeOwnerIdentity.captureAuthorizationSnapshot())
    SettingsOwnerRequestCapture.respond(with: "{\"status\":\"error\"}")
    do {
      _ = try await api.editMemory(id: "original", content: "draft", authorizationSnapshot: snapshot)
      XCTFail("An unsuccessful body must not trigger a local success commit")
    } catch APIError.invalidResponse {}
  }
}
