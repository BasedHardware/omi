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

  func testLoadedFailureSurvivesFiltersAndCompletionAndAccountResetRemoveIt() async {
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
    store.forget("search")
    XCTAssertTrue(store.activity([]).isEmpty)
    store.remember([conversation("search", step: "failed")], for: "fixture")
    store.reset()
    await store.refresh()
    XCTAssertTrue(store.activity([]).isEmpty)
  }

  func testOffPageSearchFailureLeavesActivityWhenRetryIsProcessingOrCompleted() async {
    let store = HomeFailurePlacementStore(load: { true }, owner: { "fixture" })
    await store.refresh()
    for status: ConversationStatus in [.processing, .completed] {
      store.remember([conversation("off-page", step: "failed")], for: "fixture")
      XCTAssertEqual(store.activity([]).map(\.id), ["off-page"])
      // Activity's retry explicitly remembers the authoritative result, even
      // when replaceConversation has no matching row in the current query.
      store.remember([conversation("off-page", status: status)], for: "fixture")
      XCTAssertTrue(store.activity([]).isEmpty)
    }
    store.remember([conversation("off-page", step: "failed")], for: "fixture")
    // A transport failure never supplies an authoritative replacement.
    XCTAssertEqual(store.activity([]).map(\.id), ["off-page"])
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

  private func ledger(_ id: String = "notes", kind: String = "conversation_notes_failed_with_outputs")
    -> AttentionLedgerItem
  {
    AttentionLedgerItem(
      id: id, kind: kind, conversationId: "conversation", retryable: true,
      retry: AttentionLedgerRetry(state: "none"), title: "Planning follow-up")
  }

  func testNoiseStaysOffHomeWithoutBecomingAttentionAndSwitchOffRestoresIt() {
    let noise = conversation("noise", step: "noise")
    XCTAssertTrue(ConversationFailurePlacement.home([noise], confirmed: true).isEmpty)
    XCTAssertTrue(ConversationFailurePlacement.activity([noise], confirmed: true).isEmpty)
    XCTAssertEqual(ConversationFailurePlacement.home([noise], confirmed: false).map(\.id), ["noise"])
  }

  func testLedgerMinimalContractAndUnknownKindAreSafe() throws {
    let json = """
      {"items":[{"id":"notes","kind":"conversation_notes_failed_with_outputs","conversation_id":"c",
      "retryable":true,"retry":{"state":"none","operation_id":null}},
      {"id":"future","kind":"future","conversation_id":"future","retryable":true,"retry":{"state":"none"}}]}
      """
    let page = try JSONDecoder().decode(AttentionLedgerPage.self, from: Data(json.utf8))
    XCTAssertTrue(page.items[0].canRetry)
    XCTAssertFalse(page.items[1].canRetry)
  }

  func testNotesRetryUsesLedgerItemAndDeduplicatesLegacyAndProjectedFailuresAfterSuccess() async {
    let notes = ledger()
    let unknown = AttentionLedgerItem(
      id: "future", kind: "future", conversationId: "future", retryable: true,
      retry: AttentionLedgerRetry(state: "none"))
    var calls: [String] = []
    let store = AttentionLedgerStore(
      load: {
        AttentionLedgerPage(
          enabled: true,
          items: [self.ledger("summary", kind: "conversation_summary_failed"), notes, unknown])
      },
      retry: { id, _ in
        calls.append(id)
        return AttentionLedgerRetry(state: "in_progress", operationId: "op")
      },
      owner: { "fixture" })
    await store.refresh()
    XCTAssertEqual(store.rows.map(\.id), ["notes", "future"])
    await store.retry(unknown)
    XCTAssertTrue(calls.isEmpty)
    await store.retry(notes)
    XCTAssertEqual(calls, ["notes"])
    XCTAssertEqual(store.rows.map(\.id), ["future"])
    XCTAssertTrue(store.conversationIds.contains("conversation"))
    await store.refresh()
    XCTAssertEqual(store.rows.map(\.id), ["future"], "stale ledger must not resurrect accepted retries")
  }

  func testLedgerRetryFailuresRetainErrorAndUnknownResponseStateIsNotSuccess() async {
    for failure in [0, 1, 2] {
      let store = AttentionLedgerStore(
        load: { AttentionLedgerPage(items: [self.ledger()]) },
        retry: { _, _ in
          if failure == 0 { throw RetryError.offline }
          if failure == 1 { throw APIError.httpError(statusCode: 409, detail: "not_retryable") }
          return AttentionLedgerRetry(state: "not_retryable")
        }, owner: { "fixture" })
      await store.refresh()
      await store.retry(store.rows[0])
      XCTAssertEqual(store.rows.count, 1)
      XCTAssertTrue(store.errors.contains("notes"))
      XCTAssertTrue(store.rows[0].canRetry)
      XCTAssertTrue(store.retrying.isEmpty)
    }
  }

  func testLedgerOldReadCannotResurrectNotesAndNewGenerationCanSurface() async {
    var completion: CheckedContinuation<AttentionLedgerPage, Never>?
    let (started, continuation) = AsyncStream<Void>.makeStream()
    var reads = 0
    let notes = ledger()
    let fresh = ledger("new-generation")
    let store = AttentionLedgerStore(
      load: {
        reads += 1
        if reads == 2 {
          return await withCheckedContinuation {
            completion = $0
            continuation.yield(())
          }
        }
        return AttentionLedgerPage(items: [reads > 2 ? fresh : notes])
      }, retry: { _, _ in AttentionLedgerRetry(state: "in_progress", operationId: "op") }, owner: { "fixture" })
    await store.refresh()
    let refresh = Task { await store.refresh() }
    for await _ in started { break }
    continuation.finish()
    await store.retry(notes)
    completion?.resume(returning: AttentionLedgerPage(items: [ledger("old-generation")]))
    await refresh.value
    XCTAssertTrue(store.rows.isEmpty)
    XCTAssertTrue(store.conversationIds.contains("conversation"))
    await store.refresh()
    XCTAssertEqual(store.rows.map(\.id), ["new-generation"])
  }

  func testLedgerDoubleTapAndAccountResetFenceLateRetry() async {
    let notes = ledger()
    var completion: CheckedContinuation<AttentionLedgerRetry, Error>?
    let (started, continuation) = AsyncStream<Void>.makeStream()
    var calls = 0
    var owner = "first"
    let store = AttentionLedgerStore(
      load: { AttentionLedgerPage(items: [notes]) },
      retry: { _, _ in
        calls += 1
        return try await withCheckedThrowingContinuation {
          completion = $0
          continuation.yield(())
        }
      }, owner: { owner })
    await store.refresh()
    let first = Task { await store.retry(notes) }
    for await _ in started { break }
    continuation.finish()
    await store.retry(notes)
    XCTAssertEqual(calls, 1)
    owner = "second"
    store.reset()
    completion?.resume(returning: AttentionLedgerRetry(state: "succeeded", operationId: "op"))
    await first.value
    XCTAssertTrue(store.rows.isEmpty)
    XCTAssertTrue(store.conversationIds.isEmpty)
  }

  func testRenderNotesAttentionCases010011012() async throws {
    guard let output = ProcessInfo.processInfo.environment["PROCESSING_TODAY_RENDER_OUTPUT"] else {
      throw XCTSkip("Set PROCESSING_TODAY_RENDER_OUTPUT for PNG evidence")
    }
    _ = NSApplication.shared
    NSApp.appearance = NSAppearance(named: .aqua)
    for (index, title) in ["Planning follow-up", "Actions captured", "Meeting scheduled"].enumerated() {
      var item = ledger("case-0\(10 + index)")
      item.title = title
      let fixture = item
      let store = AttentionLedgerStore(load: { AttentionLedgerPage(items: [fixture]) }, owner: { "fixture" })
      await store.refresh()
      try capture(
        VStack(alignment: .leading, spacing: 20) {
          Text("Activity").font(.title2).foregroundStyle(Ink.primary)
          AttentionLedgerSection(store: store, onOpen: { _ in })
          Spacer()
        }, to: output, name: "0\(25 + index)-desktop-macos-notes-case-0\(10 + index).png")
    }
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
