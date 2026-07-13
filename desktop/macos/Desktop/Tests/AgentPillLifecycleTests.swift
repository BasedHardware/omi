import AppKit
import XCTest

@testable import Omi_Computer

final class AgentPillLifecycleTests: XCTestCase {
  @MainActor
  func testVoiceResponseWaitingDrivesGlowUntilPlaybackOrClear() {
    let state = FloatingControlBarState()
    let coordinator = VoiceTurnCoordinator()
    coordinator.configure(barState: state)

    XCTAssertFalse(state.isVoiceResponseGlowActive)

    let turnID = coordinator.begin(intent: .hold)
    coordinator.send(.selectRoute(turnID: turnID, route: .deepgramBatch))
    coordinator.send(.finalize(turnID: turnID))
    coordinator.send(.transcriptionFinal(turnID: turnID, text: "fixture"))
    XCTAssertTrue(state.isVoiceResponseWaiting)
    XCTAssertFalse(state.isVoiceResponseActive)
    XCTAssertTrue(state.isVoiceResponseGlowActive)

    let identity = coordinator.activeTurn!.providerEffectIdentity!
    coordinator.send(
      .providerResponseStartedScoped(
        turnID: turnID,
        identity: identity,
        sessionID: nil,
        responseID: nil))
    XCTAssertFalse(state.isVoiceResponseWaiting)
    XCTAssertTrue(state.isVoiceResponseActive)
    XCTAssertTrue(state.isVoiceResponseGlowActive)

    coordinator.send(.finish(turnID: turnID, reason: .providerFailed))
    XCTAssertFalse(state.isVoiceResponseWaiting)
    XCTAssertFalse(state.isVoiceResponseActive)
    XCTAssertFalse(state.isVoiceResponseGlowActive)
  }

  func testFloatingPillSpawnsCanonicalBackgroundAgentRun() throws {
    let source = try agentPillSource()

    XCTAssertTrue(source.contains("DesktopCoordinatorService.shared.spawnAgent("))
    XCTAssertTrue(source.contains("AgentRuntimeStatusStore.shared.recordAcceptedRun("))
    XCTAssertTrue(source.contains("await self.pollCanonicalRun(for: pill, generation: generation)"))
    XCTAssertFalse(source.contains("Self.backgroundAgentSystemPromptSuffix"))
  }

  func testExternallySpawnedPillsPollCanonicalRunToTerminalState() throws {
    let source = try agentPillSource()

    XCTAssertTrue(source.contains("func upsertSpawnedPill("))
    XCTAssertTrue(source.contains("Self.ensureStreamingAssistantMessage(for: pill)"))
    XCTAssertTrue(source.contains("surface: .floatingPill(pillId: pill.id)"))
    XCTAssertTrue(source.contains("startCanonicalRunPolling(for: pill)"))
    XCTAssertTrue(source.contains("private func startCanonicalRunPolling(for pill: AgentPill)"))
    XCTAssertTrue(source.contains("await self.pollCanonicalRun(for: pill, generation: generation)"))
  }

  func testFloatingPillProjectionMergeRequiresCanonicalKernelIds() throws {
    let source = try agentPillSource()

    XCTAssertTrue(source.contains("DesktopCoordinatorService.shared.listFloatingAgentPills(limit: 50)"))
    XCTAssertTrue(source.contains("guard let pillId = canonicalPillId(from: entry),"))
    XCTAssertTrue(source.contains("let sessionId = canonicalString(entry[\"sessionId\"]),"))
    XCTAssertTrue(source.contains("let runId = canonicalString(entry[\"runId\"])"))
    XCTAssertTrue(source.contains("pill.canonicalSessionId = sessionId"))
    XCTAssertTrue(source.contains("pill.canonicalRunId = runId"))
    XCTAssertTrue(source.contains("pill.canonicalAttemptId = canonicalString(entry[\"attemptId\"])"))
    XCTAssertTrue(source.contains("reconcileProjectedPillRun(entryStatus: projectedStatus, pill: pill)"))
    XCTAssertTrue(source.contains("removeRenderedProjection(pillID: pill.id)"))
    XCTAssertTrue(source.contains("func resolveAndPresentAgent("))
    XCTAssertTrue(source.contains("hydratePillFromKernel(preference: preference, ownerID: ownerID)"))
    XCTAssertTrue(source.contains("inspectAgentRun(runId: runId)"))
    XCTAssertFalse(source.contains("stablePillUUID"))
    XCTAssertFalse(source.contains("UUID(uuidString: idString) ??"))
  }

  func testProjectedPillsStartCanonicalPollingForTerminalOutputReconciliation() throws {
    let source = try agentPillSource()

    XCTAssertTrue(source.contains("private func reconcileProjectedPillRun(entryStatus: String, pill: AgentPill)"))
    XCTAssertTrue(source.contains("guard shouldPollCanonicalRun(for: pill, projectedStatus: entryStatus) else { return }"))
    XCTAssertTrue(source.contains("startCanonicalRunPolling(for: pill)"))
    XCTAssertTrue(source.contains("private func shouldPollCanonicalRun(for pill: AgentPill, projectedStatus: String)"))
    XCTAssertTrue(source.contains("if isTerminalProjectedStatus(projectedStatus)"))
    XCTAssertTrue(source.contains("return !Self.hasTerminalAssistantMessage(for: pill)"))
    XCTAssertTrue(source.contains("return !pill.status.isFinished && runTasksByPill[pill.id] == nil"))
    XCTAssertTrue(source.contains("private static func hasTerminalAssistantMessage(for pill: AgentPill)"))
    XCTAssertTrue(source.contains("if isCurrentRunAttempt(pillID: pill.id, generation: generation) {\n                runTasksByPill[pill.id] = nil"))
    XCTAssertTrue(source.contains("if pill.status.isFinished && !isTerminalProjectedStatus(status)"))
    XCTAssertTrue(source.contains("if pill.status.isFinished && !isTerminalProjectedStatus(inspection.status)"))
  }

  func testFloatingPillInspectResultsAreGuardedByCurrentRunAttempt() throws {
    let source = try agentPillSource()

    XCTAssertTrue(source.contains("private var runAttemptGenerationByPill: [UUID: Int] = [:]"))
    XCTAssertTrue(source.contains("let generation = nextRunAttemptGeneration(for: pill.id)"))
    XCTAssertTrue(source.contains("guard isCurrentRunAttempt(pillID: pill.id, generation: generation) else { return }"))
    XCTAssertTrue(source.contains("apply(inspection: inspection, to: pill, expectedRunId: runId, expectedAttemptId: attemptId)"))
    XCTAssertTrue(source.contains("guard pill.canonicalRunId == runId else"))
    XCTAssertTrue(source.contains("if let attemptId, pill.canonicalAttemptId != attemptId"))
    XCTAssertTrue(source.contains("guard pill.canonicalSessionId == sessionId else { return }"))
    XCTAssertTrue(source.contains("if let expectedRunId, let inspectedRunId = inspection.runId, inspectedRunId != expectedRunId"))
    XCTAssertTrue(source.contains("if let expectedAttemptId, let inspectedAttemptId = inspection.attemptId, inspectedAttemptId != expectedAttemptId"))
    XCTAssertTrue(source.contains("if let expectedRunId, pill.canonicalRunId != expectedRunId"))
    XCTAssertTrue(source.contains("if let expectedAttemptId, pill.canonicalAttemptId != expectedAttemptId"))
    XCTAssertTrue(source.contains("\"stale_inspection_ignored\""))
  }

  func testFloatingPillRunChangesResetAttemptAndPreserveTransients() throws {
    let source = try agentPillSource()

    XCTAssertTrue(source.contains("private func updateCanonicalRun("))
    XCTAssertTrue(source.contains("if nextRunId != previousRunId {\n            pill.canonicalAttemptId = nextAttemptId"))
    XCTAssertTrue(source.contains("preservingAttemptForSameRun: true"))
    XCTAssertTrue(source.contains("return !hasLocalTransientState(pillID: pill.id)"))
    XCTAssertTrue(source.contains("private func hasLocalTransientState(pillID: UUID) -> Bool"))
    XCTAssertTrue(source.contains("recordingPillID == pillID || pendingFollowUpsByPill[pillID]?.isEmpty == false"))
  }

  func testFinishedAgentArtifactsAreDeliveredToParentChatSurfaces() throws {
    let agentPillSource = try agentPillSource()
    let windowSource = try floatingControlBarWindowSource()

    XCTAssertTrue(agentPillSource.contains("FloatingControlBarManager.shared.recordPillTerminalCompletion("))
    XCTAssertTrue(agentPillSource.contains("resources: resources"))
    XCTAssertTrue(windowSource.contains("func recordPillTerminalCompletion("))
    XCTAssertTrue(windowSource.contains("kernelTurnProjection.appendAgentCompletion("))
    XCTAssertFalse(windowSource.contains("func recordAgentArtifactCompletion("))
    XCTAssertFalse(windowSource.contains("pill_completion"))
    XCTAssertTrue(windowSource.contains("deliverAgentArtifactCompletionToFloatingSurface"))
  }

  func testArtifactDeliveryClearsFloatingTypingState() throws {
    let windowSource = try floatingControlBarWindowSource()
    let responseSource = try aiResponseViewSource()

    XCTAssertTrue(windowSource.contains("chatCancellable?.cancel()"))
    XCTAssertTrue(windowSource.contains("completedMessage.isStreaming = false"))
    XCTAssertTrue(windowSource.contains("window.state.archiveCurrentExchange(using: self.historyChatProvider)"))
    XCTAssertTrue(
      windowSource.contains("window.state.bindAnswerMessage(completedMessage)")
        || windowSource.contains("window.state.setLocalAnswerOverride(completedMessage)")
    )
    XCTAssertFalse(windowSource.contains("window.state.chatHistory.append"))
    XCTAssertTrue(responseSource.contains("} else if isLoading {"))
    XCTAssertTrue(responseSource.contains("&& message.displayResources.isEmpty {"))
  }

  func testTypingIndicatorUsesSharedNotchThinkingMarkInsteadOfBounce() throws {
    let typingSource = try typingIndicatorSource()
    let notchSource = try floatingControlBarViewSource()

    XCTAssertTrue(typingSource.contains("struct OmiThinkingMark: View"))
    XCTAssertTrue(typingSource.contains("struct TypingIndicator: View"))
    XCTAssertTrue(typingSource.contains("OmiThinkingMark()"))
    XCTAssertTrue(typingSource.contains(".linear(duration: 0.9).repeatForever(autoreverses: false)"))
    XCTAssertTrue(notchSource.contains("private struct NotchThinkingMark: View"))
    XCTAssertTrue(notchSource.contains("OmiThinkingMark()"))
    XCTAssertFalse(notchSource.contains("Text(\"Thinking\")"))
    XCTAssertFalse(typingSource.contains("animationPhase"))
    XCTAssertFalse(typingSource.contains("scaleEffect(animationPhase"))
    XCTAssertFalse(typingSource.contains(".delay(Double(index) * 0.15)"))
  }

  func testVoiceAgentKickoffUsesCachedPhrasePack() throws {
    let agentPillSource = try agentPillSource()
    let voiceServiceSource = try floatingBarVoicePlaybackServiceSource()

    XCTAssertTrue(agentPillSource.contains("FloatingBarVoicePlaybackService.shared.speakBackgroundAgentKickoff()"))
    XCTAssertFalse(agentPillSource.contains("FloatingBarVoicePlaybackService.shared.speakOneShot(phrase)"))

    XCTAssertTrue(voiceServiceSource.contains("static let backgroundAgentKickoffPhrases: [String]"))
    XCTAssertTrue(voiceServiceSource.contains("\"I'll get an agent on that.\""))
    XCTAssertTrue(voiceServiceSource.contains("\"Starting an agent for that now.\""))
    XCTAssertTrue(voiceServiceSource.contains("\"Got it. I'm handing this to an agent.\""))
    XCTAssertTrue(voiceServiceSource.contains("\"I'll have an agent work on that.\""))
    XCTAssertTrue(voiceServiceSource.contains("\"I'm getting an agent started.\""))
    XCTAssertTrue(voiceServiceSource.contains("\"I'll have an agent take it from here.\""))
    XCTAssertTrue(voiceServiceSource.contains("\"Got it. I'm starting an agent now.\""))
    XCTAssertTrue(voiceServiceSource.contains("\"I'll put an agent on that.\""))
    XCTAssertTrue(voiceServiceSource.contains("\"An agent is getting started on that.\""))
    XCTAssertTrue(voiceServiceSource.contains("\"I'm kicking off an agent now.\""))
    XCTAssertTrue(voiceServiceSource.contains("background-agent-kickoff-v1"))
    XCTAssertTrue(voiceServiceSource.contains("cachedOrSynthesizedBackgroundAgentKickoffAudio"))
    XCTAssertTrue(voiceServiceSource.contains("DesktopLocalProfile.applicationSupportURL()"))
    XCTAssertFalse(voiceServiceSource.contains(".appendingPathComponent(\"Omi\", isDirectory: true)"))
    XCTAssertTrue(voiceServiceSource.contains("CredentialHealthManager.shared.canUseBYOK"))
    XCTAssertTrue(voiceServiceSource.contains("CredentialHealthManager.shared.recordProviderFailure"))
    XCTAssertTrue(voiceServiceSource.contains("context: \"openai_tts\""))
  }

  func testFloatingPillCapabilitiesAreNotRewrittenBySwiftPrompts() throws {
    let source = try chatProviderSource()

    XCTAssertFalse(source.contains("isFloatingPillSurface("))
    XCTAssertFalse(source.contains("buildFloatingBarSystemPrompt("))
    XCTAssertFalse(source.contains("cachedFloatingPillSystemPrompt"))
    XCTAssertFalse(source.contains("scopedDesktopToolPrompt(excluding:"))
  }

  func testProviderCorrectionUsesPreviousFloatingRequestObjective() throws {
    let directive = AgentPillsManager.providerDirective(
      from: "I meant ask OpenClaw",
      contextualPreviousRequest: "ask grok to search for david zhang on X and tell me who the top 3 are")

    XCTAssertEqual(directive?.provider, .openclaw)
    XCTAssertEqual(directive?.rewrittenQuery, "search for david zhang on X and tell me who the top 3 are")
  }

  func testFloatingRouterProvidesRecentVisibleRequestToProviderDirective() throws {
    let source = try floatingControlBarWindowSource()

    XCTAssertTrue(source.contains("contextualPreviousRequest: recentVisibleUserRequest(in: barWindow)"))
    XCTAssertTrue(source.contains("private func recentVisibleUserRequest(in barWindow: FloatingControlBarWindow) -> String?"))
    XCTAssertTrue(source.contains("barWindow.state.derivedChatHistory(from: historyChatProvider)"))
  }

  func testTypedProviderDirectiveDelegatesAvailabilityToKernel() throws {
    let source = try floatingControlBarWindowSource()

    XCTAssertTrue(source.contains("let resolvedProvider = directedProvider"))
    XCTAssertFalse(source.contains("LocalAgentProviderDetector.availability"))
    XCTAssertFalse(source.contains("provider-unavailable"))
    XCTAssertTrue(source.contains("originSurface: .floatingBar"))
  }

  func testSubagentChatFollowUpAlwaysContinuesCurrentAgent() throws {
    let source = try floatingControlBarViewSource()

    XCTAssertFalse(source.contains("AgentPillsManager.floatingAgentHandoff(for: trimmed)"))
    XCTAssertFalse(source.contains("AgentDelegationExecutor.shared.spawnResolvedDelegation"))
    XCTAssertFalse(source.contains("onSpawnSibling"))
    XCTAssertTrue(source.contains("manager.continueAgent(from: pill, text: trimmed, attachments: staged)"))
  }

  func testSubagentChatRendersMarkdownAndLargeBackHitTarget() throws {
    let source = try floatingControlBarViewSource()

    XCTAssertTrue(source.contains("import MarkdownUI"))
    XCTAssertFalse(source.contains("Markdown(outputText.isEmpty ? \"Working...\" : outputText)"))
    XCTAssertTrue(source.contains("ForEach(displayedMessages) { message in"))
    XCTAssertTrue(source.contains("agentMessageBubble(message)"))
    XCTAssertTrue(source.contains("agentAssistantContent(message)"))
    XCTAssertTrue(source.contains("ForEach(groupedContentBlocks(for: message))"))
    XCTAssertTrue(source.contains("private func groupedContentBlocks(for message: ChatMessage) -> [ContentBlockGroup]"))
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

    guard let dockRange = source.range(of: "NotchDockShape(") else {
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
    XCTAssertTrue(source.contains("@State private var notchSettingsHovering = false"))
    XCTAssertTrue(source.contains("if !showingNotchThinking && notchSettingsHovering"))
    XCTAssertTrue(source.contains("private var notchSettingsButton: some View"))
    XCTAssertTrue(source.contains(".frame(width: 44, height: 44)"))
    XCTAssertTrue(source.contains(".accessibilityIdentifier(\"notch_floating_bar_settings\")"))
    XCTAssertFalse(source.contains(".background(Color.white.opacity(0.12))\n                .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))"))
    XCTAssertTrue(source.contains("notchSettingsHovering = hovering"))
    XCTAssertTrue(source.contains("openFloatingBarSettings()"))
    XCTAssertTrue(source.contains("openAgentChatsFromNotchLogo()"))
    XCTAssertFalse(source.contains(".onHover { hovering in\n            withAnimation(.easeInOut(duration: 0.12)) {\n                notchSettingsHovering = hovering"))
    XCTAssertFalse(source.contains(".onTapGesture {\n                    openFloatingBarSettings()\n                }"))
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
    let scrollSource = try chatScrollBehaviorSource()

    XCTAssertTrue(windowSource.contains("responseStreamingResizeStep"))
    XCTAssertTrue(windowSource.contains("let steppedHeight = (targetHeight / Self.responseStreamingResizeStep).rounded(.up) * Self.responseStreamingResizeStep"))
    XCTAssertTrue(windowSource.contains("to: NSSize(width: max(self.expandedContentWidth, self.currentResponseSurfaceWidth()), height: clampedHeight)"))
    XCTAssertTrue(windowSource.contains("animated: false,\n                    anchorTop: true"))
    XCTAssertTrue(viewSource.contains(".transition(.opacity)"))
    XCTAssertFalse(viewSource.contains("conversationView\n                    .padding(.horizontal, 12)\n                    .padding(.top, 4)\n                    .padding(.bottom, 9)\n                    .transition(.move(edge: .top).combined(with: .opacity))"))
    XCTAssertTrue(responseSource.contains("ChatScrollContainer("))
    XCTAssertTrue(viewSource.contains("ChatScrollContainer("))
    XCTAssertTrue(responseSource.contains("contentChangeToken: scrollContentToken"))
    XCTAssertTrue(viewSource.contains("contentChangeToken: scrollContentToken"))
    XCTAssertFalse(responseSource.contains("proxy.scrollTo(\"bottom\", anchor: .bottom)"))
    XCTAssertFalse(viewSource.contains("proxy.scrollTo(\"agentBottom\", anchor: .bottom)"))
    XCTAssertTrue(scrollSource.contains("struct ChatScrollContainer<Content: View>: View"))
    XCTAssertTrue(scrollSource.contains("UserScrollDetector {"))
    XCTAssertTrue(scrollSource.contains("onScrollSettledAtBottom"))
    XCTAssertTrue(scrollSource.contains("scheduleSettledBottomChecks"))
    XCTAssertTrue(scrollSource.contains("Self.isAtBottom(scrollView)"))
    XCTAssertTrue(scrollSource.contains("scrollMode = .freeScrolling"))
    XCTAssertTrue(scrollSource.contains("if scrollMode == .followingBottom"))
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
    XCTAssertTrue(source.contains("NotchAgentListRow("))
    XCTAssertTrue(source.contains("title: pill.title"))
    XCTAssertTrue(source.contains("status: pill.status"))
    XCTAssertTrue(
      source.contains("ChatContinuityInvariants.agentPreviewText(")
        && source.contains("prompt: pill.query")
        && source.contains("output: pill.latestActivity"),
      "notch agent list must preview query/objective, not raw latestActivity output"
    )
    XCTAssertTrue(source.contains("isSelected: pill.id == activePillID"))
    XCTAssertTrue(source.contains("progress: rowRevealProgress"))
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
    // Fixed window, animated content: the notch NSPanel frame never animates
    // for hover expand/collapse (window-frame animation was the hover jank),
    // so the content morph (notchSwitcherProgress) carries the whole visible
    // transition using the SHARED animation constants — one authority for the
    // spring on open and the settle on close, both Reduce Motion-gated.
    XCTAssertTrue(source.contains("? FloatingControlBarWindow.notchHoverMenuExpandAnimation"))
    XCTAssertTrue(source.contains(": FloatingControlBarWindow.notchHoverMenuCollapseAnimation"))
    // Pill mode still resizes its panel with these durations.
    XCTAssertEqual(FloatingControlBarWindow.notchHoverMenuExpandDuration, 0.16, accuracy: 0.0001)
    XCTAssertEqual(FloatingControlBarWindow.notchHoverMenuCollapseDuration, 0.10, accuracy: 0.0001)
    XCTAssertFalse(source.contains(".animation(.spring(response: 0.18, dampingFraction: 0.9), value: shouldShowNotchHoverMenu)"))
    XCTAssertTrue(source.contains(".transition(.identity)"))
    XCTAssertTrue(source.contains("notchOmiChatRow\n                            .frame(width: notchHoverRowWidth, height: FloatingControlBarWindow.notchAgentListRowHeight)"))
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
    XCTAssertTrue(source.contains("agentPills.pills.isEmpty || state.showingAIConversation || !shouldShowNotchHoverMenu ? 1 : 0"))
    XCTAssertTrue(source.contains("ZStack(alignment: .trailing)"))
    XCTAssertTrue(source.contains("static let logoFrameSize: CGFloat = 21"))
    XCTAssertTrue(source.contains(".frame(width: 44, height: 44)"))
    XCTAssertTrue(source.contains(".onTapGesture {\n                    openAgentChatsFromNotchLogo()\n                }"))
    XCTAssertTrue(source.contains("Image(systemName: \"gearshape.fill\")"))
    XCTAssertTrue(source.contains("private func openAgentChatsFromNotchLogo()"))
    XCTAssertTrue(source.contains("showAgentListFromConversation()"))
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
    XCTAssertTrue(source.contains("if state.usesNotchIsland && shouldUseOmiChatOverlayHitTarget"))
    XCTAssertTrue(source.contains("rowTopOffset: FloatingControlBarWindow.notchAgentListRowHeight"))
    XCTAssertTrue(source.contains("private var showingNotchWaveform: Bool"))
    XCTAssertTrue(source.contains("private var escToClearHint: some View"))
    XCTAssertTrue(source.contains("if state.hasVisibleConversation {\n                        escToClearHint\n                    }"))
    XCTAssertTrue(source.contains("canClearVisibleConversation: false"))
    XCTAssertTrue(source.contains("showsHeader: false"))
    XCTAssertTrue(responseSource.contains("var showsHeader: Bool = true"))
    XCTAssertTrue(responseSource.contains("if showsHeader {"))
    XCTAssertTrue(responseSource.contains(".padding(.top, state.usesNotchIsland ? 0 : OmiSpacing.lg)"))
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
    XCTAssertTrue(windowSource.contains("private static let askOmiAnimationDuration: TimeInterval = 0.14"))
    XCTAssertTrue(windowSource.contains("private static let askOmiSettleDelay: TimeInterval = 0.16"))
    XCTAssertTrue(windowSource.contains("FloatingControlBarGeometry.surfaceTransitionFrame("))
    XCTAssertTrue(windowSource.contains("? .notch(screenFrame: screenForPlacement?.frame)"))
    XCTAssertFalse(windowSource.contains("let currentTopCenteredFrame = NSRect("))
    XCTAssertTrue(windowSource.contains("let keepVoiceResponseAlive = state.isVoiceResponseGlowActive"))
    XCTAssertTrue(windowSource.contains("FloatingControlBarManager.shared.cancelChat(keepVoiceAlive: keepVoiceResponseAlive)"))
    XCTAssertTrue(windowSource.contains("static func notchAgentListHeight(agentCount: Int) -> CGFloat"))
    XCTAssertTrue(windowSource.contains("+ notchAgentListBottomMargin"))
    XCTAssertTrue(windowSource.contains("static let notchActiveSideWidth: CGFloat = 42"))
    XCTAssertTrue(windowSource.contains("func resizeForAgentSwitcher(visible: Bool)"))
    XCTAssertTrue(windowSource.contains("max(collapsedBarSize.width, Self.notchExpandedWidth)"))
    XCTAssertTrue(windowSource.contains("if state.showingAIConversation {\n                return\n            }"))
  }

  func testSpacesTransitionDoesNotReplayNotchRevealPop() throws {
    let windowSource = try floatingControlBarWindowSource()

    guard let start = windowSource.range(of: "private func performSpacesTransitionGrowIn()"),
      let end = windowSource.range(of: "private func defaultFrameForCurrentState()")
    else {
      return XCTFail("Expected performSpacesTransitionGrowIn section")
    }
    let body = String(windowSource[start.lowerBound..<end.lowerBound])

    // Switching Spaces must NOT replay the reveal "pop": animateGrowOutFromNotch
    // resets notchRevealProgress to 0.001 and re-zooms the island. The panel
    // already lives on every Space (.canJoinAllSpaces), so a Space switch should
    // keep it fully revealed and only re-assert the frame if it drifted.
    XCTAssertFalse(body.contains("animateGrowOutFromNotch"))
    XCTAssertTrue(body.contains("state.notchRevealProgress = 1"))
    XCTAssertTrue(body.contains("guard !Self.framesEquivalent(frame, targetFrame) else { return }"))
  }

  func testAgentSwitcherResizeMatchesContentMorphDurations() throws {
    let windowSource = try floatingControlBarWindowSource()

    // Pill mode still resizes its panel, and that resize must animate with the
    // same durations as its content, or the panel keeps sliding after the rows
    // settle. Notch mode is fixed-window: the switcher open/close must never
    // animate the NSPanel frame — it only re-asserts the constant idle/hover
    // surface frame and lets the SwiftUI content morph carry the transition.
    XCTAssertTrue(windowSource.contains("static let notchHoverMenuExpandDuration: TimeInterval = 0.16"))
    XCTAssertTrue(windowSource.contains("static let notchHoverMenuCollapseDuration: TimeInterval = 0.10"))
    XCTAssertTrue(windowSource.contains("static let notchHoverMenuExpandAnimation: Animation = .spring(response: 0.35, dampingFraction: 0.75)"))
    XCTAssertTrue(windowSource.contains("static let notchHoverMenuCollapseAnimation: Animation = .spring(response: 0.3, dampingFraction: 1.0)"))

    guard let start = windowSource.range(of: "func resizeForAgentSwitcher(visible: Bool)"),
      let end = windowSource.range(of: "private func pillAgentListWindowSize(")
    else {
      return XCTFail("Expected resizeForAgentSwitcher section")
    }
    let body = String(windowSource[start.lowerBound..<end.lowerBound])

    // Notch: fixed frame only, before any pill-mode resize.
    XCTAssertTrue(body.contains("if notchModeEnabled {"))
    XCTAssertTrue(body.contains("assertNotchFixedHoverSurfaceFrame()"))
    XCTAssertTrue(body.contains("animationDuration: Self.notchHoverMenuExpandDuration"))
    XCTAssertTrue(body.contains("animationDuration: Self.notchHoverMenuCollapseDuration"))
    XCTAssertTrue(body.contains("resizeSurfaceTransition("))
    XCTAssertTrue(body.contains(".agentSwitcher(visible: true)"))
    XCTAssertTrue(body.contains(".agentSwitcher(visible: false)"))
    XCTAssertFalse(body.contains("resizeAnchored("))
    // No bare animated resize (which defaults to the slow 0.3s) may remain in
    // the hover-menu expand/collapse path.
    XCTAssertFalse(body.contains("animated: true, anchorTop: true)"))
  }

  func testPTTResizeUsesSemanticSurfaceTransitionPlacement() throws {
    let windowSource = try floatingControlBarWindowSource()

    guard let start = windowSource.range(of: "func resizeForPTTState(expanded: Bool)"),
      let end = windowSource.range(
        of: "/// Size the notch to fit the \"thinking\" indicator",
        range: start.upperBound..<windowSource.endIndex
      )
    else {
      return XCTFail("Expected resizeForPTTState section")
    }
    let body = String(windowSource[start.lowerBound..<end.lowerBound])

    XCTAssertTrue(body.contains("resizeSurfaceTransition("))
    XCTAssertTrue(body.contains(".pushToTalk(expanded: expanded)"))
    XCTAssertFalse(body.contains("resizeAnchored("))
    XCTAssertFalse(body.contains("FloatingControlBarGeometry.targetFrame("))
  }

  func testTopLevelDelegationExecutorRemainsOutsideSubagentComposer() throws {
    let viewSource = try floatingControlBarViewSource()
    let executorURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/AgentDelegationExecutor.swift")
    let executorSource = try String(contentsOf: executorURL, encoding: .utf8)

    XCTAssertFalse(viewSource.contains("AgentDelegationExecutor.shared.spawnResolvedDelegation"))
    XCTAssertTrue(viewSource.contains("manager.continueAgent(from: pill, text: trimmed, attachments: staged)"))
    XCTAssertTrue(executorSource.contains("harnessOverride ?? task.directedProvider?.harnessMode"))
  }

  func testSpawnAgentToolCallOpensSubagentChat() throws {
    let responseSource = try aiResponseViewSource()
    let viewSource = try floatingControlBarViewSource()
    let chatBubbleSource = try chatBubbleSource()

    XCTAssertTrue(responseSource.contains("var onOpenAgent: ((UUID, @escaping (Bool) -> Void) -> Void)?"))
    XCTAssertTrue(responseSource.contains("var onOpenAgentRef: ((AgentTimelineRef, @escaping (Bool) -> Void) -> Void)? = nil"))
    XCTAssertTrue(responseSource.contains("onOpenAgent: onOpenAgent,\n                        onOpenAgentRef: onOpenAgentRef"))
    XCTAssertFalse(responseSource.contains("openNewlySpawnedAgentIfNeeded()"))
    XCTAssertFalse(responseSource.contains("autoOpenedSpawnedAgentIDs"))
    XCTAssertTrue(viewSource.contains("onOpenAgent: { agentID, completion in\n                openAgentInChat(agentID: agentID, completion: completion)"))
    XCTAssertTrue(viewSource.contains("onOpenAgentRef: { ref, completion in\n                openAgentInChat(ref: ref, completion: completion)"))
    XCTAssertTrue(chatBubbleSource.contains("var onOpenAgent: ((UUID, @escaping (Bool) -> Void) -> Void)? = nil"))
    XCTAssertTrue(chatBubbleSource.contains("var onOpenAgentRef: ((AgentTimelineRef, @escaping (Bool) -> Void) -> Void)? = nil"))
    XCTAssertTrue(chatBubbleSource.contains("calls.compactMap(\\.agentOpenRef).last"))
    XCTAssertTrue(chatBubbleSource.contains("agentOpenRef: block.agentOpenRef"))
    XCTAssertTrue(chatBubbleSource.contains("Self.cleanToolName(name) == \"spawn_agent\""))
    XCTAssertTrue(chatBubbleSource.contains("Self.labeledValue(in: output, keys: [\"id\"])"))
    XCTAssertTrue(chatBubbleSource.contains("keys: [\"sessionid\", \"session_id\"]"))
    XCTAssertTrue(chatBubbleSource.contains("keys: [\"runid\", \"run_id\"]"))
    XCTAssertTrue(chatBubbleSource.contains("AgentTimelineOpenFeedback.shouldShowUnavailable(succeeded:"))
    XCTAssertTrue(viewSource.contains("openAgentInChat(\n            ref: AgentTimelineRef(pillId: agentID, sessionId: nil, runId: nil),\n            completion: completion"))
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
      let inputEnd = viewSource.range(of: "private func recomputeUnifiedInputHeight")
    else {
      return XCTFail("Expected AI input view section")
    }
    let inputSource = String(viewSource[inputRange.lowerBound..<inputEnd.lowerBound])

    XCTAssertTrue(inputSource.contains(".beginVisibleMainQuery(message, fromVoice: false, animated: true)"))
    XCTAssertTrue(viewSource.contains("state.archiveCurrentExchange(using: floatingChatProvider)"))
    XCTAssertTrue(viewSource.contains(".beginVisibleMainQuery(message, fromVoice: false, animated: true)"))
    XCTAssertFalse(inputSource.contains("state.showingAIResponse = true"))
    XCTAssertFalse(viewSource.contains("state.conversationSurface == .mainResponse || state.showingAIResponse"))
    XCTAssertTrue(windowSource.contains("func beginVisibleMainQuery(_ message: String, fromVoice: Bool, animated: Bool = true)"))
    XCTAssertTrue(windowSource.contains("state.resetMeasuredContentHeight(for: .mainResponse)"))
    XCTAssertTrue(windowSource.contains("state.present(.mainResponse)"))
    XCTAssertTrue(windowSource.contains("beginMainResponseHeight(animated: animated)"))
    XCTAssertFalse(windowSource.contains("state.showingAIResponse = true"))
    XCTAssertFalse(windowSource.contains("state.chatHistory"))
    XCTAssertTrue(windowSource.contains("barWindow?.state.bindAnswerMessage(aiMessage)"))
  }

  func testActiveSubagentChatRefreshesWhenAgentOutputChanges() throws {
    let agentSource = try agentPillSource()
    let viewSource = try floatingControlBarViewSource()

    XCTAssertTrue(agentSource.contains("@Published var conversationMessages: [ChatMessage] = []"))
    XCTAssertTrue(agentSource.contains("pill.conversationMessages = displayMessages"))
    XCTAssertTrue(agentSource.contains("return message.sender == .user"))
    XCTAssertTrue(agentSource.contains("|| !trimmed.isEmpty"))
    XCTAssertTrue(agentSource.contains("|| message.isStreaming"))
    XCTAssertTrue(agentSource.contains("|| !message.contentBlocks.isEmpty"))
    XCTAssertTrue(viewSource.contains("private var displayedMessages: [ChatMessage]"))
    XCTAssertTrue(viewSource.contains("ChatMessage(id: \"\\(pill.id.uuidString)-query\", text: pill.query, sender: .user)"))
    XCTAssertTrue(viewSource.contains("Text(trimmed)"))
    XCTAssertTrue(agentSource.contains("@Published var contentRevision: Int = 0"))
    XCTAssertTrue(agentSource.contains("func markContentChanged()"))
    XCTAssertTrue(agentSource.contains("pill.markContentChanged()"))
    XCTAssertTrue(viewSource.contains(".id(pill.contentRevision)"))
    XCTAssertTrue(viewSource.contains("private var scrollContentToken: AnyHashable"))
    XCTAssertTrue(viewSource.contains("String(pill.contentRevision)"))
    XCTAssertTrue(viewSource.contains("message.text"))
    XCTAssertTrue(viewSource.contains("contentChangeToken: scrollContentToken"))
    XCTAssertTrue(viewSource.contains("state.reportContentHeight(height, for: .agent(pill.id))"))
  }

  func testFloatingSubagentWorkingStateUsesStreamingAssistantMessage() throws {
    let agentSource = try agentPillSource()
    let viewSource = try floatingControlBarViewSource()

    XCTAssertTrue(agentSource.contains("Self.ensureStreamingAssistantMessage(for: pill)"))
    XCTAssertTrue(agentSource.contains("private static func ensureStreamingAssistantMessage(for pill: AgentPill)"))
    XCTAssertTrue(agentSource.contains("var streamingMessage = ChatMessage(text: \"\", sender: .ai)"))
    XCTAssertTrue(agentSource.contains("streamingMessage.isStreaming = true"))
    XCTAssertTrue(agentSource.contains("pill.conversationMessages.append(streamingMessage)"))
    XCTAssertTrue(agentSource.contains("private static func clearStreamingAssistantMessage(for pill: AgentPill)"))
    XCTAssertTrue(agentSource.contains("private static func removeEmptyStreamingAssistantMessages(for pill: AgentPill)"))
    XCTAssertTrue(agentSource.contains("private static func upsertAssistantMessage(_ message: ChatMessage, for pill: AgentPill)"))
    XCTAssertTrue(agentSource.contains("completedMessage.isStreaming = false"))
    XCTAssertTrue(agentSource.contains("pill.conversationMessages.removeAll { $0.id == aiMessage.id }"))
    XCTAssertTrue(agentSource.contains("pill.conversationMessages[index] = message"))
    XCTAssertTrue(agentSource.contains("if !aiMessage.isStreaming, Self.hasVisibleAssistantContent(aiMessage)"))
    XCTAssertTrue(agentSource.contains("pill.status = .done"))
    XCTAssertTrue(viewSource.contains("private func normalizedAgentMessages(_ messages: [ChatMessage]) -> [ChatMessage]"))
    XCTAssertTrue(viewSource.contains("private var hasFinalAssistantOutput: Bool"))
    XCTAssertTrue(viewSource.contains("if hasFinalAssistantOutput, !pill.status.isFinished"))
    XCTAssertTrue(viewSource.contains("} else if trimmed.isEmpty && message.isStreaming && message.displayResources.isEmpty {"))
    XCTAssertTrue(viewSource.contains("TypingIndicator()"))
  }

  func testSharedChatMessagesOpenAndSendFollowLatest() throws {
    let source = try chatMessagesViewSource()

    XCTAssertTrue(source.contains("On the first load of a saved conversation, follow the latest message."))
    XCTAssertTrue(source.contains("scrollToBottom(proxy: proxy)\n        scheduleInitialScroll(proxy: proxy, delay: 0.05)"))
    XCTAssertTrue(source.contains("scheduleInitialScroll(proxy: proxy, delay: 0.18)"))
    XCTAssertTrue(source.contains("scheduleInitialScroll(proxy: proxy, delay: 0.45)"))
    XCTAssertTrue(source.contains("private func handleViewportSizeChange(_ size: CGSize, proxy: ScrollViewProxy)"))
    XCTAssertTrue(source.contains(".background(viewportResizeDetector(proxy: proxy))"))
    XCTAssertTrue(source.contains("scrollMode = .followingBottom\n        hasActivityBelow = false\n        userIsScrolling = false"))
    XCTAssertFalse(source.contains("Find the last user message"))
  }

  func testFloatingSubagentChatSettlesToLatestOnOpenContentAndResize() throws {
    let viewSource = try floatingControlBarViewSource()
    let scrollSource = try chatScrollBehaviorSource()

    XCTAssertTrue(viewSource.contains("ChatScrollContainer("))
    XCTAssertTrue(viewSource.contains("bottomAnchorId: \"agentBottom\""))
    XCTAssertTrue(viewSource.contains("contentChangeToken: scrollContentToken"))
    XCTAssertTrue(scrollSource.contains("@State private var lastViewportSize: CGSize = .zero"))
    XCTAssertTrue(scrollSource.contains(".background(viewportResizeDetector(proxy: proxy))"))
    XCTAssertTrue(scrollSource.contains("private func handleViewportSizeChange(_ size: CGSize, proxy: ScrollViewProxy)"))
    XCTAssertTrue(scrollSource.contains("scheduleSettledBottomFollow(proxy: proxy)"))
    XCTAssertTrue(scrollSource.contains("for delay in [0.05, 0.16, 0.32]"))
    XCTAssertFalse(viewSource.contains("private func agentChatViewportResizeDetector"))
    XCTAssertFalse(viewSource.contains("private func scrollToBottomSettled(_ proxy: ScrollViewProxy)"))
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

    XCTAssertTrue(agentSource.contains("@Published var viewedAt: Date?"))
    XCTAssertTrue(agentSource.contains("private let viewedFinishedTTL: TimeInterval = 10 * 60"))
    XCTAssertTrue(agentSource.contains("func markViewed(pillID: UUID)"))
    XCTAssertTrue(agentSource.contains("scheduleViewedExpiration(for: pill)"))
    XCTAssertTrue(agentSource.contains("private func trimForNewPillIfNeeded()"))
    XCTAssertTrue(agentSource.contains(".filter({ $0.status == .done && $0.id != activeChatPillID })"))
    XCTAssertTrue(viewSource.contains("manager.markViewed(pillID: pill.id)"))
    XCTAssertTrue(viewSource.contains("if displayStatus.isFinished"))
    XCTAssertTrue(viewSource.contains("manager.dismiss(pillID: pill.id)"))
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

  func testRealtimeHubGlowUsesSharedVoicePlaybackService() throws {
    let source = try realtimeHubControllerSource()

    // RealtimeHub owns turn orchestration, but selected app voice playback owns
    // speech synthesis and its fallback state. The glow must defer while the
    // shared playback service is speaking instead of tracking a second local
    // synthesizer inside RealtimeHub.
    XCTAssertTrue(source.contains("FloatingBarVoicePlaybackService.shared.isSpeaking"))
    XCTAssertTrue(source.contains("if clearResponseGlow"))
    XCTAssertTrue(
      source.contains(
        "|| (!audioReceivedThisTurn && !FloatingBarVoicePlaybackService.shared.isSpeaking)"))
    XCTAssertFalse(source.contains("private var localSpeechActive = false"))
    XCTAssertFalse(source.contains("AVSpeechSynthesizer"))
  }

  func testRealtimeHubKeepsSpeechFallbackArmedWhenNativeAudioDoesNotSchedule() throws {
    let hubSource = try realtimeHubControllerSource()
    let playerSource = try streamingPCMPlayerSource()

    XCTAssertTrue(playerSource.contains("private func ensureRunning() -> Bool"))
    XCTAssertTrue(playerSource.contains("@discardableResult\n  func enqueue(_ data: Data) -> Bool"))
    XCTAssertTrue(hubSource.contains("guard let pcmPlayer, pcmPlayer.enqueue(pcm24k) else"))
    XCTAssertTrue(hubSource.contains("keeping text fallback armed"))
    XCTAssertTrue(hubSource.contains("audioReceivedThisTurn = true\n    realtimePlaybackEpoch = pcmPlayer.playbackEpoch\n    responseGlowGate.markPlaybackActive(lease: lease)"))
    XCTAssertFalse(hubSource.contains("pcmPlayer?.playbackEpoch ??"))
    XCTAssertFalse(hubSource.contains("audioReceivedThisTurn = true\n    // If PTT muted music/system output"))
  }

  func testBeginTurnStopsQueuedLocalSpeechOnBargeIn() throws {
    let source = try realtimeHubControllerSource()

    // beginTurn must interrupt the shared playback service so queued OpenAI
    // one-shots, cached kickoff samples, and Apple fallback speech all stop
    // through one owner.
    XCTAssertTrue(source.contains("let voicePlaybackActive = FloatingBarVoicePlaybackService.shared.isSpeaking"))
    XCTAssertTrue(source.contains("FloatingBarVoicePlaybackService.shared.interruptCurrentResponse()"))
    XCTAssertFalse(source.contains("speech.stopSpeaking(at: .immediate)"))
    XCTAssertFalse(source.contains("localSpeechActive = false"))
  }

  func testRealtimeBargeInTracksLocalPlaybackNotOnlyServerTurn() throws {
    let source = try realtimeHubControllerSource()

    // Provider turn completion only means the server finished sending audio; the
    // local AVAudioPlayerNode may still be draining queued PCM. Keep playback as
    // an explicit owner so the next PTT is classified correctly and non-barge-in
    // starts do not blindly stop the player.
    XCTAssertFalse(source.contains("private var realtimePlaybackActive = false"))
    XCTAssertTrue(source.contains("private var reducerNativePlaybackActive: Bool"))
    XCTAssertTrue(source.contains("let voicePlaybackActive = FloatingBarVoicePlaybackService.shared.isSpeaking"))
    XCTAssertTrue(source.contains("let bargeIn = providerResponseInFlight || reducerNativePlaybackActive || voicePlaybackActive"))
    XCTAssertTrue(source.contains("if bargeIn {\n      pcmPlayer?.stop()"))
    XCTAssertTrue(source.contains("audioReceivedThisTurn = true\n    realtimePlaybackEpoch = pcmPlayer.playbackEpoch"))
    XCTAssertTrue(source.contains("private var realtimePlaybackEpoch = 0"))
    XCTAssertTrue(source.contains("player.onPlaybackScheduled = { [weak self] playbackEpoch in"))
    XCTAssertTrue(source.contains("self.realtimePlaybackEpoch = playbackEpoch"))
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
    // connects and holds early PTT audio during that remint gap. If the user
    // releases before the replacement is ready, the commit is deferred onto the
    // replacement session instead of dropping captured speech.
    XCTAssertTrue(sessionSource.contains("enum RealtimeHubBargeInStrategy"))
    XCTAssertTrue(sessionSource.contains("provider == .gemini ? .freshSession : .inSessionCancel"))
    XCTAssertTrue(hubSource.contains("private var sessionAuth: HubAuth?"))
    XCTAssertTrue(hubSource.contains("struct RealtimeReplacementAudioBuffer"))
    XCTAssertTrue(hubSource.contains("private var replacementAudioBuffer: RealtimeReplacementAudioBuffer?"))
    XCTAssertTrue(hubSource.contains("func commitTurn() -> RealtimeHubCommitResult"))
    XCTAssertTrue(hubSource.contains("private func restartSessionForBargeIn("))
    XCTAssertTrue(hubSource.contains("interruptedTurnTask: Task<InterruptedTurnPayload?, Never>?"))
    XCTAssertTrue(hubSource.contains("case .ephemeral:\n            self.remintReplacementSessionForBargeIn(provider: provider)"))
    XCTAssertTrue(hubSource.contains("expectedOwnerID: ownerID"))
    XCTAssertTrue(hubSource.contains("ownerScope: ownerScope"))
    XCTAssertTrue(hubSource.contains("barge-in replacement queued behind existing token mint"))
    XCTAssertTrue(hubSource.contains("finishBargeInReplacementAfterSessionReady()"))
    XCTAssertTrue(hubSource.contains("replacementAudioBuffer?.appendAudio(pcm16k)"))
    XCTAssertTrue(hubSource.contains("barge-in replacement not ready at commit"))
    XCTAssertTrue(hubSource.contains(".hubCommitDeferredForReplacement(turnID: turnID)"))
    XCTAssertTrue(hubSource.contains("return .deferredForReplacement"))
    XCTAssertTrue(hubSource.contains("return .rejectedNoSession"))
    XCTAssertTrue(hubSource.contains("failBargeInReplacement(provider: provider, reason: error.localizedDescription)"))
    XCTAssertFalse(hubSource.contains("attachGeminiScreenFrameAfterActivityStartIfNeeded"))
    XCTAssertFalse(hubSource.contains("attached early in-turn screen frame after activityStart"))
    XCTAssertFalse(hubSource.contains("attachGeminiScreenFrameBeforeCommitIfNeeded"))
    XCTAssertFalse(hubSource.contains("speculativeScreenshot"))
    XCTAssertTrue(hubSource.contains("case .screenshot:"))
    XCTAssertTrue(hubSource.contains("effect: { [ScreenCaptureManager.captureScreenJPEG()] }"))
    XCTAssertTrue(hubSource.contains("self.session?.injectImage(shot)"))
    XCTAssertTrue(hubSource.contains("screenshotToolResultTextForCurrentProvider(capturedBytes: shot?.count)"))
    XCTAssertTrue(sessionSource.contains("case .openai:"))
    XCTAssertTrue(sessionSource.contains("case .gemini:"))
    XCTAssertTrue(sessionSource.contains("\"realtimeInput\": [\"video\":"))
    XCTAssertFalse(hubSource.contains("responding = false"))
    XCTAssertFalse(hubSource.contains("realtimePlaybackActive = false"))
    XCTAssertTrue(hubSource.contains("exitVoiceUI(clearResponseGlow: true)"))
    XCTAssertTrue(hubSource.contains("exitVoiceUI(clearResponseGlow: true)\n      return .rejectedNoSession"))
    XCTAssertTrue(hubSource.contains("let providerResponseInFlight = reducerInterruptsPreviousTurn"))
    XCTAssertFalse(hubSource.contains("voiceTurnScreenContextSentEpoch"))
    XCTAssertFalse(hubSource.contains("sendVoiceTurnScreenContextIfNeeded"))
    XCTAssertFalse(hubSource.contains("voiceTurnScreenContextEnvelopeJSON"))
    XCTAssertFalse(hubSource.contains("<auto_voice_screen_context>"))
    XCTAssertFalse(hubSource.contains("ambient_voice_turn_context"))
    XCTAssertFalse(sessionSource.contains("func sendTurnContextText"))
    XCTAssertTrue(sessionSource.contains("private var pendingTextInputs: [(text: String, logLabel: String)] = []"))
    XCTAssertTrue(sessionSource.contains("bufferTextInput(text, logLabel: logLabel, reason: \"socket not open\")"))
    XCTAssertTrue(sessionSource.contains("bufferTextInput(text, logLabel: logLabel, reason: \"no open activity window\")"))
    XCTAssertTrue(sessionSource.contains("private func flushPendingTextInputs()"))
    XCTAssertTrue(sessionSource.contains("private func sendTextInputNow(_ text: String, logLabel: String)"))
    XCTAssertFalse(hubSource.contains("turnGeneration"))
    XCTAssertTrue(hubSource.contains("captureInterruptedTurnPayloadIfNeeded()"))
    XCTAssertTrue(hubSource.contains("completeBargeInReplacementAfterContinuity("))
    XCTAssertTrue(hubSource.contains("var replacementSessionOwnsInputTurn = false"))
    XCTAssertTrue(hubSource.contains("case .replaceSession:"))
    XCTAssertTrue(hubSource.contains("replace the connection and let the fresh session buffer this new turn while it opens"))
    XCTAssertTrue(hubSource.contains("case .cancelInSession:"))
    XCTAssertTrue(hubSource.contains("barge-in — stopping local playback tail"))
    XCTAssertTrue(hubSource.contains("if !replacementSessionOwnsInputTurn"))
    XCTAssertTrue(hubSource.contains("interrupting: providerResponseInFlight"))
    XCTAssertFalse(hubSource.contains("attachGeminiScreenFrameAfterActivityStartIfNeeded"))
    XCTAssertTrue(hubSource.contains("session?.cancelActiveResponse()"))
    XCTAssertTrue(hubSource.contains("private func isCurrentSession(_ source: RealtimeHubSession) -> Bool"))
    XCTAssertTrue(hubSource.contains("guard isCurrentSession(source) else { return }"))
    XCTAssertTrue(hubSource.contains("private func sendToolResultIfCurrent("))
    XCTAssertFalse(hubSource.contains("self.session?.sendToolResult(callId: callId"))
    XCTAssertTrue(sessionSource.contains("delegate.hubDidReceiveAudio(pcm, identity: identity, source: self)"))
    XCTAssertTrue(sessionSource.contains("guard isCurrentOpenAIResponseEvent(e) else"))
    XCTAssertTrue(sessionSource.contains("private var openAIResponseCreatePending = false"))
    XCTAssertTrue(sessionSource.contains("guard !openAIResponseCreatePending, let expected = openAIActiveResponseID else { return false }"))
    XCTAssertTrue(sessionSource.contains("return eventResponseID == expected"))
    XCTAssertFalse(sessionSource.contains("guard let expected = openAIActiveResponseID else { return true }"))
    XCTAssertTrue(sessionSource.contains("ignoring stale response.done"))
    XCTAssertTrue(sessionSource.contains("private var pendingOpenAIToolCallIds = Set<String>()"))
    XCTAssertTrue(sessionSource.contains("pendingOpenAIToolCallIds.insert(callId)"))
    XCTAssertTrue(sessionSource.contains("waiting for \\(self.pendingOpenAIToolCallIds.count) OpenAI tool result(s)"))
    XCTAssertTrue(sessionSource.contains("private var pendingGeminiToolCallIds = Set<String>()"))
    XCTAssertTrue(sessionSource.contains("pendingGeminiToolCallIds.insert(callId)"))
    XCTAssertTrue(sessionSource.contains("deferring Gemini turnComplete with"))
    XCTAssertTrue(sessionSource.contains("nextGeminiSyntheticToolCallId(name: name)"))
    XCTAssertFalse(sessionSource.contains("let callId = call[\"id\"] as? String ?? name"))
  }

  func testPointClickRejectsMissingAndMalformedCoordinates() {
    XCTAssertNil(RealtimeHubController.finiteCoordinate(nil))
    XCTAssertNil(RealtimeHubController.finiteCoordinate("12"))
    XCTAssertNil(RealtimeHubController.finiteCoordinate(true))
    XCTAssertNil(RealtimeHubController.finiteCoordinate(Double.nan))
    XCTAssertNil(RealtimeHubController.finiteCoordinate(Double.infinity))
    XCTAssertEqual(RealtimeHubController.finiteCoordinate(12), 12)
    XCTAssertEqual(RealtimeHubController.finiteCoordinate(12.5), 12.5)
    XCTAssertEqual(RealtimeHubController.finiteCoordinate(NSNumber(value: 7.25)), 7.25)
  }

  func testCredentialHealthRetryAndFailoverInvariants() throws {
    let apiSource = try apiClientSource()
    let hubSource = try realtimeHubControllerSource()

    XCTAssertTrue(
      apiSource.contains("authorizedRetryRequest")
        && apiSource.contains("getAuthHeader(forceRefresh: true)")
        && apiSource.contains("forHTTPHeaderField: \"Authorization\""),
      "Backend 401 retry paths must force-refresh Firebase auth")
    XCTAssertTrue(
      apiSource.contains("throw CredentialHealthError.backendTransient(statusCode: nil, message: error.localizedDescription)"),
      "Realtime mint retry transport failures must stay transient, not requires-login")
    XCTAssertTrue(
      apiSource.contains("invalidateSessionAfterUnauthorized")
        && apiSource.contains("throw CredentialHealthError.requiresLogin"),
      "Definitive session 401 after retry must invalidate and require login")
    XCTAssertTrue(
      apiSource.contains("} catch AuthError.notSignedIn {\n      await invalidateSessionAfterUnauthorized"),
      "Only definitive not-signed-in refresh failures should invalidate and require login")
    XCTAssertTrue(
      hubSource.contains("self.releaseMint(generation: mintGeneration, ownerScope: ownerScope)")
        && hubSource.contains(
          "CredentialHealthManager.shared.record(error, context: \"realtime_mint\")"),
      "Mint failure must clear minting before failover starts the alternate provider")
    XCTAssertTrue(
      hubSource.contains("if case .providerAuthFailed = credentialFailureClass {\n      if aliveFor < 10, failoverToAlternateProvider(reason: \"auth\") { return }"),
      "Provider auth failures should try alternate provider before stopping reconnect")
    XCTAssertTrue(
      hubSource.contains("if case .providerQuotaExceeded = credentialFailureClass {\n      if failoverToAlternateProvider(reason: \"quota\") { return }"),
      "Provider quota failures should try alternate provider regardless of socket age")
    XCTAssertTrue(
      hubSource.contains("let shouldRedactProviderMessage: Bool"),
      "Credential close logs must redact raw provider auth/quota payloads")
    XCTAssertTrue(
      hubSource.contains("private func shouldFailoverToAlternate(for failureClass: CredentialFailureClass?) -> Bool"),
      "Provider switching must be centralized and limited to stable credential/quota failures")
    XCTAssertFalse(
      hubSource.contains("if aliveFor < 10, failoverToAlternateProvider() { return }\n    // Re-warm"),
      "Transient fast closes should not switch voice providers")
  }

  func testSpeechSynthesizerDidCancelClearsGlow() throws {
    let source = try floatingBarVoicePlaybackServiceSource()

    // The single voice playback service owns AVSpeechSynthesizerDelegate and
    // must still clear glow on non-explicit cancellation paths.
    XCTAssertTrue(source.contains("func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance)"))
    XCTAssertTrue(source.contains("self.localSpeechActive = false"))
  }

  func testVoiceResponseGlowTriggersCompactResizeOnLegacyDisplays() throws {
    let source = try floatingControlBarWindowSource()

    // The glow observer must trigger a resize to the glow-adjusted collapsed
    // size on legacy displays, not just record the boolean — and it collapses
    // to the canonical pill frame so drift cannot accumulate.
    XCTAssertTrue(source.contains("guard !self.notchModeEnabled else { return }"))
    XCTAssertTrue(source.contains("self.resizeToFrame(self.canonicalCollapsedPillFrame(), makeResizable: false, animated: false)"))
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
    // window transition. Back from a subagent goes to the row list on every
    // display mode when pills exist; otherwise main-input/main-response.
    XCTAssertTrue(viewSource.contains("onBackToAgentRows: {\n                        showAgentListFromConversation()"))
    XCTAssertTrue(viewSource.contains("private func showAgentListFromConversation() {\n        (window as? FloatingControlBarWindow)?.leaveAgentConversation() ?? onCloseAI()\n    }"))
    XCTAssertTrue(windowSource.contains("func leaveAgentConversation()"))
    XCTAssertTrue(windowSource.contains("if !AgentPillsManager.shared.pills.isEmpty {\n            showAgentRowsFromConversation()"))
    XCTAssertTrue(windowSource.contains("private func showAgentRowsFromConversation()"))
    XCTAssertTrue(windowSource.contains("private func showMainConversationFromAgent()"))
    XCTAssertTrue(windowSource.contains("state.hideConversationSurface()"))
    XCTAssertTrue(windowSource.contains("openNotchHoverMenuUntilExit()"))
    XCTAssertTrue(windowSource.contains("resizeForMainInputAfterAgentExit()"))
    XCTAssertTrue(windowSource.contains("window.leaveAgentConversation()"))
    XCTAssertTrue(windowSource.contains("let expectsRows = !AgentPillsManager.shared.pills.isEmpty"))
    XCTAssertTrue(windowSource.contains("\"mode\": expectsRows ? \"rows\" : \"main\""))
    XCTAssertFalse(viewSource.contains("let onBackToOmi: () -> Void"))
  }

  func testNonNotchExpandedChatUsesUnifiedSurface() throws {
    let viewSource = try floatingControlBarViewSource()

    guard let bodyRange = viewSource.range(of: "var body: some View"),
      let bodyEnd = viewSource.range(of: "private var barNeedsFullWidth")
    else {
      return XCTFail("Expected floating bar body section")
    }
    let bodySource = String(viewSource[bodyRange.lowerBound..<bodyEnd.lowerBound])

    XCTAssertTrue(bodySource.contains("if state.usesNotchIsland || state.showingAIConversation || state.isNotchHoverMenuVisible {\n                unifiedFloatingSurface"))
    XCTAssertTrue(viewSource.contains("private var unifiedFloatingSurface: some View"))
    XCTAssertTrue(viewSource.contains("if state.showingAIConversation {\n                conversationView"))
    XCTAssertFalse(bodySource.contains("conversationView"))
    XCTAssertFalse(bodySource.contains("AskAIInputView("))
    XCTAssertFalse(bodySource.contains("AIResponseView("))
    XCTAssertTrue(viewSource.contains("private var barChrome: some View"))
    XCTAssertTrue(viewSource.contains("chrome only ever shows the idle pill, hover hints, and voice states"))
  }

  func testPTTCollapsePreservesGlowPaddingOnLegacyDisplays() throws {
    let source = try floatingControlBarWindowSource()

    // Legacy PTT collapse supplies the bare compact surface to the shared
    // transition path, which applies the active response/agent glow exactly once.
    XCTAssertTrue(source.contains("toSurfaceSize: expanded ? Self.voiceBarSize : Self.minBarSize"))
    XCTAssertTrue(source.contains("let windowSize = responseGlowWindowSizeForCurrentScreen(forSurfaceSize: size)"))
    XCTAssertTrue(source.contains("guard state.isVoiceResponseGlowActive || collapsedPillAgentGlowActive else"))
  }

  func testTerminalProjectionPreservesStatusText() throws {
    let source = try agentRuntimeStatusStoreSource()
    let agentSource = try agentPillSource()

    // Terminal projections must preserve the final result text so consumers
    // (floating pill latestActivity, task agent voice summary) can display it.
    XCTAssertFalse(source.contains("projection.statusText = terminal ? nil : statusText"))
    XCTAssertTrue(source.contains("projection.statusText = statusText"))
    XCTAssertTrue(agentSource.contains("case .succeeded:"))
    XCTAssertTrue(agentSource.contains("var finalMessage = currentAssistantMessage(for: pill) ?? ChatMessage(text: statusText, sender: .ai)"))
    XCTAssertTrue(agentSource.contains("upsertAssistantMessage(finalMessage, for: pill)"))
    XCTAssertTrue(agentSource.contains("let failureText = AgentFailureTranscriptFormatter.transcriptText(for: errorText) ?? \"Failed: \\(errorText)\""))
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
    XCTAssertTrue(source.contains("if pill.status.isFinished, pill.viewedAt != nil"))
    XCTAssertTrue(source.contains("let activity = Self.describeActivity(for: aiMessage)"))
    XCTAssertFalse(source.contains("AgentRuntimeStatusStore.shared.recordPresentationCompletion("))
    XCTAssertFalse(statusStoreSource.contains("func recordPresentationCompletion("))
    XCTAssertFalse(statusStoreSource.contains("func recordLocalSuccess("))
    XCTAssertTrue(statusStoreSource.contains("if !terminal, projectionsBySurface[surface.key]?.status.isTerminal == true {\n      return\n    }"))
  }

  func testStoppedPillIgnoresLateNonCancellationProjection() throws {
    let source = try agentPillSource()

    XCTAssertTrue(source.contains("if pill.status == .stopped && projection.status != .cancelled"))
    XCTAssertTrue(source.contains("if pill.status.isFinished && !projection.status.isTerminal"))
    XCTAssertTrue(source.contains("switch projection.status"))
  }

  func testDirectedProviderPillsDoNotForwardClaudeModelOverrides() throws {
    let source = try agentPillSource()
    let logoMarkSource = try agentProviderLogoMarkSource()
    let viewSource = try floatingControlBarViewSource()

    XCTAssertTrue(source.contains("let modelForSpawn = bridgeHarnessOverride == nil"))
    XCTAssertTrue(source.contains("model: modelForSpawn"))
    XCTAssertTrue(source.contains("model: pill.bridgeHarnessOverride == nil ? pill.model : nil"))
    XCTAssertTrue(source.contains("harnessMode: bridgeHarnessOverride"))
    XCTAssertTrue(viewSource.contains("AgentProviderLogoMark("))
    XCTAssertTrue(viewSource.contains("provider: pill.bridgeHarnessOverride"))
    XCTAssertTrue(logoMarkSource.contains("private static let hermesLogo = load(\"hermes_logo_flat\")"))
    XCTAssertTrue(logoMarkSource.contains("private static let openClawLogo = load(\"openclaw_logo_flat\")"))
    XCTAssertTrue(logoMarkSource.contains("return hermesLogo"))
    XCTAssertTrue(logoMarkSource.contains("return openClawLogo"))
    XCTAssertTrue(logoMarkSource.contains(".renderingMode(.template)"))
    XCTAssertTrue(logoMarkSource.contains(".foregroundStyle(statusColor)"))
    XCTAssertFalse(logoMarkSource.contains("return load(\"hermes_logo\")"))
    XCTAssertFalse(logoMarkSource.contains("return load(\"openclaw_logo\")"))
    // Provider agents without a dedicated logo fall back to a flat, status-tinted
    // robot mark — not the Omi round dot. Omi-native agents (nil override) keep
    // the dot via the `provider != nil` guard.
    XCTAssertTrue(logoMarkSource.contains("} else if provider != nil {"))
    XCTAssertTrue(logoMarkSource.contains("Text(\"🤖\")"))
    XCTAssertTrue(logoMarkSource.contains("statusColor\n                    .mask("))
  }

  func testCanonicalPillLifecycleQueuesFollowUpsAndCancelsActiveDismissals() throws {
    let source = try agentPillSource()

    XCTAssertTrue(source.contains("private var pendingFollowUpsByPill: [UUID: [PendingAgentFollowUp]] = [:]"))
    XCTAssertTrue(source.contains("private struct PendingAgentFollowUp"))
    XCTAssertTrue(source.contains("pendingFollowUpsByPill[pill.id, default: []].append(PendingAgentFollowUp(text: text, attachments: attachments))"))
    XCTAssertTrue(source.contains("Queued follow-up until the agent starts"))
    XCTAssertTrue(source.contains("Queued follow-up until the current run stops"))
    XCTAssertTrue(source.contains("let queuedFollowUps = self.pendingFollowUpsByPill.removeValue(forKey: pill.id) ?? []"))
    XCTAssertTrue(source.contains("text: queuedFollowUps.map(\\.text).joined(separator: \"\\n\\n\")"))
    XCTAssertTrue(source.contains("attachments: queuedFollowUps.flatMap(\\.attachments)"))
    XCTAssertTrue(source.contains("switch await self.cancelActiveRunBeforeFollowUp(runId: activeRunId, pill: pill, generation: generation)"))
    XCTAssertTrue(source.contains("case .cancelled:\n                        completion?(.providerFailed)\n                        return"))
    XCTAssertTrue(source.contains("private enum ActiveRunCancellationResult"))
    XCTAssertTrue(source.contains("private func cancelActiveRunBeforeFollowUp(runId: String, pill: AgentPill, generation: Int) async -> ActiveRunCancellationResult"))
    XCTAssertTrue(source.contains("let shouldCancelRun = pill?.status.isFinished == false"))
    XCTAssertTrue(source.contains("pendingFollowUpsByPill[pillID] = nil"))
    XCTAssertTrue(source.contains("DesktopCoordinatorService.shared.cancelAgentRun(runId: runId)"))
    XCTAssertTrue(source.contains("AgentRuntimeStatusStore.shared.recordLocalFailure("))
  }

  func testProviderMarkRoutingIsCentralized() throws {
    let routingSource = try agentRuntimeRoutingSource()
    XCTAssertTrue(routingSource.contains("var rendersProviderMark: Bool { self != nil }"))

    let viewSource = try floatingControlBarViewSource()
    XCTAssertTrue(viewSource.contains("pill.bridgeHarnessOverride.rendersProviderMark"))
    XCTAssertTrue(viewSource.contains("if provider.rendersProviderMark {"))
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
    let chatBubbleSource = try chatBubbleSource()
    let providerSource = try chatProviderSource()

    XCTAssertTrue(chatBubbleSource.contains("var compact: Bool = false"))
    XCTAssertTrue(chatBubbleSource.contains("var expandRunning: Bool = true"))
    XCTAssertTrue(chatBubbleSource.contains("State(initialValue: expandRunning && Self.hasRunningTool(in: calls))"))
    XCTAssertTrue(chatBubbleSource.contains(".onChange(of: hasRunningTool)"))
    XCTAssertTrue(chatBubbleSource.contains("private var header: some View"))
    XCTAssertTrue(chatBubbleSource.contains("private var expandedToolCalls: some View"))
    XCTAssertTrue(chatBubbleSource.contains("VStack(alignment: .leading, spacing: compact ? 0 : 6)"))
    XCTAssertTrue(chatBubbleSource.contains(".frame(height: compact ? 34 : nil)"))
    XCTAssertTrue(chatBubbleSource.contains("Image(systemName: isExpanded ? \"chevron.up\" : \"chevron.down\")"))
    XCTAssertTrue(chatBubbleSource.contains("ToolCallCard(\n              name: name"))
    XCTAssertTrue(chatBubbleSource.contains("agentOpenRef: block.agentOpenRef"))
    XCTAssertTrue(chatBubbleSource.contains("onOpenAgent: onOpenAgent"))
    XCTAssertTrue(chatBubbleSource.contains("onOpenAgentRef: onOpenAgentRef"))
    XCTAssertTrue(chatBubbleSource.contains("summaryEmbeddedInToolName"))
    XCTAssertTrue(providerSource.contains("cleanName.lowercased().hasPrefix(\"read:\")"))
    XCTAssertTrue(providerSource.contains("return \"Reading file\""))
  }

  func testSelectableMarkdownRoutesGFMTablesThroughMarkdownUI() throws {
    let selectableSource = try selectableMarkdownSource()
    let chatBubbleSource = try chatBubbleSource()
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
    XCTAssertTrue(chatBubbleSource.contains(".table { configuration in"))
    XCTAssertTrue(chatBubbleSource.contains(".markdownTableBorderStyle"))
    XCTAssertTrue(chatBubbleSource.contains(".markdownTableBackgroundStyle"))
  }

  func testNonProductionBundlesDoNotInstallNativeSentryHandlers() throws {
    let source = try omiAppSource()
    let loggerSource = try loggerSource()

    XCTAssertTrue(source.contains("options.enableAutoSessionTracking = !isDev"))
    XCTAssertTrue(source.contains("options.enableCrashHandler = !isDev"))
    XCTAssertTrue(source.contains("options.enableAppHangTracking = !isDev"))
    XCTAssertTrue(source.contains("options.enableWatchdogTerminationTracking = !isDev"))
    XCTAssertTrue(source.contains("options.appHangTimeoutInterval = isDev ? 0 : 3.0"))
    XCTAssertTrue(source.contains("guard !AnalyticsManager.isDevBuild else { return }"))
    XCTAssertTrue(source.contains("let breadcrumb = Breadcrumb(level: .info, category: \"lifecycle\")"))
    XCTAssertTrue(source.contains("breadcrumb.message = \"App Terminating\""))
    XCTAssertFalse(source.contains("SentrySDK.capture(message: \"App Terminating\")"))
    XCTAssertTrue(loggerSource.contains("if !isDevBuild {\n    let breadcrumb = Breadcrumb(level: .info, category: \"app\")"))
    XCTAssertTrue(loggerSource.contains("guard !isDevBuild else { return }"))
  }

  func testFloatingVoicePlaybackIgnoresStaleBargeInCallbacks() throws {
    let source = try floatingBarVoicePlaybackServiceSource()

    XCTAssertTrue(source.contains("private var playbackGeneration: UInt64 = 0"))
    XCTAssertTrue(source.contains("private var localSpeechActive = false"))
    XCTAssertTrue(source.contains("if localSpeechActive { return true }"))
    XCTAssertTrue(source.contains("localSpeechActive = true\n    let utterance = AVSpeechUtterance"))
    XCTAssertTrue(source.contains("playbackGeneration &+= 1"))
    XCTAssertTrue(source.contains("let generation = playbackGeneration"))
    XCTAssertTrue(source.contains("guard self.playbackGeneration == generation else { return }"))
    XCTAssertTrue(source.contains("guard self.audioPlayer === player else { return }"))
    XCTAssertTrue(source.contains("speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance)"))
    XCTAssertTrue(source.contains("self.localSpeechActive = false\n      self.clearFloatingPillResponseGlowIfIdle()"))
  }

  func testFloatingBarResizeCoalescesNoopFrames() throws {
    let source = try floatingControlBarWindowSource()

    XCTAssertTrue(source.contains("private static let frameNoopEpsilon: CGFloat = 0.5"))
    XCTAssertTrue(source.contains("private var pendingFrameAnimationTarget: NSRect?"))
    XCTAssertTrue(source.contains("let wasResizable = styleMask.contains(.resizable)"))
    XCTAssertTrue(source.contains("let alreadyAnimatingToTarget = pendingFrameAnimationTarget.map"))
    XCTAssertTrue(source.contains("if alreadyAtTarget, wasResizable == makeResizable"))
    XCTAssertTrue(source.contains("if alreadyAnimatingToTarget, wasResizable == makeResizable"))
    XCTAssertTrue(source.contains("frameAnimationToken += 1"))
    XCTAssertTrue(source.contains("pendingFrameAnimationTarget = frame"))
    XCTAssertTrue(source.contains("private static func framesEquivalent(_ lhs: NSRect, _ rhs: NSRect) -> Bool"))
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

  private func chatBubbleSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/Components/ChatBubble.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func typingIndicatorSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/TypingIndicator.swift")
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

  private func chatScrollBehaviorSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/Components/ChatScrollBehavior.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func agentProviderLogoMarkSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/AgentProviderLogoMark.swift")
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

  private func chatMessagesViewSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/Components/ChatMessagesView.swift")
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

  private func omiAppSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/OmiApp.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func floatingBarVoicePlaybackServiceSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/FloatingBarVoicePlaybackService.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func loggerSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Logger.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}
