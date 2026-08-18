import XCTest

@testable import Omi_Computer

private actor SessionStepRecorder {
  private(set) var steps: [String] = []

  func record(_ step: String) {
    steps.append(step)
  }
}

/// Closing screen egress must not disconnect the sanitized non-screen context
/// path, and nothing may reach a VM that still holds screen activity. The gate
/// refuses the session; it never deletes the data to clear itself. These drive
/// the real session preparation with injected hooks.
@MainActor
final class AgentVMSessionStartupTests: XCTestCase {
  private var ownerFixture: RuntimeOwnerAuthorityTestFixture?
  private let ownerID = "agent-vm-session-owner"

  override func setUp() async throws {
    ownerFixture = RuntimeOwnerAuthorityTestFixture()
    await ownerFixture?.establish(authOwnerID: ownerID)
  }

  override func tearDown() async throws {
    await ownerFixture?.restore()
    ownerFixture = nil
  }

  private func makeService(
    recorder: SessionStepRecorder,
    screenActivityAbsent: Bool
  ) -> AgentVMService {
    AgentVMService(
      sessionHooks: AgentVMService.SessionHooks(
        screenActivityAbsent: { _, _ in
          await recorder.record("screen-check")
          return screenActivityAbsent
        },
        startNonScreenSync: { _, _ in await recorder.record("sync") },
        sendFirebaseToken: { _, _, _, _ in await recorder.record("token") }))
  }

  private func readyStatus() -> APIClient.AgentStatusResponse {
    APIClient.AgentStatusResponse(
      vmName: "vm-test",
      zone: "",
      ip: "10.0.0.1",
      status: "ready",
      authToken: "vm-token",
      createdAt: "",
      lastQueryAt: nil)
  }

  func testReadyVMConfirmsNoScreenActivityThenStartsNonScreenSync() async {
    let recorder = SessionStepRecorder()
    let service = makeService(recorder: recorder, screenActivityAbsent: true)

    await service.prepareReadyVM(readyStatus(), ip: "10.0.0.1", ownerID: ownerID, generation: 0)

    let steps = await recorder.steps
    XCTAssertEqual(steps, ["screen-check", "sync", "token"])
  }

  func testRemainingScreenActivityBlocksSyncAndBackendToken() async {
    let recorder = SessionStepRecorder()
    let service = makeService(recorder: recorder, screenActivityAbsent: false)

    await service.prepareReadyVM(readyStatus(), ip: "10.0.0.1", ownerID: ownerID, generation: 0)

    let steps = await recorder.steps
    XCTAssertEqual(steps, ["screen-check"])
  }

  /// Full-database upload is retired because the local database can hold
  /// screen/OCR rows; the sync-failure recovery hook must not reopen it.
  func testDatabaseReuploadStaysDisabled() async {
    let recorder = SessionStepRecorder()
    let service = makeService(recorder: recorder, screenActivityAbsent: true)

    let reuploaded = await service.reuploadDatabase(vmIP: "10.0.0.1", authToken: "vm-token")

    XCTAssertFalse(reuploaded)
  }
}
