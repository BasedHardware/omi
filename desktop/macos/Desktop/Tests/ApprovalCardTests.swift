import XCTest

@testable import Omi_Computer

/// The device tool approval card: what the daemon's `approval_requested`
/// becomes on screen, what each button sends back through direct control, and
/// how `approval_resolved` closes it. Every test calls the production store
/// and presentation; the runtime is a recording fake.
@MainActor
final class ApprovalCardTests: XCTestCase {
  private let now = Date(timeIntervalSince1970: 1_760_000_000)

  @MainActor private final class RecordingResolver {
    var calls: [(approvalId: String, input: [String: Any])] = []
    var responses: [String] = []
    var errors: [Error] = []

    func resolve(approvalId: String, input: [String: Any]) async throws -> String {
      calls.append((approvalId, input))
      if !errors.isEmpty { throw errors.removeFirst() }
      return responses.isEmpty ? #"{"ok":true,"dispatch":{"status":"resolved"},"grant":null}"# : responses.removeFirst()
    }
  }

  private func requestedFrame(
    approvalId: String = "disp_1",
    toolName: String = "send_message",
    resourceRef: String? = "+15551234567",
    preview: [String: Any] = ["to": "+15551234567", "text": "Running late", "service": "auto"],
    options: [[String: Any]]? = nil,
    expiresInSeconds: Double = 180,
    capability: String? = nil,
    title: String? = nil,
    decisionPrompt: String? = nil
  ) throws -> AgentRuntimeProcess.RuntimeMessage {
    var payload: [String: Any] = [
      "type": "approval_requested",
      "protocolVersion": 2,
      "approvalId": approvalId,
      "ownerId": "owner-1",
      "sessionId": "ses_1",
      "runId": "run_1",
      "attemptId": "att_1",
      "invocationId": "inv_1",
      "adapterId": "pi-mono",
      "surfaceKind": "main_chat",
      "policy": "default_user_approval",
      "toolName": toolName,
      "capability": capability
        ?? (toolName == "run_applescript" ? "desktop.automation.act" : "desktop.messaging.send"),
      "operation": toolName,
      "inputHash": "sha256:abc",
      "effectClass": "non_idempotent_write",
      "title": title ?? (toolName == "run_applescript" ? "Run an AppleScript" : "Send a message"),
      "decisionPrompt": decisionPrompt
        ?? (toolName == "run_applescript"
          ? "Run this AppleScript on your Mac?" : "Send this message to +15551234567?"),
      "preview": preview,
      "previewTruncated": false,
      "reason": "Sensitive action requires dispatch or scoped grant.",
      "options": options ?? [
        ["id": "allow_once", "effect": "allow", "scope": "run"],
        [
          "id": "allow_session", "effect": "allow", "scope": "session",
          "covers": "any message or attachment to this recipient",
        ],
        ["id": "deny", "effect": "deny", "scope": "request"],
      ],
      "defaultOptionId": "deny",
      "requestedAtMs": now.timeIntervalSince1970 * 1_000,
      "expiresAtMs": (now.timeIntervalSince1970 + expiresInSeconds) * 1_000,
    ]
    if let resourceRef { payload["resourceRef"] = resourceRef } else { payload["resourceRef"] = NSNull() }
    return try runtimeMessage(payload)
  }

  private func resolvedFrame(
    approvalId: String = "disp_1",
    decision: String,
    selectedOptionId: String? = nil,
    grantId: String? = nil,
    resolvedBy: String = "user"
  ) throws -> AgentRuntimeProcess.RuntimeMessage {
    try runtimeMessage([
      "type": "approval_resolved",
      "protocolVersion": 2,
      "approvalId": approvalId,
      "ownerId": "owner-1",
      "sessionId": "ses_1",
      "runId": "run_1",
      "attemptId": "att_1",
      "invocationId": "inv_1",
      "toolName": "send_message",
      "decision": decision,
      "selectedOptionId": selectedOptionId as Any,
      "grantId": grantId as Any,
      "resolvedBy": resolvedBy,
      "resolvedAtMs": (now.timeIntervalSince1970 + 5) * 1_000,
      "automatic": resolvedBy != "user",
    ])
  }

  private func runtimeMessage(_ payload: [String: Any]) throws -> AgentRuntimeProcess.RuntimeMessage {
    let data = try JSONSerialization.data(withJSONObject: payload)
    return try XCTUnwrap(AgentRuntimeProcess.RuntimeMessage.parse(String(decoding: data, as: UTF8.self)))
  }

  private func makeStore(_ resolver: RecordingResolver) -> DesktopToolApprovalStore {
    DesktopToolApprovalStore(resolver: { try await resolver.resolve(approvalId: $0, input: $1) }, now: { self.now })
  }

  // MARK: - Showing the card

  func testRequestedFrameBecomesAPendingCardWithTargetPreviewAndThreeAnswers() throws {
    let store = makeStore(RecordingResolver())

    store.ingest(message: try requestedFrame())

    let approval = try XCTUnwrap(store.approval(id: "disp_1"))
    XCTAssertEqual(approval.state, .pending)
    XCTAssertEqual(approval.request.toolName, "send_message")
    XCTAssertEqual(approval.request.resourceRef, "+15551234567")
    XCTAssertEqual(
      approval.request.preview.map(\.key), ["to", "text", "service"], "the tool's own field order, not dictionary order"
    )
    XCTAssertTrue(approval.request.offersSessionGrant)
    XCTAssertEqual(store.approvals(forSessionId: "ses_1").map(\.id), ["disp_1"])
    XCTAssertEqual(store.approvals(forRunId: "run_1").map(\.id), ["disp_1"])
    XCTAssertTrue(store.approvals(forSessionId: "ses_other").isEmpty)

    let presentation = DesktopToolApprovalCardPresentation(approval: approval, now: now)
    XCTAssertEqual(presentation.headline, "Send a message")
    XCTAssertEqual(presentation.question, "Send this message to +15551234567?")
    XCTAssertEqual(presentation.targetLabel, "To")
    XCTAssertEqual(presentation.target, "+15551234567")
    XCTAssertEqual(presentation.preview.map(\.key), ["text", "service"], "the target line already shows the recipient")
    XCTAssertEqual(
      presentation.actions.map(\.title),
      [
        DesktopToolApprovalCardPresentation.allowOnceTitle,
        DesktopToolApprovalCardPresentation.allowForChatTitle,
        DesktopToolApprovalCardPresentation.denyTitle,
      ])
    XCTAssertEqual(
      presentation.sessionGrantNote,
      "Allow for This Chat also allows any message or attachment to this recipient for the next hour.")
    XCTAssertTrue(presentation.status.hasPrefix("Waits until "))
    XCTAssertFalse(presentation.isFinal)
  }

  func testCardOffersAllowForThisChatOnlyWhenTheRuntimeDoes() throws {
    let store = makeStore(RecordingResolver())
    store.ingest(
      message: try requestedFrame(
        approvalId: "disp_read",
        toolName: "read_message_history",
        resourceRef: nil,
        preview: ["limit": 20],
        options: [
          ["id": "allow_once", "effect": "allow", "scope": "run"],
          ["id": "deny", "effect": "deny", "scope": "request"],
        ]))

    let approval = try XCTUnwrap(store.approval(id: "disp_read"))
    let presentation = DesktopToolApprovalCardPresentation(approval: approval, now: now)
    XCTAssertFalse(approval.request.offersSessionGrant)
    XCTAssertEqual(presentation.actions.map(\.answer), [.allowOnce, .deny])
    XCTAssertNil(presentation.sessionGrantNote)
    XCTAssertEqual(presentation.preview.map(\.key), ["limit"])
  }

  func testAScreenshotCardAsksInPlainWordsAndOffersOnlyAllowOnce() async throws {
    let resolver = RecordingResolver()
    let store = makeStore(resolver)
    store.ingest(
      message: try requestedFrame(
        approvalId: "disp_screen",
        toolName: "capture_screen",
        resourceRef: "screen",
        preview: [:],
        options: [
          ["id": "allow_once", "effect": "allow", "scope": "run"],
          ["id": "deny", "effect": "deny", "scope": "request"],
        ],
        capability: "desktop.context.screenshot_image",
        title: "Take a screenshot",
        decisionPrompt: "Let Omi take a screenshot of your whole screen?"))

    let approval = try XCTUnwrap(store.approval(id: "disp_screen"))
    let presentation = DesktopToolApprovalCardPresentation(approval: approval, now: now)
    XCTAssertEqual(presentation.headline, "Take a screenshot")
    XCTAssertEqual(presentation.question, "Let Omi take a screenshot of your whole screen?")
    // The resource ref "screen" is an internal key, not something to show: no target or preview rows.
    XCTAssertNil(presentation.targetLabel)
    XCTAssertNil(presentation.target)
    XCTAssertTrue(presentation.preview.isEmpty)
    // Each screenshot is asked for on its own: no "Allow for This Chat" and no note about one.
    XCTAssertFalse(approval.request.offersSessionGrant)
    XCTAssertEqual(
      presentation.actions.map(\.title),
      [DesktopToolApprovalCardPresentation.allowOnceTitle, DesktopToolApprovalCardPresentation.denyTitle])
    XCTAssertNil(presentation.sessionGrantNote)

    await store.answer(approvalId: "disp_screen", with: .allowForSession)
    XCTAssertTrue(resolver.calls.isEmpty, "a session grant the card never offered is refused before sending")

    await store.answer(approvalId: "disp_screen", with: .allowOnce)
    let call = try XCTUnwrap(resolver.calls.first)
    XCTAssertEqual(resolver.calls.count, 1)
    XCTAssertEqual((call.input["resolution"] as? [String: Any])?["selectedOptionId"] as? String, "allow_once")
    XCTAssertNil(call.input["grant"], "a screenshot approval mints nothing")
  }

  func testMalformedRequestedFrameIsIgnored() throws {
    let store = makeStore(RecordingResolver())
    store.ingest(
      message: try runtimeMessage(["type": "approval_requested", "protocolVersion": 2, "approvalId": "disp_x"]))
    XCTAssertTrue(store.approvals.isEmpty)
  }

  // MARK: - Answering

  func testAllowOnceSendsOneResolutionWithNoGrant() async throws {
    let resolver = RecordingResolver()
    let store = makeStore(resolver)
    store.ingest(message: try requestedFrame())

    await store.answer(approvalId: "disp_1", with: .allowOnce)

    XCTAssertEqual(resolver.calls.count, 1)
    let call = try XCTUnwrap(resolver.calls.first)
    XCTAssertEqual(call.approvalId, "disp_1")
    XCTAssertEqual(call.input["dispatchId"] as? String, "disp_1")
    XCTAssertEqual(call.input["status"] as? String, "resolved")
    XCTAssertEqual(call.input["resolvedBy"] as? String, "user")
    XCTAssertEqual((call.input["resolution"] as? [String: Any])?["decision"] as? String, "allow")
    XCTAssertEqual((call.input["resolution"] as? [String: Any])?["selectedOptionId"] as? String, "allow_once")
    XCTAssertNil(call.input["grant"], "allow once mints nothing")
    XCTAssertEqual(store.approval(id: "disp_1")?.state, .allowed(selectedOptionId: "allow_once", grantId: nil))
    XCTAssertEqual(
      DesktopToolApprovalCardPresentation(approval: try XCTUnwrap(store.approval(id: "disp_1")), now: now).status,
      "Allowed once")
  }

  func testAllowForThisChatSendsASessionScopedOneHourGrantForTheExactResource() async throws {
    let resolver = RecordingResolver()
    resolver.responses = [#"{"ok":true,"dispatch":{"status":"resolved"},"grant":{"grantId":"grant_9"}}"#]
    let store = makeStore(resolver)
    store.ingest(message: try requestedFrame())

    await store.answer(approvalId: "disp_1", with: .allowForSession)

    let call = try XCTUnwrap(resolver.calls.first)
    XCTAssertEqual((call.input["resolution"] as? [String: Any])?["decision"] as? String, "allow")
    let grant = try XCTUnwrap(call.input["grant"] as? [String: Any])
    XCTAssertTrue(grant["runId"] is NSNull, "null runId scopes the grant to the whole chat")
    XCTAssertEqual(grant["capability"] as? String, "desktop.messaging.send")
    XCTAssertEqual(grant["operation"] as? String, "send_message")
    XCTAssertEqual(grant["resourcePattern"] as? String, "+15551234567")
    XCTAssertEqual(grant["effect"] as? String, "allow")
    XCTAssertEqual(grant["source"] as? String, "user")
    XCTAssertEqual(grant["expiresAtMs"] as? Int, Int((now.timeIntervalSince1970 + 3_600) * 1_000))
    XCTAssertEqual(store.approval(id: "disp_1")?.state, .allowed(selectedOptionId: "allow_session", grantId: "grant_9"))
    XCTAssertTrue(
      DesktopToolApprovalCardPresentation(approval: try XCTUnwrap(store.approval(id: "disp_1")), now: now).status
        .hasPrefix("Allowed for this chat until "))
  }

  func testAllowForThisChatIsRefusedLocallyWhenTheRuntimeDidNotOfferIt() async throws {
    let resolver = RecordingResolver()
    let store = makeStore(resolver)
    store.ingest(
      message: try requestedFrame(
        approvalId: "disp_read",
        toolName: "read_message_history",
        resourceRef: nil,
        preview: ["limit": 20],
        options: [
          ["id": "allow_once", "effect": "allow", "scope": "run"],
          ["id": "deny", "effect": "deny", "scope": "request"],
        ]))

    await store.answer(approvalId: "disp_read", with: .allowForSession)

    XCTAssertTrue(resolver.calls.isEmpty)
    XCTAssertEqual(store.approval(id: "disp_read")?.state, .pending)
  }

  func testDenySendsADenyResolutionAndTheCardReadsDenied() async throws {
    let resolver = RecordingResolver()
    let store = makeStore(resolver)
    store.ingest(message: try requestedFrame())

    await store.answer(approvalId: "disp_1", with: .deny)

    let call = try XCTUnwrap(resolver.calls.first)
    XCTAssertEqual(call.input["status"] as? String, "resolved")
    XCTAssertEqual((call.input["resolution"] as? [String: Any])?["decision"] as? String, "deny")
    XCTAssertNil(call.input["grant"])
    XCTAssertEqual(store.approval(id: "disp_1")?.state, .denied)
    let presentation = DesktopToolApprovalCardPresentation(
      approval: try XCTUnwrap(store.approval(id: "disp_1")), now: now)
    XCTAssertEqual(presentation.status, "Denied, not run")
    XCTAssertTrue(presentation.actions.isEmpty)
    XCTAssertTrue(presentation.isFinal)
  }

  func testASecondPressWhileAnsweringOrAfterTheDecisionSendsNothing() async throws {
    let resolver = RecordingResolver()
    let store = makeStore(resolver)
    store.ingest(message: try requestedFrame())

    await store.answer(approvalId: "disp_1", with: .allowOnce)
    await store.answer(approvalId: "disp_1", with: .deny)
    await store.answer(approvalId: "disp_1", with: .allowOnce)

    XCTAssertEqual(resolver.calls.count, 1, "the kernel decided once; later presses are not resent")
    XCTAssertEqual(store.approval(id: "disp_1")?.state, .allowed(selectedOptionId: "allow_once", grantId: nil))
  }

  func testARefusedAnswerPutsTheCardBackToPendingWithTheReason() async throws {
    let resolver = RecordingResolver()
    resolver.responses = [
      #"{"ok":false,"error":{"code":"control_tool_failed","message":"Desktop dispatch disp_1 signature was rejected"}}"#
    ]
    let store = makeStore(resolver)
    store.ingest(message: try requestedFrame())

    await store.answer(approvalId: "disp_1", with: .allowOnce)

    let approval = try XCTUnwrap(store.approval(id: "disp_1"))
    XCTAssertEqual(approval.state, .pending)
    XCTAssertEqual(
      approval.lastError, "Couldn't send your answer: Desktop dispatch disp_1 signature was rejected")
    let presentation = DesktopToolApprovalCardPresentation(approval: approval, now: now)
    XCTAssertEqual(presentation.actions.count, 3, "the user can try again")
    XCTAssertEqual(presentation.error, approval.lastError)

    // The next attempt clears the error.
    await store.answer(approvalId: "disp_1", with: .deny)
    XCTAssertEqual(store.approval(id: "disp_1")?.state, .denied)
    XCTAssertNil(store.approval(id: "disp_1")?.lastError)
  }

  func testATransportFailurePutsTheCardBackToPending() async throws {
    let resolver = RecordingResolver()
    resolver.errors = [NSError(domain: "test", code: 1, userInfo: [NSLocalizedDescriptionKey: "runtime restarting"])]
    let store = makeStore(resolver)
    store.ingest(message: try requestedFrame())

    await store.answer(approvalId: "disp_1", with: .allowOnce)

    XCTAssertEqual(store.approval(id: "disp_1")?.state, .pending)
    XCTAssertEqual(store.approval(id: "disp_1")?.lastError, "Couldn't send your answer: runtime restarting")
  }

  // MARK: - The kernel's resolution is final

  func testResolvedFramesCloseTheCardWhateverEndedIt() throws {
    let store = makeStore(RecordingResolver())
    for (index, decision) in ["expired", "cancelled", "deny", "allow"].enumerated() {
      let id = "disp_\(index)"
      store.ingest(message: try requestedFrame(approvalId: id))
      store.ingest(
        message: try resolvedFrame(
          approvalId: id, decision: decision, selectedOptionId: decision == "allow" ? "allow_once" : nil,
          resolvedBy: decision == "expired" ? "system" : "user"))
    }

    XCTAssertEqual(store.approval(id: "disp_0")?.state, .expired)
    XCTAssertEqual(store.approval(id: "disp_1")?.state, .cancelled)
    XCTAssertEqual(store.approval(id: "disp_2")?.state, .denied)
    XCTAssertEqual(store.approval(id: "disp_3")?.state, .allowed(selectedOptionId: "allow_once", grantId: nil))
    XCTAssertEqual(store.approval(id: "disp_0")?.resolvedBy, "system")
    XCTAssertEqual(
      DesktopToolApprovalCardPresentation(approval: try XCTUnwrap(store.approval(id: "disp_0")), now: now).status,
      "Expired, not run")
    XCTAssertEqual(
      DesktopToolApprovalCardPresentation(approval: try XCTUnwrap(store.approval(id: "disp_1")), now: now).status,
      "Cancelled, not run")
    XCTAssertTrue(store.pendingApprovals.isEmpty)
  }

  func testAResolutionThatArrivesBeforeItsRequestStillClosesTheCard() throws {
    let store = makeStore(RecordingResolver())

    store.ingest(message: try resolvedFrame(decision: "expired", resolvedBy: "system"))
    XCTAssertTrue(store.approvals.isEmpty)
    store.ingest(message: try requestedFrame())

    XCTAssertEqual(store.approval(id: "disp_1")?.state, .expired)
  }

  func testAResolutionForAnotherCardOrWithAnUnknownDecisionChangesNothing() throws {
    let store = makeStore(RecordingResolver())
    store.ingest(message: try requestedFrame())

    store.ingest(message: try resolvedFrame(approvalId: "disp_other", decision: "allow"))
    store.ingest(message: try resolvedFrame(decision: "maybe"))

    XCTAssertEqual(store.approval(id: "disp_1")?.state, .pending)
  }

  func testTheKernelsResolutionWinsOverALocalAnswerInFlight() async throws {
    let resolver = RecordingResolver()
    let store = makeStore(resolver)
    store.ingest(message: try requestedFrame())
    // The user presses Allow once, and before the receipt arrives the daemon
    // reports the card expired: the card shows the kernel's answer.
    resolver.responses = [#"{"ok":false,"error":{"code":"control_tool_failed","message":"not pending"}}"#]
    let answering = Task { await store.answer(approvalId: "disp_1", with: .allowOnce) }
    store.ingest(message: try resolvedFrame(decision: "expired", resolvedBy: "system"))
    await answering.value

    XCTAssertEqual(store.approval(id: "disp_1")?.state, .expired)
    XCTAssertNil(
      store.approval(id: "disp_1")?.lastError, "a refused answer against a closed card is not an error to show")
  }

  func testResolvedCardsAreTrimmedButPendingOnesNeverAre() throws {
    let store = makeStore(RecordingResolver())
    for index in 0..<60 {
      let id = "disp_\(index)"
      store.ingest(message: try requestedFrame(approvalId: id))
      if index % 2 == 0 { store.ingest(message: try resolvedFrame(approvalId: id, decision: "deny")) }
    }

    XCTAssertEqual(store.approvals.count, 50)
    XCTAssertEqual(store.pendingApprovals.count, 30, "every pending card survives")
    XCTAssertNil(store.approval(id: "disp_0"), "the oldest resolved card is the first to go")
  }

  // MARK: - Direct control carries the full resolution

  private final class ApprovalRecordingRuntime: DesktopCoordinatorRuntimeControlling, @unchecked Sendable {
    struct Call {
      let name: String
      let input: [String: Any]
    }

    private(set) var calls: [Call] = []

    func directControlTool(
      clientId: String,
      harnessMode: String,
      name: String,
      input: RuntimeJSONPayloadBox
    ) async throws -> String {
      calls.append(Call(name: name, input: input.value))
      return #"{"ok":true,"dispatch":{"status":"resolved"}}"#
    }
  }

  func testCoordinatorServicePassesTheFullResolutionThroughDirectControl() async throws {
    let runtime = ApprovalRecordingRuntime()
    let service = DesktopCoordinatorService(
      runtime: runtime,
      clientId: "test-approval",
      harnessModeProvider: { AgentHarnessMode.piMono.rawValue },
      checkpointDefaults: try XCTUnwrap(UserDefaults(suiteName: "ApprovalCardTests.coordinator")))
    let request = try XCTUnwrap(
      DesktopToolApprovalRequest.parse(try requestedFrame().payload))

    _ = try await service.resolveDispatchJSON(
      dispatchId: "disp_1",
      input: DesktopToolApprovalAnswer.allowForSession.controlToolInput(for: request, now: now))

    let call = try XCTUnwrap(runtime.calls.first)
    XCTAssertEqual(call.name, "resolve_desktop_dispatch")
    XCTAssertEqual(call.input["dispatchId"] as? String, "disp_1")
    XCTAssertEqual((call.input["grant"] as? [String: Any])?["resourcePattern"] as? String, "+15551234567")
  }

  // MARK: - Harness drivers

  /// `omi-ctl` reads and answers the same store the card renders, so a headless
  /// run can drive a real approval without Accessibility permission. The
  /// registered handlers add only the non-production guard, which the xctest
  /// bundle cannot satisfy, so the helpers behind them are exercised directly.
  func testBridgeActionsReadAndAnswerTheSharedStoreLikeTheCard() async throws {
    let shared = DesktopToolApprovalStore.shared
    shared.reset()
    defer { shared.reset() }
    // The shared store runs on the wall clock, so these cards expire 180 s from now.
    let liveExpiry = Date().timeIntervalSince(now) + 180
    shared.ingest(message: try requestedFrame(approvalId: "disp_bridge", expiresInSeconds: liveExpiry))
    shared.ingest(
      message: try requestedFrame(
        approvalId: "disp_bridge_once",
        options: [
          ["id": "allow_once", "effect": "allow", "scope": "once"],
          ["id": "deny", "effect": "deny", "scope": "once"],
        ],
        expiresInSeconds: liveExpiry))

    let registry = DesktopAutomationActionRegistry()
    registry.registerBuiltins()
    let descriptors = registry.descriptors()
    let snapshotDescriptor = try XCTUnwrap(descriptors.first { $0.name == "tool_approval_snapshot" })
    XCTAssertEqual(snapshotDescriptor.effects, [])
    let answerDescriptor = try XCTUnwrap(descriptors.first { $0.name == "answer_tool_approval" })
    XCTAssertEqual(Set(answerDescriptor.effects), Set(DesktopAutomationActionEffect.allCases))

    let snapshot = DesktopAutomationActionRegistry.toolApprovalSnapshot(sessionId: "ses_1")
    XCTAssertEqual(snapshot["count"], "2")
    XCTAssertEqual(snapshot["pending"], "2")
    let rows = try XCTUnwrap(
      JSONSerialization.jsonObject(with: Data((snapshot["approvals"] ?? "").utf8)) as? [[String: Any]])
    XCTAssertEqual(rows.compactMap { $0["approvalId"] as? String }, ["disp_bridge", "disp_bridge_once"])
    XCTAssertEqual(rows.first?["state"] as? String, "pending")
    XCTAssertEqual(rows.first?["answers"] as? [String], ["allow_once", "allow_session", "deny"])
    XCTAssertEqual(rows.first?["resourceRef"] as? String, "+15551234567")
    XCTAssertEqual(rows.last?["answers"] as? [String], ["allow_once", "deny"])
    XCTAssertEqual(DesktopAutomationActionRegistry.toolApprovalSnapshot(sessionId: "ses_other")["count"], "0")

    let unknown = await DesktopAutomationActionRegistry.answerToolApproval(approvalId: "nope", answer: .deny)
    XCTAssertEqual(unknown["error"], "unknown approval_id")
    let notOffered = await DesktopAutomationActionRegistry.answerToolApproval(
      approvalId: "disp_bridge_once", answer: .allowForSession)
    XCTAssertEqual(notOffered["error"], "allow_session is not offered for this approval")
    XCTAssertEqual(shared.approval(id: "disp_bridge")?.state, .pending)
    XCTAssertEqual(shared.approval(id: "disp_bridge_once")?.state, .pending)
  }

  // MARK: - Clearing, expiry and refusals

  func testBridgeAnswersCarryTheBridgeResolverId() async throws {
    let resolver = RecordingResolver()
    let store = makeStore(resolver)
    store.ingest(message: try requestedFrame())

    let result = await DesktopAutomationActionRegistry.answerToolApproval(
      approvalId: "disp_1", answer: .deny, store: store)

    XCTAssertEqual(result["state"], "denied")
    XCTAssertEqual(resolver.calls.count, 1)
    XCTAssertEqual(resolver.calls.first?.input["resolvedBy"] as? String, "desktop_automation")
    // The card's own buttons still answer as the person.
    let direct = makeStore(RecordingResolver())
    let input = DesktopToolApprovalAnswer.deny.controlToolInput(
      for: try XCTUnwrap(store.approval(id: "disp_1")).request, now: now)
    XCTAssertEqual(input["resolvedBy"] as? String, "user")
    _ = direct
  }

  func testAPendingCardExpiresLocallyAtItsDeadlineAndOffersNoButtons() async throws {
    let resolver = RecordingResolver()
    var clock = now
    let store = DesktopToolApprovalStore(
      resolver: { try await resolver.resolve(approvalId: $0, input: $1) }, now: { clock })
    store.ingest(message: try requestedFrame(expiresInSeconds: 180))

    clock = now.addingTimeInterval(179)
    store.expireOverdue()
    XCTAssertEqual(store.approval(id: "disp_1")?.state, .pending)

    clock = now.addingTimeInterval(181)
    store.expireOverdue()
    let expired = try XCTUnwrap(store.approval(id: "disp_1"))
    XCTAssertEqual(expired.state, .expired)
    XCTAssertEqual(expired.resolvedBy, "system")
    let presentation = DesktopToolApprovalCardPresentation(approval: expired, now: clock)
    XCTAssertEqual(presentation.status, "Expired, not run")
    XCTAssertTrue(presentation.actions.isEmpty)

    // A press after the deadline, before the timer ran, sends nothing either.
    let late = makeStore(resolver)
    late.ingest(message: try requestedFrame(approvalId: "disp_late", expiresInSeconds: -1))
    let overdueStillPending = DesktopToolApproval(
      request: try XCTUnwrap(late.approval(id: "disp_late")).request, state: .pending,
      resolvedAt: nil, resolvedBy: nil, lastError: nil)
    let overduePresentation = DesktopToolApprovalCardPresentation(approval: overdueStillPending, now: now)
    XCTAssertTrue(overduePresentation.actions.isEmpty)
    XCTAssertTrue(overduePresentation.isFinal)
    await late.answer(approvalId: "disp_late", with: .allowOnce)
    XCTAssertEqual(resolver.calls.count, 0)
    XCTAssertEqual(late.approval(id: "disp_late")?.state, .expired)
  }

  func testARefusalBecauseTheDispatchIsNoLongerPendingClosesTheCardLikeTheKernelDid() async throws {
    let resolver = RecordingResolver()
    resolver.responses = [
      #"{"ok":false,"error":{"code":"runtime_error","message":"Desktop dispatch disp_1 is not pending"}}"#,
      #"{"ok":false,"error":{"code":"runtime_error","message":"Desktop dispatch disp_gone is not pending"}}"#,
    ]
    let store = makeStore(resolver)
    store.ingest(message: try requestedFrame())
    store.ingest(message: try requestedFrame(approvalId: "disp_gone", expiresInSeconds: 1))

    await store.answer(approvalId: "disp_1", with: .allowOnce)
    let closed = try XCTUnwrap(store.approval(id: "disp_1"))
    XCTAssertEqual(closed.state, .cancelled)
    XCTAssertNil(closed.lastError)
    XCTAssertEqual(DesktopToolApprovalCardPresentation(approval: closed, now: now).status, "Cancelled, not run")

    // Refused after its own deadline: the kernel expired it, and so does the card.
    let late = DesktopToolApprovalStore(
      resolver: { try await resolver.resolve(approvalId: $0, input: $1) },
      now: { self.now.addingTimeInterval(0.5) })
    late.ingest(message: try requestedFrame(approvalId: "disp_gone", expiresInSeconds: 1))
    resolver.responses = [
      #"{"ok":false,"error":{"code":"runtime_error","message":"Desktop dispatch disp_gone is not pending"}}"#
    ]
    await late.answer(approvalId: "disp_gone", with: .deny)
    XCTAssertEqual(late.approval(id: "disp_gone")?.state, .cancelled)
  }

  func testResetDropsEveryCardAndEarlyResolutionsStayBounded() throws {
    let store = makeStore(RecordingResolver())
    store.ingest(message: try requestedFrame())
    store.ingest(message: try resolvedFrame(approvalId: "disp_other", decision: "deny"))
    XCTAssertEqual(store.approvals.count, 1)

    store.reset()
    XCTAssertTrue(store.approvals.isEmpty)
    // The early resolution went with it: its request now opens a plain pending card.
    store.ingest(message: try requestedFrame(approvalId: "disp_other"))
    XCTAssertEqual(store.approval(id: "disp_other")?.state, .pending)

    let bounded = makeStore(RecordingResolver())
    for index in 0..<60 {
      bounded.ingest(message: try resolvedFrame(approvalId: "disp_early_\(index)", decision: "deny"))
    }
    bounded.ingest(message: try requestedFrame(approvalId: "disp_early_0"))
    XCTAssertEqual(bounded.approval(id: "disp_early_0")?.state, .pending, "the oldest early resolution was pruned")
    bounded.ingest(message: try requestedFrame(approvalId: "disp_early_59"))
    XCTAssertEqual(bounded.approval(id: "disp_early_59")?.state, .denied, "the newest still closes its card")
  }

  func testPreviewTextIsDisplaySafeAndAThreadReadKeepsItsHandle() throws {
    let store = makeStore(RecordingResolver())
    store.ingest(
      message: try requestedFrame(
        resourceRef: "+1555\u{202E}1000",
        preview: [
          "to": "+1555\u{202E}1000",
          "text": "Running\u{0007} late\nSERVICE\nsms",
          "service": "auto",
        ]))
    let request = try XCTUnwrap(store.approval(id: "disp_1")).request
    // The grant covers the exact resource the kernel bound; the card shows what hides in it.
    XCTAssertEqual(request.resourceRef, "+1555\u{202E}1000")
    XCTAssertEqual(request.displayResourceRef, "+1555⟨U+202E⟩1000")
    XCTAssertEqual(request.preview.first { $0.key == "to" }?.value, "+1555⟨U+202E⟩1000")
    XCTAssertEqual(request.preview.first { $0.key == "text" }?.value, "Running⟨U+0007⟩ late\nSERVICE\nsms")
    XCTAssertEqual(DesktopToolApprovalRequest.displaySafe("a\u{2066}b\u{200F}c\td"), "a⟨U+2066⟩b⟨U+200F⟩c\td")
    XCTAssertEqual(DesktopToolApprovalRequest.displaySafe("x\u{200B}y\u{FEFF}z\u{2060}"), "x⟨U+200B⟩y⟨U+FEFF⟩z⟨U+2060⟩")
    XCTAssertEqual(DesktopToolApprovalRequest.displaySafe("👩\u{200D}💻"), "👩\u{200D}💻")
    let shown = DesktopToolApprovalCardPresentation(approval: try XCTUnwrap(store.approval(id: "disp_1")), now: now)
    XCTAssertEqual(shown.target, "+1555⟨U+202E⟩1000")
    XCTAssertEqual(shown.preview.map(\.key), ["text", "service"])
    let grant = DesktopToolApprovalAnswer.allowForSession.controlToolInput(for: request, now: now)
    XCTAssertEqual((grant["grant"] as? [String: Any])?["resourcePattern"] as? String, "+1555\u{202E}1000")

    store.ingest(
      message: try requestedFrame(
        approvalId: "disp_thread",
        toolName: "read_message_history",
        resourceRef: "chat123",
        preview: ["chat_id": "chat123", "handle": "+15551234567", "limit": "20"]))
    let presentation = DesktopToolApprovalCardPresentation(
      approval: try XCTUnwrap(store.approval(id: "disp_thread")), now: now)
    XCTAssertEqual(presentation.targetLabel, "Conversation")
    XCTAssertEqual(presentation.target, "chat123")
    XCTAssertEqual(presentation.preview.map(\.key), ["handle", "limit"])
  }

  // MARK: - Reading an app window

  private func snapshotFrame(
    approvalId: String = "disp_snap", resourceRef: String = "com.apple.textedit",
    preview: [String: Any] = ["window_title": "Untitled"]
  ) throws -> AgentRuntimeProcess.RuntimeMessage {
    try runtimeMessage([
      "type": "approval_requested",
      "protocolVersion": 2,
      "approvalId": approvalId,
      "ownerId": "owner-1",
      "sessionId": "ses_1",
      "runId": "run_1",
      "attemptId": "att_1",
      "invocationId": "inv_1",
      "adapterId": "pi-mono",
      "surfaceKind": "main_chat",
      "policy": "default_user_approval",
      "toolName": "ui_snapshot",
      "capability": "desktop.automation.observe",
      "operation": "ui_snapshot",
      "resourceRef": resourceRef,
      "inputHash": "sha256:abc",
      "effectClass": "read_only",
      "title": "Read an app window",
      "decisionPrompt": "Let Omi read the window of \(resourceRef)?",
      "preview": preview,
      "previewTruncated": false,
      "reason": "Sensitive action requires dispatch or scoped grant.",
      "options": [
        ["id": "allow_once", "effect": "allow", "scope": "run"],
        ["id": "allow_session", "effect": "allow", "scope": "session", "covers": "reading any window of this app"],
        ["id": "deny", "effect": "deny", "scope": "request"],
      ],
      "defaultOptionId": "deny",
      "requestedAtMs": now.timeIntervalSince1970 * 1_000,
      "expiresAtMs": (now.timeIntervalSince1970 + 180) * 1_000,
    ])
  }

  private func makeSnapshotStore(
    _ resolver: RecordingResolver, apps: [String: DesktopToolApprovalTargetApp]
  ) -> DesktopToolApprovalStore {
    DesktopToolApprovalStore(
      resolver: { try await resolver.resolve(approvalId: $0, input: $1) }, now: { self.now },
      resolveApp: { apps[$0] })
  }

  private static let textEdit = DesktopToolApprovalTargetApp(name: "TextEdit", bundleID: "com.apple.TextEdit")

  func testAWindowReadNamesTheAppOmiResolvedBesideItsBundleID() throws {
    let store = makeSnapshotStore(RecordingResolver(), apps: ["com.apple.textedit": Self.textEdit])
    store.ingest(
      message: try snapshotFrame(preview: ["window_title": "Untitled", "window_id": 4411]))

    let presentation = DesktopToolApprovalCardPresentation(
      approval: try XCTUnwrap(store.approval(id: "disp_snap")), now: now)

    XCTAssertEqual(presentation.headline, "Read an app window")
    XCTAssertEqual(presentation.question, "Let Omi read the window of TextEdit?")
    XCTAssertEqual(presentation.targetLabel, "App")
    XCTAssertEqual(presentation.target, "TextEdit · com.apple.TextEdit")
    XCTAssertEqual(presentation.preview.map(\.key), ["window_title", "window_id"], "no element limit row")
    XCTAssertEqual(
      presentation.sessionGrantNote, "Allow for This Chat also allows reading any window of TextEdit for the next hour."
    )
    XCTAssertEqual(presentation.actions.map(\.answer), [.allowOnce, .allowForSession, .deny])
  }

  func testAnAppOmiCannotResolveFallsBackToTheKernelsWords() throws {
    let store = makeSnapshotStore(RecordingResolver(), apps: [:])
    store.ingest(message: try snapshotFrame(resourceRef: "com.example.unknown"))

    let presentation = DesktopToolApprovalCardPresentation(
      approval: try XCTUnwrap(store.approval(id: "disp_snap")), now: now)

    XCTAssertEqual(presentation.question, "Let Omi read the window of com.example.unknown?")
    XCTAssertEqual(presentation.target, "com.example.unknown")
  }

  func testOnlyAWindowReadLooksItsResourceUpAsAnApp() throws {
    var lookups: [String] = []
    let store = DesktopToolApprovalStore(
      resolver: { _, _ in "" }, now: { self.now },
      resolveApp: {
        lookups.append($0)
        return Self.textEdit
      })
    store.ingest(message: try requestedFrame())

    let presentation = DesktopToolApprovalCardPresentation(
      approval: try XCTUnwrap(store.approval(id: "disp_1")), now: now)

    XCTAssertEqual(lookups, [], "a recipient is never looked up as an app")
    XCTAssertEqual(presentation.target, "+15551234567")
    XCTAssertNil(try XCTUnwrap(store.approval(id: "disp_1")).request.targetApp)
  }

  func testAllowForThisChatOnAWindowReadGrantsThatAppForTheChat() async throws {
    let resolver = RecordingResolver()
    let store = makeSnapshotStore(resolver, apps: ["com.apple.textedit": Self.textEdit])
    store.ingest(message: try snapshotFrame())

    await store.answer(approvalId: "disp_snap", with: .allowForSession)

    let grant = try XCTUnwrap(resolver.calls.first?.input["grant"] as? [String: Any])
    XCTAssertTrue(grant["runId"] is NSNull)
    XCTAssertEqual(grant["capability"] as? String, "desktop.automation.observe")
    XCTAssertEqual(grant["operation"] as? String, "ui_snapshot")
    XCTAssertEqual(grant["resourcePattern"] as? String, "com.apple.textedit")
  }

  func testAWindowTitleAndAnAppNameShowTheCharactersHidingInThem() throws {
    let spoofed = DesktopToolApprovalTargetApp(name: "Text\u{202E}Edit", bundleID: "com.apple.TextEdit")
    let store = makeSnapshotStore(RecordingResolver(), apps: ["com.apple.textedit": spoofed])
    store.ingest(message: try snapshotFrame(preview: ["window_title": "Chat\u{2066} with Ria"]))

    let presentation = DesktopToolApprovalCardPresentation(
      approval: try XCTUnwrap(store.approval(id: "disp_snap")), now: now)

    XCTAssertEqual(presentation.preview.first?.value, "Chat⟨U+2066⟩ with Ria")
    XCTAssertEqual(presentation.target, "Text⟨U+202E⟩Edit · com.apple.TextEdit")
  }

  func testAnAppNameCannotForgeTheBundleIDOrRunLong() throws {
    let spoof = DesktopToolApprovalTargetApp(name: "TextEdit · com.apple.TextEdit", bundleID: "com.evil.app")
    let store = makeSnapshotStore(RecordingResolver(), apps: ["com.evil.app": spoof])
    store.ingest(message: try snapshotFrame(resourceRef: "com.evil.app"))

    let presentation = DesktopToolApprovalCardPresentation(
      approval: try XCTUnwrap(store.approval(id: "disp_snap")), now: now)

    XCTAssertEqual(presentation.target, "TextEdit com.apple.TextEdit · com.evil.app")
    XCTAssertEqual(DesktopToolApprovalRequest.cardAppName(String(repeating: "A", count: 100)).count, 40)
    for separator in [
      "\u{2022}", "\u{2219}", "\u{22C5}", "\u{2027}", "\u{30FB}", "\u{FF65}", "\u{2218}", "\u{0387}", "|", "/",
    ] {
      XCTAssertEqual(
        DesktopToolApprovalRequest.cardAppName("TextEdit \(separator) com.apple.TextEdit"),
        "TextEdit com.apple.TextEdit",
        separator)
    }
    XCTAssertEqual(DesktopToolApprovalRequest.cardAppName("Text\u{2063}Edit\u{E0041}"), "Text⟨U+2063⟩Edit")
    XCTAssertEqual(DesktopToolApprovalRequest.cardAppName("Café 2 (Beta)"), "Café 2 (Beta)")
  }
}
