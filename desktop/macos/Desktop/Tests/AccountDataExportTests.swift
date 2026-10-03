import XCTest

@testable import Omi_Computer

#if DEBUG
  // omi-release-compile: this suite drives DEBUG-only test seams; the release-mode
  // notification regression step must compile the bundle without them.

  private final class ExportStubProtocol: URLProtocol, @unchecked Sendable {
    struct Response {
      let status: Int
      let headers: [String: String]
      let body: Data
    }

    private static let lock = NSLock()
    private nonisolated(unsafe) static var recordedRequests: [URLRequest] = []
    private nonisolated(unsafe) static var queuedResponses: [Response] = []

    static func reset() {
      lock.withLock {
        recordedRequests = []
        queuedResponses = []
      }
    }

    static func enqueue(status: Int, headers: [String: String] = [:], body: String = "") {
      lock.withLock {
        queuedResponses.append(
          Response(status: status, headers: headers, body: Data(body.utf8)))
      }
    }

    static var requests: [URLRequest] { lock.withLock { recordedRequests } }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
      let response = Self.lock.withLock { () -> Response in
        Self.recordedRequests.append(request)
        if !Self.queuedResponses.isEmpty {
          return Self.queuedResponses.removeFirst()
        }
        return Response(status: 500, headers: [:], body: Data())
      }
      guard let url = request.url,
        let httpResponse = HTTPURLResponse(
          url: url,
          statusCode: response.status,
          httpVersion: nil,
          headerFields: response.headers
        )
      else { return }
      client?.urlProtocol(self, didReceive: httpResponse, cacheStoragePolicy: .notAllowed)
      client?.urlProtocol(self, didLoad: response.body)
      client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
  }

  private final class SuspendedExportStub: URLProtocol, @unchecked Sendable {
    private static let lock = NSLock()
    private nonisolated(unsafe) static var pending: SuspendedExportStub?
    private nonisolated(unsafe) static var started = false
    private nonisolated(unsafe) static var completed = false
    private var released = false

    static func reset() {
      lock.withLock {
        pending = nil
        started = false
        completed = false
      }
    }

    static func waitUntilStarted() async {
      while !lock.withLock({ started }) { await Task.yield() }
    }

    static var hasStarted: Bool { lock.withLock { started } }
    static var didFinish: Bool { lock.withLock { completed } }

    static func release(status: Int = 200, headers: [String: String] = [:], body: String = "") {
      let request = lock.withLock { () -> SuspendedExportStub? in
        defer { pending = nil }
        return pending
      }
      request?.respond(status: status, headers: headers, body: body)
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
      Self.lock.withLock {
        Self.pending = self
        Self.started = true
      }
    }

    override func stopLoading() {
      Self.lock.withLock { Self.completed = true }
    }

    private func respond(status: Int, headers: [String: String], body: String) {
      guard !released else { return }
      released = true
      guard let url = request.url,
        let httpResponse = HTTPURLResponse(
          url: url,
          statusCode: status,
          httpVersion: nil,
          headerFields: headers
        )
      else { return }
      client?.urlProtocol(self, didReceive: httpResponse, cacheStoragePolicy: .notAllowed)
      client?.urlProtocol(self, didLoad: Data(body.utf8))
      client?.urlProtocolDidFinishLoading(self)
    }
  }

  @MainActor
  final class AccountDataExportTests: XCTestCase {
    private let exportDirectory = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-export-test-\(UUID().uuidString)")
    private var savedEnv: [String: String?] = [:]

    private static let completionSuffix = ",\n  \"export_complete\": true\n}\n"
    private static let validBody = "{\n  \"chat_messages\": []\n" + completionSuffix
    private static let jsonHeaders = ["Content-Type": "application/json; charset=utf-8"]

    private func setEnv(_ key: String, _ value: String) {
      if savedEnv[key] == nil {
        savedEnv[key] = ProcessInfo.processInfo.environment[key]
      }
      setenv(key, value, 1)
    }

    private func stagedExportParts() -> [String] {
      let tmp = FileManager.default.temporaryDirectory.path
      return
        ((try? FileManager.default.contentsOfDirectory(atPath: tmp)) ?? [])
        .filter { $0.hasPrefix("omi-export-") && $0.hasSuffix(".part") }
    }

    override func setUp() async throws {
      await establishOwnerForExportTest("export-owner")
      ExportStubProtocol.reset()
      SuspendedExportStub.reset()
      try FileManager.default.createDirectory(at: exportDirectory, withIntermediateDirectories: true)
      setEnv("OMI_PYTHON_API_URL", "http://python-test.local:8000/")
      setEnv("OMI_DESKTOP_API_URL", "http://rust-test.local:9002/")
    }

    override func tearDown() async throws {
      SuspendedExportStub.release()
      try? FileManager.default.removeItem(at: exportDirectory)
      for (key, value) in savedEnv {
        if let value {
          setenv(key, value, 1)
        } else {
          unsetenv(key)
        }
      }
      savedEnv = [:]
      AuthService.shared.tokenStorageHooks = .live
      AuthService.shared.tokenRefreshHooks = .live
      await establishOwnerForExportTest(nil)
    }

    private func makeClient(suspended: Bool = false) async -> APIClient {
      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [suspended ? SuspendedExportStub.self : ExportStubProtocol.self]
      let client = APIClient(session: URLSession(configuration: config))
      await client.setTestAuthHeader("Bearer export-test-token")
      return client
    }

    private func ownerSnapshot(
      _ ownerID: String = "export-owner"
    ) async throws -> RuntimeOwnerAuthorizationSnapshot {
      await transitionOwnerForExportTest(to: ownerID)
      return try XCTUnwrap(
        RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: ownerID))
    }

    private func currentSnapshot() throws -> RuntimeOwnerAuthorizationSnapshot {
      try XCTUnwrap(RuntimeOwnerIdentity.captureAuthorizationSnapshot())
    }

    private func destinationURL() -> URL {
      exportDirectory.appendingPathComponent("omi-export.json")
    }

    func testExportHitsMainBackendStreamEndpointWithoutBYOK() async throws {
      let client = await makeClient()
      let snapshot = try await ownerSnapshot()
      ExportStubProtocol.enqueue(status: 200, headers: Self.jsonHeaders, body: Self.validBody)

      let destination = destinationURL()
      try await client.exportUserData(to: destination, authorizationSnapshot: snapshot) { _ in }

      let request = try XCTUnwrap(ExportStubProtocol.requests.first)
      XCTAssertEqual(request.url?.path, "/v1/users/export")
      XCTAssertEqual(request.url?.host, "python-test.local")
      XCTAssertEqual(request.url?.query, "stream=true")
      XCTAssertEqual(request.httpMethod, "GET")
      XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer export-test-token")
      for field in request.allHTTPHeaderFields?.keys ?? [:].keys {
        XCTAssertFalse(field.hasPrefix("X-BYOK"), "export must not carry BYOK header \(field)")
      }
      XCTAssertEqual(request.timeoutInterval, 120)

      let saved = try Data(contentsOf: destination)
      XCTAssertEqual(saved, Data(Self.validBody.utf8))
      let attributes = try FileManager.default.attributesOfItem(atPath: destination.path)
      XCTAssertEqual(attributes[.posixPermissions] as? Int, 0o600)
    }

    func testExportRetriesOnceAfter401() async throws {
      let client = await makeClient()
      DesktopDiagnosticsManager.shared.resetForTests()
      try configureRefreshableSession(userId: "export-owner")
      setEnv("FIREBASE_API_KEY", "test-key")
      let snapshot = try await ownerSnapshot()
      ExportStubProtocol.enqueue(status: 401, body: "{\"detail\":\"expired\"}")
      ExportStubProtocol.enqueue(status: 200, headers: Self.jsonHeaders, body: Self.validBody)

      try await client.exportUserData(to: destinationURL(), authorizationSnapshot: snapshot) { _ in }
      XCTAssertEqual(ExportStubProtocol.requests.count, 2)
      XCTAssertEqual(
        ExportStubProtocol.requests.last?.value(forHTTPHeaderField: "Authorization"),
        "Bearer \(Self.makeJWT(payload: ["user_id": "export-owner"]))")
      XCTAssertEqual(try latestHealthSnapshot()["retry_outcome"] as? String, "succeeded")
    }

    func testPersistentExport401InvalidatesTheCapturedSession() async throws {
      let client = await makeClient()
      DesktopDiagnosticsManager.shared.resetForTests()
      try configureRefreshableSession(userId: "export-owner")
      setEnv("FIREBASE_API_KEY", "test-key")
      let snapshot = try await ownerSnapshot()
      ExportStubProtocol.enqueue(status: 401, body: "{\"detail\":\"expired\"}")
      ExportStubProtocol.enqueue(status: 401, body: "{\"detail\":\"still expired\"}")

      await xctAssertThrowsErrorAsync(
        try await client.exportUserData(to: destinationURL(), authorizationSnapshot: snapshot) { _ in }
      ) { error in
        guard case APIError.unauthorized = error else {
          return XCTFail("expected unauthorized, got \(error)")
        }
      }

      XCTAssertEqual(UserDefaults.standard.string(forKey: .authUserId), "export-owner")
      XCTAssertNil(UserDefaults.standard.string(forKey: .authIdToken))
      XCTAssertEqual(AuthState.shared.sessionPhase, .needsReauth)
      XCTAssertEqual(try latestHealthSnapshot()["retry_outcome"] as? String, "unauthorized")
    }

    func testFailedExportRetryIsRecordedAsFailed() async throws {
      let client = await makeClient()
      DesktopDiagnosticsManager.shared.resetForTests()
      try configureRefreshableSession(userId: "export-owner")
      setEnv("FIREBASE_API_KEY", "test-key")
      let snapshot = try await ownerSnapshot()
      ExportStubProtocol.enqueue(status: 401, body: "{\"detail\":\"expired\"}")
      ExportStubProtocol.enqueue(status: 500, body: "{\"detail\":\"failed\"}")

      await xctAssertThrowsErrorAsync(
        try await client.exportUserData(to: destinationURL(), authorizationSnapshot: snapshot) { _ in }
      ) { error in
        guard case APIError.httpError(let statusCode, _) = error else {
          return XCTFail("expected HTTP 500, got \(error)")
        }
        XCTAssertEqual(statusCode, 500)
      }
      XCTAssertEqual(try latestHealthSnapshot()["retry_outcome"] as? String, "failed")
    }

    func testExportUnauthorizedFromOldOwnerDoesNotInvalidateNewOwner() async throws {
      let client = await makeClient(suspended: true)
      try configureRefreshableSession(userId: "export-owner")
      let snapshot = try await ownerSnapshot("export-owner")
      let task = Task {
        try await client.exportUserData(to: destinationURL(), authorizationSnapshot: snapshot) { _ in }
      }
      await SuspendedExportStub.waitUntilStarted()
      await transitionOwnerForExportTest(to: "new-owner")
      try configureRefreshableSession(userId: "new-owner")
      SuspendedExportStub.release(status: 401)

      await xctAssertThrowsErrorAsync(try await task.value) { error in
        guard case AuthError.userChangedDuringRequest = error else {
          return XCTFail("expected owner-change rejection, got \(error)")
        }
      }
      XCTAssertEqual(
        RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: "new-owner")?.ownerID,
        "new-owner")
      XCTAssertEqual(UserDefaults.standard.string(forKey: .authIdToken), "id-token")
    }

    func testTruncated200PreservesExistingDestination() async throws {
      let client = await makeClient()
      let snapshot = try await ownerSnapshot()
      let destination = destinationURL()
      try Data("existing-export".utf8).write(to: destination)
      ExportStubProtocol.enqueue(
        status: 200, headers: Self.jsonHeaders, body: "{\"chat_messages\": []")

      await xctAssertThrowsErrorAsync(
        try await client.exportUserData(to: destination, authorizationSnapshot: snapshot) { _ in }
      ) { error in
        XCTAssertEqual(error as? APIClient.DataExportError, .incompleteExport)
      }
      XCTAssertEqual(
        try String(contentsOf: destination, encoding: .utf8), "existing-export")
    }

    func testMissingCompletionMarkerFailsWithoutTouchingDestination() async throws {
      let client = await makeClient()
      let snapshot = try await ownerSnapshot()
      let destination = destinationURL()
      ExportStubProtocol.enqueue(
        status: 200, headers: Self.jsonHeaders, body: "{\"chat_messages\": []}\n")

      await xctAssertThrowsErrorAsync(
        try await client.exportUserData(to: destination, authorizationSnapshot: snapshot) { _ in }
      ) { error in
        XCTAssertEqual(error as? APIClient.DataExportError, .incompleteExport)
      }
      XCTAssertFalse(FileManager.default.fileExists(atPath: destination.path))
    }

    func testNonJSONContentTypeFails() async throws {
      let client = await makeClient()
      let snapshot = try await ownerSnapshot()
      ExportStubProtocol.enqueue(
        status: 200,
        headers: ["Content-Type": "text/plain"],
        body: Self.validBody)

      await xctAssertThrowsErrorAsync(
        try await client.exportUserData(to: destinationURL(), authorizationSnapshot: snapshot) { _ in }
      ) { error in
        XCTAssertEqual(error as? APIClient.DataExportError, .unexpectedContentType)
      }
    }

    func testHTTPErrorStatusThrows() async throws {
      let client = await makeClient()
      let snapshot = try await ownerSnapshot()
      ExportStubProtocol.enqueue(status: 500, body: "{\"detail\":\"boom\"}")

      await xctAssertThrowsErrorAsync(
        try await client.exportUserData(to: destinationURL(), authorizationSnapshot: snapshot) { _ in }
      ) { error in
        guard case APIError.httpError(let statusCode, _) = error else {
          return XCTFail("expected httpError, got \(error)")
        }
        XCTAssertEqual(statusCode, 500)
      }
    }

    func testProgressReportsBytesDownloaded() async throws {
      let client = await makeClient()
      let snapshot = try await ownerSnapshot()
      ExportStubProtocol.enqueue(status: 200, headers: Self.jsonHeaders, body: Self.validBody)
      let progress = ExportProgressRecorder()

      try await client.exportUserData(to: destinationURL(), authorizationSnapshot: snapshot) { bytes in
        progress.record(bytes)
      }
      XCTAssertEqual(progress.last, Int64(Self.validBody.utf8.count))
    }

    func testCancelledDownloadLeavesDestinationUntouched() async throws {
      let client = await makeClient(suspended: true)
      let snapshot = try await ownerSnapshot()
      let destination = destinationURL()
      try Data("prior".utf8).write(to: destination)

      let task = Task {
        try await client.exportUserData(to: destination, authorizationSnapshot: snapshot) { _ in }
      }
      await SuspendedExportStub.waitUntilStarted()
      task.cancel()

      await xctAssertThrowsErrorAsync(try await task.value) { _ in }
      XCTAssertEqual(try String(contentsOf: destination, encoding: .utf8), "prior")
      let leftovers =
        (try? FileManager.default.contentsOfDirectory(atPath: exportDirectory.path)) ?? []
      XCTAssertTrue(leftovers.allSatisfy { !$0.contains(".part") })
    }

    func testOwnerSwitchDuringDownloadRejectsResult() async throws {
      let client = await makeClient(suspended: true)
      let snapshot = try await ownerSnapshot("export-owner")
      let priorParts = Set(stagedExportParts())

      let task = Task {
        try await client.exportUserData(to: destinationURL(), authorizationSnapshot: snapshot) { _ in }
      }
      await SuspendedExportStub.waitUntilStarted()
      await transitionOwnerForExportTest(to: "other-owner")
      SuspendedExportStub.release(headers: Self.jsonHeaders, body: Self.validBody)

      await xctAssertThrowsErrorAsync(try await task.value) { error in
        guard case AuthError.userChangedDuringRequest = error else {
          return XCTFail("expected owner-change rejection, got \(error)")
        }
      }
      XCTAssertFalse(FileManager.default.fileExists(atPath: destinationURL().path))
      XCTAssertTrue(Set(stagedExportParts()).isSubset(of: priorParts))
    }

    func testExportReplacing0644DestinationKeeps0600() async throws {
      let client = await makeClient()
      let snapshot = try await ownerSnapshot()
      let destination = destinationURL()
      try Data("old".utf8).write(to: destination)
      try FileManager.default.setAttributes(
        [.posixPermissions: 0o644],
        ofItemAtPath: destination.path)
      ExportStubProtocol.enqueue(status: 200, headers: Self.jsonHeaders, body: Self.validBody)

      try await client.exportUserData(to: destination, authorizationSnapshot: snapshot) { _ in }

      let attributes = try FileManager.default.attributesOfItem(atPath: destination.path)
      XCTAssertEqual(attributes[.posixPermissions] as? Int, 0o600)
      XCTAssertEqual(try String(contentsOf: destination, encoding: .utf8), Self.validBody)
    }

    func testModelSavePanelCancelIsANoOp() async throws {
      var downloadCalls = 0
      let snapshot = try currentSnapshot()
      let model = AccountDataExportModel(
        runSavePanel: { nil },
        ownerSnapshot: { snapshot },
        download: { _, _, _ in downloadCalls += 1 },
        confirm: { _ in })
      model.startExport()
      await drainMainTasks()
      XCTAssertEqual(downloadCalls, 0)
      XCTAssertFalse(model.isExporting)
      XCTAssertNil(model.errorMessage)
    }

    func testModelMissingOwnerSnapshotSurfacesError() async {
      var downloadCalls = 0
      let model = AccountDataExportModel(
        runSavePanel: { URL(fileURLWithPath: "/tmp/x.json") },
        ownerSnapshot: { nil },
        download: { _, _, _ in downloadCalls += 1 },
        confirm: { _ in })
      model.startExport()
      await drainMainTasks()
      XCTAssertEqual(downloadCalls, 0)
      XCTAssertNotNil(model.errorMessage)
    }

    func testModelSuccessConfirmsAndClearsBusy() async throws {
      var confirmed: [String] = []
      var downloadCalls = 0
      let snapshot = try currentSnapshot()
      let model = AccountDataExportModel(
        runSavePanel: { URL(fileURLWithPath: "/tmp/out.json") },
        ownerSnapshot: { snapshot },
        download: { _, _, onProgress in
          downloadCalls += 1
          onProgress(42)
        },
        confirm: { confirmed.append($0) })
      model.startExport()
      await waitUntil { downloadCalls > 0 && !model.isExporting }
      XCTAssertEqual(downloadCalls, 1)
      XCTAssertEqual(confirmed, ["Export Saved"])
      await waitUntil { model.bytesReceived == 42 }
      XCTAssertNil(model.errorMessage)
    }

    func testModelFailurePersistsErrorAndTryAgainRetries() async throws {
      struct Boom: Error {}
      var downloadCalls = 0
      var confirmed = 0
      let snapshot = try currentSnapshot()
      let model = AccountDataExportModel(
        runSavePanel: { URL(fileURLWithPath: "/tmp/out.json") },
        ownerSnapshot: { snapshot },
        download: { _, _, _ in
          downloadCalls += 1
          if downloadCalls == 1 { throw Boom() }
        },
        confirm: { _ in confirmed += 1 })
      model.startExport()
      await waitUntil { downloadCalls > 0 && !model.isExporting }
      XCTAssertEqual(downloadCalls, 1)
      XCTAssertNotNil(model.errorMessage)
      XCTAssertEqual(confirmed, 0)

      model.startExport()
      await waitUntil { downloadCalls > 1 && !model.isExporting }
      XCTAssertEqual(downloadCalls, 2)
      XCTAssertNil(model.errorMessage)
      XCTAssertEqual(confirmed, 1)
    }

    func testModelRetryAfterIncompleteExportSucceeds() async throws {
      let client = await makeClient()
      let snapshot = try await ownerSnapshot()
      let destination = destinationURL()
      var downloadCalls = 0
      var confirmed: [String] = []
      var capturedErrors: [APIClient.DataExportError] = []
      let model = AccountDataExportModel(
        runSavePanel: { destination },
        ownerSnapshot: { snapshot },
        download: { destination, snapshot, onProgress in
          downloadCalls += 1
          do {
            try await client.exportUserData(
              to: destination, authorizationSnapshot: snapshot, onProgress: onProgress)
          } catch let error as APIClient.DataExportError {
            capturedErrors.append(error)
            throw error
          }
        },
        confirm: { confirmed.append($0) })

      ExportStubProtocol.enqueue(
        status: 200, headers: Self.jsonHeaders, body: "{\"chat_messages\": []")
      model.startExport()
      await waitUntil { downloadCalls == 1 && !model.isExporting }
      XCTAssertEqual(capturedErrors, [.incompleteExport])
      XCTAssertNotNil(model.errorMessage)
      XCTAssertTrue(confirmed.isEmpty)

      ExportStubProtocol.enqueue(status: 200, headers: Self.jsonHeaders, body: Self.validBody)
      model.startExport()
      await waitUntil { downloadCalls == 2 && !model.isExporting }
      XCTAssertEqual(ExportStubProtocol.requests.count, 2)
      XCTAssertNil(model.errorMessage)
      XCTAssertEqual(confirmed, ["Export Saved"])
      XCTAssertEqual(try Data(contentsOf: destination), Data(Self.validBody.utf8))
    }

    func testModelCancelDoesNotConfirm() async throws {
      var confirmed = 0
      let snapshot = try currentSnapshot()
      let model = AccountDataExportModel(
        runSavePanel: { URL(fileURLWithPath: "/tmp/out.json") },
        ownerSnapshot: { snapshot },
        download: { _, _, _ in try await ExportDownloadGate().wait() },
        confirm: { _ in confirmed += 1 })
      model.startExport()
      await waitUntil { model.isExporting }
      model.cancelExport()
      await waitUntil { !model.isExporting }
      XCTAssertEqual(confirmed, 0)
      XCTAssertNil(model.errorMessage)
    }

    func testCancelledRunCannotDisturbNewExport() async throws {
      let gate = ExportDownloadGate()
      var downloadCalls = 0
      var confirmed = 0
      let snapshot = try currentSnapshot()
      let model = AccountDataExportModel(
        runSavePanel: { URL(fileURLWithPath: "/tmp/out.json") },
        ownerSnapshot: { snapshot },
        download: { _, _, onProgress in
          downloadCalls += 1
          if downloadCalls == 1 {
            _ = try? await gate.wait()
            onProgress(9999)
            return
          }
          onProgress(7)
        },
        confirm: { _ in confirmed += 1 })
      model.startExport()
      await waitUntil { downloadCalls == 1 }
      model.cancelExport()
      model.startExport()
      await waitUntil { downloadCalls == 2 }
      await waitUntil { !model.isExporting }
      XCTAssertEqual(confirmed, 1)
      await waitUntil { model.bytesReceived == 7 }
      XCTAssertNil(model.errorMessage)
    }

    func testAutomationExportCompletesAndCleansOwnedFile() async throws {
      setEnv("OMI_PYTHON_API_URL", "http://127.0.0.1:8000/")
      let snapshot = try currentSnapshot()
      var usedDestination: URL?
      let model = AccountDataExportModel(
        runSavePanel: { nil },
        ownerSnapshot: { snapshot },
        download: { destination, _, _ in
          usedDestination = destination
          try Data(Self.validBody.utf8).write(to: destination)
        },
        confirm: { _ in },
        allowsAutomation: { true })
      let result = try await model.exportForAutomation()
      XCTAssertEqual(result["completed"], "true")
      XCTAssertEqual(result["bytes"], "\(Self.validBody.utf8.count)")
      let destination = try XCTUnwrap(usedDestination)
      XCTAssertFalse(FileManager.default.fileExists(atPath: destination.path))
      XCTAssertFalse(FileManager.default.fileExists(atPath: destination.deletingLastPathComponent().path))
    }

    func testAutomationExportRejectsNonLoopbackBackendBeforeDownload() async throws {
      var downloadCalls = 0
      let model = AccountDataExportModel(
        runSavePanel: { nil },
        ownerSnapshot: { nil },
        download: { _, _, _ in downloadCalls += 1 },
        confirm: { _ in },
        allowsAutomation: { true })
      await xctAssertThrowsErrorAsync(try await model.exportForAutomation()) { error in
        guard case DesktopAutomationActionError.invalidParams(let detail) = error else {
          return XCTFail("expected invalidParams, got \(error)")
        }
        XCTAssertTrue(detail.contains("loopback backend"))
      }
      XCTAssertEqual(downloadCalls, 0)
    }

    func testAutomationActionCanBeUnregisteredWithItsViewLifecycle() async throws {
      let registry = DesktopAutomationActionRegistry.shared
      let model = AccountDataExportModel(
        ownerSnapshot: { nil },
        download: { _, _, _ in },
        confirm: { _ in },
        allowsAutomation: { true })
      model.registerAutomationActions()
      XCTAssertTrue(registry.descriptors().contains { $0.name == "settings_export_data_fixture" })

      model.unregisterAutomationActions()

      XCTAssertFalse(registry.descriptors().contains { $0.name == "settings_export_data_fixture" })
      do {
        _ = try await registry.perform("settings_export_data_fixture", params: [:])
        XCTFail("expected the removed action to be unavailable")
      } catch let error as DesktopAutomationActionError {
        guard case .unknownAction("settings_export_data_fixture") = error else {
          return XCTFail("expected unknownAction, got \(error)")
        }
      }
    }

    private func latestHealthSnapshot() throws -> [String: Any] {
      let url = try XCTUnwrap(DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment())
      defer { try? FileManager.default.removeItem(at: url) }
      let data = try Data(contentsOf: url)
      let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
      return try XCTUnwrap((root["snapshots"] as? [[String: Any]])?.last)
    }

    private func transitionOwnerForExportTest(to ownerID: String?) async {
      do {
        _ = try await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
          plannedNextOwner: { _, _ in ownerID },
          quiesceVoice: { _, _ in },
          retargetLocalStorage: { _, _ in },
          ownerDidChange: {},
          { defaults in
            defaults.removeObject(forKey: .automationOwnerOverride)
            if let ownerID {
              defaults.set(ownerID, forKey: .authUserId)
            } else {
              defaults.removeObject(forKey: .authUserId)
            }
          }
        )
      } catch {
        XCTFail("owner transition failed: \(error)")
      }
    }

    private func establishOwnerForExportTest(_ ownerID: String?) async {
      let bootstrapOwner = "account-data-export-bootstrap"
      if ownerID == bootstrapOwner {
        await transitionOwnerForExportTest(to: nil)
      } else {
        await transitionOwnerForExportTest(to: bootstrapOwner)
      }
      await transitionOwnerForExportTest(to: ownerID)
    }

    private func configureRefreshableSession(userId: String) throws {
      let auth = AuthService.shared
      auth.tokenStorageHooks = AuthService.TokenStorageHooks(
        usesKeychainTokenStorage: { false },
        allowsUserDefaultsFallback: { true },
        readKeychainString: { _, _ in nil },
        writeKeychainString: { _, _, _ in true },
        deleteKeychainString: { _, _ in },
        recordsFallbackTelemetry: false
      )
      try auth.saveTokens(
        idToken: "id-token",
        refreshToken: "refresh-token",
        expiresIn: 3600,
        userId: userId
      )
      let refreshedJWT = Self.makeJWT(payload: ["user_id": userId])
      auth.tokenRefreshHooks = AuthService.TokenRefreshHooks(
        dataForRequest: { _ in
          let body = Data(
            "{\"id_token\":\"\(refreshedJWT)\",\"refresh_token\":\"new-refresh\",\"expires_in\":\"3600\",\"user_id\":\"\(userId)\"}"
              .utf8)
          let response = try XCTUnwrap(
            HTTPURLResponse(
              url: URL(string: "https://securetoken.googleapis.com/v1/token")!,
              statusCode: 200,
              httpVersion: nil,
              headerFields: nil
            ))
          return (body, response)
        }
      )
    }

    private static func makeJWT(payload: [String: Any]) -> String {
      func segment(_ json: [String: Any]) -> String {
        guard let data = try? JSONSerialization.data(withJSONObject: json, options: [.sortedKeys])
        else { return "" }
        return
          data
          .base64EncodedString()
          .replacingOccurrences(of: "+", with: "-")
          .replacingOccurrences(of: "/", with: "_")
          .replacingOccurrences(of: "=", with: "")
      }
      return "\(segment(["alg": "none", "typ": "JWT"])).\(segment(payload))."
    }

    private func drainMainTasks() async {
      for _ in 0..<20 { await Task.yield() }
    }

    private func waitUntil(_ condition: @MainActor () -> Bool) async {
      for _ in 0..<10_000 where !condition() { await Task.yield() }
      XCTAssertTrue(condition())
    }
  }

  private final class ExportDownloadGate: @unchecked Sendable {
    private let lock = NSLock()
    private var continuation: CheckedContinuation<Void, Error>?

    func wait() async throws {
      try await withTaskCancellationHandler {
        try await withCheckedThrowingContinuation { (c: CheckedContinuation<Void, Error>) in
          lock.withLock { continuation = c }
        }
      } onCancel: {
        let pending = lock.withLock { () -> CheckedContinuation<Void, Error>? in
          defer { continuation = nil }
          return continuation
        }
        pending?.resume(throwing: CancellationError())
      }
    }
  }

  private final class ExportProgressRecorder: @unchecked Sendable {
    private let lock = NSLock()
    private var values: [Int64] = []
    func record(_ value: Int64) { lock.withLock { values.append(value) } }
    var last: Int64? { lock.withLock { values.last } }
  }

  @MainActor
  private func xctAssertThrowsErrorAsync<T>(
    _ expression: @autoclosure () async throws -> T,
    _ validator: @MainActor (Error) -> Void
  ) async {
    do {
      _ = try await expression()
      XCTFail("expected error")
    } catch {
      validator(error)
    }
  }

#endif
