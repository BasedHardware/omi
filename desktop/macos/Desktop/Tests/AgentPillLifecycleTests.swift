import AppKit
import VoiceTurnDomain
import XCTest

@testable import Omi_Computer

@MainActor final class AgentPillLifecycleTests: XCTestCase {
  @MainActor
  func testHydratedPillUsesKernelProviderIdentityForRendering() {
    let pill = AgentPill(query: "fixture", model: "fixture", ownerID: "owner")
    XCTAssertNil(pill.providerIdentity)

    pill.applyCanonicalProviderIdentity("openclaw")
    XCTAssertEqual(pill.providerIdentity, .openclaw)

    pill.applyCanonicalProviderIdentity("unknown")
    XCTAssertEqual(pill.providerIdentity, .openclaw)
  }

  @MainActor
  func testVoiceResponseWaitingDrivesGlowUntilPlaybackOrClear() {
    let state = FloatingControlBarState()
    let coordinator = VoiceTurnCoordinator()
    coordinator.configure(barState: state)

    XCTAssertFalse(state.isVoiceResponseGlowActive)

    let turnID = coordinator.begin(intent: .hold)
    coordinator.publish(.selectRoute(turnID: turnID, route: .deepgramBatch))
    coordinator.publish(.finalize(turnID: turnID))
    coordinator.publish(.transcriptionFinal(turnID: turnID, text: "fixture"))
    XCTAssertTrue(state.isVoiceResponseWaiting)
    XCTAssertFalse(state.isVoiceResponseActive)
    XCTAssertTrue(state.isVoiceResponseGlowActive)

    let identity = coordinator.activeTurn!.providerEffectIdentity!
    coordinator.publish(
      .providerResponseStartedScoped(
        turnID: turnID,
        identity: identity,
        sessionID: nil,
        responseID: nil))
    XCTAssertFalse(state.isVoiceResponseWaiting)
    XCTAssertTrue(state.isVoiceResponseActive)
    XCTAssertTrue(state.isVoiceResponseGlowActive)

    coordinator.publish(.finish(turnID: turnID, reason: .providerFailed))
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

  func testMainChatSpawnReceiptProjectsTheExistingFloatingPill() throws {
    let providerSource = try chatProviderSource()
    let viewSource = try floatingControlBarViewSource()
    let pillSource = try agentPillSource()

    XCTAssertTrue(providerSource.contains("AgentPillsManager.shared.upsertSpawnedPill("))
    XCTAssertTrue(providerSource.contains("producingJournalSurface: mainChatSurfaceReference()"))
    XCTAssertTrue(providerSource.contains("struct SpawnedAgentPillProjection: Equatable, Sendable"))
    XCTAssertTrue(pillSource.contains("guard !pill.status.isFinished else { return }"))
    XCTAssertTrue(viewSource.contains("private func mainConversationBackAction()"))
    XCTAssertTrue(viewSource.contains(".help(agentPills.pills.isEmpty ? \"Close Omi Chat\" : \"Back to subagents\")"))
  }

  func testFloatingPillProjectionMergeRequiresCanonicalKernelIds() throws {
    let source = try agentPillSource()

    XCTAssertTrue(source.contains("DesktopCoordinatorService.shared.listFloatingAgentPills(limit: 50)"))
    XCTAssertTrue(source.contains("guard let pillId = canonicalPillId(from: entry) else"))
    XCTAssertTrue(source.contains("guard let sessionId = canonicalString(entry[\"sessionId\"]) else"))
    XCTAssertTrue(source.contains("guard let runId = canonicalString(entry[\"runId\"]) else"))
    XCTAssertTrue(source.contains("canonical projection source="))
    XCTAssertTrue(source.contains("pill.canonicalSessionId = sessionId"))
    XCTAssertTrue(source.contains("    updateCanonicalRun(\n      for: pill,\n      runId: runId,"))
    XCTAssertTrue(source.contains("attemptId: canonicalString(entry[\"attemptId\"]),"))
    XCTAssertTrue(source.contains("reconcileProjectedPillRun(entryStatus: projectedStatus, pill: pill)"))
    XCTAssertTrue(source.contains("removeRenderedProjection(pillID: pill.id)"))
    XCTAssertTrue(source.contains("Self.shouldRemoveRenderedProjection("))
    XCTAssertTrue(source.contains("func resolveAndPresentAgent("))
    XCTAssertTrue(source.contains("hydratePillFromKernel(preference: preference, ownerID: ownerID)"))
    XCTAssertTrue(source.contains("inspectAgentRun(runId: runId)"))
    XCTAssertFalse(source.contains("stablePillUUID"))
    XCTAssertFalse(source.contains("UUID(uuidString: idString) ??"))
  }

  func testProjectedPillsKeepTerminalJournalReconciliationSeparateFromRunPolling() throws {
    let source = try agentPillSource()

    XCTAssertTrue(source.contains("private func reconcileProjectedPillRun(entryStatus: String, pill: AgentPill)"))
    XCTAssertTrue(
      source.contains("guard shouldPollCanonicalRun(for: pill, projectedStatus: entryStatus) else { return }"))
    XCTAssertTrue(source.contains("startCanonicalRunPolling(for: pill)"))
    XCTAssertTrue(source.contains("private func shouldPollCanonicalRun(for pill: AgentPill, projectedStatus: String)"))
    XCTAssertTrue(source.contains("AgentPillLifecycleConvergencePolicy.shouldStartCanonicalPoll("))
    XCTAssertTrue(source.contains("private func ensureCanonicalReconciliation()"))
    XCTAssertTrue(source.contains("await self.refreshProjectedPillsFromKernel()"))
    XCTAssertTrue(source.contains("func lifecycleConvergenceSnapshot(runIDs: Set<String>) async -> String"))
    XCTAssertTrue(source.contains("pill.producingJournalSurface != nil"))
    XCTAssertTrue(source.contains("private func ensureTerminalJournalMaterialization(for pill: AgentPill)"))
    XCTAssertTrue(
      source.contains(
        "      if isCurrentRunAttempt(pillID: pill.id, generation: generation) {\n        runTasksByPill[pill.id] = nil"
      ))
    XCTAssertTrue(source.contains("if pill.status.isFinished && !isTerminalProjectedStatus(status)"))
    XCTAssertTrue(source.contains("if pill.status.isFinished && !isTerminalProjectedStatus(inspection.status)"))
  }

  func testProjectionBootstrapRetriesUntilTheRuntimeCanReadCanonicalPills() throws {
    let source = try agentPillSource()

    XCTAssertTrue(source.contains("private func scheduleProjectionBootstrap()"))
    XCTAssertTrue(source.contains("for _ in 0..<projectionBootstrapAttempts"))
    XCTAssertTrue(source.contains("AgentRuntimeProcess.shared.isReadyForDirectControl()"))
    XCTAssertTrue(source.contains("await refreshProjectedPillsFromKernel()"))
    XCTAssertTrue(source.contains("func refreshProjectedPillsFromKernel() async -> Bool"))
    XCTAssertTrue(source.contains("canonical projection bootstrap started"))
    XCTAssertTrue(source.contains("projection bootstrap did not reach a ready runtime"))
  }

  func testRuntimeHandshakeRestartsCanonicalPillProjectionBootstrap() throws {
    let pillSource = try agentPillSource()
    let runtimeSource = try agentRuntimeProcessSource()

    XCTAssertTrue(runtimeSource.contains("static let agentRuntimeDidBecomeReady"))
    XCTAssertTrue(runtimeSource.contains("func isReadyForDirectControl() -> Bool"))
    XCTAssertTrue(runtimeSource.contains("NotificationCenter.default.post(name: .agentRuntimeDidBecomeReady"))
    XCTAssertTrue(pillSource.contains("publisher(for: .agentRuntimeDidBecomeReady)"))
    XCTAssertTrue(pillSource.contains("self?.scheduleProjectionBootstrap()"))
  }

  func testDirectControlTimeoutsSeparateBoundedReadsFromRunCompletion() throws {
    let runtimeSource = try agentRuntimeProcessSource()

    XCTAssertTrue(runtimeSource.contains("private var activeControlTimeoutTasks"))
    XCTAssertTrue(runtimeSource.contains("static func directControlTimeoutNanoseconds"))
    XCTAssertTrue(runtimeSource.contains("case \"list_agent_sessions\", \"get_agent_run\""))
    XCTAssertEqual(AgentRuntimeProcess.directControlTimeoutNanoseconds(for: "get_agent_run"), 2_000_000_000)
    XCTAssertEqual(AgentRuntimeProcess.directControlTimeoutNanoseconds(for: "send_agent_message"), 180_000_000_000)
    XCTAssertEqual(AgentRuntimeProcess.directControlTimeoutNanoseconds(for: "spawn_agent"), 15_000_000_000)
    XCTAssertTrue(runtimeSource.contains("private func timeoutControlRequest("))
    XCTAssertTrue(runtimeSource.contains("if !isBridgeReady {\n      try await registerClient("))
    XCTAssertTrue(runtimeSource.contains("BridgeError.timeout"))
  }

  func testFloatingPillInspectResultsAreGuardedByCurrentRunAttempt() throws {
    let source = try agentPillSource()

    XCTAssertTrue(source.contains("private var runAttemptGenerationByPill: [UUID: Int] = [:]"))
    XCTAssertTrue(source.contains("let generation = nextRunAttemptGeneration(for: pill.id)"))
    XCTAssertTrue(source.contains("guard isCurrentRunAttempt(pillID: pill.id, generation: generation) else { return }"))
    XCTAssertTrue(
      source.contains("apply(inspection: inspection, to: pill, expectedRunId: runId, expectedAttemptId: attemptId)"))
    XCTAssertTrue(source.contains("guard pill.canonicalRunId == runId else"))
    XCTAssertTrue(source.contains("if let attemptId, pill.canonicalAttemptId != attemptId"))
    XCTAssertTrue(source.contains("guard pill.canonicalSessionId == sessionId else { return }"))
    XCTAssertTrue(
      source.contains("if let expectedRunId, let inspectedRunId = inspection.runId, inspectedRunId != expectedRunId"))
    XCTAssertTrue(
      source.contains(
        "if let expectedAttemptId, let inspectedAttemptId = inspection.attemptId, inspectedAttemptId != expectedAttemptId"
      ))
    XCTAssertTrue(source.contains("if let expectedRunId, pill.canonicalRunId != expectedRunId"))
    XCTAssertTrue(source.contains("if let expectedAttemptId, pill.canonicalAttemptId != expectedAttemptId"))
    XCTAssertTrue(source.contains("\"stale_inspection_ignored\""))
  }

  @MainActor
  func testCanonicalReconciliationRequiresTerminalJournalMaterialization() {
    XCTAssertTrue(
      AgentPillLifecycleConvergencePolicy.requiresCanonicalReconciliation(
        status: .running,
        requiresJournalCompletion: false,
        hasTerminalJournalCompletion: false,
        hasTerminalJournalMaterializationFailure: false,
        hasPendingFollowUp: false))
    XCTAssertFalse(
      AgentPillLifecycleConvergencePolicy.requiresCanonicalReconciliation(
        status: .done,
        requiresJournalCompletion: false,
        hasTerminalJournalCompletion: false,
        hasTerminalJournalMaterializationFailure: false,
        hasPendingFollowUp: false))
    XCTAssertTrue(
      AgentPillLifecycleConvergencePolicy.requiresCanonicalReconciliation(
        status: .done,
        requiresJournalCompletion: true,
        hasTerminalJournalCompletion: false,
        hasTerminalJournalMaterializationFailure: false,
        hasPendingFollowUp: false))
    XCTAssertFalse(
      AgentPillLifecycleConvergencePolicy.requiresCanonicalReconciliation(
        status: .done,
        requiresJournalCompletion: true,
        hasTerminalJournalCompletion: true,
        hasTerminalJournalMaterializationFailure: false,
        hasPendingFollowUp: false))
    XCTAssertTrue(
      AgentPillLifecycleConvergencePolicy.requiresCanonicalReconciliation(
        status: .done,
        requiresJournalCompletion: true,
        hasTerminalJournalCompletion: true,
        hasTerminalJournalMaterializationFailure: false,
        hasPendingFollowUp: true))
    XCTAssertFalse(
      AgentPillLifecycleConvergencePolicy.requiresCanonicalReconciliation(
        status: .done,
        requiresJournalCompletion: true,
        hasTerminalJournalCompletion: false,
        hasTerminalJournalMaterializationFailure: true,
        hasPendingFollowUp: false))

    XCTAssertTrue(
      AgentPillLifecycleConvergencePolicy.shouldStartCanonicalPoll(
        projectedStatusIsTerminal: true,
        pillStatus: .done,
        hasCanonicalTerminalDetail: false,
        isPolling: false))
    XCTAssertFalse(
      AgentPillLifecycleConvergencePolicy.shouldStartCanonicalPoll(
        projectedStatusIsTerminal: true,
        pillStatus: .done,
        hasCanonicalTerminalDetail: true,
        isPolling: false))
    XCTAssertFalse(
      AgentPillLifecycleConvergencePolicy.shouldStartCanonicalPoll(
        projectedStatusIsTerminal: false,
        pillStatus: .running,
        hasCanonicalTerminalDetail: false,
        isPolling: true))
  }

  @MainActor
  func testTerminalListProjectionWaitsForCanonicalDetailBeforeJournalizingExactOutput() {
    let statusOnly = AgentPillTerminalJournalMaterializationPolicy.decision(
      status: .done,
      canonicalRunID: "run-123",
      canonicalDetailRunID: nil,
      canonicalDetailOutput: nil)
    XCTAssertEqual(statusOnly, .awaitingCanonicalDetail)

    let finalText = "The background agent completed the requested task."
    let canonicalDetail = AgentPillTerminalJournalMaterializationPolicy.decision(
      status: .done,
      canonicalRunID: "run-123",
      canonicalDetailRunID: "run-123",
      canonicalDetailOutput: finalText)
    XCTAssertEqual(canonicalDetail, .materialize(status: "completed", output: finalText))
  }

  func testFloatingPillRunChangesResetAttemptAndPreserveTransients() throws {
    let source = try agentPillSource()

    XCTAssertTrue(source.contains("private func updateCanonicalRun("))
    XCTAssertTrue(source.contains("terminalJournalMaterializedPillIDs.remove(pill.id)"))
    XCTAssertTrue(source.contains("preservingAttemptForSameRun: true"))
    XCTAssertTrue(source.contains("return !isSeenInRuntimeSnapshot && !hasLocalTransientState"))
    XCTAssertTrue(source.contains("private func hasLocalTransientState(pillID: UUID) -> Bool"))
    XCTAssertTrue(source.contains("pendingFollowUpsByPill[pillID]?.isEmpty == false"))
    XCTAssertFalse(source.contains("recordingPillID"))
    XCTAssertFalse(source.contains("toggleFollowUpVoice"))
    XCTAssertFalse(source.contains("startPillFollowUp"))
    XCTAssertFalse(source.contains("cancelPillFollowUp"))
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
    XCTAssertTrue(responseSource.contains("&& message.displayResources.isEmpty\n            {"))
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

    XCTAssertTrue(source.contains("legacyClientScope == AgentLegacyClientScope.floatingPill"))
    XCTAssertTrue(source.contains("private var cachedFloatingPillSystemPrompt: String = \"\""))
    XCTAssertTrue(source.contains("cachedFloatingPillSystemPrompt = floatingPillSystemPrompt"))
    XCTAssertTrue(source.contains("cachedFloatingPillSystemPrompt = \"\""))
    XCTAssertTrue(source.contains("if cachedFloatingPillSystemPrompt.isEmpty"))
    XCTAssertTrue(source.contains("systemPrompt = cachedFloatingPillSystemPrompt"))
    XCTAssertTrue(source.contains(#"excludingToolNames: ["spawn_agent", "delegate_agent", "setup_agent_provider"]"#))
    XCTAssertTrue(
      source.contains(
        "let scopedToolPrompt = DesktopCapabilityRegistry.scopedDesktopToolPrompt(excluding: excludedToolNames)"))
    XCTAssertTrue(source.contains(#".replacingOccurrences(of: "{user_name}", with: promptUserName)"#))
  }

  func testAgentRunInstallAssistPillMachineryIsGone() throws {
    let source = try agentPillSource()

    // The agent-run installer was replaced by the deterministic
    // LocalAgentProviderInstaller (native confirm dialog + Process): no
    // code-built install brief, no auto-approving installer pill, no
    // Combine status watcher, and no stale `npm bin -g` probing prose.
    XCTAssertFalse(source.contains("installAssistBrief"))
    XCTAssertFalse(source.contains("spawnInstallAssistPill"))
    XCTAssertFalse(source.contains("installAssistWatchersByPill"))
    XCTAssertFalse(source.contains("npm bin -g"))
  }

  func testProviderCorrectionUsesPreviousFloatingRequestObjective() throws {
    let directive = AgentPillsManager.providerDirective(
      from: "I meant ask OpenClaw",
      contextualPreviousRequest: "ask grok to search for david zhang on X and tell me who the top 3 are")

    XCTAssertEqual(directive?.provider, .openclaw)
    XCTAssertEqual(directive?.rewrittenQuery, "search for david zhang on X and tell me who the top 3 are")
  }

  func testFuzzyProviderDirectiveRoutesMangledNames() throws {
    // STT / typos the strict token list misses still route to the right agent,
    // and the objective is preserved (the provider word is not swallowed).
    let codecs = AgentPillsManager.providerDirective(from: "ask codecs to summarize my last meeting")
    XCTAssertEqual(codecs?.provider, .codex)
    XCTAssertEqual(codecs?.rewrittenQuery, "to summarize my last meeting")

    let openFlaw = AgentPillsManager.providerDirective(from: "run open flaw on the auth module")
    XCTAssertEqual(openFlaw?.provider, .openclaw)
    XCTAssertEqual(openFlaw?.rewrittenQuery, "on the auth module")

    let hermies = AgentPillsManager.providerDirective(from: "tell hermies to draft the reply")
    XCTAssertEqual(hermies?.provider, .hermes)
  }

  func testFuzzyProviderDirectiveDoesNotHijackOrdinaryTasks() throws {
    // No directive verb, or a provider that maps to a default (non-directed)
    // agent, must not produce a directed pill.
    XCTAssertNil(AgentPillsManager.providerDirective(from: "summarize my unread messages"))
    XCTAssertNil(AgentPillsManager.providerDirective(from: "run the integration tests"))
    // Claude Code (.acp) is a default provider, not a directed pill.
    XCTAssertNil(AgentPillsManager.providerDirective(from: "use claude code to refactor this"))
  }

  func testFloatingRouterProvidesRecentVisibleRequestToProviderDirective() throws {
    let source = try floatingControlBarWindowSource()

    XCTAssertTrue(source.contains("contextualPreviousRequest: recentVisibleUserRequest(in: barWindow)"))
    XCTAssertTrue(
      source.contains("private func recentVisibleUserRequest(in barWindow: FloatingControlBarWindow) -> String?"))
    XCTAssertTrue(source.contains("barWindow.state.chatHistory.reversed().compactMap"))
  }

  func testTypedProviderDirectivePromptsForSetupWhenProviderUnavailable() throws {
    let source = try floatingControlBarWindowSource()

    XCTAssertTrue(source.contains("LocalAgentProviderRouting.resolveSpawnWithAutoInstall("))
    XCTAssertTrue(source.contains("requestedProvider: directive.provider"))
    XCTAssertTrue(source.contains("floating-agent-provider-unavailable"))
    XCTAssertTrue(source.contains("completeVisibleAgentResponse("))
    XCTAssertFalse(source.contains("completeVisibleProviderSetupPrompt("))
    XCTAssertTrue(source.contains("FloatingBarVoicePlaybackService.shared.speakOneShot(spokenStatus)"))
  }

  func testSubagentChatSpawnRequestCreatesSiblingAgent() throws {
    let source = try floatingControlBarViewSource()

    XCTAssertTrue(
      source.contains("if staged.isEmpty, let handoff = AgentPillsManager.floatingAgentHandoff(for: trimmed)"))
    XCTAssertTrue(source.contains("harnessOverride: pill.bridgeHarnessOverride"))
    XCTAssertTrue(source.contains("state.present(.agent(sibling.id))"))
    XCTAssertTrue(agentPillSource.contains("@Published private(set) var bridgeHarnessOverride: AgentHarnessMode?"))
    XCTAssertTrue(agentPillSource.contains("bridgeHarnessOverride: AgentHarnessMode? = nil"))
    XCTAssertTrue(agentPillSource.contains("self.bridgeHarnessOverride = bridgeHarnessOverride"))
    XCTAssertTrue(
      agentPillSource.contains(
        "let pill = AgentPill(query: query, model: model, bridgeHarnessOverride: bridgeHarnessOverride)"))
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
    XCTAssertTrue(
      source.contains("barWindow?.resizeForActiveAgentChatPublic(pillID: pill.id, animated: !wasShowingConversation)"))
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
      "The response glow is declared after the black dock fill in the ZStack, so it renders on top of the dock surface — keeping the glow on the lower edge without cutting into the pure-black notch island."
    )
    XCTAssertTrue(source.contains("private var notchSurfaceHorizontalInset: CGFloat"))
    XCTAssertTrue(source.contains("state.usesNotchIsland ? FloatingControlBarWindow.notchGlowOutsetX : 0"))
    XCTAssertTrue(source.contains("state.usesNotchIsland ? FloatingControlBarWindow.notchGlowOutsetBottom : 0"))
    XCTAssertTrue(source.contains("geometry.size.width - notchSurfaceHorizontalInset * 2"))
    XCTAssertTrue(source.contains("geometry.size.height - notchSurfaceBottomInset"))
    XCTAssertTrue(source.contains(".padding(.horizontal, notchSurfaceHorizontalInset)"))
    XCTAssertTrue(source.contains(".padding(.bottom, notchSurfaceBottomInset)"))
    XCTAssertTrue(windowSource.contains("    if usesNotchIsland {\n      return NSSize("))
    XCTAssertFalse(
      windowSource.contains(
        "let targetSize = self.currentSurfaceSizeForCurrentScreen(frameIncludesVoiceGlow: wasActive)"))
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
    XCTAssertFalse(lobeSource.contains("showingNotchPttHint"))
    XCTAssertTrue(source.contains("pttStatusBanner"))
    XCTAssertTrue(source.contains("state.isVoiceListening && state.pttHintText.isEmpty"))
    XCTAssertFalse(source.contains("!state.isVoiceFollowUp && !state.showingAIConversation"))
  }

  func testVoiceWaveformBarsOwnedByChromeMorph() throws {
    let view = try floatingControlBarViewSource()
    let response = try aiResponseViewSource()
    let waveformSites = view.components(separatedBy: "VoiceWaveformBars(").count - 1
    // Chrome morph lobe + optional idle pill voiceListeningView.
    XCTAssertEqual(waveformSites, 2)
    XCTAssertTrue(view.contains("private var notchAgentLobe: some View"))
    XCTAssertTrue(view.contains("private var voiceListeningView: some View"))
    XCTAssertTrue(
      view.contains("      if state.usesNotchIsland || state.showingAIConversation {\n        notchChrome"))
    XCTAssertFalse(response.contains("VoiceWaveformBars("))
    XCTAssertFalse(view.contains("voiceFollowUpView"))
    XCTAssertFalse(view.contains("toggleFollowUpVoice"))
    XCTAssertFalse(view.contains("agentFollowUp"))
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

    XCTAssertTrue(
      source.contains(
        "            notchAgentLogoHitTarget\n              .frame(width: notchChromeLayoutWidth, height: notchChromeHeight)"
      ))
    XCTAssertFalse(
      source.contains(
        "notchAgentLogoHitTarget\n                            .frame(width: notchChromeLayoutWidth, height: notchChromeHeight + notchHoverMenuHeight)"
      ))
    XCTAssertTrue(source.contains("@State private var notchSettingsHovering = false"))
    XCTAssertTrue(source.contains("if !state.isVoicePresentationActive && notchSettingsHovering"))
    XCTAssertTrue(source.contains("private var notchSettingsButton: some View"))
    XCTAssertTrue(source.contains(".frame(width: 44, height: 44)"))
    XCTAssertTrue(source.contains(".accessibilityIdentifier(\"notch_floating_bar_settings\")"))
    XCTAssertFalse(
      source.contains(
        ".background(Color.white.opacity(0.12))\n                .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))"
      ))
    XCTAssertTrue(source.contains("notchSettingsHovering = showsHoverChrome"))
    XCTAssertTrue(source.contains("openFloatingBarSettings()"))
    XCTAssertTrue(source.contains("openAgentChatsFromNotchLogo()"))
    XCTAssertFalse(
      source.contains(
        ".onHover { hovering in\n            withAnimation(.easeInOut(duration: 0.12)) {\n                notchSettingsHovering = hovering"
      ))
    XCTAssertFalse(source.contains(".onTapGesture {\n                    openFloatingBarSettings()\n                }"))
  }

  func testNotchChatSizingPreservesSurfaceWidthAndGlowList() throws {
    let source = try floatingControlBarWindowSource()

    XCTAssertTrue(
      source.contains("let width = max(defaultWidth, currentResponseSurfaceWidth(usesNotchIsland: usesNotchIsland))"))
    XCTAssertTrue(source.contains("func resizeForAgentSwitcher(visible: Bool)"))
    XCTAssertFalse(source.contains("!state.isVoiceResponseActive,\n              !state.isShowingNotification"))
  }

  func testStreamingResponseGrowthIsSteppedAndNonAnimated() throws {
    let windowSource = try floatingControlBarWindowSource()
    let viewSource = try floatingControlBarViewSource()
    let responseSource = try aiResponseViewSource()
    let scrollSource = try chatScrollBehaviorSource()

    XCTAssertTrue(windowSource.contains("responseStreamingResizeStep"))
    XCTAssertTrue(
      windowSource.contains(
        "let steppedHeight =\n          (targetHeight / Self.responseStreamingResizeStep).rounded(.up) * Self.responseStreamingResizeStep"
      ))
    XCTAssertTrue(
      windowSource.contains(
        "to: NSSize(width: max(self.expandedContentWidth, self.currentResponseSurfaceWidth()), height: clampedHeight)"))
    XCTAssertTrue(windowSource.contains("      animated: false,\n      anchorTop: true"))
    XCTAssertTrue(viewSource.contains(".transition(.opacity)"))
    XCTAssertFalse(
      viewSource.contains(
        "conversationView\n                    .padding(.horizontal, 12)\n                    .padding(.top, 4)\n                    .padding(.bottom, 9)\n                    .transition(.move(edge: .top).combined(with: .opacity))"
      ))
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
    XCTAssertTrue(source.contains("isChatChromePinned || shouldShowNotchHoverMenu"))
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
    // The provider logo must be drawn exactly once per row. The row itself must
    // NOT draw its own `AgentProviderLogoMark`, or it would double up under the
    // separate static header mark.
    XCTAssertFalse(source.contains("AgentProviderLogoMark(provider: provider, statusColor: statusColor, size: 16)"))
    XCTAssertTrue(
      source.contains("      Color.clear\n        .frame(width: NotchAgentStackMetrics.listOrbSlotWidth, height: 18)")
    )
    XCTAssertEqual(
      source.components(separatedBy: "AgentProviderLogoMark(provider: provider").count - 1,
      1,
      "Notch row path must construct the provider logo mark exactly once (only in notchAgentIdentityMark)"
    )
    XCTAssertTrue(source.contains("notchAgentIdentityMark(\n            provider: pill.providerIdentity,"))
    XCTAssertTrue(
      source.contains(
        "let rowWidth = max(\n        0,\n        min(\n          width - NotchAgentStackMetrics.listHorizontalInset * 2,\n          FloatingControlBarWindow.notchExpandedWidth - NotchAgentStackMetrics.listHorizontalInset * 2))"
      ))
    XCTAssertTrue(source.contains("static let listHorizontalInset: CGFloat = 12"))
    XCTAssertTrue(source.contains("static let listRowLeadingPadding: CGFloat = 12"))
    XCTAssertTrue(source.contains("GeometryReader { geometry in"))
    XCTAssertTrue(source.contains("notchHiddenCenterWidth: notchHiddenCenterWidth"))
    XCTAssertTrue(source.contains("notchSideWidth: notchSideWidth"))
    XCTAssertTrue(
      source.contains("let rowRevealProgress = NotchAgentStackMetrics.smoothStep((progress - 0.38) / 0.62)"))
    XCTAssertTrue(source.contains("ForEach(Array(pills.enumerated()), id: \\.offset)"))
    XCTAssertTrue(source.contains(".position(orbCenter)"))
    XCTAssertFalse(source.contains("quadraticBezier(\n                        from: ringPoint"))
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
    XCTAssertFalse(
      source.contains(".animation(.spring(response: 0.18, dampingFraction: 0.9), value: shouldShowNotchHoverMenu)"))
    XCTAssertTrue(source.contains(".transition(.identity)"))
    XCTAssertTrue(
      source.contains(
        "            notchOmiChatRow\n              .frame(width: notchHoverRowWidth, height: FloatingControlBarWindow.notchAgentListRowHeight)"
      ))
    XCTAssertTrue(
      source.contains(".allowsHitTesting(!shouldUseOmiChatOverlayHitTarget && notchSwitcherProgress > 0.6)"))
    XCTAssertTrue(
      source.contains(
        "          notchOmiChatOverlayHitTarget\n            .frame(width: notchHoverRowWidth, height: FloatingControlBarWindow.notchAgentListRowHeight)"
      ))
    XCTAssertTrue(source.contains(".offset(y: notchChromeHeight)"))
    XCTAssertTrue(source.contains(".zIndex(2)"))
    XCTAssertTrue(source.contains("height: notchHoverMenuHeight - FloatingControlBarWindow.notchAgentListRowHeight"))
    XCTAssertTrue(source.contains("state.present(.agent(pill.id))"))
    XCTAssertTrue(source.contains("private let agentChatSwitchTransition = Animation.easeOut(duration: 0.10)"))
    XCTAssertTrue(source.contains("if state.conversationSurface == .agent(pill.id)"))
    XCTAssertTrue(source.contains("@State private var notchLogoHovering = false"))
    XCTAssertTrue(source.contains("private func setNotchLogoHovering(_ hovering: Bool)"))
    XCTAssertTrue(source.contains("private var notchAgentLogoHitTarget: some View"))
    XCTAssertTrue(source.contains("The Omi mark always belongs to the compact notch header."))
    XCTAssertTrue(source.contains("ZStack(alignment: .trailing)"))
    XCTAssertTrue(source.contains("static let logoFrameSize: CGFloat = 21"))
    XCTAssertTrue(source.contains(".frame(width: 44, height: 44)"))
    XCTAssertTrue(
      source.contains("        .onTapGesture {\n          openAgentChatsFromNotchLogo()\n        }"))
    XCTAssertTrue(source.contains("Image(systemName: \"gearshape.fill\")"))
    XCTAssertTrue(source.contains("private func openAgentChatsFromNotchLogo()"))
    XCTAssertTrue(source.contains("showAgentListFromConversation()"))
    XCTAssertTrue(source.contains("setAgentSwitcherHovering(hovering)"))
    XCTAssertFalse(source.contains("@State private var agentSwitcherPinned"))
    XCTAssertFalse(source.contains("@State private var agentSwitcherHovering"))
    XCTAssertTrue(source.contains("leaveAgentConversation()"))
    XCTAssertTrue(source.contains("Text(\"Omi Chat\")"))
    XCTAssertTrue(
      source.contains("barWindow?.resizeForActiveAgentChatPublic(pillID: pill.id, animated: !wasShowingConversation)"))
    XCTAssertTrue(source.contains(".opacity(rowRevealProgress)"))
    XCTAssertFalse(source.contains("NotchLogoPlaceholderDot(progress: logoPlaceholderProgress)"))
    XCTAssertTrue(source.contains("private var shouldUseOmiChatOverlayHitTarget: Bool"))
    XCTAssertTrue(source.contains("if state.usesNotchIsland && shouldUseOmiChatOverlayHitTarget"))
    XCTAssertTrue(source.contains("rowTopOffset: FloatingControlBarWindow.notchAgentListRowHeight"))
    XCTAssertTrue(source.contains("private var showingNotchWaveform: Bool"))
    XCTAssertTrue(source.contains("private var escToClearHint: some View"))
    XCTAssertTrue(
      source.contains("        if state.hasVisibleConversation {\n          escToClearHint\n        }"))
    XCTAssertTrue(source.contains("canClearVisibleConversation: false"))
    XCTAssertTrue(source.contains("showsHeader: false"))
    XCTAssertTrue(responseSource.contains("var showsHeader: Bool = true"))
    XCTAssertTrue(responseSource.contains("if showsHeader {"))
    XCTAssertTrue(responseSource.contains(".padding(.top, 0)"))
    XCTAssertFalse(responseSource.contains(".padding(.top, state.usesNotchIsland ? 0 : OmiSpacing.lg)"))
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
    XCTAssertTrue(
      windowSource.contains("FloatingControlBarManager.shared.cancelChat(keepVoiceAlive: keepVoiceResponseAlive)"))
    XCTAssertTrue(windowSource.contains("static func notchAgentListHeight(agentCount: Int) -> CGFloat"))
    XCTAssertTrue(windowSource.contains("+ notchAgentListBottomMargin"))
    XCTAssertTrue(windowSource.contains("static let notchActiveSideWidth: CGFloat = 42"))
    XCTAssertTrue(windowSource.contains("func resizeForAgentSwitcher(visible: Bool)"))
    XCTAssertTrue(windowSource.contains("max(collapsedBarSize.width, Self.notchExpandedWidth)"))
    XCTAssertTrue(windowSource.contains("      if state.showingAIConversation {\n        return\n      }"))
  }

  func testSpacesTransitionDoesNotReplayNotchRevealPop() throws {
    let windowSource = try floatingControlBarWindowSource()

    XCTAssertTrue(source.contains("let handoff = AgentPillsManager.floatingAgentHandoff(for: message)"))
    XCTAssertTrue(source.contains("AgentPillsManager.shared.spawnFromHandoff("))
    XCTAssertTrue(source.contains("completeVisibleAgentHandoff(\n                    handoff,\n                    pill: pill"))
    XCTAssertTrue(source.contains("completeVisibleAgentHandoff(\n                        .init(originalRequest: message, agentTask: message),\n                        pill: pill"))
    XCTAssertTrue(source.contains("let toolUseId = \"floating-agent-\\(pill.id.uuidString)\""))
    XCTAssertTrue(source.contains("name: \"spawn_agent\""))
    XCTAssertTrue(source.contains("status: .completed"))
    XCTAssertTrue(source.contains("id: \\(pill.id.uuidString)"))
    XCTAssertTrue(source.contains("completeVisibleAgentResponse("))
    XCTAssertFalse(source.contains("barWindow.closeAIConversation()"))
  }

  func testSpawnAgentToolCallOpensSubagentChat() throws {
    let responseSource = try aiResponseViewSource()
    let viewSource = try floatingControlBarViewSource()
    let chatBubbleSource = try chatBubbleSource()

    XCTAssertTrue(responseSource.contains("var onOpenAgent: ((UUID, @escaping (Bool) -> Void) -> Void)?"))
    XCTAssertTrue(
      responseSource.contains("var onOpenAgentRef: ((AgentTimelineRef, @escaping (Bool) -> Void) -> Void)? = nil"))
    XCTAssertTrue(
      responseSource.contains("            onOpenAgent: onOpenAgent,\n            onOpenAgentRef: onOpenAgentRef"))
    XCTAssertFalse(responseSource.contains("openNewlySpawnedAgentIfNeeded()"))
    XCTAssertFalse(responseSource.contains("autoOpenedSpawnedAgentIDs"))
    XCTAssertTrue(
      viewSource.contains(
        "      onOpenAgent: { agentID, completion in\n        openAgentInChat(agentID: agentID, completion: completion)"
      ))
    XCTAssertTrue(
      viewSource.contains(
        "      onOpenAgentRef: { ref, completion in\n        openAgentInChat(ref: ref, completion: completion)"))
    XCTAssertTrue(chatBubbleSource.contains("var onOpenAgent: ((UUID, @escaping (Bool) -> Void) -> Void)? = nil"))
    XCTAssertTrue(
      chatBubbleSource.contains("var onOpenAgentRef: ((AgentTimelineRef, @escaping (Bool) -> Void) -> Void)? = nil"))
    XCTAssertTrue(chatBubbleSource.contains("calls.compactMap(\\.agentOpenRef).last"))
    XCTAssertTrue(chatBubbleSource.contains("agentOpenRef: block.agentOpenRef"))
    XCTAssertTrue(chatBubbleSource.contains("Self.cleanToolName(name) == \"spawn_agent\""))
    XCTAssertTrue(chatBubbleSource.contains("Self.labeledValue(in: output, keys: [\"id\"])"))
    XCTAssertTrue(chatBubbleSource.contains("keys: [\"sessionid\", \"session_id\"]"))
    XCTAssertTrue(chatBubbleSource.contains("keys: [\"runid\", \"run_id\"]"))
    XCTAssertTrue(chatBubbleSource.contains("AgentTimelineOpenFeedback.shouldShowUnavailable(succeeded:"))
    XCTAssertTrue(
      viewSource.contains(
        "    openAgentInChat(\n      ref: AgentTimelineRef(pillId: agentID, sessionId: nil, runId: nil),\n      completion: completion"
      ))
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
    XCTAssertTrue(
      source.contains("let startHeight = max(responseHeight.initialHeight, currentResponseSurfaceHeight())"))
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
    XCTAssertTrue(
      windowSource.contains("func beginVisibleMainQuery(_ message: String, fromVoice: Bool, animated: Bool = true)"))
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
    XCTAssertTrue(agentSource.contains("pill.conversationMessages = pill.providerFallbackNotices + displayMessages"))
    XCTAssertTrue(agentSource.contains("return message.sender == .user"))
    XCTAssertTrue(agentSource.contains("|| !trimmed.isEmpty"))
    XCTAssertTrue(agentSource.contains("|| message.isStreaming"))
    XCTAssertTrue(agentSource.contains("|| !message.contentBlocks.isEmpty"))
    XCTAssertTrue(viewSource.contains("private var displayedMessages: [ChatMessage]"))
    XCTAssertTrue(
      viewSource.contains("ChatMessage(id: \"\\(pill.id.uuidString)-query\", text: pill.query, sender: .user)"))
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
    XCTAssertTrue(
      agentSource.contains("private static func removeEmptyStreamingAssistantMessages(for pill: AgentPill)"))
    XCTAssertTrue(
      agentSource.contains("private static func upsertAssistantMessage(_ message: ChatMessage, for pill: AgentPill)"))
    XCTAssertTrue(agentSource.contains("completedMessage.isStreaming = false"))
    XCTAssertTrue(agentSource.contains("pill.conversationMessages.removeAll { $0.id == aiMessage.id }"))
    XCTAssertTrue(agentSource.contains("pill.conversationMessages[index] = message"))
    XCTAssertTrue(agentSource.contains("if !aiMessage.isStreaming, Self.hasVisibleAssistantContent(aiMessage)"))
    XCTAssertTrue(agentSource.contains("pill.status = .done"))
    XCTAssertTrue(
      viewSource.contains("private func normalizedAgentMessages(_ messages: [ChatMessage]) -> [ChatMessage]"))
    XCTAssertTrue(viewSource.contains("private var hasFinalAssistantOutput: Bool"))
    XCTAssertTrue(viewSource.contains("if hasFinalAssistantOutput, !pill.status.isFinished"))
    XCTAssertTrue(
      viewSource.contains("} else if trimmed.isEmpty && message.isStreaming && message.displayResources.isEmpty {"))
    XCTAssertTrue(viewSource.contains("TypingIndicator()"))
  }

  func testSharedChatMessagesOpenAndSendFollowLatest() throws {
    let source = try chatMessagesViewSource()

    XCTAssertTrue(source.contains("On the first load of a saved conversation, follow the latest message."))
    XCTAssertTrue(
      source.contains("    scrollToBottom(proxy: proxy)\n    scheduleInitialScroll(proxy: proxy, delay: 0.05)"))
    XCTAssertTrue(source.contains("scheduleInitialScroll(proxy: proxy, delay: 0.18)"))
    XCTAssertTrue(source.contains("scheduleInitialScroll(proxy: proxy, delay: 0.45)"))
    XCTAssertTrue(source.contains("private func handleViewportSizeChange(_ size: CGSize, proxy: ScrollViewProxy)"))
    XCTAssertTrue(source.contains(".background(viewportResizeDetector(proxy: proxy))"))
    XCTAssertTrue(
      source.contains(
        "    scrollMode = .followingBottom\n    hasActivityBelow = false\n    userIsScrolling = false"))
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
    XCTAssertTrue(
      scrollSource.contains("private func handleViewportSizeChange(_ size: CGSize, proxy: ScrollViewProxy)"))
    XCTAssertTrue(scrollSource.contains("scheduleSettledBottomFollow(proxy: proxy)"))
    XCTAssertTrue(scrollSource.contains("for delay in [0.05, 0.16, 0.32]"))
    XCTAssertFalse(viewSource.contains("private func agentChatViewportResizeDetector"))
    XCTAssertFalse(viewSource.contains("private func scrollToBottomSettled(_ proxy: ScrollViewProxy)"))
  }

  func testActiveSubagentChatDoesNotDependOnMainChatHeight() throws {
    let viewSource = try floatingControlBarViewSource()
    let windowSource = try floatingControlBarWindowSource()

    XCTAssertTrue(
      viewSource.contains(
        "barWindow?.resizeForActiveAgentChatPublic(pillID: pill.id, animated: !wasShowingConversation)"))
    XCTAssertTrue(
      windowSource.contains("func resizeForActiveAgentChatPublic(pillID: UUID? = nil, animated: Bool = false)"))
    XCTAssertTrue(windowSource.contains("height: max(responseHeight.initialHeight, currentResponseSurfaceHeight())"))
    XCTAssertTrue(
      windowSource.contains("setupResponseHeightObserver(for: surface, maxHeight: responseHeight.maxHeight)"))
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

  func testFinishedPillSurvivesAnActiveRuntimeSnapshotRefresh() {
    XCTAssertFalse(
      AgentPillsManager.shouldRemoveRenderedProjection(
        status: .done,
        isPolling: false,
        isSeenInRuntimeSnapshot: false,
        hasLocalTransientState: false
      )
    )
    XCTAssertFalse(
      AgentPillsManager.shouldRemoveRenderedProjection(
        status: .running,
        isPolling: true,
        isSeenInRuntimeSnapshot: false,
        hasLocalTransientState: false
      )
    )
    XCTAssertTrue(
      AgentPillsManager.shouldRemoveRenderedProjection(
        status: .running,
        isPolling: false,
        isSeenInRuntimeSnapshot: false,
        hasLocalTransientState: false
      )
    )
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
    XCTAssertTrue(hubSource.contains("RealtimeNativeAudioScheduleFailureAction.decide("))
    XCTAssertTrue(hubSource.contains("VoiceTurnCoordinator.shared.noteOutputProgress(lease)"))
    XCTAssertTrue(hubSource.contains("responseGlowGate.markPlaybackActive(lease: lease)"))
    XCTAssertFalse(hubSource.contains("pcmPlayer?.playbackEpoch ??"))
    XCTAssertFalse(hubSource.contains("audioReceivedThisTurn = true\n    // If PTT muted music/system output"))
  }

  func testVoiceHandoffCloseDoesNotCancelAnAdmittedPTTTurn() throws {
    XCTAssertTrue(FloatingConversationCloseIntent.userDismissal.cancelsInFlightWork)
    XCTAssertFalse(FloatingConversationCloseIntent.voiceHandoff.cancelsInFlightWork)

    // omi-test-quality: source-inspection -- static contract: the AppKit voice handoff passes the non-cancelling intent.
    let source = try floatingControlBarWindowSource()
    XCTAssertTrue(source.contains("window.closeAIConversation(intent: .voiceHandoff)"))
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
    XCTAssertTrue(source.contains("var reducerNativePlaybackActive: Bool"))
    XCTAssertTrue(source.contains("let voicePlaybackActive = FloatingBarVoicePlaybackService.shared.isSpeaking"))
    XCTAssertTrue(
      source.contains("let bargeIn = providerResponseInFlight || reducerNativePlaybackActive || voicePlaybackActive"))
    XCTAssertTrue(source.contains("if bargeIn {\n      pcmPlayer?.stop()"))
    XCTAssertTrue(source.contains("audioReceivedThisTurn = true\n    realtimePlaybackEpoch = pcmPlayer.playbackEpoch"))
    XCTAssertTrue(source.contains("var realtimePlaybackEpoch = 0"))
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
    XCTAssertTrue(hubSource.contains("var sessionAuth: HubAuth?"))
    let inputAdmissionSource = try realtimeHubInputAdmissionSource()
    XCTAssertTrue(inputAdmissionSource.contains("struct RealtimeReplacementAudioBuffer"))
    XCTAssertTrue(hubSource.contains("var replacementAudioBuffer: RealtimeReplacementAudioBuffer?"))
    XCTAssertTrue(hubSource.contains("func commitTurn() -> RealtimeHubCommitResult"))
    XCTAssertTrue(hubSource.contains("func restartSessionForBargeIn("))
    XCTAssertTrue(hubSource.contains("interruptedTurnTask: Task<InterruptedTurnPayload?, Never>?"))
    XCTAssertTrue(
      hubSource.contains("case .ephemeral:\n            self.remintReplacementSessionForBargeIn(provider: provider)"))
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
    XCTAssertFalse(hubSource.contains("ScreenCaptureManager.captureScreenJPEG"))
    XCTAssertTrue(hubSource.contains("effect: { [currentEvidence] in [currentEvidence] }"))
    XCTAssertTrue(hubSource.contains("authorizedRealtimeScreenshotImages[command.invocationID] = attachment"))
    XCTAssertTrue(hubSource.contains("screenshotToolResultTextForCurrentProvider(attachment: attachment)"))
    XCTAssertTrue(sessionSource.contains("case .openai:"))
    XCTAssertTrue(sessionSource.contains("case .gemini:"))
    XCTAssertTrue(sessionSource.contains("static func geminiToolResponse("))
    XCTAssertTrue(sessionSource.contains("\"parts\""))
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
    XCTAssertTrue(
      sessionSource.contains("bufferTextInput(text, logLabel: logLabel, reason: \"no open activity window\")"))
    XCTAssertTrue(sessionSource.contains("private func flushPendingTextInputs()"))
    XCTAssertTrue(sessionSource.contains("private func sendTextInputNow(_ text: String, logLabel: String)"))
    XCTAssertFalse(hubSource.contains("turnGeneration"))
    XCTAssertTrue(hubSource.contains("captureInterruptedTurnPayloadIfNeeded()"))
    XCTAssertTrue(hubSource.contains("completeBargeInReplacementAfterContinuity("))
    XCTAssertTrue(hubSource.contains("beginContextFreshInputPreparation("))
    XCTAssertTrue(hubSource.contains("finishContextFreshInputOnCurrentSession()"))
    XCTAssertTrue(hubSource.contains("case .replaceSession:"))
    XCTAssertTrue(
      hubSource.contains("replace the connection and let the fresh session buffer this new turn while it opens"))
    XCTAssertTrue(hubSource.contains("case .cancelInSession:"))
    XCTAssertTrue(hubSource.contains("barge-in — stopping local playback tail"))
    XCTAssertTrue(hubSource.contains("if !deferredFreshSessionContextPrefetch"))
    XCTAssertTrue(hubSource.contains("interrupting: providerResponseInFlight"))
    XCTAssertFalse(hubSource.contains("attachGeminiScreenFrameAfterActivityStartIfNeeded"))
    XCTAssertTrue(hubSource.contains("session?.cancelActiveResponse()"))
    XCTAssertTrue(hubSource.contains("func isCurrentSession(_ source: RealtimeHubSession) -> Bool"))
    XCTAssertTrue(hubSource.contains("guard isCurrentSession(source) else { return }"))
    XCTAssertTrue(hubSource.contains("func sendToolResultIfCurrent("))
    XCTAssertFalse(hubSource.contains("self.session?.sendToolResult(callId: callId"))
    XCTAssertTrue(sessionSource.contains("delegate.hubDidReceiveAudio(pcm, identity: identity, source: self)"))
    XCTAssertTrue(sessionSource.contains("guard isCurrentOpenAIResponseEvent(e) else"))
    XCTAssertTrue(sessionSource.contains("private var openAIResponseCreatePending = false"))
    XCTAssertTrue(
      sessionSource.contains(
        "guard !openAIResponseCreatePending, let expected = openAIActiveResponseID else { return false }"))
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
      apiSource.contains(
        "throw CredentialHealthError.backendTransient(statusCode: nil, message: error.localizedDescription)"),
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
      hubSource.contains(
        "if case .providerAuthFailed = credentialFailureClass {\n      if aliveFor < 10, failoverToAlternateProvider(reason: \"auth\") { return }"
      ),
      "Provider auth failures should try alternate provider before stopping reconnect")
    XCTAssertTrue(
      hubSource.contains(
        "if case .providerQuotaExceeded = credentialFailureClass {\n      if failoverToAlternateProvider(reason: \"quota\") { return }"
      ),
      "Provider quota failures should try alternate provider regardless of socket age")
    XCTAssertTrue(
      hubSource.contains("let shouldRedactProviderMessage: Bool"),
      "Credential close logs must redact raw provider auth/quota payloads")
    XCTAssertTrue(
      hubSource.contains("func shouldFailoverToAlternate(for failureClass: CredentialFailureClass?) -> Bool"),
      "Provider switching must be centralized and limited to stable credential/quota failures")
    XCTAssertFalse(
      hubSource.contains("if aliveFor < 10, failoverToAlternateProvider() { return }\n    // Re-warm"),
      "Transient fast closes should not switch voice providers")
  }

  func testSpeechSynthesizerDidCancelClearsGlow() throws {
    let source = try floatingBarVoicePlaybackServiceSource()

    // The single voice playback service owns AVSpeechSynthesizerDelegate and
    // must clear glow only after proving that the callback belongs to the
    // utterance that currently owns playback.
    XCTAssertTrue(
      source.contains(
        "func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance)"))
    XCTAssertTrue(source.contains("guard self.completeSystemSpeechIfCurrent(utteranceBox.value) else { return }"))
    XCTAssertTrue(source.contains("self.clearFloatingPillResponseGlowIfIdle()"))
  }

  func testVoiceResponseGlowTriggersCompactResizeOnLegacyDisplays() throws {
    let source = try floatingControlBarWindowSource()

    // The glow observer must trigger a resize to the glow-adjusted collapsed
    // size on legacy displays, not just record the boolean — and it collapses
    // to the canonical pill frame so drift cannot accumulate.
    XCTAssertTrue(source.contains("guard !self.notchModeEnabled else { return }"))
    XCTAssertTrue(
      source.contains("self.resizeToFrame(self.canonicalCollapsedPillFrame(), makeResizable: false, animated: false)"))
  }

  func testStartupRevalidatesDisplayMetadataForAutomaticNotchMode() throws {
    let source = try floatingControlBarWindowSource()

    // Some MacBook notch safe-area metadata can arrive after the floating bar
    // window is created. Startup retries should use the same layout path as
    // display changes so users do not need to change screen resolution first.
    XCTAssertTrue(
      source.contains("private static let startupDisplayRevalidationDelays: [TimeInterval] = [0.2, 0.8, 2.0]"))
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
    XCTAssertTrue(viewSource.contains("          onBackToAgentRows: {\n            showAgentListFromConversation()"))
    XCTAssertTrue(
      viewSource.contains(
        "  private func showAgentListFromConversation() {\n    (window as? FloatingControlBarWindow)?.leaveAgentConversation() ?? onCloseAI()\n  }"
      ))
    XCTAssertTrue(windowSource.contains("func leaveAgentConversation()"))
    XCTAssertTrue(
      windowSource.contains("    if !AgentPillsManager.shared.pills.isEmpty {\n      showAgentRowsFromConversation()")
    )
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

    XCTAssertTrue(
      bodySource.contains(
        "if state.usesNotchIsland || state.showingAIConversation || state.isNotchHoverMenuVisible {\n        unifiedFloatingSurface"
      ))
    XCTAssertTrue(viewSource.contains("private var unifiedFloatingSurface: some View"))
    XCTAssertTrue(viewSource.contains("      if state.showingAIConversation {\n        conversationView"))
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
    XCTAssertTrue(
      agentSource.contains(
        "var finalMessage = currentAssistantMessage(for: pill) ?? ChatMessage(text: statusText, sender: .ai)"))
    XCTAssertTrue(agentSource.contains("upsertAssistantMessage(finalMessage, for: pill)"))
    XCTAssertTrue(
      agentSource.contains(
        "let failureText = AgentFailureTranscriptFormatter.transcriptText(for: errorText) ?? \"Failed: \\(errorText)\"")
    )
  }

  func testFloatingPillDoesNotTreatMissingTerminalProjectionAsSuccess() throws {
    let source = try agentPillSource()

    XCTAssertTrue(source.contains("Agent ended before reporting a final result"))
    XCTAssertFalse(
      source.contains("pill.latestActivity = pill.latestActivity.isEmpty ? \"Finished\" : pill.latestActivity"))
  }

  func testFallbackFailurePathsRecordCompletionTime() throws {
    let source = try agentPillSource()

    XCTAssertTrue(
      source.contains(
        "      pill.status = .failed(errorText)\n      pill.latestActivity = errorText\n      pill.completedAt = Date()"
      ))
    XCTAssertTrue(
      source.contains(
        "      pill.status = .failed(\"Agent ended before reporting a final result\")\n      pill.completedAt = Date()")
    )
    XCTAssertTrue(source.contains("Self.ensureFailureMessage(errorText, for: pill)"))
    XCTAssertTrue(
      source.contains("Self.ensureFailureMessage(\"Agent ended before reporting a final result\", for: pill)"))
    XCTAssertTrue(source.contains("ensureFailureMessage(message, for: pill)"))
    XCTAssertTrue(source.contains("projection.failure?.displayMessage ?? projection.errorMessage ?? \"Agent failed\""))
    XCTAssertTrue(source.contains("AgentFailureTranscriptFormatter.transcriptText(for: errorText)"))
    XCTAssertTrue(source.contains("ChatMessage(text: failureText, sender: .ai)"))
  }

  func testLateMessageActivityCannotOverwriteTerminalPillStatus() throws {
    let source = try agentPillSource()
    let statusStoreSource = try agentRuntimeStatusStoreSource()

    XCTAssertTrue(source.contains("    if pill.status.isFinished {\n      return\n    }"))
    XCTAssertTrue(source.contains("if pill.status.isFinished, pill.viewedAt != nil"))
    XCTAssertTrue(source.contains("let activity = Self.describeActivity(for: aiMessage)"))
    XCTAssertFalse(source.contains("AgentRuntimeStatusStore.shared.recordPresentationCompletion("))
    XCTAssertFalse(statusStoreSource.contains("func recordPresentationCompletion("))
    XCTAssertFalse(statusStoreSource.contains("func recordLocalSuccess("))
    XCTAssertTrue(
      statusStoreSource.contains(
        "if !terminal, projectionsBySurface[surface.key]?.status.isTerminal == true {\n      return\n    }"))
  }

  func testStoppedPillIgnoresLateNonCancellationProjection() throws {
    let source = try agentPillSource()

    XCTAssertTrue(source.contains("if pill.status == .stopped && projection.status != .cancelled"))
    XCTAssertTrue(source.contains("if pill.status.isFinished && !projection.status.isTerminal"))
    XCTAssertTrue(source.contains("switch projection.status"))
  }

  func testProviderStartupFallbackChainOrderAndCap() {
    // Remaining available providers in fixed [openclaw, hermes, codex] order,
    // ending with the Omi default agent (nil).
    XCTAssertEqual(
      AgentPillsManager.fallbackChain(afterFailed: [.openclaw], available: [.openclaw, .hermes, .codex]),
      [.hermes, .codex, nil])

    // The fixed order wins regardless of the order of `available`.
    XCTAssertEqual(
      AgentPillsManager.fallbackChain(afterFailed: [.hermes], available: [.codex, .openclaw, .hermes]),
      [.openclaw, .codex, nil])

    // Unavailable providers are never part of the chain.
    XCTAssertEqual(
      AgentPillsManager.fallbackChain(afterFailed: [.hermes], available: [.hermes, .codex]),
      [.codex, nil])

    // Nothing left → the default agent is the only remaining attempt.
    XCTAssertEqual(
      AgentPillsManager.fallbackChain(afterFailed: [.codex], available: [.codex]),
      [nil])

    // Attempt cap: requested + at most 2 directed fallbacks + default.
    XCTAssertEqual(
      AgentPillsManager.fallbackChain(
        afterFailed: [.openclaw, .hermes, .codex],
        available: [.openclaw, .hermes, .codex]),
      [nil])
  }

  func testProviderStartupFallbackNeverRunsAfterTaskOutput() throws {
    let source = try agentPillSource()

    // HARD SAFETY RULE: fallback must be gated on the failed attempt having
    // produced no output — re-running a partially-executed brief could repeat
    // side effects (e.g. double-send messages).
    XCTAssertTrue(source.contains("guard !pill.hasProducedTaskOutput else { return false }"))
    XCTAssertTrue(source.contains("HARD SAFETY RULE: never fall back once the failed attempt produced"))
    // The output flag flips as soon as any assistant text or tool/thinking
    // content block streams in, and startup fallback only applies to initial
    // runs — follow-up turns must never retry the brief on another provider.
    XCTAssertTrue(source.contains("pill.markTaskOutputProduced()"))
    // The live hook: canonical-run inspections route `failed` runs through the
    // fallback gate before committing a terminal failure; timeouts and
    // orphaned runs never qualify.
    XCTAssertTrue(source.contains("if inspection.status == \"failed\","))
    XCTAssertTrue(
      source.contains("attemptProviderStartupFallback(for: pill, errorText: startupFailure.displayMessage)"))
    // The failed attempt's terminal projection is cleared eagerly so a stray
    // publish can't re-fail the retried pill.
    XCTAssertTrue(source.contains("AgentRuntimeStatusStore.shared.beginRequest("))
    // The switch is surfaced to the user in the pill chat + activity line.
    XCTAssertTrue(source.contains("failed to start — continuing with"))
    XCTAssertTrue(source.contains("AgentPill: provider fallback"))
  }

  func testProviderStartupFallbackRequiresStructuredStartupFailure() {
    // ALLOWLIST gate: only a terminal .failed run whose structured failure
    // the Node runtime tagged phase == "startup" (provably pre-execution) is
    // eligible for a retry on another provider.
    XCTAssertNotNil(
      AgentPillsManager.startupFallbackFailure(
        projection: fallbackProjection(status: .failed, failure: runtimeFailure(phase: "startup"))))

    // Execution-phase or untagged failures must surface as terminal failures
    // — the adapter may already have executed side-effecting work.
    XCTAssertNil(
      AgentPillsManager.startupFallbackFailure(
        projection: fallbackProjection(status: .failed, failure: runtimeFailure(phase: "execution"))))
    XCTAssertNil(
      AgentPillsManager.startupFallbackFailure(
        projection: fallbackProjection(status: .failed, failure: runtimeFailure(phase: nil))))

    // Timeouts and orphaned runs never fall back: the remote adapter may
    // still be executing, so a retry would run the brief concurrently twice.
    XCTAssertNil(
      AgentPillsManager.startupFallbackFailure(
        projection: fallbackProjection(status: .timedOut, failure: runtimeFailure(phase: "startup"))))
    XCTAssertNil(
      AgentPillsManager.startupFallbackFailure(
        projection: fallbackProjection(status: .orphaned, failure: runtimeFailure(phase: "startup"))))

    // No projection, no structured failure, or a successful run (e.g. a
    // tool-only run with empty finalText) is never a fallback candidate —
    // "ended with no error and no result" is a normal terminal failure now.
    XCTAssertNil(AgentPillsManager.startupFallbackFailure(projection: nil))
    XCTAssertNil(
      AgentPillsManager.startupFallbackFailure(
        projection: fallbackProjection(status: .failed, failure: nil)))
    XCTAssertNil(
      AgentPillsManager.startupFallbackFailure(
        projection: fallbackProjection(status: .succeeded, failure: runtimeFailure(phase: "startup"))))
  }

  func testProviderStartupFallbackGateSourceUsesStructuredClassification() throws {
    let source = try agentPillSource()
    let failureSource = try agentRuntimeFailureSource()

    // complete() feeds the projection into the pure structured gate; the old
    // string-based classifier (which treated empty finalText and any
    // provider.errorMessage as a startup failure) must stay deleted.
    XCTAssertTrue(source.contains("let startupFailure = Self.startupFallbackFailure("))
    XCTAssertTrue(source.contains("projection.status == .failed,"))
    XCTAssertTrue(source.contains("failure.isStartupPhase"))
    XCTAssertFalse(source.contains("startupFailureText"))
    XCTAssertFalse(source.contains("return \"Agent ended before reporting a final result\""))
    // The phase tag rides the structured failure payload from the Node
    // runtime (agent/src/runtime/failures.ts) into Swift.
    XCTAssertTrue(failureSource.contains("let phase: String?"))
    XCTAssertTrue(failureSource.contains("payload[\"phase\"] as? String"))
    XCTAssertTrue(failureSource.contains("var isStartupPhase: Bool { phase == \"startup\" }"))
  }

  func testProviderStartupFallbackTearsDownDisplacedAttempt() throws {
    let source = try agentPillSource()

    // Installing a retry attempt must first cancel the displaced attempt's
    // run task so the old poll loop can't keep applying the dead run's
    // terminal state to the pill.
    XCTAssertTrue(
      source.contains(
        """
        // A retry displaces the failed attempt's still-registered run task;
                // the initial spawn has nothing to displace.
                runTasksByPill[pill.id]?.cancel()
        """))
    // The retry spawns a fresh canonical session/run — the failed attempt's
    // ids are dropped so follow-ups queue for the new run instead of
    // targeting the dead session.
    XCTAssertTrue(
      source.contains(
        """
        canonicalSessionId = nil
                canonicalRunId = nil
                canonicalAttemptId = nil
        """))
  }

  func testProviderStartupFallbackRetryReusesCanonicalSpawnPath() throws {
    let source = try agentPillSource()

    // A retry re-enters the same canonical spawn wiring as the initial
    // attempt and reads the pill's CURRENT harness override, so it lands on
    // the provider the fallback moved the pill to.
    XCTAssertTrue(source.contains("private func startProviderAttempt(for pill: AgentPill)"))
    XCTAssertTrue(source.contains("let bridgeHarnessOverride = pill.bridgeHarnessOverride"))
    XCTAssertTrue(source.contains("startProviderAttempt(for: pill)"))
    // Provider-switch notices stay pinned above the brief when the retry's
    // accept rebuilds the transcript.
    XCTAssertTrue(
      source.contains(
        "pill.conversationMessages = pill.providerFallbackNotices + [ChatMessage(text: pill.query, sender: .user)]"))
  }

  func testPillSnapshotExposesCurrentProvider() throws {
    // After a startup fallback the hub must be able to tell which provider a
    // pill actually landed on — the snapshot carries it explicitly.
    let snapshot = AgentPillsManager.Snapshot(
      id: "pill-1",
      title: "Test",
      status: "running",
      provider: "codex",
      latestActivity: "Working…",
      query: "do the thing",
      createdAt: "2026-07-02T00:00:00Z",
      completedAt: nil)
    let data = try JSONEncoder().encode(snapshot)
    let json = try XCTUnwrap(String(data: data, encoding: .utf8))
    XCTAssertTrue(json.contains("\"provider\":\"codex\""))

    let source = try agentPillSource()
    XCTAssertTrue(source.contains("provider: pill.currentDirectedProvider?.rawValue ?? \"omi\""))
  }

  private func runtimeFailure(phase: String?) -> AgentRuntimeFailure {
    AgentRuntimeFailure(
      code: "adapter_process_exited",
      userMessage:
        "Codex is not available. Make sure Codex and the codex-acp bridge are installed first, then try again.",
      technicalMessage: nil,
      source: "adapter_process",
      adapterId: "codex",
      provider: nil,
      retryable: false,
      phase: phase)
  }

  private func fallbackProjection(
    status: AgentRunProjectionStatus,
    failure: AgentRuntimeFailure?
  ) -> AgentRunProjection {
    AgentRunProjection(
      surface: .floatingPill(pillId: UUID()),
      sessionId: nil,
      runId: nil,
      attemptId: nil,
      adapterSessionId: nil,
      status: status,
      statusText: nil,
      errorMessage: failure?.displayMessage,
      failure: failure,
      updatedAt: Date(),
      completedAt: Date(),
      costUsd: nil,
      inputTokens: nil,
      outputTokens: nil)
  }

  private func agentRuntimeFailureSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeFailure.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  func testDirectedProviderPillsDoNotForwardClaudeModelOverrides() throws {
    let source = try agentPillSource()
    let logoMarkSource = try agentProviderLogoMarkSource()
    let viewSource = try floatingControlBarViewSource()

    XCTAssertTrue(source.contains("let modelForSpawn =\n      bridgeHarnessOverride == nil"))
    XCTAssertTrue(source.contains("model: modelForSpawn"))
    XCTAssertTrue(source.contains("model: pill.bridgeHarnessOverride == nil ? pill.model : nil"))
    XCTAssertTrue(source.contains("harnessMode: bridgeHarnessOverride"))
    XCTAssertTrue(viewSource.contains("AgentProviderLogoMark("))
    XCTAssertTrue(viewSource.contains("provider: pill.providerIdentity"))
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
    XCTAssertTrue(logoMarkSource.contains("        statusColor\n          .mask("))
  }

  func testCanonicalPillLifecycleQueuesFollowUpsAndCancelsActiveDismissals() throws {
    let source = try agentPillSource()

    XCTAssertTrue(source.contains("private var pendingFollowUpsByPill: [UUID: [PendingAgentFollowUp]] = [:]"))
    XCTAssertTrue(source.contains("private struct PendingAgentFollowUp"))
    XCTAssertTrue(
      source.contains(
        "pendingFollowUpsByPill[pill.id, default: []].append(PendingAgentFollowUp(text: text, attachments: attachments))"
      ))
    XCTAssertTrue(source.contains("Queued follow-up until the agent starts"))
    XCTAssertTrue(source.contains("Queued follow-up until the current run stops"))
    XCTAssertTrue(
      source.contains("let queuedFollowUps = self.pendingFollowUpsByPill.removeValue(forKey: pill.id) ?? []"))
    XCTAssertTrue(source.contains("text: queuedFollowUps.map(\\.text).joined(separator: \"\\n\\n\")"))
    XCTAssertTrue(source.contains("attachments: queuedFollowUps.flatMap(\\.attachments)"))
    XCTAssertTrue(
      source.contains(
        "switch await self.cancelActiveRunBeforeFollowUp(runId: activeRunId, pill: pill, generation: generation)"))
    XCTAssertTrue(
      source.contains(
        "          case .cancelled:\n            completion?(.providerFailed)\n            return"))
    XCTAssertTrue(source.contains("private enum ActiveRunCancellationResult"))
    XCTAssertTrue(
      source.contains(
        "private func cancelActiveRunBeforeFollowUp(runId: String, pill: AgentPill, generation: Int) async\n    -> ActiveRunCancellationResult"
      ))
    XCTAssertTrue(source.contains("let shouldCancelRun = pill?.status.isFinished == false"))
    XCTAssertTrue(source.contains("pendingFollowUpsByPill[pillID] = nil"))
    XCTAssertTrue(source.contains("DesktopCoordinatorService.shared.cancelAgentRun(runId: runId)"))
    XCTAssertTrue(source.contains("AgentRuntimeStatusStore.shared.recordLocalFailure("))
  }

  func testProviderMarkRoutingIsCentralized() throws {
    let routingSource = try agentRuntimeRoutingSource()
    XCTAssertTrue(routingSource.contains("var rendersProviderMark: Bool { self != nil }"))

    let viewSource = try floatingControlBarViewSource()
    XCTAssertTrue(viewSource.contains("pill.providerIdentity.rendersProviderMark"))
    XCTAssertTrue(viewSource.contains("if provider.rendersProviderMark {"))
  }

  func testDirectedProviderLogoAssetsUseSingleTemplateMasks() throws {
    let hermes = try logoMaskStats("hermes_logo_flat")
    XCTAssertEqual(hermes.width, 256)
    XCTAssertEqual(hermes.height, 256)
    XCTAssertEqual(hermes.transparentCorners, 4)
    XCTAssertGreaterThan(
      hermes.boundsWidth, 180, "Hermes must keep the winged caduceus, not a narrow replacement glyph.")
    XCTAssertGreaterThan(hermes.boundsHeight, 170)
    XCTAssertEqual(hermes.coloredPixels, 0, "Hermes row mark must be a template mask so status color owns identity.")

    let openClaw = try logoMaskStats("openclaw_logo_flat")
    XCTAssertEqual(openClaw.width, 180)
    XCTAssertEqual(openClaw.height, 180)
    XCTAssertEqual(openClaw.transparentCorners, 4)
    XCTAssertGreaterThan(
      openClaw.boundsWidth, 150, "OpenClaw must keep the round mascot silhouette, not an arrow glyph.")
    XCTAssertGreaterThan(openClaw.boundsHeight, 130)
    XCTAssertGreaterThan(
      openClaw.transparentPixelsInsideBounds, 500, "Eye holes must remain transparent in the provider mark.")
    XCTAssertEqual(
      openClaw.coloredPixels, 0, "OpenClaw row mark must be a template mask so status color owns identity.")
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
    XCTAssertTrue(
      loggerSource.contains("if !isDevBuild {\n    let breadcrumb = Breadcrumb(level: .info, category: \"app\")"))
    XCTAssertTrue(loggerSource.contains("guard !isDevBuild else { return }"))
  }

  func testFloatingVoicePlaybackIgnoresStaleBargeInCallbacks() throws {
    let source = try floatingBarVoicePlaybackServiceSource()

    XCTAssertTrue(source.contains("private var playbackGeneration: UInt64 = 0"))
    XCTAssertTrue(source.contains("private var activeSystemSpeechToken: SystemSpeechToken?"))
    XCTAssertTrue(source.contains("if activeSystemSpeechToken != nil { return true }"))
    XCTAssertTrue(source.contains("activeSystemSpeechToken = SystemSpeechToken("))
    XCTAssertTrue(source.contains("playbackGeneration &+= 1"))
    XCTAssertTrue(source.contains("let generation = playbackGeneration"))
    XCTAssertTrue(source.contains("guard self.playbackGeneration == generation else { return }"))
    XCTAssertTrue(source.contains("guard self.audioPlayer === player else { return }"))
    XCTAssertTrue(
      source.contains("speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance)"))
    XCTAssertTrue(source.contains("guard self.completeSystemSpeechIfCurrent(utteranceBox.value) else { return }"))
  }

  func testFloatingBarResizeCoalescesNoopFrames() throws {
    let source = try floatingControlBarWindowSource()

    XCTAssertTrue(source.contains("private static let frameNoopEpsilon: CGFloat = 0.5"))
    XCTAssertTrue(source.contains("private var pendingFrameAnimationTarget: NSRect?"))
    XCTAssertTrue(source.contains("let wasResizable = styleMask.contains(.resizable)"))
    XCTAssertTrue(source.contains("let alreadyAnimatingToTarget =\n      pendingFrameAnimationTarget.map"))
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
              - min(color.redComponent, color.greenComponent, color.blueComponent) > 0.08
          {
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

  private func agentRuntimeProcessSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    // omi-test-quality: source-inspection -- static contract: runtime bridge wiring stays owned by the process boundary.
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func realtimeHubControllerSource() throws -> String {
    try RealtimeHubControllerSourceTestSupport.moduleSource(testFilePath: #filePath)
  }

  private func realtimeHubInputAdmissionSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/RealtimeHubInputAdmission.swift")
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
