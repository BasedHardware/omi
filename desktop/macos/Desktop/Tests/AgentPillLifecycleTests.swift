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
    XCTAssertTrue(source.contains("state.present(.agent(sibling.id))"))
  }

  func testSubagentChatRendersMarkdownAndLargeBackHitTarget() throws {
    let source = try floatingControlBarViewSource()

    XCTAssertTrue(source.contains("import MarkdownUI"))
    XCTAssertFalse(source.contains("Markdown(outputText.isEmpty ? \"Working...\" : outputText)"))
    XCTAssertTrue(source.contains("Markdown(outputText)"))
    XCTAssertTrue(source.contains(".markdownTheme(.aiMessage(scale: 0.88))"))
    XCTAssertTrue(source.contains(".frame(width: 36, height: 36)"))
    XCTAssertTrue(source.contains(".contentShape(Rectangle())"))
    XCTAssertTrue(source.contains("barWindow?.resizeForActiveAgentChatPublic(pillID: pill.id, animated: !wasShowingConversation)"))
  }

  func testNotchResponseGlowStaysBehindDockSurface() throws {
    let source = try floatingControlBarViewSource()
    let windowSource = try floatingControlBarWindowSource()

    guard let dockRange = source.range(of: "NotchDockShape(bottomRadius:") else {
      return XCTFail("Expected expanded notch dock surface")
    }
    guard let glowRange = source.range(of: "NotchResponseGlowView(") else {
      return XCTFail("Expected notch response glow view")
    }

    XCTAssertGreaterThan(
      glowRange.lowerBound,
      dockRange.lowerBound,
      "The response glow is declared after the black dock fill in the ZStack, so it renders on top of the dock surface — keeping the glow on the lower edge without cutting into the pure-black notch island.")
    XCTAssertTrue(source.contains("private var notchSurfaceHorizontalInset: CGFloat"))
    XCTAssertTrue(source.contains("state.usesNotchIsland ? FloatingControlBarWindow.notchGlowOutsetX : 0"))
    XCTAssertTrue(source.contains("state.usesNotchIsland ? FloatingControlBarWindow.notchGlowOutsetBottom : 0"))
    XCTAssertTrue(source.contains("geometry.size.width - notchSurfaceHorizontalInset * 2"))
    XCTAssertTrue(source.contains("geometry.size.height - notchSurfaceBottomInset"))
    XCTAssertTrue(source.contains(".padding(.horizontal, notchSurfaceHorizontalInset)"))
    XCTAssertTrue(source.contains(".padding(.bottom, notchSurfaceBottomInset)"))
    XCTAssertTrue(windowSource.contains("if usesNotchIsland {\n            return NSSize("))
    XCTAssertFalse(windowSource.contains("let targetSize = self.currentSurfaceSizeForCurrentScreen(frameIncludesVoiceGlow: wasActive)"))
  }

  func testNotchPTTUsesCompactWaveformOnly() throws {
    let source = try floatingControlBarViewSource()

    guard let lobeRange = source.range(of: "private var notchAgentLobe: some View"),
      let controlRange = source.range(of: "private var notchControlLobe: some View")
    else {
      return XCTFail("Expected notch lobe sections")
    }
    let lobeSource = String(source[lobeRange.lowerBound..<controlRange.lowerBound])

    XCTAssertTrue(lobeSource.contains("VoiceWaveformBars(isActive: true)"))
    XCTAssertFalse(lobeSource.contains("Image(systemName: \"mic.fill\")"))
  }

  func testNotchChatSizingPreservesSurfaceWidthAndGlowList() throws {
    let source = try floatingControlBarWindowSource()

    XCTAssertTrue(source.contains("let width = max(defaultWidth, currentResponseSurfaceWidth(usesNotchIsland: usesNotchIsland))"))
    XCTAssertTrue(source.contains("func resizeForAgentSwitcher(visible: Bool)"))
    XCTAssertFalse(source.contains("!state.isVoiceResponseActive,\n              !state.isShowingNotification"))
  }

  func testStreamingResponseGrowthIsSteppedAndNonAnimated() throws {
    let windowSource = try floatingControlBarWindowSource()
    let viewSource = try floatingControlBarViewSource()
    let responseSource = try aiResponseViewSource()

    XCTAssertTrue(windowSource.contains("responseStreamingResizeStep"))
    XCTAssertTrue(windowSource.contains("let steppedHeight = (targetHeight / Self.responseStreamingResizeStep).rounded(.up) * Self.responseStreamingResizeStep"))
    XCTAssertTrue(windowSource.contains("to: NSSize(width: max(self.expandedContentWidth, self.currentResponseSurfaceWidth()), height: clampedHeight)"))
    XCTAssertTrue(windowSource.contains("animated: false,\n                    anchorTop: true"))
    XCTAssertTrue(viewSource.contains(".transition(.opacity)"))
    XCTAssertFalse(viewSource.contains("conversationView\n                    .padding(.horizontal, 12)\n                    .padding(.top, 4)\n                    .padding(.bottom, 9)\n                    .transition(.move(edge: .top).combined(with: .opacity))"))
    XCTAssertTrue(responseSource.contains(".onChange(of: currentMessage?.text) {\n                    proxy.scrollTo(\"bottom\", anchor: .bottom)\n                }"))
    XCTAssertTrue(responseSource.contains(".onChange(of: currentMessage?.contentBlocks.count) {\n                    proxy.scrollTo(\"bottom\", anchor: .bottom)\n                }"))
  }

  func testNotchAgentIndicatorUsesOmiDotsAndStackedList() throws {
    let source = try floatingControlBarViewSource()
    let windowSource = try floatingControlBarWindowSource()
    let responseSource = try aiResponseViewSource()

    // The old literal expression "state.showingAIConversation || state.agentSwitcherPinned
    // || state.agentSwitcherHovering" was replaced by the shouldShowAgentSwitcher computed
    // property; the notchChromeLayoutWidth assertion below covers the derived usage.

    XCTAssertTrue(source.contains("state.showingAIConversation || shouldShowAgentSwitcher"))
    XCTAssertTrue(source.contains("static let maxAgents = FloatingControlBarWindow.notchAgentListMaxVisibleAgents"))
    XCTAssertTrue(source.contains("static let dotDiameterRatio: CGFloat = 0.18"))
    XCTAssertTrue(source.contains("static let ringRadiusRatio: CGFloat = 0.33"))
    XCTAssertTrue(source.contains("NotchAgentOmiIndicatorView(pills: stackedPills)"))
    XCTAssertTrue(source.contains("NotchOmiMark(dotColors: visiblePills.map"))
    XCTAssertTrue(source.contains("NotchAgentMorphField("))
    XCTAssertTrue(source.contains("NotchAgentListRow(\n                                title: pill.title,\n                                status: pill.status,\n                                activity: pill.latestActivity,\n                                isSelected: pill.id == activePillID,\n                                progress: rowRevealProgress"))
    XCTAssertTrue(source.contains("ForEach(0..<NotchAgentStackMetrics.maxAgents"))
    XCTAssertTrue(source.contains("let rowWidth = max(0, min(width - NotchAgentStackMetrics.listHorizontalInset * 2, FloatingControlBarWindow.notchExpandedWidth - NotchAgentStackMetrics.listHorizontalInset * 2))"))
    XCTAssertTrue(source.contains("static let listHorizontalInset: CGFloat = 12"))
    XCTAssertTrue(source.contains("static let listRowLeadingPadding: CGFloat = 12"))
    XCTAssertTrue(source.contains("static func logoCenterX("))
    XCTAssertTrue(source.contains("static func logoDotSourceOffset(for index: Int) -> CGSize"))
    XCTAssertTrue(source.contains("GeometryReader { geometry in"))
    XCTAssertTrue(source.contains("notchHiddenCenterWidth: notchHiddenCenterWidth"))
    XCTAssertTrue(source.contains("notchSideWidth: notchSideWidth"))
    XCTAssertTrue(source.contains("static func quadraticBezier(from start: CGPoint, control: CGPoint, to end: CGPoint, progress: CGFloat) -> CGPoint"))
    XCTAssertTrue(source.contains("let rowRevealProgress = NotchAgentStackMetrics.smoothStep((progress - 0.38) / 0.62)"))
    XCTAssertTrue(source.contains("let logoPlaceholderProgress = NotchAgentStackMetrics.smoothStep(progress / 0.42)"))
    XCTAssertTrue(source.contains("? .spring(response: 0.34, dampingFraction: 0.86)"))
    XCTAssertTrue(source.contains(": .spring(response: 0.18, dampingFraction: 0.92)"))
    XCTAssertTrue(source.contains(".transition(.identity)"))
    XCTAssertTrue(source.contains("Color.clear\n                    .frame(width: notchChromeLayoutWidth, height: notchAgentListHeight)"))
    XCTAssertTrue(source.contains("state.present(.agent(pill.id))"))
    XCTAssertTrue(source.contains("private let agentChatSwitchTransition = Animation.easeOut(duration: 0.10)"))
    XCTAssertTrue(source.contains("if state.conversationSurface == .agent(pill.id)"))
    XCTAssertTrue(source.contains("@State private var notchLogoHovering = false"))
    XCTAssertTrue(source.contains("private func setNotchLogoHovering(_ hovering: Bool)"))
    XCTAssertTrue(source.contains("private var notchAgentLogoHitTarget: some View"))
    XCTAssertTrue(source.contains("(agentPills.pills.isEmpty || state.showingAIConversation) && !notchLogoHovering ? 1 : 0"))
    XCTAssertTrue(source.contains("ZStack(alignment: .trailing)"))
    XCTAssertTrue(source.contains(".frame(width: NotchAgentStackMetrics.logoFrameSize, height: NotchAgentStackMetrics.logoFrameSize)"))
    XCTAssertTrue(source.contains(".frame(width: 44, height: 44)"))
    XCTAssertTrue(source.contains(".onTapGesture {\n                    openFloatingBarSettings()\n                }"))
    XCTAssertTrue(source.contains("Image(systemName: \"gearshape.fill\")"))
    XCTAssertTrue(source.contains("setAgentSwitcherHovering(hovering)"))
    XCTAssertFalse(source.contains("@State private var agentSwitcherPinned"))
    XCTAssertFalse(source.contains("@State private var agentSwitcherHovering"))
    XCTAssertTrue(source.contains("state.hideConversationSurface()"))
    XCTAssertTrue(source.contains("Text(\"Omi Chat\")"))
    XCTAssertTrue(source.contains("barWindow?.resizeForActiveAgentChatPublic(pillID: pill.id, animated: !wasShowingConversation)"))
    XCTAssertTrue(source.contains("ForEach(0..<NotchAgentStackMetrics.maxAgents"))
    XCTAssertTrue(source.contains("NotchLogoPlaceholderDot(progress: logoPlaceholderProgress)"))
    XCTAssertTrue(source.contains("Color.white.opacity(0.96 * Double(1 - progress))"))
    XCTAssertTrue(source.contains("if !agentPills.pills.isEmpty && !showingNotchWaveform && !state.showingAIConversation"))
    XCTAssertTrue(source.contains("private var showingNotchWaveform: Bool"))
    XCTAssertTrue(source.contains("private var escToClearHint: some View"))
    XCTAssertTrue(source.contains("if state.hasVisibleConversation {\n                        escToClearHint\n                    }"))
    XCTAssertTrue(source.contains("canClearVisibleConversation: state.usesNotchIsland ? false : state.hasVisibleConversation"))
    XCTAssertTrue(source.contains("showsHeader: !state.usesNotchIsland"))
    XCTAssertTrue(responseSource.contains("var showsHeader: Bool = true"))
    XCTAssertTrue(responseSource.contains("if showsHeader {"))
    XCTAssertTrue(responseSource.contains(".padding(.top, state.usesNotchIsland ? 0 : 16)"))
    XCTAssertFalse(source.contains("NotchAgentSwitcherMenu("))
    XCTAssertFalse(source.contains("Text(\"Subagents\")"))
    XCTAssertFalse(source.contains(".fill(Color.white.opacity(0.025))"))
    XCTAssertTrue(windowSource.contains("static let notchAgentListMaxVisibleAgents = 8"))
    XCTAssertTrue(windowSource.contains("static let notchAgentListRowHeight: CGFloat = 44"))
    XCTAssertTrue(windowSource.contains("static let notchAgentListRowSpacing: CGFloat = 0"))
    XCTAssertTrue(windowSource.contains("static let notchAgentListVerticalPadding: CGFloat = 0"))
    XCTAssertTrue(windowSource.contains("static let notchAgentListBottomMargin: CGFloat = 8"))
    XCTAssertTrue(source.contains(".fill(isSelected ? Color.white.opacity(0.12 * Double(progress)) : .clear)"))
    XCTAssertTrue(source.contains(".overlay(alignment: .bottom)"))
    XCTAssertFalse(source.contains(".strokeBorder(Color.white.opacity(0.10 * Double(progress)), lineWidth: 0.6)"))
    XCTAssertTrue(windowSource.contains("private static let askOmiAnimationDuration: TimeInterval = 0.055"))
    XCTAssertTrue(windowSource.contains("private static let askOmiSettleDelay: TimeInterval = 0.065"))
    XCTAssertTrue(windowSource.contains("let currentTopCenteredFrame = NSRect("))
    XCTAssertTrue(windowSource.contains("abs(frame.midX - targetFrame.midX) > 0.5"))
    XCTAssertTrue(windowSource.contains("let keepVoiceResponseAlive = state.isVoiceResponseActive"))
    XCTAssertTrue(windowSource.contains("FloatingControlBarManager.shared.cancelChat(keepVoiceAlive: keepVoiceResponseAlive)"))
    XCTAssertTrue(windowSource.contains("static func notchAgentListHeight(agentCount: Int) -> CGFloat"))
    XCTAssertTrue(windowSource.contains("+ notchAgentListBottomMargin"))
    XCTAssertTrue(windowSource.contains("static let notchActiveSideWidth: CGFloat = 42"))
    XCTAssertTrue(windowSource.contains("func resizeForAgentSwitcher(visible: Bool)"))
    XCTAssertTrue(windowSource.contains("max(collapsedBarSize.width, Self.notchExpandedWidth)"))
    XCTAssertTrue(windowSource.contains("if state.showingAIConversation {\n                return\n            }"))
  }

  func testFloatingBarExplicitSpawnCompletesParentTurn() throws {
    let source = try floatingControlBarWindowSource()

    XCTAssertTrue(source.contains("let handoff = AgentPillsManager.floatingAgentHandoff(for: message)"))
    XCTAssertTrue(source.contains("AgentPillsManager.shared.spawnFromHandoff("))
    XCTAssertTrue(source.contains("completeVisibleAgentHandoff("))
  }

  func testResizeGripKeepsNotchCentered() throws {
    let source = try resizeHandleSource()
    let viewSource = try floatingControlBarViewSource()

    XCTAssertTrue(source.contains("initialWindowFrame.width + deltaX * 2"))
    XCTAssertTrue(source.contains("let newOriginX = initialWindowFrame.midX - newWidth / 2"))
    XCTAssertTrue(source.contains("NSRect(x: newOriginX, y: newOriginY, width: newWidth, height: newHeight)"))
    XCTAssertTrue(source.contains("finishUserResponseResize()"))
    XCTAssertFalse(source.contains("NSRect(x: initialWindowFrame.minX, y: newOriginY"))
    XCTAssertTrue(viewSource.contains(".padding(.trailing, notchSurfaceHorizontalInset + 4)"))
    XCTAssertTrue(viewSource.contains(".padding(.bottom, notchSurfaceBottomInset + 4)"))
  }

  func testResponseResizePreservesUserSurfaceSize() throws {
    let source = try floatingControlBarWindowSource()

    XCTAssertTrue(source.contains("private func currentResponseSurfaceWidth(usesNotchIsland: Bool? = nil) -> CGFloat"))
    XCTAssertFalse(source.contains("guard state.isVoiceResponseActive else { return frame.height }"))
    XCTAssertFalse(source.contains("guard state.isVoiceResponseActive else { return frame.width }"))
    XCTAssertTrue(source.contains("let startWidth = max(expandedContentWidth, currentResponseSurfaceWidth())"))
    XCTAssertTrue(source.contains("let responseHeight = responseHeightConfiguration()"))
    XCTAssertTrue(source.contains("let startHeight = max(responseHeight.initialHeight, currentResponseSurfaceHeight())"))
    XCTAssertTrue(source.contains("private func defaultAutoResponseMaxHeight() -> CGFloat"))
    XCTAssertTrue(source.contains("floor(screenHeight / 3)"))
    XCTAssertTrue(source.contains("func finishUserResponseResize()"))
    XCTAssertTrue(source.contains("persistCurrentResponseSurfaceSize()"))
    XCTAssertFalse(source.contains("let initialSize = NSSize(width: expandedContentWidth, height: startHeight)"))
  }

  func testActiveSubagentChatRefreshesWhenAgentOutputChanges() throws {
    let agentSource = try agentPillSource()
    let viewSource = try floatingControlBarViewSource()

    XCTAssertTrue(agentSource.contains("@Published var contentRevision: Int = 0"))
    XCTAssertTrue(agentSource.contains("func markContentChanged()"))
    XCTAssertTrue(agentSource.contains("pill.markContentChanged()"))
    XCTAssertTrue(viewSource.contains(".id(pill.contentRevision)"))
    XCTAssertTrue(viewSource.contains(".onChange(of: pill.contentRevision)"))
    XCTAssertTrue(viewSource.contains("state.reportContentHeight(height, for: .agent(pill.id))"))
  }

  func testActiveSubagentChatDoesNotDependOnMainChatHeight() throws {
    let viewSource = try floatingControlBarViewSource()
    let windowSource = try floatingControlBarWindowSource()

    XCTAssertTrue(viewSource.contains("barWindow?.resizeForActiveAgentChatPublic(pillID: pill.id, animated: !wasShowingConversation)"))
    XCTAssertTrue(windowSource.contains("func resizeForActiveAgentChatPublic(pillID: UUID? = nil, animated: Bool = false)"))
    XCTAssertTrue(windowSource.contains("height: max(responseHeight.initialHeight, currentResponseSurfaceHeight())"))
    XCTAssertTrue(windowSource.contains("setupResponseHeightObserver(for: surface, maxHeight: responseHeight.maxHeight)"))
  }

  func testSubagentDoneBadgeDismissesAndViewedAgentsExpire() throws {
    let agentSource = try agentPillSource()
    let viewSource = try floatingControlBarViewSource()
    let popoverSource = try agentPillsViewSource()

    XCTAssertTrue(agentSource.contains("@Published var viewedAt: Date?"))
    XCTAssertTrue(agentSource.contains("private let viewedFinishedTTL: TimeInterval = 10 * 60"))
    XCTAssertTrue(agentSource.contains("func markViewed(pillID: UUID)"))
    XCTAssertTrue(agentSource.contains("scheduleViewedExpiration(for: pill)"))
    XCTAssertTrue(agentSource.contains("private func trimForNewPillIfNeeded()"))
    XCTAssertTrue(agentSource.contains(".filter({ $0.status == .done && $0.id != activeChatPillID })"))
    XCTAssertTrue(viewSource.contains("manager.markViewed(pillID: pill.id)"))
    XCTAssertTrue(viewSource.contains("if pill.status == .done"))
    XCTAssertTrue(viewSource.contains("manager.dismiss(pillID: pill.id)"))
    XCTAssertTrue(popoverSource.contains("if pill.status == .done"))
    XCTAssertTrue(popoverSource.contains("Button(action: onDismiss)"))
  }

  func testViewedExpirationReArmsWhenActiveChatBlocksExpiry() throws {
    let source = try agentPillSource()

    // The one-shot DispatchWorkItem must re-arm itself when it fires while the
    // pill is the active chat — otherwise auto-expiration is permanently
    // disabled for a viewed finished pill after the user navigates away.
    XCTAssertTrue(source.contains("if FloatingControlBarManager.shared.activeAgentChatPillID == pillID {"))
    XCTAssertTrue(source.contains("self.scheduleViewedExpiration(for: pill)"))
  }

  func testTrimForNewPillSkipsActiveChatPill() throws {
    let source = try agentPillSource()

    // Both the done/finished trim filters and the last-resort fallback must
    // skip the pill the user is actively viewing, so the active chat doesn't
    // disappear/revert to stale/blank content when a new pill is spawned.
    XCTAssertTrue(source.contains("$0.status == .done && $0.id != activeChatPillID"))
    XCTAssertTrue(source.contains("$0.status.isFinished && $0.id != activeChatPillID"))
    XCTAssertTrue(source.contains("if let victimID = pills.first(where: { $0.id != activeChatPillID })?.id {"))
  }

  func testLocalSpeechGlowUsesLocalSpeechActiveNotIsSpeaking() throws {
    let source = try realtimeHubControllerSource()

    // The glow-clear deferral must track localSpeechActive (set synchronously
    // in speak) rather than speech.isSpeaking, which is racy — isSpeaking is
    // false until the synthesizer starts the queued utterance.
    XCTAssertTrue(source.contains("private var localSpeechActive = false"))
    XCTAssertTrue(source.contains("if clearResponseGlow || (!audioReceivedThisTurn && !localSpeechActive)"))
    XCTAssertTrue(source.contains("localSpeechActive = true"))
  }

  func testBeginTurnStopsQueuedLocalSpeechOnBargeIn() throws {
    let source = try realtimeHubControllerSource()

    // beginTurn must check localSpeechActive (not just speech.isSpeaking) when
    // stopping speech, so a barge-in before the synthesizer starts playback
    // still cancels the prior turn's reply. localSpeechActive must be reset
    // AFTER the stopSpeaking call, not before.
    XCTAssertTrue(source.contains("if localSpeechActive || speech.isSpeaking {"))
    XCTAssertTrue(source.contains("speech.stopSpeaking(at: .immediate)\n      localSpeechActive = false\n    }"))
    XCTAssertFalse(source.contains("audioReceivedThisTurn = false\n    localSpeechActive = false\n    suppressAssistantOutputForCurrentTurn = false"))
  }

  func testSpeechSynthesizerDidCancelClearsGlow() throws {
    let source = try realtimeHubControllerSource()

    // The AVSpeechSynthesizerDelegate must implement didCancel so non-explicit
    // cancellation paths (system interruption, stopSpeaking) always release the
    // response glow instead of leaving it stuck.
    XCTAssertTrue(source.contains("func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance)"))
    XCTAssertTrue(source.contains("self.localSpeechActive = false"))
  }

  func testVoiceResponseGlowTriggersCompactResizeOnLegacyDisplays() throws {
    let source = try floatingControlBarWindowSource()

    // The glow observer must trigger a resize to the glow-adjusted collapsed
    // size on legacy displays, not just record the boolean.
    XCTAssertTrue(source.contains("guard !self.notchModeEnabled else { return }"))
    XCTAssertTrue(source.contains("self.resizeAnchored(to: self.collapsedBarSize, makeResizable: false, animated: false, anchorTop: true)"))
  }

  func testEscapeFromAgentUsesInputResizeWhenMainInput() throws {
    let source = try floatingControlBarWindowSource()

    // The Escape path must mirror the Back button: use input-height resize
    // when leaveAgentSurface() lands on .mainInput, not the response-size helper.
    XCTAssertTrue(source.contains("if state.conversationSurface == .mainInput {\n                resizeForMainInputAfterAgentExit()"))
  }

  func testPTTCollapsePreservesGlowPaddingOnLegacyDisplays() throws {
    let source = try floatingControlBarWindowSource()

    // Legacy PTT collapse must use the glow-adjusted compact size when
    // isVoiceResponseActive is still true.
    XCTAssertTrue(source.contains("let compactSize: NSSize = state.isVoiceResponseActive"))
    XCTAssertTrue(source.contains("responseGlowWindowSizeForCurrentScreen(forSurfaceSize: Self.minBarSize)"))
    XCTAssertTrue(source.contains("compactSize: compactSize"))
  }

  func testTerminalProjectionPreservesStatusText() throws {
    let source = try agentRuntimeStatusStoreSource()

    // Terminal projections must preserve the final result text so consumers
    // (floating pill latestActivity, task agent voice summary) can display it.
    XCTAssertFalse(source.contains("projection.statusText = terminal ? nil : statusText"))
    XCTAssertTrue(source.contains("projection.statusText = statusText"))
  }

  func testFloatingAgentHandoffExcludesQuestionStarters() throws {
    // Informational questions that mention agents + action words must not be
    // treated as explicit spawn requests.  Call the real handoff matcher so the
    // test verifies behavior, not just source-string presence.
    let questionsThatContainAgentAndActionWords = [
      "How do I start a background agent?",
      "How do you spawn a subagent?",
      "What is the floating agent feature?",
      "Can you explain how to launch agents?",
      "Why does the agent run?",
      "Are agents able to start tasks?",
      "Do agents create pills automatically?",
      "Tell me about starting a subagent",
      // Modal question starters — contain agent noun + action verb but are
      // questions, not imperative spawn commands.
      "Can I run agents in the background?",
      "Will agents run while I work?",
      "Should I start an agent?",
      "Would I need to spawn a subagent?",
      "May I launch a floating agent?",
      "Do I need to create a background agent?",
    ]
    for question in questionsThatContainAgentAndActionWords {
      XCTAssertNil(
        AgentPillsManager.floatingAgentHandoff(for: question),
        "Expected nil handoff for informational question: \(question)")
    }

    // Genuine spawn requests must still produce a handoff.
    let genuineRequests = [
      "Spawn a background agent to summarize my notes",
      "Start a subagent that tracks my calendar",
      "Launch a floating agent to research X",
      "Run an agent to clean up my inbox",
    ]
    for request in genuineRequests {
      XCTAssertNotNil(
        AgentPillsManager.floatingAgentHandoff(for: request),
        "Expected non-nil handoff for genuine request: \(request)")
    }
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
    let statusStoreSource = try agentRuntimeStatusStoreSource()

    XCTAssertTrue(source.contains("if pill.status.isFinished {\n            return\n        }"))
    XCTAssertTrue(source.contains("guard !pill.status.isFinished || projection.status.isTerminal else { return }"))
    XCTAssertTrue(source.contains("let activity = Self.describeActivity(for: aiMessage)"))
    XCTAssertTrue(source.contains("AgentRuntimeStatusStore.shared.recordLocalSuccess("))
    XCTAssertTrue(statusStoreSource.contains("func recordLocalSuccess(surface: AgentSurfaceReference, statusText: String? = nil)"))
    XCTAssertTrue(statusStoreSource.contains("if !terminal, projectionsBySurface[surface.key]?.status.isTerminal == true {\n      return\n    }"))
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

  private func aiResponseViewSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/AIResponseView.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func agentPillsViewSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/AgentPillsView.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func resizeHandleSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/ResizeHandleView.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func floatingControlBarWindowSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/FloatingControlBarWindow.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func agentRuntimeStatusStoreSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeStatusStore.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func realtimeHubControllerSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/RealtimeHubController.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}
