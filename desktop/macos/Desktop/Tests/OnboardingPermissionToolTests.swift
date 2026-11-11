import XCTest

@testable import Omi_Computer

final class OnboardingPermissionToolTests: XCTestCase {
  private let hasCompletedFileIndexingKey = "hasCompletedFileIndexing"
  private let resumeStepKey = "sbOnboardingResumeStep"

  override func setUp() {
    super.setUp()
    UserDefaults.standard.removeObject(forKey: hasCompletedFileIndexingKey)
    UserDefaults.standard.removeObject(forKey: resumeStepKey)
  }

  override func tearDown() {
    UserDefaults.standard.removeObject(forKey: hasCompletedFileIndexingKey)
    UserDefaults.standard.removeObject(forKey: resumeStepKey)
    super.tearDown()
  }

  func testPermissionStatusPayloadIncludesEveryPermissionAdvertisedToOnboardingAgent() {
    let statuses = ChatToolExecutor.onboardingPermissionStatusPayload(
      screenRecording: false,
      microphone: false,
      notifications: false,
      accessibility: false,
      automation: false,
      fullDiskAccess: false
    )

    XCTAssertEqual(
      Set(statuses.keys),
      Set(ChatToolExecutor.onboardingPermissionTypes)
    )
    XCTAssertTrue(statuses.keys.contains("notifications"))
  }

  func testSupportedPermissionTypesIncludeNotifications() {
    XCTAssertEqual(
      ChatToolExecutor.onboardingPermissionTypes,
      [
        "screen_recording",
        "microphone",
        "notifications",
        "accessibility",
        "automation",
        "full_disk_access",
      ])
  }

  @MainActor
  func testPregrantedScreenRecordingDoesNotSkipSeparateSystemAudioConsent() {
    let appState = AppState()
    appState.hasScreenRecordingPermission = true
    appState.recordSystemAudioCaptureOutcome(.unknown)
    let model = SBOnboardingModel(
      appState: appState,
      chatProvider: ChatProvider(),
      onComplete: nil)

    XCTAssertFalse(
      model.isGranted("system_audio"),
      "Screen Recording alone must never be reported as a system-audio grant")
    XCTAssertEqual(
      model.firstUnaskedStep(from: .systemAudio),
      .systemAudio,
      "Screen Recording is only a prerequisite; it cannot stand in for a successful Core Audio tap")

    appState.recordSystemAudioCaptureOutcome(.denied)
    XCTAssertEqual(
      model.firstUnaskedStep(from: .systemAudio),
      .systemAudio,
      "a real denied tap must keep the system-audio permission step visible")
  }

  @MainActor
  func testRepeatedSystemAudioPollingCancelsTheOlderConsentTask() throws {
    let model = SBOnboardingModel(
      appState: AppState(),
      chatProvider: ChatProvider(),
      onComplete: nil)

    model.pollPermission("system_audio")
    let first = try XCTUnwrap(model.pollTasks["system_audio"])
    model.pollPermission("system_audio")
    let second = try XCTUnwrap(model.pollTasks["system_audio"])
    defer { second.cancel() }

    XCTAssertTrue(first.isCancelled)
    XCTAssertFalse(second.isCancelled)
  }

  @MainActor
  func testFilesStageScansAndFormsProfileBeforeAdvancing() async {
    var scanCalls = 0
    let appState = AppState()
    let chatProvider = ChatProvider()
    let model = SBOnboardingModel(
      appState: appState,
      chatProvider: chatProvider,
      fileScanRunner: { _ in
        scanCalls += 1
        return .complete(fileCount: 42, memoryCount: 3, deniedFolders: [])
      },
      onComplete: nil)
    model.step = .files
    model.fdaState = .on

    model.answerFiles()
    await model.localFileScanTask?.value

    XCTAssertEqual(scanCalls, 1)
    XCTAssertEqual(model.step, .files, "Files must wait for local profile formation")
    XCTAssertEqual(model.localFileProfileState, .complete(fileCount: 42, memoryCount: 3, deniedFolders: []))
    XCTAssertTrue(UserDefaults.standard.bool(forKey: hasCompletedFileIndexingKey))
    XCTAssertEqual(
      UserDefaults.standard.integer(forKey: SBOnboardingModel.resumeStepKey),
      SBOnboardingModel.Step.accessibility.rawValue,
      "a completed scan must not repeat after a relaunch before Continue")

    model.finishFilesStep()

    XCTAssertNotEqual(model.step, .files, "Files must advance even when the test host already has later TCC grants")
  }

  @MainActor
  func testFilesStageCanContinueAfterScanFailure() async {
    let appState = AppState()
    let chatProvider = ChatProvider()
    let model = SBOnboardingModel(
      appState: appState,
      chatProvider: chatProvider,
      fileScanRunner: { _ in .failed(message: "No readable folders") },
      onComplete: nil)
    model.step = .files
    model.fdaState = .on

    model.answerFiles()
    await model.localFileScanTask?.value
    model.finishFilesStep()

    XCTAssertNotEqual(model.step, .files, "Files must advance even when the test host already has later TCC grants")
    XCTAssertFalse(UserDefaults.standard.bool(forKey: hasCompletedFileIndexingKey))
  }

  @MainActor
  func testLeavingFilesCancelsTheScanAndAllowsARetryOnReturn() async {
    let firstScanStarted = expectation(description: "first scan started")
    let releaseFirstScan = expectation(description: "release first scan")
    var scanCalls = 0
    let appState = AppState()
    let chatProvider = ChatProvider()
    let model = SBOnboardingModel(
      appState: appState,
      chatProvider: chatProvider,
      fileScanRunner: { _ in
        scanCalls += 1
        if scanCalls == 1 {
          firstScanStarted.fulfill()
          await self.fulfillment(of: [releaseFirstScan], timeout: 1)
        }
        return .complete(fileCount: 1, memoryCount: 1, deniedFolders: [])
      },
      onComplete: nil)
    model.step = .files
    model.fdaState = .on

    model.answerFiles()
    await fulfillment(of: [firstScanStarted], timeout: 1)
    model.goBack()

    XCTAssertEqual(model.localFileProfileState, .idle)
    XCTAssertNotNil(model.localFileScanTask, "a cancelled scan must finish before another scan can start")

    releaseFirstScan.fulfill()
    await model.localFileScanTask?.value
    model.step = .files
    model.fdaState = .on
    model.answerFiles()
    await model.localFileScanTask?.value

    XCTAssertEqual(scanCalls, 2)
    XCTAssertEqual(model.localFileProfileState, .complete(fileCount: 1, memoryCount: 1, deniedFolders: []))
  }
}
