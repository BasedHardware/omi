import XCTest

@testable import Omi_Computer

@MainActor
final class AppStateOwnershipTests: XCTestCase {

  func testAppStateCurrentMatchesMostRecentlyInitializedInstance() {
    let state = AppState()
    XCTAssertTrue(state === AppState.current)
  }

  func testDesktopHomeViewDoesNotOwnAppState() throws {
    let sourceRoot = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/DesktopHomeView.swift")
    let source = try String(contentsOf: sourceRoot, encoding: .utf8)
    XCTAssertFalse(
      source.contains("@StateObject private var appState = AppState()"),
      "DesktopHomeView must receive AppState from OmiApp via environmentObject, not create its own"
    )
    XCTAssertTrue(
      source.contains("@EnvironmentObject private var appState: AppState"),
      "DesktopHomeView must declare @EnvironmentObject for appState"
    )
  }

  func testOmiAppInjectsAppStateIntoDesktopHomeView() throws {
    let sourceRoot = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/OmiApp.swift")
    let source = try String(contentsOf: sourceRoot, encoding: .utf8)
    XCTAssertTrue(
      source.contains(".environmentObject(appState)"),
      "OmiApp must inject the root AppState into DesktopHomeView"
    )
  }
}
