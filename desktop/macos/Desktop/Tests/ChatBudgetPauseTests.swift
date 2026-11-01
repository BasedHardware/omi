import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

@MainActor
final class ChatBudgetPauseTests: XCTestCase {
  private func state(_ plan: String) throws -> APIClient.ChatAtCap {
    let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
      .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    let data = try Data(contentsOf: root.appendingPathComponent("backend/tests/fixtures/chat_at_cap_\(plan).json"))
    return try JSONDecoder().decode(APIClient.ChatAtCap.self, from: data)
  }
  func testBackendPauseCopyAndReset() throws {
    for plan in ["basic", "plus", "operator", "architect"] {
      let pause = try state(plan)
      XCTAssertEqual(pause.title, "Chat is paused")
      XCTAssertEqual(pause.trigger, "usage_budget")
      XCTAssertEqual(pause.resetLine, "Chat is back on Nov 1.")
      if plan == "operator" { XCTAssertEqual(pause.upgradeLabel, "Upgrade to Omi Pro") }
      let expired = APIClient.ChatAtCap(
        state: pause.state, title: pause.title, body: pause.body,
        resetAt: 1, resetLine: pause.resetLine, trigger: pause.trigger, upgradePlan: pause.upgradePlan,
        upgradeLabel: pause.upgradeLabel)
      XCTAssertFalse(expired.active)
    }
  }
  func testSharedBudgetDoesNotApplyTheOldQuestionCounter() throws {
    let data = Data(
      #"{"plan":"Free","plan_type":"basic","unit":"questions","used":999,"limit":30,"percent":100,"allowed":true,"uses_shared_budget":true}"#
        .utf8)
    let quota = try JSONDecoder().decode(APIClient.ChatUsageQuota.self, from: data)
    let limiter = FloatingBarUsageLimiter()
    limiter.applyQuota(quota)
    XCTAssertFalse(limiter.isLimitReached)
    limiter.recordQuery()
    XCTAssertFalse(limiter.isLimitReached)
  }

  func testRendersChatPauseStates() throws {
    for plan in ["basic", "plus", "operator", "architect"] {
      let pause = try state(plan)
      let view = VStack(alignment: .leading, spacing: OmiSpacing.xl) {
        Text("Chat").font(.title)
        Spacer()
        Text("What were the highlights of my day?").foregroundStyle(Ink.secondary)
        ChatBudgetPauseView(state: pause, onUpgrade: {})
      }.padding(24).frame(width: 640, height: 480)
        .background(Color(nsColor: .windowBackgroundColor)).environment(\.colorScheme, .dark)
      let renderer = ImageRenderer(content: view)
      renderer.scale = 2
      let image = try XCTUnwrap(renderer.cgImage)
      let png = try XCTUnwrap(NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:]))
      if let dir = ProcessInfo.processInfo.environment["OMI_STOREFRONT_RENDER_DIR"] {
        try png.write(to: URL(fileURLWithPath: dir).appendingPathComponent("021-desktop-macos-chat-at-cap-\(plan).png"))
      }
    }
  }
}
