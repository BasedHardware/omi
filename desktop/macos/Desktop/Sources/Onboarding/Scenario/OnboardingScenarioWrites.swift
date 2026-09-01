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

  static func createActionItem(
    title: String,
    dueDate: Date,
    ownerID: String,
    authorization: RuntimeOwnerAuthorizationSnapshot
  ) async -> Bool {
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return false }
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    let result = await ChatToolExecutor.execute(
      ToolCall(
        name: "create_action_item",
        arguments: ["description": title, "due_at": formatter.string(from: dueDate)],
        thoughtSignature: nil
      ),
      originatingUserText: title,
      isOnboardingSurface: true,
      expectedOwnerID: ownerID,
      authorizationSnapshot: authorization
    )
    return RuntimeOwnerIdentity.isAuthorizationCurrent(authorization)
      && !result.hasPrefix("Error:") && !result.contains(#""ok":false"#)
  }
}
