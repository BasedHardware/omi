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
