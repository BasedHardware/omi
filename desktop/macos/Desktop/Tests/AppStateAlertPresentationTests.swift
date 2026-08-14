import XCTest

@testable import Omi_Computer

@MainActor
final class AppStateAlertPresentationTests: XCTestCase {
  func testShowAlertPresentsThroughTheNonBlockingSheetSeam() {
    let state = AppState()
    let presenter = RecordingAlertPresenter()
    state.alertPresenter = presenter

    state.showAlert(title: "Microphone Isn't Capturing Audio", message: "Check your input device and try again.")

    XCTAssertEqual(
      presenter.presentations,
      [
        .init(
          title: "Microphone Isn't Capturing Audio",
          message: "Check your input device and try again.")
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
}

@MainActor
private final class RecordingAlertPresenter: DesktopAlertPresenting {
  struct Presentation: Equatable {
    let title: String
    let message: String
  }

  private(set) var presentations: [Presentation] = []

  func present(title: String, message: String) {
    presentations.append(.init(title: title, message: message))
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

  func present(alert: NSAlert, window: NSWindow, completion: @escaping () -> Void) {
    presentations.append(.init(title: alert.messageText, message: alert.informativeText, window: window))
    completion()
  }
}
