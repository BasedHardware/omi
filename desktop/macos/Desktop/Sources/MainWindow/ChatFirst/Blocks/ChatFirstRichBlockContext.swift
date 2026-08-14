import Foundation

/// Explicit rendering capability for persisted chat-first blocks. The journal
/// is shared by every Chat surface, but rich controls belong exclusively to
/// the enabled main-window shell. Passing this context is therefore a
/// rendering capability, not a second transcript or a user-controlled flag.
@MainActor
struct ChatFirstRichBlockContext {
  let navigation: ChatFirstShellNavigation
  let tasksStore: TasksStore
  let chatProvider: ChatProvider
  let canonicalGoalsStore: CanonicalGoalsStore
  let promptMaterializationCoordinator: ChatFirstPromptMaterializationCoordinator

  init(
    navigation: ChatFirstShellNavigation,
    tasksStore: TasksStore,
    chatProvider: ChatProvider,
    canonicalGoalsStore: CanonicalGoalsStore,
    promptMaterializationCoordinator: ChatFirstPromptMaterializationCoordinator
  ) {
    self.navigation = navigation
    self.tasksStore = tasksStore
    self.chatProvider = chatProvider
    self.canonicalGoalsStore = canonicalGoalsStore
    self.promptMaterializationCoordinator = promptMaterializationCoordinator
  }
}
