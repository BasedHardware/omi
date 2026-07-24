import XCTest

@testable import Omi_Computer

/// Regression coverage for the onboarding Google (Calendar/Gmail) connect fix.
///
/// Two failures this locks:
///  1. Onboarding connected a Google connector by only running a transient
///     `verifyConnection()` probe and flipping an in-memory chip — it never wrote
///     the `lastSyncedAt` latch the Apps page reads, so the connector showed
///     "connected" in onboarding and "Not connected" in the app. The connect now
///     runs the SAME import+persist seam the Apps page uses.
///  2. The onboarding id "gmail" must persist under the status-store id "email";
///     writing "gmail" would land on a key nothing reads.
///  3. A real `.error` (e.g. the Calendar API key not yet loaded) must be distinct
///     from `.needsSignIn` — only the latter should open the Google sign-in page.
@MainActor
final class OnboardingGoogleConnectTests: XCTestCase {

  func testResolutionOnlyPersistsAndSignsInForTheRightStates() {
    // Upstream's `googleContextResolution` owns the state decision; our persistence
    // branch keys off `state == "on"`, and only `.needsSignIn` opens the Google page.
    let connected = SBOnboardingModel.googleContextResolution(
      connectorID: "gmail", connected: true, needsSignIn: false)
    XCTAssertEqual(connected.state, "on")
    XCTAssertFalse(connected.shouldOpenSignIn)

    let signIn = SBOnboardingModel.googleContextResolution(
      connectorID: "gmail", connected: false, needsSignIn: true)
    XCTAssertEqual(signIn.state, "needsSignIn")
    XCTAssertTrue(signIn.shouldOpenSignIn)

    let error = SBOnboardingModel.googleContextResolution(
      connectorID: "calendar", connected: false, needsSignIn: false)
    XCTAssertEqual(error.state, "error")
    XCTAssertFalse(error.shouldOpenSignIn, "A real error must not open the sign-in page")
  }

  func testGmailOnboardingIdMapsToEmailStatusStoreId() {
    XCTAssertEqual(SBOnboardingModel.statusStoreConnectorID(forOnboardingID: "gmail"), "email")
    XCTAssertEqual(SBOnboardingModel.statusStoreConnectorID(forOnboardingID: "calendar"), "calendar")
  }

  /// The shared connect+persist seam must write the connector's `lastSyncedAt` latch
  /// on a successful import, so the Apps page (and onboarding) read it as connected.
  /// Uses the real `ImportConnectorStatusStore` + a fresh runner instance, mirroring
  /// `ConnectorImportRunnerTests` — no network / no cookies.
  func testStartPersistingImportWritesConnectedLatchUnderMappedId() async throws {
    let defaults = try XCTUnwrap(UserDefaults(suiteName: "test-\(UUID().uuidString)"))
    let store = ImportConnectorStatusStore(defaults: defaults, sessionUserID: "test-user")
    let email = try XCTUnwrap(ImportConnector.all.first { $0.id == "email" })
    XCTAssertFalse(store.snapshot(for: email).isConnected, "precondition: not connected")

    let task = ConnectorImportRunner.startPersistingImport(
      connectorID: SBOnboardingModel.statusStoreConnectorID(forOnboardingID: "gmail"),
      statusStore: store,
      title: "Importing Gmail history",
      detail: "…",
      runner: ConnectorImportRunner()
    ) { _ in
      .success(
        ConnectorImportOperations.SyncResult(sourceCount: 12, memoryCount: 8, newItems: 12),
        message: "ok")
    }
    await task?.value

    XCTAssertTrue(
      store.snapshot(for: email).isConnected,
      "A successful onboarding Gmail connect must persist the same latch the Apps page reads")
  }

  func testFailedImportDoesNotMarkConnected() async throws {
    let defaults = try XCTUnwrap(UserDefaults(suiteName: "test-\(UUID().uuidString)"))
    let store = ImportConnectorStatusStore(defaults: defaults, sessionUserID: "test-user")
    let calendar = try XCTUnwrap(ImportConnector.all.first { $0.id == "calendar" })

    let task = ConnectorImportRunner.startPersistingImport(
      connectorID: "calendar", statusStore: store, title: "t", detail: "d",
      runner: ConnectorImportRunner()
    ) { _ in .failure(message: "no session") }
    await task?.value

    XCTAssertFalse(store.snapshot(for: calendar).isConnected)
  }
}
