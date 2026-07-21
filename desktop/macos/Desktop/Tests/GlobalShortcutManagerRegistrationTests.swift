import XCTest

@testable import Omi_Computer

#if DEBUG
  // omi-release-compile: this suite drives DEBUG-only registration-result factories;
  // the release-mode notification regression step must compile the bundle without them.

  @MainActor
  final class GlobalShortcutManagerRegistrationTests: XCTestCase {
    private struct Attempt: Equatable {
      let keyCode: Int
      let modifiers: Int
    }

    private let settings = ShortcutSettings.shared

    func testAtomicEnableAndShortcutUpdateRegistersOnlyTheFinalShortcut() {
      let original = savedRegistration()
      defer { restoreRegistration(original) }
      settings.updateAskOmiRegistration(enabled: false, shortcut: ShortcutSettings.askOmiCommandOShortcut)

      var attempts: [Attempt] = []
      var failures: [GlobalShortcutManager.HotKeyRegistrationOutcome] = []
      let manager = makeManager(
        registrar: { keyCode, modifiers in
          attempts.append(Attempt(keyCode: keyCode, modifiers: modifiers))
          return .testing(status: noErr, reference: .init("atomic"))
        },
        failureRecorder: { _, _, _, outcome in failures.append(outcome) }
      )
      defer { manager.stopObservingSettingsForTests() }

      settings.updateAskOmiRegistration(enabled: true, shortcut: ShortcutSettings.askOmiCommandJShortcut)

      XCTAssertEqual(attempts, [Attempt(keyCode: 38, modifiers: 256)])
      XCTAssertEqual(manager.askOmiRegistrationTraceForAutomation(), [.registered])
      XCTAssertTrue(failures.isEmpty, "The stale saved shortcut must never be registered or reported as a conflict.")
    }

    func testStandaloneEnableAndShortcutChangesStillRegisterCurrentValue() {
      let original = savedRegistration()
      defer { restoreRegistration(original) }
      settings.updateAskOmiRegistration(enabled: false, shortcut: ShortcutSettings.askOmiCommandOShortcut)

      var attempts: [Attempt] = []
      let manager = makeManager(registrar: { keyCode, modifiers in
        attempts.append(Attempt(keyCode: keyCode, modifiers: modifiers))
        return .testing(status: noErr, reference: .init("standalone"))
      })
      defer { manager.stopObservingSettingsForTests() }

      settings.askOmiEnabled = true
      settings.askOmiShortcut = ShortcutSettings.askOmiCommandReturnShortcut

      XCTAssertEqual(attempts, [Attempt(keyCode: 31, modifiers: 256), Attempt(keyCode: 36, modifiers: 256)])
    }

    func testLaterAtomicUpdateIsNotDroppedAfterAnEarlierNotification() {
      let original = savedRegistration()
      defer { restoreRegistration(original) }
      settings.updateAskOmiRegistration(enabled: false, shortcut: ShortcutSettings.askOmiCommandOShortcut)

      var attempts: [Int] = []
      let manager = makeManager(registrar: { keyCode, _ in
        attempts.append(keyCode)
        return .testing(status: noErr, reference: .init("later"))
      })
      defer { manager.stopObservingSettingsForTests() }

      settings.updateAskOmiRegistration(enabled: true, shortcut: ShortcutSettings.askOmiCommandReturnShortcut)
      settings.updateAskOmiRegistration(enabled: true, shortcut: ShortcutSettings.askOmiCommandJShortcut)

      XCTAssertEqual(attempts, [36, 38])
    }

    func testNoErrWithoutReferenceRecordsGenericFailureAndNeverLogsSuccess() throws {
      let original = savedRegistration()
      defer { restoreRegistration(original) }
      let result = try driveRegistration(status: noErr, reference: nil)

      assertRegistrationIncident(result.incidents, failureClass: "unknown", osStatus: 0)
      XCTAssertFalse(result.successLogs.contains { $0.contains("Registered Ask Omi") })
    }

    func testCarbonConflictRecordsOneConflictIncidentAndNeverLogsSuccess() throws {
      let original = savedRegistration()
      defer { restoreRegistration(original) }
      let result = try driveRegistration(status: OSStatus(-9878), reference: nil)

      assertRegistrationIncident(result.incidents, failureClass: "hotkey_conflict", osStatus: -9878)
      XCTAssertFalse(result.successLogs.contains { $0.contains("Registered Ask Omi") })
    }

    func testOtherCarbonFailureRecordsGenericIncidentAndNeverLogsSuccess() throws {
      let original = savedRegistration()
      defer { restoreRegistration(original) }
      let result = try driveRegistration(status: OSStatus(-50), reference: nil)

      assertRegistrationIncident(result.incidents, failureClass: "unknown", osStatus: -50)
      XCTAssertFalse(result.successLogs.contains { $0.contains("Registered Ask Omi") })
    }

    func testSuccessfulCarbonRegistrationLogsSuccessAndRecordsNoFailure() throws {
      let original = savedRegistration()
      defer { restoreRegistration(original) }
      let result = try driveRegistration(status: noErr, reference: .init("success"))

      XCTAssertTrue(result.incidents.isEmpty)
      XCTAssertEqual(result.successLogs, ["GlobalShortcutManager: Registered Ask Omi shortcut: ⌘ O"])
    }

    func testSuccessfulRegistrationRetainsReturnedReferenceThenReplacementAndDisableUnregisterItOnce() {
      let original = savedRegistration()
      defer { restoreRegistration(original) }
      settings.updateAskOmiRegistration(enabled: false, shortcut: ShortcutSettings.askOmiCommandOShortcut)

      let first = GlobalShortcutManager.TestHotKeyReference("first")
      let second = GlobalShortcutManager.TestHotKeyReference("second")
      var registered = [first, second]
      var unregistered: [GlobalShortcutManager.TestHotKeyReference] = []
      let manager = makeManager(
        registrar: { _, _ in .testing(status: noErr, reference: registered.removeFirst()) },
        testUnregisterer: {
          unregistered.append($0)
          return noErr
        }
      )
      defer { manager.stopObservingSettingsForTests() }

      settings.updateAskOmiRegistration(enabled: true, shortcut: ShortcutSettings.askOmiCommandOShortcut)
      XCTAssertEqual(manager.retainedTestHotKeyReferences(), [first])
      XCTAssertTrue(unregistered.isEmpty)

      settings.updateAskOmiRegistration(enabled: true, shortcut: ShortcutSettings.askOmiCommandJShortcut)
      XCTAssertEqual(manager.retainedTestHotKeyReferences(), [second])
      XCTAssertEqual(unregistered, [first])

      settings.updateAskOmiRegistration(enabled: false, shortcut: ShortcutSettings.askOmiCommandJShortcut)
      XCTAssertEqual(manager.retainedTestHotKeyReferences(), [])
      XCTAssertEqual(unregistered, [first, second])
    }

    func testNoReferenceFailuresNeverRetainOrUnregisterReferences() {
      let original = savedRegistration()
      defer { restoreRegistration(original) }
      settings.updateAskOmiRegistration(enabled: true, shortcut: ShortcutSettings.askOmiCommandOShortcut)

      var unregistered: [GlobalShortcutManager.TestHotKeyReference] = []
      var statuses: [OSStatus] = [noErr, OSStatus(-9878), OSStatus(-50)]
      let manager = makeManager(
        registrar: { _, _ in .testing(status: statuses.removeFirst(), reference: nil) },
        testUnregisterer: {
          unregistered.append($0)
          return noErr
        },
        observesSettings: false
      )

      manager.registerAskOmi()
      manager.registerAskOmi()
      manager.registerAskOmi()
      XCTAssertEqual(manager.retainedTestHotKeyReferences(), [])
      XCTAssertTrue(unregistered.isEmpty)
    }

    private func driveRegistration(
      status: OSStatus,
      reference: GlobalShortcutManager.TestHotKeyReference?
    ) throws -> (incidents: [[String: Any]], successLogs: [String]) {
      settings.updateAskOmiRegistration(enabled: true, shortcut: ShortcutSettings.askOmiCommandOShortcut)
      DesktopDiagnosticsManager.shared.resetForTests()
      var successLogs: [String] = []
      let manager = makeManager(
        registrar: { _, _ in .testing(status: status, reference: reference) },
        logger: { successLogs.append($0) },
        observesSettings: false
      )

      manager.registerAskOmi()
      return (try registrationIncidents(), successLogs)
    }

    private func makeManager(
      registrar: @escaping GlobalShortcutManager.HotKeyRegistrar,
      testUnregisterer: GlobalShortcutManager.TestHotKeyUnregisterer? = nil,
      failureRecorder: GlobalShortcutManager.HotKeyFailureRecorder? = nil,
      logger: @escaping GlobalShortcutManager.HotKeyLogger = { _ in },
      observesSettings: Bool = true
    ) -> GlobalShortcutManager {
      GlobalShortcutManager(
        registrar: registrar,
        testUnregisterer: testUnregisterer,
        failureRecorder: failureRecorder,
        logger: logger,
        observesSettings: observesSettings)
    }

    private func assertRegistrationIncident(
      _ incidents: [[String: Any]],
      failureClass: String,
      osStatus: Int,
      file: StaticString = #filePath,
      line: UInt = #line
    ) {
      XCTAssertEqual(incidents.count, 1, file: file, line: line)
      let incident = incidents[0]
      XCTAssertEqual(incident["event"] as? String, "user_visible_issue", file: file, line: line)
      XCTAssertEqual(incident["area"] as? String, "startup", file: file, line: line)
      XCTAssertEqual(incident["phase"] as? String, "startup", file: file, line: line)
      XCTAssertEqual(incident["failure_class"] as? String, failureClass, file: file, line: line)
      XCTAssertEqual(incident["osstatus"] as? Int, osStatus, file: file, line: line)
      XCTAssertEqual(incident["keycode"] as? Int, 31, file: file, line: line)
      XCTAssertEqual(incident["modifiers"] as? Int, 256, file: file, line: line)
    }

    private func registrationIncidents() throws -> [[String: Any]] {
      let url = try XCTUnwrap(DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment())
      defer { try? FileManager.default.removeItem(at: url) }
      let data = try Data(contentsOf: url)
      let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
      let snapshots = try XCTUnwrap(root["snapshots"] as? [[String: Any]])
      return snapshots.filter { $0["event"] as? String == "user_visible_issue" }
    }

    private func savedRegistration() -> (enabled: Bool, shortcut: ShortcutSettings.KeyboardShortcut) {
      (settings.askOmiEnabled, settings.askOmiShortcut)
    }

    private func restoreRegistration(_ registration: (enabled: Bool, shortcut: ShortcutSettings.KeyboardShortcut)) {
      settings.updateAskOmiRegistration(enabled: registration.enabled, shortcut: registration.shortcut)
      DesktopDiagnosticsManager.shared.resetForTests()
    }
  }
#endif
