import XCTest

@testable import Omi_Computer

final class PersistedCaptureLaunchPolicyTests: XCTestCase {
  func testRestoresListeningFromPersistedIntentWithoutWaitingForRemoteKeys() {
    XCTAssertTrue(
      PersistedCaptureLaunchPolicy.shouldStartTranscription(
        intentEnabled: true,
        isTranscribing: false,
        micPermissionAuthorized: true
      )
    )
  }

  func testDoesNotRestartListeningWhenUserDisabledItOrItIsAlreadyRunning() {
    XCTAssertFalse(
      PersistedCaptureLaunchPolicy.shouldStartTranscription(
        intentEnabled: false,
        isTranscribing: false,
        micPermissionAuthorized: true
      )
    )
    XCTAssertFalse(
      PersistedCaptureLaunchPolicy.shouldStartTranscription(
        intentEnabled: true,
        isTranscribing: true,
        micPermissionAuthorized: true
      )
    )
  }

  func testRestoreNeverStartsOrPromptsWithoutMicrophoneAuthorization() {
    // The skip-mic prompt loop: intent stays on, TCC is notDetermined or denied.
    // An automatic start here would raise the system sheet (notDetermined) on
    // every launch/reactivation/key-load/settings-sync — or bounce a denied
    // alert. The restore must abandon instead and wait for an explicit action.
    XCTAssertFalse(
      PersistedCaptureLaunchPolicy.shouldStartTranscription(
        intentEnabled: true,
        isTranscribing: false,
        micPermissionAuthorized: false
      )
    )
  }

  func testRestoresCaptureWhenSettingsSyncFinishesAfterLaunch() {
    XCTAssertTrue(
      PersistedCaptureLaunchPolicy.shouldStartScreenAnalysis(
        intentEnabled: true,
        isMonitoring: false
      )
    )
  }

  func testDoesNotRestartCaptureWhenUserDisabledItOrItIsAlreadyRunning() {
    XCTAssertFalse(
      PersistedCaptureLaunchPolicy.shouldStartScreenAnalysis(
        intentEnabled: false,
        isMonitoring: false
      )
    )
    XCTAssertFalse(
      PersistedCaptureLaunchPolicy.shouldStartScreenAnalysis(
        intentEnabled: true,
        isMonitoring: true
      )
    )
  }
}

@MainActor
final class SettingsSyncCaptureRestorationTests: XCTestCase {
  func testApplyingServerSettingsNotifiesCaptureRuntimeToReconcile() {
    let notification = expectation(description: "capture runtime reconciliation notification")
    let observer = NotificationCenter.default.addObserver(
      forName: .assistantSettingsDidSyncFromServer,
      object: nil,
      queue: nil
    ) { _ in
      notification.fulfill()
    }
    defer { NotificationCenter.default.removeObserver(observer) }

    SettingsSyncManager.shared.applyRemoteSettings(AssistantSettingsResponse())

    XCTAssertEqual(XCTWaiter().wait(for: [notification], timeout: 0), .completed)
  }
}
