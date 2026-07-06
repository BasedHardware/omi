import AppKit
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
    XCTAssertTrue(source.contains("private var cachedFloatingPillSystemPrompt: String = \"\""))
    XCTAssertTrue(source.contains("cachedFloatingPillSystemPrompt = floatingPillSystemPrompt"))
    XCTAssertTrue(source.contains("cachedFloatingPillSystemPrompt = \"\""))
    XCTAssertTrue(source.contains("if cachedFloatingPillSystemPrompt.isEmpty"))
    XCTAssertTrue(source.contains("systemPrompt = cachedFloatingPillSystemPrompt"))
    XCTAssertTrue(source.contains(#"excludingToolNames: ["spawn_agent", "delegate_agent"]"#))
    XCTAssertTrue(source.contains("let scopedToolPrompt = DesktopCapabilityRegistry.scopedDesktopToolPrompt(excluding: excludedToolNames)"))
    XCTAssertTrue(source.contains(#".replacingOccurrences(of: "{user_name}", with: promptUserName)"#))
  }

  func testProviderCorrectionUsesPreviousFloatingRequestObjective() throws {
    let directive = AgentPillsManager.literalProviderDirective(
      from: "I meant ask OpenClaw",
      contextualPreviousRequest: "ask grok to search for david zhang on X and tell me who the top 3 are")

    XCTAssertEqual(directive?.provider, .openclaw)
    XCTAssertEqual(directive?.rewrittenQuery, "search for david zhang on X and tell me who the top 3 are")
  }

  func testFloatingRouterProvidesRecentVisibleRequestToProviderDirective() throws {
    let source = try floatingControlBarWindowSource()

    XCTAssertTrue(source.contains("contextualPreviousRequest: recentVisibleUserRequest(in: barWindow)"))
    XCTAssertTrue(source.contains("await AgentPillsManager.providerDirective("))
    XCTAssertTrue(source.contains("private func recentVisibleUserRequest(in barWindow: FloatingControlBarWindow) -> String?"))
    XCTAssertTrue(source.contains("barWindow.state.chatHistory.reversed().compactMap"))
  }

  func testTypedProviderDirectivePromptsForSetupWhenProviderUnavailable() throws {
    let source = try floatingControlBarWindowSource()
    let responseSource = try aiResponseViewSource()

    XCTAssertTrue(source.contains("LocalAgentProviderDetector.availability(for: directive.provider)"))
    XCTAssertTrue(source.contains("guard availability.isAvailable else"))
    XCTAssertTrue(source.contains("floating-agent-provider-unavailable"))
    XCTAssertTrue(source.contains("presentAgentInstallPrompt("))
    XCTAssertTrue(source.contains("completeVisibleAgentResponse("))
    XCTAssertTrue(source.contains("case .beginConnection:"))
    XCTAssertTrue(source.contains("case .runSetup:"))
    XCTAssertTrue(source.contains("$0.status = .confirming"))
    XCTAssertTrue(source.contains("AgentInstallPromptState.setupConfirmationDelay"))
    XCTAssertTrue(source.contains("prompt.confirmingSince == nil"))
    XCTAssertTrue(source.contains("runAgentInstaller(messageId: messageId, plan: prompt.plan, command: command)"))
    XCTAssertTrue(source.contains("$0.confirmingSince = nil"))
    XCTAssertFalse(source.contains("completeVisibleProviderSetupPrompt("))
    XCTAssertTrue(source.contains("FloatingBarVoicePlaybackService.shared.speakOneShot(directive.provider.setupNeededStatus)"))
    XCTAssertTrue(responseSource.contains("private var primaryActionControl: some View"))
    XCTAssertTrue(responseSource.contains(".onTapGesture {"))
    XCTAssertFalse(responseSource.contains("Button(action: onInstall)"))
    XCTAssertFalse(responseSource.contains(".accessibilityAction {"))
    XCTAssertFalse(responseSource.contains(".accessibilityAddTraits(.isButton)"))
  }

  func testSubagentChatSpawnRequestCreatesSiblingAgent() throws {
    let source = try floatingControlBarViewSource()
    let agentPillSource = try agentPillSource()

    XCTAssertTrue(source.contains("if let handoff = AgentPillsManager.floatingAgentHandoff(for: trimmed)"))
    XCTAssertTrue(source.contains("bridgeHarnessOverride: pill.bridgeHarnessOverride"))
    XCTAssertTrue(source.contains("state.present(.agent(sibling.id))"))
    XCTAssertTrue(agentPillSource.contains("let bridgeHarnessOverride: AgentHarnessMode?"))
    XCTAssertTrue(agentPillSource.contains("bridgeHarnessOverride: AgentHarnessMode? = nil"))
    XCTAssertTrue(agentPillSource.contains("self.bridgeHarnessOverride = bridgeHarnessOverride"))
    XCTAssertTrue(agentPillSource.contains("let pill = AgentPill(query: query, model: model, bridgeHarnessOverride: bridgeHarnessOverride)"))
  }

  func testSubagentChatRendersMarkdownAndLargeBackHitTarget() throws {
    let source = try floatingControlBarViewSource()

    XCTAssertTrue(source.contains("import MarkdownUI"))
    XCTAssertFalse(source.contains("Markdown(outputText.isEmpty ? \"Working...\" : outputText)"))
    XCTAssertTrue(source.contains("ForEach(displayedMessages) { message in"))
    XCTAssertTrue(source.contains("agentMessageBubble(message)"))
    XCTAssertTrue(source.contains("agentAssistantContent(message)"))
    XCTAssertTrue(source.contains("ForEach(ContentBlockGroup.group(message.contentBlocks))"))
    XCTAssertTrue(source.contains("ToolCallsGroup(calls: calls, compact: true)"))
    XCTAssertTrue(source.contains("ThinkingBlock(text: text)"))
    XCTAssertTrue(source.contains("Markdown(trimmed)"))
    XCTAssertTrue(source.contains(".markdownTheme(.aiMessage(scale: 0.88))"))
    XCTAssertTrue(source.contains(".frame(width: 36, height: 36)"))
    XCTAssertTrue(source.contains(".contentShape(Rectangle())"))
    XCTAssertTrue(source.contains("let onBackToAgentRows: () -> Void"))
    XCTAssertTrue(source.contains(".help(\"Back to chats\")"))
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

  func testNotchHoverMenuKeepsAskOmiReachable() throws {
    let source = try floatingControlBarViewSource()

    guard let rowRange = source.range(of: "private var notchOmiChatRow: some View"),
      let heightRange = source.range(of: "private var notchChromeHeight: CGFloat")
    else {
      return XCTFail("Expected notch Omi Chat hover row section")
    }
    let rowSource = String(source[rowRange.lowerBound..<heightRange.lowerBound])

    XCTAssertTrue(rowSource.contains("Text(\"Omi Chat\")"))
    XCTAssertTrue(rowSource.contains("openOmiChatFromNotchRow()"))
    XCTAssertTrue(rowSource.contains("private var notchOmiChatOverlayHitTarget: some View"))
    XCTAssertTrue(rowSource.contains(".accessibilityLabel(\"Omi Chat\")"))
    XCTAssertTrue(rowSource.contains("notchShortcutHint(\"Ask\""))
    XCTAssertTrue(rowSource.contains("notchShortcutHint(systemImage: \"mic.fill\""))
    XCTAssertFalse(rowSource.contains("notchShortcutHint(\"PTT\""))
  }

  func testNotchSettingsHitTargetDoesNotCoverChatRows() throws {
    let source = try floatingControlBarViewSource()

    XCTAssertTrue(source.contains("notchAgentLogoHitTarget\n                            .frame(width: notchChromeLayoutWidth, height: notchChromeHeight)"))
    XCTAssertFalse(source.contains("notchAgentLogoHitTarget\n                            .frame(width: notchChromeLayoutWidth, height: notchChromeHeight + notchHoverMenuHeight)"))
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

    XCTAssertTrue(source.contains("state.isNotchHoverMenuVisible"))
    XCTAssertTrue(windowSource.contains("func updateNotchPointerFromGlobalMouse()"))
    XCTAssertTrue(windowSource.contains("func openNotchHoverMenuUntilExit()"))
    XCTAssertTrue(windowSource.contains("private enum NotchPointerMode"))
    XCTAssertTrue(windowSource.contains("state.isNotchHoverMenuVisible ? .openMenuRetention : .activationOnly"))
    XCTAssertTrue(source.contains("state.showingAIConversation || shouldShowNotchHoverMenu"))
    XCTAssertTrue(source.contains("static let maxAgents = FloatingControlBarWindow.notchAgentListMaxVisibleAgents"))
    XCTAssertTrue(source.contains("static let dotDiameterRatio: CGFloat = 0.18"))
    XCTAssertTrue(source.contains("static let ringRadiusRatio: CGFloat = 0.33"))
    XCTAssertTrue(source.contains("NotchAgentOmiIndicatorView(pills: stackedPills)"))
    XCTAssertTrue(source.contains("NotchOmiMark(dotColors: visiblePills.map"))
    XCTAssertTrue(source.contains("NotchAgentMorphField("))
    XCTAssertTrue(source.contains("NotchAgentListRow(\n                                title: pill.title,\n                                status: pill.status,\n                                activity: pill.latestActivity,\n                                isSelected: pill.id == activePillID,\n                                progress: rowRevealProgress"))
    // The provider logo must be drawn exactly once per row — only by the traveling
    // `notchAgentIdentityMark` that morphs from the logo ring onto the orb slot. The
    // row itself must NOT draw its own `AgentProviderLogoMark`, or it would double up
    // under the morph mark (the "two caduceus / two mascots" bug).
    XCTAssertFalse(source.contains("AgentProviderLogoMark(provider: provider, statusColor: statusColor, size: 16)"))
    XCTAssertTrue(source.contains("Color.clear\n                .frame(width: NotchAgentStackMetrics.listOrbSlotWidth, height: 18)"))
    XCTAssertEqual(
        source.components(separatedBy: "AgentProviderLogoMark(provider: provider").count - 1,
        1,
        "Notch row path must construct the provider logo mark exactly once (only in notchAgentIdentityMark)"
    )
    XCTAssertTrue(source.contains("notchAgentIdentityMark(\n                            provider: pill.bridgeHarnessOverride"))
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
    XCTAssertTrue(source.contains("notchOmiChatRow\n                        .frame(width: notchHoverRowWidth, height: FloatingControlBarWindow.notchAgentListRowHeight)"))
    XCTAssertTrue(source.contains(".allowsHitTesting(!shouldUseOmiChatOverlayHitTarget && notchSwitcherProgress > 0.6)"))
    XCTAssertTrue(source.contains("notchOmiChatOverlayHitTarget\n                        .frame(width: notchHoverRowWidth, height: FloatingControlBarWindow.notchAgentListRowHeight)"))
    XCTAssertTrue(source.contains(".offset(y: notchChromeHeight)"))
    XCTAssertTrue(source.contains(".zIndex(2)"))
    XCTAssertTrue(source.contains("height: notchHoverMenuHeight - FloatingControlBarWindow.notchAgentListRowHeight"))
    XCTAssertTrue(source.contains("state.present(.agent(pill.id))"))
    XCTAssertTrue(source.contains("private let agentChatSwitchTransition = Animation.easeOut(duration: 0.10)"))
    XCTAssertTrue(source.contains("if state.conversationSurface == .agent(pill.id)"))
    XCTAssertTrue(source.contains("@State private var notchLogoHovering = false"))
    XCTAssertTrue(source.contains("private func setNotchLogoHovering(_ hovering: Bool)"))
    XCTAssertTrue(source.contains("private var notchAgentLogoHitTarget: some View"))
    XCTAssertTrue(source.contains("(agentPills.pills.isEmpty || state.showingAIConversation || !shouldShowNotchHoverMenu) && !notchLogoHovering ? 1 : 0"))
    XCTAssertTrue(source.contains("ZStack(alignment: .trailing)"))
    XCTAssertTrue(source.contains(".frame(width: NotchAgentStackMetrics.logoFrameSize, height: NotchAgentStackMetrics.logoFrameSize)"))
    XCTAssertTrue(source.contains(".frame(width: 44, height: 44)"))
    XCTAssertTrue(source.contains(".onTapGesture {\n                    openFloatingBarSettings()\n                }"))
    XCTAssertTrue(source.contains("Image(systemName: \"gearshape.fill\")"))
    XCTAssertTrue(source.contains("setAgentSwitcherHovering(hovering)"))
    XCTAssertFalse(source.contains("@State private var agentSwitcherPinned"))
    XCTAssertFalse(source.contains("@State private var agentSwitcherHovering"))
    XCTAssertTrue(source.contains("leaveAgentConversation()"))
    XCTAssertTrue(source.contains("Text(\"Omi Chat\")"))
    XCTAssertTrue(source.contains("barWindow?.resizeForActiveAgentChatPublic(pillID: pill.id, animated: !wasShowingConversation)"))
    XCTAssertTrue(source.contains("ForEach(0..<NotchAgentStackMetrics.maxAgents"))
    XCTAssertTrue(source.contains("NotchLogoPlaceholderDot(progress: logoPlaceholderProgress)"))
    XCTAssertTrue(source.contains("Color.white.opacity(0.96 * Double(1 - progress))"))
    XCTAssertTrue(source.contains("private var shouldUseOmiChatOverlayHitTarget: Bool"))
    XCTAssertTrue(source.contains("if shouldUseOmiChatOverlayHitTarget"))
    XCTAssertTrue(source.contains("rowTopOffset: FloatingControlBarWindow.notchAgentListRowHeight"))
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
    XCTAssertTrue(source.contains("private func storedResponseSurfaceSize() -> NSSize?"))
    XCTAssertTrue(source.contains("UserDefaults.standard.removeObject(forKey: Self.sizeKey)"))
    XCTAssertTrue(source.contains("size.height > Self.minResponseHeight + 2"))
    XCTAssertTrue(source.contains("state.conversationSurface.isResponseLike"))
    XCTAssertTrue(source.contains("func finishUserResponseResize()"))
    XCTAssertTrue(source.contains("persistCurrentResponseSurfaceSize()"))
    XCTAssertTrue(source.contains("Persisting ordinary resize notifications here records"))
    XCTAssertFalse(source.contains("let initialSize = NSSize(width: expandedContentWidth, height: startHeight)"))
  }

  func testTypedSendDelegatesResponseSizingToWindow() throws {
    let viewSource = try floatingControlBarViewSource()
    let windowSource = try floatingControlBarWindowSource()

    guard let inputRange = viewSource.range(of: "private var aiInputView: some View"),
      let inputEnd = viewSource.range(of: "private func recomputeNotchInputHeight")
    else {
      return XCTFail("Expected AI input view section")
    }
    let inputSource = String(viewSource[inputRange.lowerBound..<inputEnd.lowerBound])

    XCTAssertTrue(inputSource.contains(".beginVisibleMainQuery(message, fromVoice: false, animated: true)"))
    XCTAssertTrue(viewSource.contains("onSendFollowUp: { message in\n                archiveCurrentExchange()\n\n                (window as? FloatingControlBarWindow)?\n                    .beginVisibleMainQuery(message, fromVoice: false, animated: true)"))
    XCTAssertFalse(inputSource.contains("state.showingAIResponse = true"))
    XCTAssertFalse(viewSource.contains("state.conversationSurface == .mainResponse || state.showingAIResponse"))
    XCTAssertTrue(windowSource.contains("func beginVisibleMainQuery(_ message: String, fromVoice: Bool, animated: Bool = true)"))
    XCTAssertTrue(windowSource.contains("state.resetMeasuredContentHeight(for: .mainResponse)"))
    XCTAssertTrue(windowSource.contains("state.present(.mainResponse)"))
    XCTAssertTrue(windowSource.contains("beginMainResponseHeight(animated: animated)"))
    XCTAssertFalse(windowSource.contains("state.showingAIResponse = true"))
  }

  func testActiveSubagentChatRefreshesWhenAgentOutputChanges() throws {
    let agentSource = try agentPillSource()
    let viewSource = try floatingControlBarViewSource()

    XCTAssertTrue(agentSource.contains("@Published var conversationMessages: [ChatMessage] = []"))
    XCTAssertTrue(agentSource.contains("pill.conversationMessages = displayMessages"))
    XCTAssertTrue(agentSource.contains("message.sender == .user || !trimmed.isEmpty || message.isStreaming || !message.contentBlocks.isEmpty"))
    XCTAssertTrue(viewSource.contains("private var displayedMessages: [ChatMessage]"))
    XCTAssertTrue(viewSource.contains("ChatMessage(id: \"\\(pill.id.uuidString)-query\", text: pill.query, sender: .user)"))
    XCTAssertTrue(viewSource.contains("Text(trimmed)"))
    XCTAssertTrue(agentSource.contains("@Published var contentRevision: Int = 0"))
    XCTAssertTrue(agentSource.contains("func markContentChanged()"))
    XCTAssertTrue(agentSource.contains("pill.markContentChanged()"))
    XCTAssertTrue(viewSource.contains(".id(pill.contentRevision)"))
    XCTAssertTrue(viewSource.contains(".onChange(of: pill.contentRevision)"))
    XCTAssertTrue(viewSource.contains(".onChange(of: pill.conversationMessages.map(\\.text).joined(separator: \"\\n\"))"))
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

  func testRealtimeHubKeepsSpeechFallbackArmedWhenNativeAudioDoesNotSchedule() throws {
    let hubSource = try realtimeHubControllerSource()
    let playerSource = try streamingPCMPlayerSource()

    XCTAssertTrue(playerSource.contains("private func ensureRunning() -> Bool"))
    XCTAssertTrue(playerSource.contains("@discardableResult\n  func enqueue(_ data: Data) -> Bool"))
    XCTAssertTrue(hubSource.contains("guard let pcmPlayer, pcmPlayer.enqueue(pcm24k) else"))
    XCTAssertTrue(hubSource.contains("keeping text fallback armed"))
    XCTAssertTrue(hubSource.contains("audioReceivedThisTurn = true\n    realtimePlaybackActive = true\n    realtimePlaybackEpoch = pcmPlayer.playbackEpoch\n    responseGlowGate.markPlaybackActive()"))
    XCTAssertFalse(hubSource.contains("pcmPlayer?.playbackEpoch ??"))
    XCTAssertFalse(hubSource.contains("audioReceivedThisTurn = true\n    // If PTT muted music/system output"))
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

  func testRealtimeBargeInTracksLocalPlaybackNotOnlyServerTurn() throws {
    let source = try realtimeHubControllerSource()

    // Provider turn completion only means the server finished sending audio; the
    // local AVAudioPlayerNode may still be draining queued PCM. Keep playback as
    // an explicit owner so the next PTT is classified correctly and non-barge-in
    // starts do not blindly stop the player.
    XCTAssertTrue(source.contains("private var realtimePlaybackActive = false"))
    XCTAssertTrue(source.contains("let bargeIn = responding || realtimePlaybackActive || localSpeechActive || speech.isSpeaking"))
    XCTAssertTrue(source.contains("if bargeIn {\n      pcmPlayer?.stop()"))
    XCTAssertTrue(source.contains("audioReceivedThisTurn = true\n    realtimePlaybackActive = true"))
    XCTAssertTrue(source.contains("private var realtimePlaybackEpoch = 0"))
    XCTAssertTrue(source.contains("player.onPlaybackScheduled = { [weak self] playbackEpoch in"))
    XCTAssertTrue(source.contains("self.realtimePlaybackActive = true\n        self.realtimePlaybackEpoch = playbackEpoch"))
    XCTAssertTrue(source.contains("player.onPlaybackIdle = { [weak self] playbackEpoch in"))
    XCTAssertTrue(source.contains("guard let self, self.realtimePlaybackEpoch == playbackEpoch else { return }"))
    XCTAssertTrue(source.contains("realtimePlaybackEpoch = pcmPlayer.playbackEpoch"))
    XCTAssertTrue(source.contains("server turn done; waiting for local playback to drain"))
  }

  func testRealtimeBargeInUsesProviderInterruptionStrategy() throws {
    let hubSource = try realtimeHubControllerSource()
    let sessionSource = try realtimeHubSessionSource()

    // OpenAI can cancel a response in-session. Gemini cannot reliably cancel a
    // streaming reply, so barge-in must replace the session. Managed Gemini
    // tokens are single-use, so the replacement session remints before it
    // connects and holds early PTT audio/commit during that remint gap.
    XCTAssertTrue(sessionSource.contains("enum RealtimeHubBargeInStrategy"))
    XCTAssertTrue(sessionSource.contains("provider == .gemini ? .freshSession : .inSessionCancel"))
    XCTAssertTrue(hubSource.contains("private var sessionAuth: HubAuth?"))
    XCTAssertTrue(hubSource.contains("private var bargeInReplacementInFlight = false"))
    XCTAssertTrue(hubSource.contains("private var bargeInReplacementPendingCommit = false"))
    XCTAssertTrue(hubSource.contains("private var bargeInReplacementAudioBuffer: [Data] = []"))
    XCTAssertTrue(hubSource.contains("private func restartSessionForBargeIn() -> Bool"))
    XCTAssertTrue(hubSource.contains("case .ephemeral:\n      remintReplacementSessionForBargeIn(provider: provider)"))
    XCTAssertTrue(hubSource.contains("token = try await APIClient.shared.mintRealtimeToken(provider: providerParam)"))
    XCTAssertTrue(hubSource.contains("startReplacementSessionForBargeIn(provider: provider, auth: .ephemeral(token))"))
    XCTAssertTrue(hubSource.contains("bargeInReplacementAudioBuffer.append(pcm16k)"))
    XCTAssertTrue(hubSource.contains("bargeInReplacementPendingCommit = true"))
    XCTAssertTrue(hubSource.contains("failBargeInReplacement(provider: provider, reason: error.localizedDescription)"))
    XCTAssertTrue(hubSource.contains("if provider == .gemini, let speculativeScreenshot"))
    XCTAssertTrue(hubSource.contains("session?.sendVideoFrame(speculativeScreenshot, mime: \"image/jpeg\")"))
    XCTAssertTrue(hubSource.contains("responding = false\n    realtimePlaybackActive = false"))
    XCTAssertTrue(hubSource.contains("exitVoiceUI(clearResponseGlow: true)"))
    XCTAssertTrue(hubSource.contains("} else {\n        responding = false\n        exitVoiceUI(clearResponseGlow: true)\n      }"))
    XCTAssertTrue(hubSource.contains("let providerResponseInFlight = responding"))
    XCTAssertTrue(hubSource.contains("var replacementSessionOwnsInputTurn = false"))
    XCTAssertTrue(hubSource.contains("case .freshSession:"))
    XCTAssertTrue(hubSource.contains("replace the connection and let the fresh session buffer this new turn while it opens"))
    XCTAssertTrue(hubSource.contains("case .inSessionCancel:"))
    XCTAssertTrue(hubSource.contains("barge-in — stopping local playback tail"))
    XCTAssertTrue(hubSource.contains("if !replacementSessionOwnsInputTurn"))
    XCTAssertTrue(hubSource.contains("session?.beginInputTurn(interrupting: providerResponseInFlight)"))
    XCTAssertTrue(hubSource.contains("session?.cancelActiveResponse()"))
    XCTAssertTrue(hubSource.contains("private func isCurrentSession(_ source: RealtimeHubSession) -> Bool"))
    XCTAssertTrue(hubSource.contains("guard isCurrentSession(source) else { return }"))
    XCTAssertTrue(hubSource.contains("sendToolResultIfCurrent(source: source"))
    XCTAssertFalse(hubSource.contains("self.session?.sendToolResult(callId: callId"))
    XCTAssertTrue(sessionSource.contains("Task { @MainActor in d?.hubDidReceiveAudio(pcm, source: self) }"))
    XCTAssertTrue(sessionSource.contains("guard isCurrentOpenAIResponseEvent(e) else"))
    XCTAssertTrue(sessionSource.contains("private var openAIResponseCreatePending = false"))
    XCTAssertTrue(sessionSource.contains("guard !openAIResponseCreatePending, let expected = openAIActiveResponseID else { return false }"))
    XCTAssertTrue(sessionSource.contains("return eventResponseID == expected"))
    XCTAssertFalse(sessionSource.contains("guard let expected = openAIActiveResponseID else { return true }"))
    XCTAssertTrue(sessionSource.contains("ignoring stale response.done"))
  }

  func testCredentialHealthRetryAndFailoverInvariants() throws {
    let apiSource = try apiClientSource()
    let hubSource = try realtimeHubControllerSource()

    XCTAssertTrue(
      apiSource.contains("try await authService.getAuthHeader(forceRefresh: true), forHTTPHeaderField: \"Authorization\")"),
      "Backend 401 retry paths must force-refresh Firebase auth")
    XCTAssertTrue(
      apiSource.contains("throw CredentialHealthError.backendTransient(statusCode: nil, message: error.localizedDescription)"),
      "Realtime mint retry transport failures must stay transient, not requires-login")
    XCTAssertTrue(
      apiSource.contains("} catch AuthError.notSignedIn {\n        throw CredentialHealthError.requiresLogin"),
      "Only definitive not-signed-in refresh failures should become requires-login")
    XCTAssertTrue(
      hubSource.contains("self.minting = false\n        CredentialHealthManager.shared.record(error, context: \"realtime_mint\")"),
      "Mint failure must clear minting before failover starts the alternate provider")
    XCTAssertTrue(
      hubSource.contains("if case .providerAuthFailed = credentialFailureClass {\n      if aliveFor < 10, failoverToAlternateProvider() { return }"),
      "Provider auth failures should try alternate provider before stopping reconnect")
    XCTAssertTrue(
      hubSource.contains("if case .providerQuotaExceeded = credentialFailureClass {\n      if failoverToAlternateProvider() { return }"),
      "Provider quota failures should try alternate provider regardless of socket age")
    XCTAssertTrue(
      hubSource.contains("let shouldRedactProviderMessage: Bool"),
      "Credential close logs must redact raw provider auth/quota payloads")
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

  func testStartupRevalidatesDisplayMetadataForAutomaticNotchMode() throws {
    let source = try floatingControlBarWindowSource()

    // Some MacBook notch safe-area metadata can arrive after the floating bar
    // window is created. Startup retries should use the same layout path as
    // display changes so users do not need to change screen resolution first.
    XCTAssertTrue(source.contains("private static let startupDisplayRevalidationDelays: [TimeInterval] = [0.2, 0.8, 2.0]"))
    XCTAssertTrue(source.contains("scheduleStartupDisplayRevalidation()"))
    XCTAssertTrue(source.contains("self?.validatePositionOnScreenChange(reason: \"startup_display_revalidation\")"))
    XCTAssertTrue(source.contains("self?.validatePositionOnScreenChange(reason: \"screen_parameters_changed\")"))
  }

  func testBackFromAgentUsesSharedDisplayAwarePath() throws {
    let viewSource = try floatingControlBarViewSource()
    let windowSource = try floatingControlBarWindowSource()

    // Both the Omi Chat header and subagent header should enter one shared
    // window transition. Notch surfaces go back to the row list; legacy
    // surfaces keep their previous main-input/main-response back behavior.
    XCTAssertTrue(viewSource.contains("onBackToAgentRows: {\n                        showAgentListFromConversation()"))
    XCTAssertTrue(viewSource.contains("private func showAgentListFromConversation() {\n        (window as? FloatingControlBarWindow)?.leaveAgentConversation() ?? onCloseAI()\n    }"))
    XCTAssertTrue(windowSource.contains("func leaveAgentConversation()"))
    XCTAssertTrue(windowSource.contains("if state.usesNotchIsland, !AgentPillsManager.shared.pills.isEmpty"))
    XCTAssertTrue(windowSource.contains("private func showAgentRowsFromConversation()"))
    XCTAssertTrue(windowSource.contains("private func showMainConversationFromAgent()"))
    XCTAssertTrue(windowSource.contains("state.hideConversationSurface()"))
    XCTAssertTrue(windowSource.contains("openNotchHoverMenuUntilExit()"))
    XCTAssertTrue(windowSource.contains("resizeForMainInputAfterAgentExit()"))
    XCTAssertTrue(windowSource.contains("window.leaveAgentConversation()"))
    XCTAssertTrue(windowSource.contains("let expectsRows = window.state.usesNotchIsland && !AgentPillsManager.shared.pills.isEmpty"))
    XCTAssertTrue(windowSource.contains("\"mode\": expectsRows ? \"rows\" : \"main\""))
    XCTAssertFalse(viewSource.contains("let onBackToOmi: () -> Void"))
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

  func testFloatingAgentHandoffHonorsExplicitNegation() throws {
    // Explicit no-agent requests that contain an agent noun + action verb must
    // not be treated as spawn requests. (Codex P2 — honor explicit no-agent
    // requests.)
    let negationRequests = [
      "Don't run an agent, just answer here",
      "Do not spawn a subagent for this",
      "Without launching a background agent, summarize this",
      "No agent please, just answer inline",
      "Not creating a pill, just respond normally",
    ]
    for request in negationRequests {
      XCTAssertNil(
        AgentPillsManager.floatingAgentHandoff(for: request),
        "Expected nil handoff for negated request: \(request)")
    }

    // Genuine affirmative requests must still produce a handoff.
    let genuineRequests = [
      "Spawn a background agent to summarize my notes",
      "Start a subagent that tracks my calendar",
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
    XCTAssertTrue(source.contains("Self.ensureFailureMessage(errorText, for: pill)"))
    XCTAssertTrue(source.contains("Self.ensureFailureMessage(\"Agent ended before reporting a final result\", for: pill)"))
    XCTAssertTrue(source.contains("ensureFailureMessage(message, for: pill)"))
    XCTAssertTrue(source.contains("projection.failure?.displayMessage ?? projection.errorMessage ?? \"Agent failed\""))
    XCTAssertTrue(source.contains("AgentFailureTranscriptFormatter.transcriptText(for: errorText)"))
    XCTAssertTrue(source.contains("ChatMessage(text: failureText, sender: .ai)"))
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

  func testDirectedProviderPillsDoNotForwardClaudeModelOverrides() throws {
    let source = try agentPillSource()
    let pillViewSource = try agentPillsViewSource()

    XCTAssertTrue(source.contains("let hasBridgeHarnessOverride = bridgeHarnessOverride != nil"))
    XCTAssertTrue(source.contains("if !hasBridgeHarnessOverride {\n                provider.modelOverride = floating.modelOverride\n            }"))
    XCTAssertTrue(source.contains("model: Self.modelForSend(pill: pill, provider: provider)"))
    XCTAssertTrue(source.contains("provider.hasBridgeHarnessOverride ? nil : pill.model"))
    XCTAssertTrue(pillViewSource.contains("AgentProviderLogoMark("))
    XCTAssertTrue(pillViewSource.contains("provider: pill.bridgeHarnessOverride"))
    XCTAssertTrue(pillViewSource.contains("private var providerPill: some View"))
    XCTAssertTrue(pillViewSource.contains("private static let hermesLogo = load(\"hermes_logo_flat\")"))
    XCTAssertTrue(pillViewSource.contains("private static let openClawLogo = load(\"openclaw_logo_flat\")"))
    XCTAssertTrue(pillViewSource.contains("return hermesLogo"))
    XCTAssertTrue(pillViewSource.contains("return openClawLogo"))
    XCTAssertTrue(pillViewSource.contains(".renderingMode(.template)"))
    XCTAssertTrue(pillViewSource.contains(".foregroundStyle(statusColor)"))
    XCTAssertFalse(pillViewSource.contains("return load(\"hermes_logo\")"))
    XCTAssertFalse(pillViewSource.contains("return load(\"openclaw_logo\")"))
    XCTAssertTrue(pillViewSource.contains("if pill.bridgeHarnessOverride.rendersProviderMark {\n            return false\n        }"))
    // Provider agents without a dedicated logo fall back to a flat, status-tinted
    // robot mark — not the Omi round dot. Omi-native agents (nil override) keep
    // the dot via the `provider != nil` guard.
    XCTAssertTrue(pillViewSource.contains("} else if provider != nil {"))
    XCTAssertTrue(pillViewSource.contains("Text(\"🤖\")"))
    XCTAssertTrue(pillViewSource.contains("statusColor\n                    .mask("))
  }

  func testProviderMarkRoutingIsCentralized() throws {
    let routingSource = try agentRuntimeRoutingSource()
    XCTAssertTrue(routingSource.contains("var rendersProviderMark: Bool { self != nil }"))

    let pillViewSource = try agentPillsViewSource()
    XCTAssertTrue(pillViewSource.contains("pill.bridgeHarnessOverride.rendersProviderMark"))

    let windowSource = try floatingControlBarViewSource()
    XCTAssertTrue(windowSource.contains("if provider.rendersProviderMark {"))
  }

  func testDirectedProviderLogoAssetsUseSingleTemplateMasks() throws {
    let hermes = try logoMaskStats("hermes_logo_flat")
    XCTAssertEqual(hermes.width, 256)
    XCTAssertEqual(hermes.height, 256)
    XCTAssertEqual(hermes.transparentCorners, 4)
    XCTAssertGreaterThan(hermes.boundsWidth, 180, "Hermes must keep the winged caduceus, not a narrow replacement glyph.")
    XCTAssertGreaterThan(hermes.boundsHeight, 170)
    XCTAssertEqual(hermes.coloredPixels, 0, "Hermes row mark must be a template mask so status color owns identity.")

    let openClaw = try logoMaskStats("openclaw_logo_flat")
    XCTAssertEqual(openClaw.width, 180)
    XCTAssertEqual(openClaw.height, 180)
    XCTAssertEqual(openClaw.transparentCorners, 4)
    XCTAssertGreaterThan(openClaw.boundsWidth, 150, "OpenClaw must keep the round mascot silhouette, not an arrow glyph.")
    XCTAssertGreaterThan(openClaw.boundsHeight, 130)
    XCTAssertGreaterThan(openClaw.transparentPixelsInsideBounds, 500, "Eye holes must remain transparent in the provider mark.")
    XCTAssertEqual(openClaw.coloredPixels, 0, "OpenClaw row mark must be a template mask so status color owns identity.")
  }

  func testFloatingAgentToolCallsUseCompactOneLinePresentation() throws {
    let chatPageSource = try chatPageSource()
    let providerSource = try chatProviderSource()

    XCTAssertTrue(chatPageSource.contains("var compact: Bool = false"))
    XCTAssertTrue(chatPageSource.contains("var expandRunning: Bool = true"))
    XCTAssertTrue(chatPageSource.contains("State(initialValue: expandRunning && Self.hasRunningTool(in: calls))"))
    XCTAssertTrue(chatPageSource.contains(".onChange(of: hasRunningTool)"))
    XCTAssertTrue(chatPageSource.contains("private var header: some View"))
    XCTAssertTrue(chatPageSource.contains("private var expandedToolCalls: some View"))
    XCTAssertTrue(chatPageSource.contains("VStack(alignment: .leading, spacing: compact ? 0 : 6)"))
    XCTAssertTrue(chatPageSource.contains(".frame(height: compact ? 34 : nil)"))
    XCTAssertTrue(chatPageSource.contains("Image(systemName: isExpanded ? \"chevron.up\" : \"chevron.down\")"))
    XCTAssertTrue(chatPageSource.contains("ToolCallCard(name: name, status: status, input: input, output: output)"))
    XCTAssertTrue(chatPageSource.contains("summaryEmbeddedInToolName"))
    XCTAssertTrue(providerSource.contains("cleanName.lowercased().hasPrefix(\"read:\")"))
    XCTAssertTrue(providerSource.contains("return \"Reading file\""))
  }

  func testSelectableMarkdownRoutesGFMTablesThroughMarkdownUI() throws {
    let selectableSource = try selectableMarkdownSource()
    let chatPageSource = try chatPageSource()
    let table = """
    | Rank | Skill | Loads |
    |---:|---|---:|
    | 1 | omi | 39 |
    """
    let tableWithoutOuterPipes = """
    Rank | Skill | Loads
    ---:|---|---:
    1 | omi | 39
    """

    XCTAssertTrue(SelectableMarkdown.containsGFMTable(table))
    XCTAssertTrue(SelectableMarkdown.containsGFMTable(tableWithoutOuterPipes))
    XCTAssertFalse(SelectableMarkdown.containsGFMTable("Rank | Skill | Loads"))
    XCTAssertTrue(selectableSource.contains("markdownTableCells"))
    XCTAssertTrue(selectableSource.contains("Markdown(content)"))
    XCTAssertTrue(selectableSource.contains(".scaledMarkdownTheme(sender)"))
    XCTAssertTrue(selectableSource.contains(".inlineOnlyPreservingWhitespace"))
    XCTAssertTrue(chatPageSource.contains(".table { configuration in"))
    XCTAssertTrue(chatPageSource.contains(".markdownTableBorderStyle"))
    XCTAssertTrue(chatPageSource.contains(".markdownTableBackgroundStyle"))
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

  private func chatPageSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/Pages/ChatPage.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func selectableMarkdownSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/Components/SelectableMarkdown.swift")
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

  private func agentRuntimeRoutingSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Providers/AgentRuntimeRouting.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private struct LogoMaskStats {
    let width: Int
    let height: Int
    let boundsWidth: Int
    let boundsHeight: Int
    let nonTransparentPixels: Int
    let coloredPixels: Int
    let transparentPixelsInsideBounds: Int
    let transparentCorners: Int
  }

  private func logoMaskStats(_ name: String) throws -> LogoMaskStats {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Resources/\(name).png")
    let data = try Data(contentsOf: url)
    guard let rep = NSBitmapImageRep(data: data) else {
      throw NSError(
        domain: "AgentPillLifecycleTests",
        code: 1,
        userInfo: [NSLocalizedDescriptionKey: "Could not load \(name).png"])
    }

    var minX = rep.pixelsWide
    var minY = rep.pixelsHigh
    var maxX = -1
    var maxY = -1
    var nonTransparentPixels = 0
    var coloredPixels = 0

    for y in 0..<rep.pixelsHigh {
      for x in 0..<rep.pixelsWide {
        let color = rep.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB)
        let alpha = color?.alphaComponent ?? 0
        if alpha > 0.01 {
          nonTransparentPixels += 1
          minX = min(minX, x)
          minY = min(minY, y)
          maxX = max(maxX, x)
          maxY = max(maxY, y)
          if let color,
            max(color.redComponent, color.greenComponent, color.blueComponent)
              - min(color.redComponent, color.greenComponent, color.blueComponent) > 0.08 {
            coloredPixels += 1
          }
        }
      }
    }

    var transparentPixelsInsideBounds = 0
    if maxX >= minX, maxY >= minY {
      for y in minY...maxY {
        for x in minX...maxX {
          let alpha = rep.colorAt(x: x, y: y)?.alphaComponent ?? 0
          if alpha <= 0.01 {
            transparentPixelsInsideBounds += 1
          }
        }
      }
    }

    let cornerPoints = [
      (0, 0),
      (rep.pixelsWide - 1, 0),
      (0, rep.pixelsHigh - 1),
      (rep.pixelsWide - 1, rep.pixelsHigh - 1),
    ]
    let transparentCorners = cornerPoints.filter { point in
      (rep.colorAt(x: point.0, y: point.1)?.alphaComponent ?? 0) <= 0.01
    }.count

    return LogoMaskStats(
      width: rep.pixelsWide,
      height: rep.pixelsHigh,
      boundsWidth: maxX >= minX ? maxX - minX + 1 : 0,
      boundsHeight: maxY >= minY ? maxY - minY + 1 : 0,
      nonTransparentPixels: nonTransparentPixels,
      coloredPixels: coloredPixels,
      transparentPixelsInsideBounds: transparentPixelsInsideBounds,
      transparentCorners: transparentCorners)
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

  private func apiClientSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/APIClient.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func realtimeHubSessionSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/RealtimeHubSession.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func streamingPCMPlayerSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/StreamingPCMPlayer.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}
