import Combine
import Foundation

/// Non-production semantic actions for the live Chat-first shell. The runtime
/// owns no fixture data and makes no eligibility decision: it is installed only
/// after the root has consumed the server-owned capability sample. Individual
/// pages register their real handlers while mounted, so an action cannot claim
/// a result for an off-screen or fabricated surface.
@MainActor
final class ChatFirstAutomationRuntime: ObservableObject {
  typealias AsyncBool = @MainActor () async -> Bool
  typealias CaptureSnapshot = @MainActor () -> Bool
  typealias AsyncQuestionSelection = @MainActor (QuestionSelection) async -> Bool

  enum QuestionSelection: String {
    case first
    case deferred = "defer"
  }

  private let navigation: ChatFirstShellNavigation
  private let goalsStore: CanonicalGoalsStore
  private let tasksStore: TasksStore
  private let chatProvider: ChatProvider

  private var setFocus: AsyncBool?
  private var openRelatedTasks: AsyncBool?
  private var toggleTask: AsyncBool?
  private var openCapture: AsyncBool?
  private var discussCapture: AsyncBool?
  private var captureDetailIsVisible: CaptureSnapshot?
  private var selectQuestionOption: AsyncQuestionSelection?
  private var requestPromptMaterialization: AsyncBool?

  init(
    navigation: ChatFirstShellNavigation,
    goalsStore: CanonicalGoalsStore,
    tasksStore: TasksStore,
    chatProvider: ChatProvider
  ) {
    self.navigation = navigation
    self.goalsStore = goalsStore
    self.tasksStore = tasksStore
    self.chatProvider = chatProvider
  }

  func install() {
    // The semantic fixture actions are part of the loopback bridge contract,
    // not a generic non-production feature. Preview/release-style bundles
    // must never register them, even if code elsewhere calls this runtime.
    guard DesktopAutomationLaunchOptions.isEnabled else { return }
    let registry = DesktopAutomationActionRegistry.shared

    registry.register(
      name: "chat_first_runtime_snapshot",
      summary: "Read shape-only state from the live Chat-first pages",
      category: "read",
      surfaces: ["main_chat", "goals", "tasks", "conversations"],
      safety: "read_only",
      sideEffects: []
    ) { [weak self] _ in
      guard let self else { return nil }
      return self.runtimeSnapshot()
    }

    registry.register(
      name: "chat_first_request_prompt_materialization",
      summary: "Run the normal foreground materialization path from mounted main Chat",
      params: ["timeoutMs"],
      category: "coordinator",
      surfaces: ["main_chat"],
      safety: "chat_turn",
      sideEffects: ["requests server-owned prompt materialization"]
    ) { [weak self] params in
      guard let self, let requestPromptMaterialization = self.requestPromptMaterialization else {
        throw DesktopAutomationActionError.invalidParams("chat_first_main_chat_page_not_visible")
      }
      guard await requestPromptMaterialization() else {
        return [
          "prompt_materialization_requested": "false",
          "actionable_question_at_tail": "false",
        ]
      }
      let timeoutMs = min(60_000, max(1_000, Int(params["timeoutMs"] ?? "") ?? 30_000))
      return [
        "prompt_materialization_requested": "true",
        "actionable_question_at_tail": await waitForActionableQuestionTail(timeoutMs: timeoutMs) ? "true" : "false",
      ]
    }

    registry.register(
      name: "chat_first_render_fixture_task_card",
      summary: "Invoke the real authorized Chat-first block executor from mounted main Chat",
      category: "chat",
      surfaces: ["main_chat"],
      safety: "chat_turn",
      sideEffects: ["creates one local fixture journal turn", "validates and appends one fixture task card"]
    ) { [weak self] _ in
      guard let self, self.requestPromptMaterialization != nil else {
        throw DesktopAutomationActionError.invalidParams("chat_first_main_chat_page_not_visible")
      }
      return await self.chatProvider.runChatFirstFixtureTaskCardProbe()
    }

    registry.register(
      name: "chat_first_set_focus",
      summary: "Set focus through the currently visible Chat-first Goals page",
      category: "coordinator",
      surfaces: ["goals"],
      safety: "server_mutation",
      sideEffects: ["updates canonical goal focus"]
    ) { [weak self] _ in
      guard let self, let setFocus = self.setFocus else {
        throw DesktopAutomationActionError.invalidParams("chat_first_goals_page_not_visible")
      }
      return ["focus_updated": await setFocus() ? "true" : "false"]
    }

    registry.register(
      name: "chat_first_open_related_tasks",
      summary: "Open related Tasks through the currently visible focused Goal",
      category: "coordinator",
      surfaces: ["goals", "tasks"],
      safety: "local_ui_state",
      sideEffects: ["changes Chat-first route"]
    ) { [weak self] _ in
      guard let self, let openRelatedTasks = self.openRelatedTasks else {
        throw DesktopAutomationActionError.invalidParams("chat_first_goal_detail_not_visible")
      }
      guard await openRelatedTasks() else {
        return ["related_tasks_opened": "false"]
      }
      return ["related_tasks_opened": await self.waitForVisibleRoute(.tasks) ? "true" : "false"]
    }

    registry.register(
      name: "chat_first_toggle_task",
      summary: "Toggle one visible Chat-first task through the shared Tasks store",
      category: "coordinator",
      surfaces: ["tasks", "main_chat"],
      safety: "server_mutation",
      sideEffects: ["updates task completion"]
    ) { [weak self] _ in
      guard let self, let toggleTask = self.toggleTask else {
        throw DesktopAutomationActionError.invalidParams("chat_first_tasks_page_not_visible")
      }
      return ["task_reconciled": await toggleTask() ? "true" : "false"]
    }

    registry.register(
      name: "chat_first_open_capture",
      summary: "Select an Omi-device capture through the visible archive page",
      category: "coordinator",
      surfaces: ["conversations"],
      safety: "read_only",
      sideEffects: ["selects a local capture detail"]
    ) { [weak self] _ in
      guard let self, let openCapture = self.openCapture else {
        throw DesktopAutomationActionError.invalidParams("chat_first_capture_page_not_visible")
      }
      return ["capture_detail_opened": await openCapture() ? "true" : "false"]
    }

    registry.register(
      name: "chat_first_discuss_capture",
      summary: "Start the ordinary main-Chat turn from the selected capture detail",
      category: "chat",
      surfaces: ["conversations", "main_chat"],
      safety: "chat_turn",
      sideEffects: ["creates one main-Chat turn"]
    ) { [weak self] _ in
      guard let self, let discussCapture = self.discussCapture else {
        throw DesktopAutomationActionError.invalidParams("chat_first_capture_detail_not_visible")
      }
      let messageCount = self.chatProvider.messages.count
      guard await discussCapture() else {
        return ["capture_discussion_started": "false"]
      }
      let chatIsVisible = await self.waitForVisibleRoute(.chat)
      let turnStarted = await self.waitForMainChatTurnStart(sinceMessageCount: messageCount)
      return [
        "capture_discussion_started": chatIsVisible && turnStarted ? "true" : "false"
      ]
    }

    registry.register(
      name: "chat_first_select_question_option",
      summary: "Select a bounded actionable question option through the mounted main-Chat journal",
      params: ["selection"],
      category: "chat",
      surfaces: ["main_chat"],
      safety: "chat_turn",
      sideEffects: ["creates one prepared main-Chat turn"]
    ) { [weak self] params in
      guard let self, let selectQuestionOption = self.selectQuestionOption else {
        throw DesktopAutomationActionError.invalidParams("chat_first_main_chat_page_not_visible")
      }
      guard
        let selection = QuestionSelection(
          rawValue: params["selection"] ?? QuestionSelection.first.rawValue
        )
      else {
        throw DesktopAutomationActionError.invalidParams("selection must be first or defer")
      }
      return ["question_selection_started": await selectQuestionOption(selection) ? "true" : "false"]
    }
  }

  func uninstall() {
    let registry = DesktopAutomationActionRegistry.shared
    for name in [
      "chat_first_runtime_snapshot",
      "chat_first_request_prompt_materialization",
      "chat_first_render_fixture_task_card",
      "chat_first_set_focus",
      "chat_first_open_related_tasks",
      "chat_first_toggle_task",
      "chat_first_open_capture",
      "chat_first_discuss_capture",
      "chat_first_select_question_option",
    ] {
      registry.unregister(name)
    }
    unregisterGoalsPage()
    unregisterTasksPage()
    unregisterCapturePage()
    unregisterChatPage()
  }

  func registerGoalsPage(setFocus: @escaping AsyncBool, openRelatedTasks: @escaping AsyncBool) {
    self.setFocus = setFocus
    self.openRelatedTasks = openRelatedTasks
  }

  func unregisterGoalsPage() {
    setFocus = nil
    openRelatedTasks = nil
  }

  func registerTasksPage(toggleTask: @escaping AsyncBool) {
    self.toggleTask = toggleTask
  }

  func unregisterTasksPage() {
    toggleTask = nil
  }

  func registerCapturePage(
    openCapture: @escaping AsyncBool,
    discussCapture: @escaping AsyncBool,
    detailIsVisible: @escaping CaptureSnapshot
  ) {
    self.openCapture = openCapture
    self.discussCapture = discussCapture
    captureDetailIsVisible = detailIsVisible
  }

  func unregisterCapturePage() {
    openCapture = nil
    discussCapture = nil
    captureDetailIsVisible = nil
  }

  func registerChatPage(requestPromptMaterialization: @escaping AsyncBool) {
    selectQuestionOption = { [weak self] selection in
      guard let self else { return false }
      return await self.selectActionableQuestionOption(selection: selection)
    }
    self.requestPromptMaterialization = requestPromptMaterialization
  }

  func unregisterChatPage() {
    selectQuestionOption = nil
    requestPromptMaterialization = nil
  }

  private func runtimeSnapshot() -> [String: String] {
    [
      "route": navigation.route.stableName,
      "route_visible": navigation.visibleRoute == navigation.route ? "true" : "false",
      "focus_acknowledged": navigation.isFocusedEntityAcknowledged ? "true" : "false",
      "focused_goal_available": goalsStore.primaryFocusedGoal == nil ? "false" : "true",
      "visible_task_count": "\(tasksStore.tasks.filter { $0.deleted != true }.count)",
      "completed_visible_task_count": "\(tasksStore.tasks.filter { $0.deleted != true && $0.completed }.count)",
      "capture_detail_visible": captureDetailIsVisible?() == true ? "true" : "false",
      "actionable_question_at_tail": actionableQuestionCard() ? "true" : "false",
      "actionable_question_available": questionOptionIsAvailable(for: .first) ? "true" : "false",
      "deferrable_question_available": questionOptionIsAvailable(for: .deferred) ? "true" : "false",
    ]
  }

  private func selectActionableQuestionOption(selection: QuestionSelection) async -> Bool {
    guard let option = selectableQuestionOption(for: selection) else { return false }
    AnalyticsManager.shared.chatFirst(
      .question(lifecycle: selection == .deferred ? .deferred : .answered)
    )
    AnalyticsManager.shared.chatFirst(
      .richBlock(kind: .questionCard, outcome: .acted, action: .select)
    )
    // Yield to the bounded journal action before reporting success.  Without
    // this handoff, the next harness `wait_main_chat_idle` can read the *old*
    // idle state before the real selection enters ChatProvider.  We still do
    // not await the model response here; the following idle/tail assertions
    // own that terminal evidence.
    Task { [chatProvider] in
      await chatProvider.selectQuestionCardOption(questionID: option.questionID, optionID: option.optionID)
    }
    return await waitForQuestionSelectionToBegin(selection: selection)
  }

  private func questionOptionIsAvailable(for selection: QuestionSelection) -> Bool {
    selectQuestionOption != nil && selectableQuestionOption(for: selection) != nil
  }

  private func actionableQuestionCard() -> Bool {
    guard selectQuestionOption != nil, let tail = chatProvider.messages.last else { return false }
    return tail.contentBlocks.contains { block in
      guard case .questionCard(_, let questionID, _, _, _, _, let selectedOptionID) = block else { return false }
      return chatProvider.isQuestionCardActionable(
        messageID: tail.id,
        questionID: questionID,
        selectedOptionID: selectedOptionID
      )
    }
  }

  private func waitForActionableQuestionTail(timeoutMs: Int) async -> Bool {
    let deadline = Date().addingTimeInterval(Double(timeoutMs) / 1_000)
    while Date() < deadline {
      if actionableQuestionCard() { return true }
      try? await Task.sleep(nanoseconds: 100_000_000)
    }
    return actionableQuestionCard()
  }

  private func waitForMainChatTurnStart(sinceMessageCount: Int) async -> Bool {
    let deadline = Date().addingTimeInterval(5)
    while Date() < deadline {
      if chatProvider.isSending || chatProvider.messages.count > sinceMessageCount { return true }
      try? await Task.sleep(nanoseconds: 50_000_000)
    }
    return chatProvider.isSending || chatProvider.messages.count > sinceMessageCount
  }

  private func waitForQuestionSelectionToBegin(
    selection: QuestionSelection,
    timeoutMs: Int = 2_000
  ) async -> Bool {
    let deadline = Date().addingTimeInterval(Double(timeoutMs) / 1_000)
    while Date() < deadline {
      if chatProvider.isSending || !questionOptionIsAvailable(for: selection) { return true }
      try? await Task.sleep(nanoseconds: 25_000_000)
    }
    return chatProvider.isSending || !questionOptionIsAvailable(for: selection)
  }

  private func waitForVisibleRoute(_ route: ChatFirstRoute, timeoutMs: Int = 5_000) async -> Bool {
    let deadline = Date().addingTimeInterval(Double(timeoutMs) / 1_000)
    while Date() < deadline {
      if navigation.visibleRoute == route { return true }
      try? await Task.sleep(nanoseconds: 50_000_000)
    }
    return navigation.visibleRoute == route
  }

  private func selectableQuestionOption(for selection: QuestionSelection) -> (questionID: String, optionID: String)? {
    guard let tail = chatProvider.messages.last else { return nil }
    for block in tail.contentBlocks {
      guard case .questionCard(_, let questionID, _, _, _, let options, let selectedOptionID) = block,
        chatProvider.isQuestionCardActionable(
          messageID: tail.id,
          questionID: questionID,
          selectedOptionID: selectedOptionID
        ),
        let optionID = ChatFirstQuestionAutomationSelectionPolicy.optionID(
          in: options,
          selection: selection
        )
      else { continue }
      return (questionID, optionID)
    }
    return nil
  }
}

/// Extracts only the selected opaque option identifier from the real question
/// card payload. It deliberately never returns the question text, option label,
/// prepared answer, subject, or an arbitrary caller-supplied option ID.
enum ChatFirstQuestionAutomationSelectionPolicy {
  static func optionID(
    in options: [[String: Any]],
    selection: ChatFirstAutomationRuntime.QuestionSelection
  ) -> String? {
    let wantsDeferral = selection == .deferred
    for option in options {
      let isDeferral = option["defer"] as? Bool ?? false
      guard isDeferral == wantsDeferral else { continue }
      guard let optionID = option["optionId"] as? String else { continue }
      let normalized = optionID.trimmingCharacters(in: .whitespacesAndNewlines)
      if !normalized.isEmpty { return normalized }
    }
    return nil
  }
}
