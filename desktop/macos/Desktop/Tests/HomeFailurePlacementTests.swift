import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

@MainActor
final class HomeFailurePlacementTests: XCTestCase {
  private enum RetryError: Error { case offline }

  private func conversation(_ id: String, step: String? = nil, status: ConversationStatus = .completed)
    -> ServerConversation
  {
    let at = Date(timeIntervalSince1970: 1_794_297_600)
    return ServerConversation(
      id: id, createdAt: at, updatedAt: nil, startedAt: at, finishedAt: at,
      structured: Structured(
        title: "Unfinished planning", overview: "", emoji: "", category: "", actionItems: [], events: []),
      transcriptSegments: [], transcriptSegmentsIncluded: false, geolocation: nil, photos: [], appsResults: [],
      source: nil, language: nil, status: status, homeStep: step, discarded: false, deleted: false,
      isLocked: false, starred: false, folderId: nil, inputDeviceName: nil)
  }

  func testFailureBelongsOnlyToActivityAndOffRestoresPreviousHome() {
    let failed = conversation("failed", step: "failed", status: .processing)
    let statusFailed = conversation("status-failed", status: .failed)
    let ready = conversation("ready", step: "ready")
    let rows = [failed, statusFailed, ready]
    XCTAssertEqual(ConversationFailurePlacement.home(rows, confirmed: true).map(\.id), ["ready"])
    XCTAssertEqual(ConversationFailurePlacement.activity(rows, confirmed: true).map(\.id), ["failed", "status-failed"])
    XCTAssertEqual(ConversationFailurePlacement.home(rows, confirmed: false).count, 3)
    XCTAssertTrue(ConversationFailurePlacement.activity(rows, confirmed: false).isEmpty)
  }

  func testWireRequiresSuccessfulExplicitConfirmation() throws {
    for (json, expected) in [
      ("{}", false), ("{\"enabled\":true}", false),
      ("{\"enabled\":true,\"home_processing_today\":false}", false),
      ("{\"enabled\":true,\"home_processing_today\":true}", true),
    ] {
      XCTAssertEqual(
        try JSONDecoder().decode(HomeFailurePlacementSnapshot.self, from: Data(json.utf8)).confirmed, expected)
    }
  }

  func testFailedReadRestoresPreviousPlacement() async {
    var shouldFail = false
    let store = HomeFailurePlacementStore(
      load: {
        if shouldFail { throw RetryError.offline }
        return true
      }, owner: { "fixture" }, onReadFailure: {})
    XCTAssertFalse(store.enabled)
    await store.refresh()
    XCTAssertTrue(store.enabled)
    shouldFail = true
    await store.refresh()
    XCTAssertFalse(store.enabled)
    store.reset()
    XCTAssertFalse(store.enabled)
  }

  func testSearchOnlyFailureRemainsReachableAndCompletionAndAccountResetRemoveIt() async {
    let store = HomeFailurePlacementStore(load: { true }, owner: { "fixture" })
    await store.refresh()
    store.remember([conversation("search", step: "failed")], for: "fixture")
    XCTAssertEqual(store.activity([]).map(\.id), ["search"])
    XCTAssertTrue(store.activity([conversation("search", step: "done")]).isEmpty)
    store.remember([conversation("foreign", step: "failed")], for: "other-owner")
    XCTAssertEqual(store.activity([]).map(\.id), ["search"])
    store.remember([conversation("search", step: "done")], for: "fixture")
    XCTAssertTrue(store.activity([]).isEmpty)
    store.remember([conversation("search", step: "failed")], for: "fixture")
    store.reset()
    await store.refresh()
    XCTAssertTrue(store.activity([]).isEmpty)
  }

  func testOldSuccessfulReadCannotEnableNewAccount() async {
    var owner = "first"
    var completion: CheckedContinuation<Bool, Never>?
    let (started, startedContinuation) = AsyncStream<Void>.makeStream()
    let store = HomeFailurePlacementStore(
      load: {
        await withCheckedContinuation {
          completion = $0
          startedContinuation.yield(())
        }
      }, owner: { owner })
    let pending = Task { await store.refresh() }
    for await _ in started { break }
    startedContinuation.finish()
    owner = "second"
    store.reset()
    completion?.resume(returning: true)
    await pending.value
    XCTAssertFalse(store.enabled)
  }

  func testRetryFencesDoubleTapsAndFailureRemainsRetryable() async {
    var calls = 0
    var completion: CheckedContinuation<Void, Error>?
    let (started, startedContinuation) = AsyncStream<Void>.makeStream()
    let controller = FailureActivityRetryController {
      calls += 1
      if calls == 1 {
        try await withCheckedThrowingContinuation {
          completion = $0
          startedContinuation.yield(())
        }
      }
    }
    let first = Task { await controller.run() }
    for await _ in started { break }
    startedContinuation.finish()
    await controller.run()
    XCTAssertEqual(calls, 1)
    completion?.resume(throwing: RetryError.offline)
    await first.value
    XCTAssertTrue(controller.failed)
    XCTAssertFalse(controller.busy)
    await controller.run()
    XCTAssertEqual(calls, 2)
    XCTAssertFalse(controller.failed)
  }

  func testRenderHomeWithoutFailureAndActivityWithRetry() throws {
    guard let output = ProcessInfo.processInfo.environment["PROCESSING_TODAY_RENDER_OUTPUT"] else {
      throw XCTSkip("Set PROCESSING_TODAY_RENDER_OUTPUT for PNG evidence")
    }
    _ = NSApplication.shared
    NSApp.appearance = NSAppearance(named: .aqua)
    let failed = conversation("failed", step: "failed", status: .processing)
    XCTAssertTrue(ConversationFailurePlacement.home([failed], confirmed: true).isEmpty)
    try capture(
      VStack(alignment: .leading, spacing: 20) {
        Text("Conversations").font(.title2).foregroundStyle(Ink.primary)
        HomeFailuresMovedState(openActivity: {})
      }, to: output, name: "017-desktop-macos-home-failed-after.png")
    try capture(
      VStack(alignment: .leading, spacing: 20) {
        Text("Activity").font(.title2).foregroundStyle(Ink.primary)
        FailedConversationsActivitySection(conversations: [failed], onOpen: { _ in }, retry: { _ in })
        Spacer()
      }, to: output, name: "018-desktop-macos-activity-failed-after.png")
  }

  private func capture<V: View>(_ view: V, to output: String, name: String) throws {
    let content = view.padding(24).frame(width: 720, height: 420, alignment: .topLeading)
      .background(Ink.surface).environment(\.colorScheme, .light)
    let renderer = ImageRenderer(content: content)
    renderer.scale = 2
    let image = try XCTUnwrap(renderer.cgImage)
    let rep = NSBitmapImageRep(cgImage: image)
    let data = try XCTUnwrap(rep.representation(using: .png, properties: [:]))
    let directory = URL(fileURLWithPath: output, isDirectory: true)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    try data.write(to: directory.appendingPathComponent(name))
  }
}
