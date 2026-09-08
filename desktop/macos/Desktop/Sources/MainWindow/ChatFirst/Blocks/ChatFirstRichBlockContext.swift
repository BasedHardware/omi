import Foundation

/// The owners a persisted content block needs to become an interactable
/// control: typed navigation, the task store it checks off against, the one
/// chat provider, the canonical goals projection, and the prompt-materialization
/// coordinator. Every Chat surface has one — it is not a capability flag and it
/// is never a second transcript.
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

@MainActor
extension ChatFirstRichBlockContext {
  /// The context for a Chat surface that is not the main-window shell — the task
  /// panel and the floating/notch renderers. They own no navigation or goal
  /// state, so they bind the shell's process-wide owners: a card tapped in the
  /// notch routes the main window instead of a private copy of it.
  /// The auxiliary context for a surface that has no `ChatProvider` in hand —
  /// the floating bar and the notch, which render over `ChatProvider.mainInstance`
  /// (INV-6: there is no second provider to fall back to). Nil only before the
  /// main window has created it, which is also the only moment those surfaces
  /// have no transcript to project.
  static var floatingSurface: ChatFirstRichBlockContext? {
    guard let provider = ChatProvider.mainInstance else { return nil }
    return auxiliary(chatProvider: provider)
  }

  static func auxiliary(chatProvider: ChatProvider) -> ChatFirstRichBlockContext {
    ChatFirstRichBlockContext(
      navigation: .shared,
      tasksStore: .shared,
      chatProvider: chatProvider,
      canonicalGoalsStore: .shared,
      promptMaterializationCoordinator: .shared
    )
  }
}
