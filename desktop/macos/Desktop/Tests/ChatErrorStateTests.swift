import XCTest

@testable import Omi_Computer

/// Coverage for the catch-block-to-card pipeline (lightweight — full
/// ChatProvider integration tests are out of scope here since the
/// provider is heavy to construct in isolation).
final class ChatErrorStateMappingTests: XCTestCase {

  /// Every `ChatErrorRecoveryAction` must be *reachable* — produced by
  /// some `ChatErrorState.primaryRecovery`. Guards against dead recovery
  /// actions: an enum case with a handler in ChatProvider/ChatErrorCard
  /// but no state that ever yields it. (Relies on `CaseIterable`.)
  func testEveryRecoveryActionIsReachableFromSomeState() {
    let allStates: [ChatErrorState] = [
      .authRequired,
      .timeout(toolName: nil),
      .bridgeUnavailable(reason: .nodeMissing),
      .bridgeUnavailable(reason: .runtimeMissing),
      .bridgeUnavailable(reason: .crashed),
      .bridgeUnavailable(reason: .unknown),
      .interrupted,
      .noDataFound,
    ]
    let reachable = Set(allStates.map { $0.primaryRecovery })
    XCTAssertEqual(
      reachable, Set(ChatErrorRecoveryAction.allCases),
      "Every ChatErrorRecoveryAction must be produced by some state's primaryRecovery — unreachable actions are dead code."
    )
  }

  /// The catch-block prefers ChatErrorState over the legacy
  /// errorMessage banner ONLY when the BridgeError maps. Unmappable
  /// errors still surface via errorMessage so no error path becomes
  /// invisible during the migration. This test locks which cases
  /// map and which don't — changing the factory's mapping requires
  /// updating this test, which surfaces the user-visible impact.
  func testFactoryMappabilityIsStableUnderRefactor() {
    XCTAssertNil(ChatErrorState.from(BridgeError.stopped))
    XCTAssertNotNil(ChatErrorState.from(BridgeError.timeout))
    XCTAssertNotNil(ChatErrorState.from(BridgeError.notRunning))
    XCTAssertNotNil(ChatErrorState.from(BridgeError.restarting))
    XCTAssertNotNil(ChatErrorState.from(BridgeError.authMissing))

    // These must NOT map — they fall through to the legacy banner.
    XCTAssertNil(ChatErrorState.from(BridgeError.encodingError))
    XCTAssertNil(ChatErrorState.from(BridgeError.agentError("foo")))
    XCTAssertNil(ChatErrorState.from(BridgeError.requestAlreadyActive))
    XCTAssertNil(ChatErrorState.from(
      BridgeError.quotaExceeded(plan: "free", unit: "msg", used: 100, limit: 100, resetAtUnix: nil)
    ))
  }
}

final class ChatErrorStateTests: XCTestCase {

  // MARK: - Exhaustive recovery coverage

  /// Every `ChatErrorState` case must have a `primaryRecovery`. Implemented
  /// as an exhaustive switch so adding a new case here forces the
  /// implementation to provide a recovery action (compiler enforced).
  func testEveryCaseHasARecoveryAction() {
    let cases: [ChatErrorState] = [
      .authRequired,
      .timeout(toolName: nil),
      .timeout(toolName: "search"),
      .bridgeUnavailable(reason: .nodeMissing),
      .bridgeUnavailable(reason: .runtimeMissing),
      .bridgeUnavailable(reason: .crashed),
      .bridgeUnavailable(reason: .unknown),
      .interrupted,
      .noDataFound,
    ]

    for state in cases {
      // Exhaustive switch — any new case added to ChatErrorRecoveryAction
      // without being assigned here will fail to compile.
      switch state.primaryRecovery {
      case .retry, .signIn, .installRuntime, .dismiss:
        break
      }
    }

    // Spot-check the canonical mappings so a refactor that swaps recoveries
    // around fails loudly.
    XCTAssertEqual(ChatErrorState.authRequired.primaryRecovery, .signIn)
    XCTAssertEqual(ChatErrorState.timeout(toolName: nil).primaryRecovery, .retry)
    XCTAssertEqual(ChatErrorState.interrupted.primaryRecovery, .dismiss)
    XCTAssertEqual(ChatErrorState.noDataFound.primaryRecovery, .dismiss)
    XCTAssertEqual(
      ChatErrorState.bridgeUnavailable(reason: .nodeMissing).primaryRecovery,
      .installRuntime
    )
    XCTAssertEqual(
      ChatErrorState.bridgeUnavailable(reason: .runtimeMissing).primaryRecovery,
      .installRuntime
    )
    XCTAssertEqual(
      ChatErrorState.bridgeUnavailable(reason: .crashed).primaryRecovery,
      .retry
    )
    XCTAssertEqual(
      ChatErrorState.bridgeUnavailable(reason: .unknown).primaryRecovery,
      .retry
    )
  }

  // MARK: - BridgeError → ChatErrorState

  func testFromBridgeErrorMapsTimeoutToTimeout() {
    let mapped = ChatErrorState.from(.timeout)
    XCTAssertEqual(mapped, .timeout(toolName: nil))
  }

  func testFromBridgeErrorDoesNotMapStoppedToResumeCard() {
    let mapped = ChatErrorState.from(.stopped)
    XCTAssertNil(mapped)
  }

  func testFromBridgeErrorReturnsNilForUnmappableCases() {
    // These should fall through to the existing generic errorMessage banner
    // / paywall sheets rather than the new card.
    XCTAssertNil(ChatErrorState.from(.encodingError))
    XCTAssertNil(
      ChatErrorState.from(
        .quotaExceeded(
          plan: "Free", unit: "cost_usd", used: 5.0, limit: 5.0, resetAtUnix: nil)
      )
    )
    XCTAssertNil(ChatErrorState.from(.agentError("something opaque went wrong")))
    XCTAssertNil(
      ChatErrorState.from(
        .agentRuntimeFailure(
          AgentRuntimeFailure(
            code: "adapter_config_invalid",
            userMessage: "OpenClaw needs a config migration.",
            technicalMessage: nil,
            source: "adapter_process",
            adapterId: "openclaw",
            provider: nil,
            retryable: false
          )
        )
      )
    )
  }

  func testStructuredAgentRuntimeFailureKeepsUserMessage() {
    let error = BridgeError.agentRuntimeFailure(
      AgentRuntimeFailure(
        code: "adapter_config_invalid",
        userMessage: "OpenClaw needs a config migration. Run `openclaw doctor --fix`, then retry.",
        technicalMessage: "OpenClaw config is invalid",
        source: "adapter_process",
        adapterId: "openclaw",
        provider: nil,
        retryable: false
      )
    )

    XCTAssertEqual(
      error.localizedDescription,
      "OpenClaw needs a config migration. Run `openclaw doctor --fix`, then retry."
    )
  }

  // MARK: - Bridge-unavailable reason coverage

  func testBridgeUnavailableReasonsCoverNodeMissing() {
    let mapped = ChatErrorState.from(.nodeNotFound)
    XCTAssertEqual(mapped, .bridgeUnavailable(reason: .nodeMissing))
  }

  func testBridgeUnavailableReasonsCoverRuntimeMissing() {
    let mapped = ChatErrorState.from(.bridgeScriptNotFound)
    XCTAssertEqual(mapped, .bridgeUnavailable(reason: .runtimeMissing))
  }

  func testBridgeUnavailableReasonsCoverCrashed() {
    XCTAssertEqual(
      ChatErrorState.from(.processExited),
      .bridgeUnavailable(reason: .crashed)
    )
    XCTAssertEqual(
      ChatErrorState.from(.outOfMemory),
      .bridgeUnavailable(reason: .crashed)
    )
  }

  func testTypedBridgeStartFailureSurfacesARecoverableRetryCard() {
    let error = BridgeError.failedToStart(.handshakeTimedOut)
    XCTAssertEqual(
      ChatErrorState.from(error),
      .bridgeUnavailable(reason: .failedToStart(.handshakeTimedOut)))
    XCTAssertEqual(ChatErrorState.from(error)?.primaryRecovery, .retry)
    XCTAssertEqual(ChatErrorState.from(error)?.userFacingSummary, "AI took too long to start. Try again.")
  }

  func testBridgeUnavailableReasonsCoverUnknown() {
    XCTAssertEqual(
      ChatErrorState.from(.notRunning),
      .bridgeUnavailable(reason: .unknown)
    )
    XCTAssertEqual(
      ChatErrorState.from(.restarting),
      .bridgeUnavailable(reason: .unknown)
    )
  }

  // MARK: - Auth mapping

  func testFromBridgeErrorMapsAuthMissingToAuthRequired() {
    let mapped = ChatErrorState.from(.authMissing)
    XCTAssertEqual(mapped, .authRequired)
  }

  func testFromBridgeErrorMapsInvalidTokenAgentErrorToAuthRequired() {
    let mapped = ChatErrorState.from(.agentError("401 \"invalid_token\""))
    XCTAssertEqual(mapped, .authRequired)
    XCTAssertTrue(BridgeError.agentError("401 \"invalid_token\"").isSessionAuthenticationFailure)
  }

  func testFromBridgeErrorMapsUnauthorizedAgentErrorToAuthRequired() {
    let mapped = ChatErrorState.from(.agentError("Unauthorized - please sign in again"))
    XCTAssertEqual(mapped, .authRequired)
  }

  func testFromBridgeErrorMapsTokenAgentErrorToAuthRequired() {
    let mapped = ChatErrorState.from(.agentError("401 auth token rejected"))
    XCTAssertEqual(mapped, .authRequired)
  }

  func testFromBridgeErrorDoesNotMapProviderAuthFailuresToAuthRequired() {
    XCTAssertNil(ChatErrorState.from(.agentError("AI service authentication failed")))
    XCTAssertNil(ChatErrorState.from(.agentError("Anthropic provider unauthorized")))
    XCTAssertNil(ChatErrorState.from(.agentError("invalid key")))
    XCTAssertFalse(BridgeError.agentError("Anthropic provider unauthorized").isSessionAuthenticationFailure)
  }

  func testEnsureBridgeStartedMapsAuthMissingToAuthRequired() throws {
    let source = try sourceFile("Providers/ChatProvider.swift")
    XCTAssertTrue(source.contains("ChatErrorState.from(bridgeError)"))
    let range = source.range(of: "Failed to start agent bridge")
    XCTAssertNotNil(range)
    let snippet = String(source[range!.lowerBound...]).prefix(500)
    XCTAssertTrue(snippet.contains("currentError = card"))
    XCTAssertFalse(snippet.contains("\"AI not available: Please sign in"))
  }

  func testSendPreservesDraftUntilTurnIsAccepted() throws {
    let source = try sourceFile("Providers/ChatProvider.swift")
    XCTAssertTrue(source.contains("onAccepted: (@MainActor () -> Void)? = nil"))
    XCTAssertTrue(source.contains("onAccepted?()"))
    XCTAssertTrue(source.contains("self.draftRevision == submittedRevision"))
    XCTAssertTrue(source.contains("self.draftText == text else { return }"))
    XCTAssertFalse(source.contains("draftText = trimmedText"))
  }

  func testTerminationFlushesDraftsBeforeAsyncAgentShutdown() throws {
    let source = try sourceFile("Providers/ChatProvider.swift")
    let observerStart = try XCTUnwrap(source.range(of: "terminationObserver = NotificationCenter.default.addObserver"))
    let observerTail = String(source[observerStart.lowerBound...])
    let observerEnd = try XCTUnwrap(observerTail.range(of: "private var terminationObserver"))
    let observer = String(observerTail[..<observerEnd.lowerBound])
    let flush = try XCTUnwrap(observer.range(of: "ChatDraftStore.shared.flush()"))
    let asyncShutdown = try XCTUnwrap(observer.range(of: "Task { @MainActor in"))

    XCTAssertTrue(observer.contains("MainActor.assumeIsolated"))
    XCTAssertLessThan(flush.lowerBound, asyncShutdown.lowerBound)
  }

  func testSignInRecoveryRetriesAfterOAuth() throws {
    let source = try sourceFile("Providers/ChatProvider.swift")
    let range = source.range(of: "ChatErrorCard: .signIn recovery")
    XCTAssertNotNil(range)
    // Scope to the .signIn case block — stop at the next case to avoid
    // incidental matches from unrelated methods elsewhere in the file.
    let fromSignIn = String(source[range!.lowerBound...])
    let endOfCase = fromSignIn.range(of: "case .installRuntime:")
    XCTAssertNotNil(endOfCase, "expected .installRuntime case after .signIn recovery")
    let snippet = endOfCase.map { String(fromSignIn[..<$0.lowerBound]) } ?? fromSignIn
    XCTAssertTrue(snippet.contains("signInWithGoogle()"))
    XCTAssertTrue(snippet.contains("signInWithApple()"))
    XCTAssertTrue(snippet.contains("ensureBridgeStarted()"))
    XCTAssertTrue(snippet.contains("await sendMessage(prompt)"))
  }

  func testDashboardShowsChatErrorCard() throws {
    let source = try sourceFile("MainWindow/Pages/DashboardPage.swift")
    XCTAssertTrue(source.contains("dashboardChatErrorCard"))
    XCTAssertTrue(source.contains("ChatErrorCard("))
  }

  /// Static tripwire for the Home chat layout. The shared ChatErrorCard belongs to
  /// homePanelStage, below the composer; placing it inside homeChatPanel as well
  /// visibly duplicates the sign-in recovery CTA for the same ChatProvider state.
  func testDashboardHomeChatHasOneSharedErrorCardRenderSite() throws {
    let source = try sourceFile("MainWindow/Pages/DashboardPage.swift")
    let panelStart = try XCTUnwrap(source.range(of: "private func homePanelStage"))
    let chatStart = try XCTUnwrap(source.range(of: "private func homeChatPanel"))
    let connectStart = try XCTUnwrap(source.range(of: "private func homeConnectPanel"))

    let panelSource = String(source[panelStart.lowerBound..<chatStart.lowerBound])
    let chatSource = String(source[chatStart.lowerBound..<connectStart.lowerBound])

    XCTAssertEqual(
      panelSource.components(separatedBy: "dashboardChatErrorCard").count - 1,
      1,
      "Home must have one canonical error-card owner outside the chat panel."
    )
    XCTAssertFalse(
      chatSource.contains("dashboardChatErrorCard"),
      "The embedded chat panel must not render a second copy of the shared auth gate."
    )
  }

  func testFloatingBarReadsCurrentError() throws {
    let source = try sourceFile("Providers/ChatProvider.swift")
    XCTAssertTrue(source.contains("var displayErrorMessage"))
    XCTAssertTrue(source.contains("currentError.userFacingSummary"))
    let floating = try sourceFile("FloatingControlBar/FloatingControlBarWindow.swift")
    XCTAssertTrue(floating.contains("displayErrorMessage"))
  }

  func testChatSignInRecoveryUsesDesktopOAuthInsteadOfHomepage() throws {
    let source = try sourceFile("Providers/ChatProvider.swift")

    XCTAssertTrue(source.contains("try await AuthService.shared.signInWithGoogle()"))
    XCTAssertTrue(source.contains("ChatErrorCard: .signIn recovery — starting desktop OAuth"))
    XCTAssertFalse(source.contains("ChatErrorCard: .signIn recovery — opening omi.me sign-in URL"))
    XCTAssertFalse(source.contains(#"URL(string: "https://omi.me/")"#))
  }

  func testSavedUserDefaultsSessionIsValidatedBeforeUse() throws {
    let source = try sourceFile("AuthService.swift")

    XCTAssertTrue(source.contains("validateRestoredSession(attempt: attempt)"))
    XCTAssertTrue(source.contains("refreshSingleFlight(auth: self)"))
    XCTAssertTrue(source.contains("Restored session validated via forced refresh"))
    XCTAssertTrue(source.contains("Restored session validation deferred - preserving credentials for retry"))
    XCTAssertFalse(source.contains("cached ID token expired"))
  }

  func testRestoredSessionValidationDoesNotClearPersistedTokensOnTransientFailure() throws {
    let source = try sourceFile("AuthService.swift")
    let validationBlockRange = source.range(of: "Restored session validation deferred - preserving credentials for retry")
    XCTAssertNotNil(validationBlockRange)
    let snippet = String(source[validationBlockRange!.lowerBound...])
    let catchBlock = String(snippet[..<(snippet.range(of: "} catch {")?.lowerBound ?? snippet.endIndex)])
    XCTAssertFalse(catchBlock.contains("clearTokens()"))
    XCTAssertTrue(source.contains("invalidateSession(reason: .definitiveRefreshFailure)"))
  }

  func testRestoredSessionInvalidatesWhenValidationClearedTokens() throws {
    let source = try sourceFile("AuthService.swift")
    let range = source.range(of: "Restored session validation proved credentials absent")
    XCTAssertNotNil(range)
    let snippet = String(source[range!.lowerBound...]).prefix(200)
    XCTAssertTrue(snippet.contains("invalidateSession(reason: .restoredSessionInvalid)"))
    let methodStart = source.range(of: "private func validateRestoredSessionNow(attempt:")
    XCTAssertNotNil(methodStart)
    let methodEnd = source.range(
      of: "// MARK: - Auth State Listener",
      range: methodStart!.upperBound..<source.endIndex)
    XCTAssertNotNil(methodEnd)
    let method = String(source[methodStart!.lowerBound..<methodEnd!.lowerBound])
    XCTAssertTrue(method.contains("sessionCoordinator.phase == .needsReauth"))
    XCTAssertTrue(method.contains("storedIdToken == nil && storedRefreshToken == nil"))
  }

  func testRestoredSessionValidationForceRefreshesOnLaunch() throws {
    let source = try sourceFile("AuthService.swift")
    let validationRange = source.range(of: "private func validateRestoredSessionNow(attempt:")
    XCTAssertNotNil(validationRange)
    let snippet = String(source[validationRange!.lowerBound...])

    XCTAssertTrue(snippet.contains("storedRefreshToken != nil") || snippet.contains("storedIdToken != nil"))
    XCTAssertTrue(snippet.contains("refreshSingleFlight(auth: self)"))
    XCTAssertFalse(snippet.contains("!self.isTokenExpired"))
  }

  func testAuthListenerValidatesSavedSessionInsteadOfBlindPreserve() throws {
    let source = try sourceFile("AuthService.swift")
    XCTAssertTrue(source.contains("validateSavedSessionAfterFirebaseNil()"))
    XCTAssertFalse(source.contains("Keeping saved session (not overriding isSignedIn)"))
    XCTAssertTrue(source.contains("skipping REST validation while launch restore is in flight"))
  }

  func testChatSignInRecoveryDoesNotDuplicatePlanRefresh() throws {
    // signInWithGoogle() already schedules fetchPlan() on success (twice, in
    // the OAuth completion path); the recovery path must not duplicate it.
    let source = try sourceFile("Providers/ChatProvider.swift")
    let recoveryRange = source.range(of: "ChatErrorCard: .signIn recovery — starting desktop OAuth")
    XCTAssertNotNil(recoveryRange)
    let snippet = String(source[recoveryRange!.lowerBound...])
      .prefix(400)
    XCTAssertTrue(snippet.contains("try await AuthService.shared.signInWithGoogle()"))
    XCTAssertFalse(snippet.contains("FloatingBarUsageLimiter.shared.fetchPlan()"))
  }

  private func sourceFile(_ relativePath: String) throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
      .appendingPathComponent(relativePath)
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}
