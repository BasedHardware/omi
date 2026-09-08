import XCTest

@testable import Omi_Computer

@MainActor
final class AppStateAlertPresentationTests: XCTestCase {
  func testShowAlertPresentsThroughTheNonBlockingSheetSeam() {
    let state = AppState()
    let recorder = SheetPresentationRecorder()
    let window = NSWindow()
    state.alertPresenter = AppKitSheetAlertPresenter(
      shellWindowProvider: { window },
      appKitOperations: .init(beginSheetModal: recorder.present),
      revealMainWindow: {})

    state.showAlert(title: "Microphone Isn't Capturing Audio", message: "Check your input device and try again.")

    XCTAssertEqual(
      recorder.presentations,
      [
        .init(
          title: "Microphone Isn't Capturing Audio",
          message: "Check your input device and try again.",
          window: window)
      ])
  }

  func testAppKitPresenterUsesTheNonBlockingSheetOperationAfterRevealingTheMainWindow() {
    let windowSource = WindowSource()
    let recorder = SheetPresentationRecorder()
    let window = NSWindow()
    var revealCount = 0
    let presenter = AppKitSheetAlertPresenter(
      shellWindowProvider: { windowSource.window },
      appKitOperations: .init(beginSheetModal: recorder.present),
      revealMainWindow: {
        revealCount += 1
        windowSource.window = window
      })

    presenter.present(title: "Device Not Connected", message: "Connect your wearable device first.")

    XCTAssertEqual(revealCount, 1)
    XCTAssertEqual(
      recorder.presentations,
      [.init(title: "Device Not Connected", message: "Connect your wearable device first.", window: window)])
  }

  func testAppKitPresenterRetainsAlertUntilTheMainWindowBecomesAvailable() {
    let windowSource = WindowSource()
    let recorder = SheetPresentationRecorder()
    var revealCount = 0
    let presenter = AppKitSheetAlertPresenter(
      shellWindowProvider: { windowSource.window },
      appKitOperations: .init(beginSheetModal: recorder.present),
      revealMainWindow: { revealCount += 1 })

    presenter.present(title: "Device Not Connected", message: "Connect your wearable device first.")

    XCTAssertEqual(revealCount, 1)
    XCTAssertTrue(recorder.presentations.isEmpty)

    let window = NSWindow()
    windowSource.window = window
    NotificationCenter.default.post(name: NSWindow.didBecomeKeyNotification, object: window)

    XCTAssertEqual(
      recorder.presentations,
      [.init(title: "Device Not Connected", message: "Connect your wearable device first.", window: window)])
  }

  func testAppKitPresenterCoalescesMatchingPendingAlerts() {
    let windowSource = WindowSource()
    let recorder = SheetPresentationRecorder()
    var revealCount = 0
    let presenter = AppKitSheetAlertPresenter(
      shellWindowProvider: { windowSource.window },
      appKitOperations: .init(beginSheetModal: recorder.present),
      revealMainWindow: { revealCount += 1 })

    presenter.present(title: "Device Not Connected", message: "Connect your wearable device first.")
    presenter.present(title: "Device Not Connected", message: "Connect your wearable device first.")

    XCTAssertEqual(revealCount, 1)

    let window = NSWindow()
    windowSource.window = window
    NotificationCenter.default.post(name: NSWindow.didBecomeKeyNotification, object: window)

    XCTAssertEqual(
      recorder.presentations,
      [.init(title: "Device Not Connected", message: "Connect your wearable device first.", window: window)])
  }

  func testAppKitPresenterCoalescesMatchingActiveAlerts() {
    let window = NSWindow()
    let recorder = SheetPresentationRecorder()
    let presenter = AppKitSheetAlertPresenter(
      shellWindowProvider: { window },
      appKitOperations: .init(beginSheetModal: recorder.present),
      revealMainWindow: {})

    presenter.present(title: "Device Not Connected", message: "Connect your wearable device first.")
    presenter.present(title: "Device Not Connected", message: "Connect your wearable device first.")

    XCTAssertEqual(
      recorder.presentations,
      [.init(title: "Device Not Connected", message: "Connect your wearable device first.", window: window)])
  }

  func testPresentableShellWindowRequiresTheAppToBeActive() {
    let window = NSWindow()
    XCTAssertNil(AppKitSheetAlertPresenter.presentableShellWindow(window, isActive: false))
    XCTAssertNil(AppKitSheetAlertPresenter.presentableShellWindow(nil, isActive: true))
  }

  func testAppKitPresenterDefersWhileTheShellAlreadyOwnsASheet() async {
    let windowSource = WindowSource()
    let recorder = SheetPresentationRecorder()
    let window = NSWindow()
    var hostCanAccept = false
    let presenter = AppKitSheetAlertPresenter(
      shellWindowProvider: { windowSource.window },
      appKitOperations: .init(beginSheetModal: recorder.present),
      revealMainWindow: { windowSource.window = window },
      canHostSheet: { _ in hostCanAccept })

    presenter.present(title: "Device Not Connected", message: "Connect your wearable device first.")
    presenter.present(title: "Couldn't Start Transcription", message: "Retry or switch input devices.")

    XCTAssertTrue(recorder.presentations.isEmpty)

    // The requests are not dropped while the shell owns a sheet; once the
    // sheet ends (the host check passes again) the queued alerts drain in order.
    hostCanAccept = true
    NotificationCenter.default.post(name: NSWindow.didEndSheetNotification, object: window)
    await Task.yield()
    await Task.yield()

    XCTAssertEqual(
      recorder.presentations,
      [
        .init(title: "Device Not Connected", message: "Connect your wearable device first.", window: window),
        .init(title: "Couldn't Start Transcription", message: "Retry or switch input devices.", window: window),
      ])
  }

  func testAppKitPresenterDefersWhileTheShellOwnsASheetThenRevealsWhenNoneRemains() {
    let windowSource = WindowSource()
    let recorder = SheetPresentationRecorder()
    var revealCount = 0
    let presenter = AppKitSheetAlertPresenter(
      shellWindowProvider: { windowSource.window },
      appKitOperations: .init(beginSheetModal: recorder.present),
      revealMainWindow: { revealCount += 1 },
      canHostSheet: { $0.attachedSheet == nil })

    presenter.present(title: "Device Not Connected", message: "Connect your wearable device first.")

    XCTAssertTrue(recorder.presentations.isEmpty)
    XCTAssertEqual(revealCount, 1)

    let window = NSWindow()
    windowSource.window = window
    NotificationCenter.default.post(name: NSWindow.didBecomeKeyNotification, object: window)

    XCTAssertEqual(
      recorder.presentations,
      [.init(title: "Device Not Connected", message: "Connect your wearable device first.", window: window)])
  }

  func testAppKitPresenterRunsCompletionAfterTheSheetEnds() async {
    let window = NSWindow()
    let recorder = SheetPresentationRecorder(deferCompletions: true)
    let presenter = AppKitSheetAlertPresenter(
      shellWindowProvider: { window },
      appKitOperations: .init(beginSheetModal: recorder.present),
      revealMainWindow: {})

    var completions = 0
    presenter.present(title: "Omi Needs Microphone Access", message: "Enable Omi under System Settings.") {
      completions += 1
    }

    await Task.yield()
    await Task.yield()

    XCTAssertEqual(recorder.presentations.count, 1)
    XCTAssertEqual(completions, 0, "completion must not run before the sheet ends")

    recorder.endSheet()
    await Task.yield()
    await Task.yield()

    XCTAssertEqual(completions, 1, "completion runs once after the sheet ends")
  }

  func testAppKitPresenterPausesQueuedAlertsAfterACompletionDropsTheForeground() async {
    // The microphone-permission alert's completion opens System Settings, which
    // deactivates Omi. The next queued alert must not immediately summon Omi
    // back over the settings pane: presentation waits until Omi is active again.
    let windowSource = WindowSource()
    let recorder = SheetPresentationRecorder(deferCompletions: true)
    let presenter = AppKitSheetAlertPresenter(
      shellWindowProvider: { windowSource.window },
      appKitOperations: .init(beginSheetModal: recorder.present),
      revealMainWindow: {})

    let window = NSWindow()
    windowSource.window = window
    presenter.present(title: "Omi Needs Microphone Access", message: "Enable Omi under System Settings.")
    presenter.present(title: "Device Not Connected", message: "Connect your wearable device first.")

    await Task.yield()
    await Task.yield()
    XCTAssertEqual(recorder.presentations.count, 1, "only the permission alert presents first")

    // The first sheet's completion opens System Settings: Omi is no longer the
    // active app, so the shell provider returns no presentable window.
    windowSource.window = nil
    recorder.endSheet()
    await Task.yield()
    await Task.yield()

    XCTAssertEqual(
      recorder.presentations.count, 1,
      "queued alert must not be dragged forward while Omi is behind System Settings")

    // Omi becomes active again; the queued alert presents on the next window.
    windowSource.window = window
    NotificationCenter.default.post(name: NSApplication.didBecomeActiveNotification, object: nil)
    await Task.yield()
    await Task.yield()

    XCTAssertEqual(
      recorder.presentations,
      [
        .init(title: "Omi Needs Microphone Access", message: "Enable Omi under System Settings.", window: window),
        .init(title: "Device Not Connected", message: "Connect your wearable device first.", window: window),
      ])
  }

  func testAppKitPresenterHonorsAnExplicitQueuePauseFromCompletion() async {
    // Production ordering: the permission completion requests the pause, then
    // NSWorkspace.open returns while the shell is still presentable. The next
    // alert must stay queued until didBecomeActive, not drain synchronously.
    let windowSource = WindowSource()
    let recorder = SheetPresentationRecorder(deferCompletions: true)
    let presenter = AppKitSheetAlertPresenter(
      shellWindowProvider: { windowSource.window },
      appKitOperations: .init(beginSheetModal: recorder.present),
      revealMainWindow: {})

    let window = NSWindow()
    windowSource.window = window
    presenter.present(title: "Omi Needs Microphone Access", message: "Enable Omi under System Settings.") {
      presenter.pauseQueueUntilAppActive()
    }
    presenter.present(title: "Device Not Connected", message: "Connect your wearable device first.")

    await Task.yield()
    await Task.yield()
    XCTAssertEqual(recorder.presentations.count, 1, "only the permission alert presents first")

    recorder.endSheet()
    await Task.yield()
    await Task.yield()

    XCTAssertEqual(
      recorder.presentations.count, 1,
      "queued alert must not drain while the completion-requested pause is held")

    NotificationCenter.default.post(name: NSApplication.didBecomeActiveNotification, object: nil)
    await Task.yield()
    await Task.yield()

    XCTAssertEqual(
      recorder.presentations,
      [
        .init(title: "Omi Needs Microphone Access", message: "Enable Omi under System Settings.", window: window),
        .init(title: "Device Not Connected", message: "Connect your wearable device first.", window: window),
      ])
  }
}

@MainActor
private final class WindowSource {
  var window: NSWindow?
}

@MainActor
private final class SheetPresentationRecorder {
  struct Presentation: Equatable {
    let title: String
    let message: String
    let window: NSWindow

    static func == (lhs: Self, rhs: Self) -> Bool {
      lhs.title == rhs.title && lhs.message == rhs.message && lhs.window === rhs.window
    }
  }

  private(set) var presentations: [Presentation] = []
  private var deferredCompletions: [() -> Void] = []
  private let deferCompletions: Bool

  init(deferCompletions: Bool = false) {
    self.deferCompletions = deferCompletions
  }

  func present(alert: NSAlert, window: NSWindow, completion: @escaping () -> Void) {
    presentations.append(.init(title: alert.messageText, message: alert.informativeText, window: window))
    if deferCompletions {
      deferredCompletions.append(completion)
    } else {
      completion()
    }
  }

  /// Simulate the sheet ending; the presenter's per-alert completion runs now.
  func endSheet() {
    guard !deferredCompletions.isEmpty else { return }
    deferredCompletions.removeFirst()()
  }
}
