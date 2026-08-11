import XCTest

@testable import Omi_Computer

final class AppStateListeningTests: XCTestCase {
  private let listeningDefaultsKey = "omi.listening.enabled"

  override func setUp() {
    super.setUp()
    UserDefaults.standard.removeObject(forKey: listeningDefaultsKey)
  }

  override func tearDown() {
    UserDefaults.standard.removeObject(forKey: listeningDefaultsKey)
    super.tearDown()
  }

  @MainActor
  func testToggleListeningPersistsAndReloads() {
    let appState = AppState()
    XCTAssertTrue(appState.isConversationListening)

    appState.toggleConversationListening(source: "ui")

    XCTAssertFalse(appState.isConversationListening)
    XCTAssertEqual(UserDefaults.standard.object(forKey: listeningDefaultsKey) as? Bool, false)

    let reloadedAppState = AppState()
    XCTAssertFalse(reloadedAppState.isConversationListening)

    reloadedAppState.setConversationListening(true, source: "ui")

    XCTAssertTrue(reloadedAppState.isConversationListening)
    XCTAssertEqual(UserDefaults.standard.object(forKey: listeningDefaultsKey) as? Bool, true)
  }
}
