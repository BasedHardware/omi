import XCTest

@testable import Omi_Computer

/// Real settings HTTP encoding/decoding and sync ownership, synthetic server.
/// No live account, screen capture or two physical Macs are involved.
private final class ScreenSettingsServer: URLProtocol {
  private static let lock = NSLock()
  private nonisolated(unsafe) static var enabled = true
  private nonisolated(unsafe) static var rejectWrite = false

  static func configure(enabled: Bool, rejectWrite: Bool = false) {
    lock.withLock {
      Self.enabled = enabled
      Self.rejectWrite = rejectWrite
    }
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
  override func stopLoading() {}

  override func startLoading() {
    do {
      let (status, value): (Int, Bool) = try Self.lock.withLock {
        guard request.url?.path == "/v1/users/assistant-settings" else { return (404, false) }
        if request.httpMethod == "PATCH" {
          if Self.rejectWrite { return (403, Self.enabled) }
          var body = request.httpBody ?? Data()
          if let stream = request.httpBodyStream {
            stream.open()
            defer { stream.close() }
            var buffer = [UInt8](repeating: 0, count: 4096)
            while stream.hasBytesAvailable {
              let count = stream.read(&buffer, maxLength: buffer.count)
              if count <= 0 { break }
              body.append(contentsOf: buffer.prefix(count))
            }
          }
          let payload = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
          let shared = try XCTUnwrap(payload["shared"] as? [String: Any])
          XCTAssertEqual(Set(payload.keys), ["shared"])
          XCTAssertEqual(Set(shared.keys), ["screen_analysis_enabled"])
          Self.enabled = try XCTUnwrap(shared["screen_analysis_enabled"] as? Bool)
        }
        return (200, Self.enabled)
      }
      let body = try JSONSerialization.data(withJSONObject: ["shared": ["screen_analysis_enabled": value]])
      let url = try XCTUnwrap(request.url)
      let response = try XCTUnwrap(
        HTTPURLResponse(url: url, statusCode: status, httpVersion: nil, headerFields: nil))
      client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
      client?.urlProtocol(self, didLoad: body)
      client?.urlProtocolDidFinishLoading(self)
    } catch { client?.urlProtocol(self, didFailWithError: error) }
  }
}

@MainActor
final class ScreenAnalysisSyncIntegrationTests: XCTestCase {
  func testTwoClientSyncAndFailedSavePreserveLocalOff() async throws {
    let originalEnabled = AssistantSettings.shared.screenAnalysisEnabled
    let originalHold = UserDefaults.standard.object(forKey: .screenAnalysisHeldOffByUser)
    defer {
      AssistantSettings.shared.screenAnalysisEnabled = originalEnabled
      if let originalHold {
        // omi-test-quality: shared-defaults -- integration: restore the production settings owner's storage
        UserDefaults.standard.set(originalHold, forKey: .screenAnalysisHeldOffByUser)
      } else {
        // omi-test-quality: shared-defaults -- integration: restore the production settings owner's storage
        UserDefaults.standard.removeObject(forKey: .screenAnalysisHeldOffByUser)
      }
    }
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [ScreenSettingsServer.self]
    let session = URLSession(configuration: configuration)
    defer { session.invalidateAndCancel() }
    let client = APIClient(session: session)
    await client.setTestAuthHeader("Bearer synthetic-screen-sync")
    let sync = SettingsSyncManager.shared

    ScreenSettingsServer.configure(enabled: true, rejectWrite: true)
    sync.setUserScreenAnalysisEnabled(false, push: false)
    do {
      _ = try await client.updateAssistantSettings(SettingsSyncManager.screenAnalysisEnabledUpdate(false))
      XCTFail("Expected refused save")
    } catch { /* The local privacy intent must survive a failed network write. */  }
    sync.applyRemoteSettings(try await client.getAssistantSettings())
    XCTAssertFalse(AssistantSettings.shared.screenAnalysisEnabled)

    ScreenSettingsServer.configure(enabled: true)
    _ = try await client.updateAssistantSettings(SettingsSyncManager.screenAnalysisEnabledUpdate(false))
    // A second client with no local veto receives the account-wide off.
    sync.setUserScreenAnalysisEnabled(true, push: false)
    sync.applyRemoteSettings(try await client.getAssistantSettings())
    XCTAssertFalse(AssistantSettings.shared.screenAnalysisEnabled)
    XCTAssertFalse(sync.isScreenAnalysisHeldOffByUser)
    // A second client's explicit on does not override the first client's hold.
    _ = try await client.updateAssistantSettings(SettingsSyncManager.screenAnalysisEnabledUpdate(true))
    sync.setUserScreenAnalysisEnabled(false, push: false)
    sync.applyRemoteSettings(try await client.getAssistantSettings())
    XCTAssertFalse(AssistantSettings.shared.screenAnalysisEnabled)
    XCTAssertFalse(sync.restoreScreenAnalysisDefaultForMigration())
    sync.setUserScreenAnalysisEnabled(true, push: false)
    sync.applyRemoteSettings(try await client.getAssistantSettings())
    XCTAssertTrue(AssistantSettings.shared.screenAnalysisEnabled)
  }
}
