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

  func testSheetPresenterDefersAlertUntilAWindowBecomesVisible() {
    let windowSource = WindowSource()
    let recorder = SheetPresentationRecorder()
    let presenter = AppKitSheetAlertPresenter(
      windowProvider: { windowSource.window },
      sheetPresenter: recorder.present,
      activateApplication: {})

    presenter.present(title: "Device Not Connected", message: "Connect your wearable device first.")

    XCTAssertTrue(recorder.presentations.isEmpty)

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
