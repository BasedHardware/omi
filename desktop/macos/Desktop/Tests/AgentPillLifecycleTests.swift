import XCTest

@testable import Omi_Computer

final class AgentPillLifecycleTests: XCTestCase {
  func testFloatingPillUsesBackgroundAgentPrompt() throws {
    let source = try agentPillSource()

    XCTAssertTrue(source.contains("You are running inside a visible floating background agent pill."))
    XCTAssertTrue(source.contains("Do the requested work now; do not merely acknowledge"))
    XCTAssertTrue(source.contains("systemPromptSuffix: systemPromptSuffix ?? Self.backgroundAgentSystemPromptSuffix"))
    XCTAssertTrue(source.contains("Do not call spawn_agent or delegate_agent just to hand off this same task."))
  }

  func testFloatingPillPromptRemovesNestedSpawnCapabilities() throws {
    let source = try chatProviderSource()

    XCTAssertTrue(source.contains("legacyClientScope == AgentLegacyClientScope.floatingPill"))
    XCTAssertTrue(source.contains(#"excludingToolNames: ["spawn_agent", "delegate_agent"]"#))
    XCTAssertTrue(source.contains("let scopedToolPrompt = DesktopCapabilityRegistry.scopedDesktopToolPrompt(excluding: excludedToolNames)"))
    XCTAssertTrue(source.contains(#".replacingOccurrences(of: "{user_name}", with: promptUserName)"#))
  }

  func testSubagentChatSpawnRequestCreatesSiblingAgent() throws {
    let source = try floatingControlBarViewSource()

    XCTAssertTrue(source.contains("if let handoff = AgentPillsManager.floatingAgentHandoff(for: trimmed)"))
    XCTAssertTrue(source.contains("let sibling = manager.spawnFromHandoff(handoff, model: pill.model)"))
    XCTAssertTrue(source.contains("state.activeAgentChatPillID = sibling.id"))
  }

  func testSubagentChatRendersMarkdownAndLargeBackHitTarget() throws {
    let source = try floatingControlBarViewSource()

    XCTAssertTrue(source.contains("import MarkdownUI"))
    XCTAssertTrue(source.contains("Markdown(outputText.isEmpty ? \"Working...\" : outputText)"))
    XCTAssertTrue(source.contains(".markdownTheme(.aiMessage(scale: 0.88))"))
    XCTAssertTrue(source.contains(".frame(width: 36, height: 36)"))
    XCTAssertTrue(source.contains(".contentShape(Rectangle())"))
  }

  func testNotchResponseGlowDrawsAboveDockSurface() throws {
    let source = try floatingControlBarViewSource()

    guard let dockRange = source.range(of: "NotchDockShape(bottomRadius: 22)") else {
      return XCTFail("Expected expanded notch dock surface")
    }
    guard let glowRange = source.range(of: "NotchResponseGlowView(") else {
      return XCTFail("Expected notch response glow view")
    }

    XCTAssertLessThan(
      dockRange.lowerBound,
      glowRange.lowerBound,
      "The response glow must be drawn after the black dock fill so the straight left, right, and bottom strokes stay visible in expanded chat.")
  }

  func testNotchAgentSwitcherUsesStackedPersistentList() throws {
    let source = try floatingControlBarViewSource()
    let windowSource = try floatingControlBarWindowSource()

    XCTAssertTrue(source.contains("state.showingAIConversation || agentSwitcherPinned || agentSwitcherHovering"))
    XCTAssertTrue(source.contains("NotchAgentStackMetrics.overlapStep"))
    XCTAssertTrue(source.contains(".offset(x: CGFloat(index) * NotchAgentStackMetrics.overlapStep)"))
    XCTAssertTrue(source.contains("NotchAgentSwitcherMenu("))
    XCTAssertTrue(source.contains("state.activeAgentChatPillID = pill.id"))
    XCTAssertFalse(source.contains(".popover(isPresented: groupPopoverBinding"))
    XCTAssertTrue(windowSource.contains("func resizeForAgentSwitcher(visible: Bool)"))
  }

  func testFloatingBarExplicitSpawnCompletesParentTurn() throws {
    let source = try floatingControlBarWindowSource()

    XCTAssertTrue(source.contains("let handoff = AgentPillsManager.floatingAgentHandoff(for: message)"))
    XCTAssertTrue(source.contains("AgentPillsManager.shared.spawnFromHandoff("))
    XCTAssertTrue(source.contains("completeVisibleAgentHandoff("))
  }

  func testFloatingPillDoesNotTreatMissingTerminalProjectionAsSuccess() throws {
    let source = try agentPillSource()

    XCTAssertTrue(source.contains("Agent ended before reporting a final result"))
    XCTAssertFalse(source.contains("pill.latestActivity = pill.latestActivity.isEmpty ? \"Finished\" : pill.latestActivity"))
  }

  func testFallbackFailurePathsRecordCompletionTime() throws {
    let source = try agentPillSource()

    XCTAssertTrue(
      source.contains(
        """
        pill.status = .failed(errorText)
                    pill.latestActivity = errorText
                    pill.completedAt = Date()
        """))
    XCTAssertTrue(
      source.contains(
        "pill.status = .failed(\"Agent ended before reporting a final result\")\n            pill.completedAt = Date()"))
  }

  func testLateMessageActivityCannotOverwriteTerminalPillStatus() throws {
    let source = try agentPillSource()

    XCTAssertTrue(source.contains("if pill.status.isFinished {\n            return\n        }"))
    XCTAssertTrue(source.contains("let activity = Self.describeActivity(for: aiMessage)"))
  }

  private func agentPillSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/AgentPill.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func chatProviderSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Providers/ChatProvider.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func floatingControlBarViewSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/FloatingControlBarView.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func floatingControlBarWindowSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/FloatingControlBarWindow.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}
