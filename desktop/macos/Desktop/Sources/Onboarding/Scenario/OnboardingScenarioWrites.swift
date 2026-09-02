import Foundation

@MainActor
enum OnboardingScenarioWrites {
  static func createMemory(
    _ content: String,
    ownerID: String,
    authorization: RuntimeOwnerAuthorizationSnapshot
  ) async -> Bool {
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return false }
    let result = await ChatToolExecutor.executeCreateMemory(
      ["content": content],
      originatingUserText: "Remember \(content)",
      originatingSurface: nil,
      originatingClientScope: nil,
      expectedOwnerID: ownerID,
      authorizationSnapshot: authorization,
      api: .shared
    )
    return RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) && result.contains(#""ok":true"#)
  }

  /// Creates the task and returns its id, so the caller can put the real task in the chat.
  static func createActionItem(
    title: String,
    dueDate: Date,
    ownerID: String,
    authorization: RuntimeOwnerAuthorizationSnapshot
  ) async -> String? {
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return nil }
    do {
      let item = try await APIClient.shared.createActionItem(
        description: title,
        dueAt: dueDate,
        source: "onboarding",
        expectedOwnerId: ownerID,
        authorizationSnapshot: authorization)
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return nil }
      await TasksStore.shared.refreshDashboardTasksFromServer(
        expectedOwnerID: ownerID,
        authorizationSnapshot: authorization)
      return item.id
    } catch {
      logError("Onboarding scenario: failed to create action item", error: error)
      return nil
    }
  }

  /// The task goes into the main chat as the chat's own task card (the check-off element every
  /// other created task gets), not as a notification about a task. The notch receipt is transient
  /// and is not journaled; this is the durable record.
  static func journalTaskCard(
    taskID: String,
    title: String,
    chatProvider: ChatProvider,
    ownerID: String
  ) async {
    let recorded = await chatProvider.recordJournalExchange(
      surface: chatProvider.mainChatSurfaceReference(),
      ownerID: ownerID,
      continuityKey: "onboarding-task-\(taskID)",
      userText: "",
      assistantText: title,
      origin: "onboarding_scenario",
      contentBlocks: [.taskCard(id: "onboarding-task-\(taskID)", taskId: taskID)]
    )
    log("Onboarding scenario: task card journaled=\(recorded.assistant != nil)")
  }
}
