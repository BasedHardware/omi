//
//  ConversationRowPrompts.swift — a row asks; the page presents.
//
//  A confirmation's dim is an overlay on the view it is mounted on (`shellConfirmation`), so a row
//  that presented its own delete confirmation would darken only itself inside the scroll view. Rows
//  therefore raise requests here and the page that owns the list mounts the confirmation and the
//  rename sheet once, over the whole page.
//

import SwiftUI

@MainActor
final class ConversationRowPrompts: ObservableObject {
  @Published var deleting: ServerConversation?
  @Published var renaming: ServerConversation?
  @Published var renameText = ""
  /// The conversation the open confirmation is about. Kept past `deleting`, because the dialog
  /// clears its presentation binding before it calls the confirm action.
  private(set) var deleteTarget: ServerConversation?

  func requestDelete(_ conversation: ServerConversation) {
    deleteTarget = conversation
    deleting = conversation
  }

  func requestRename(_ conversation: ServerConversation) {
    renameText = conversation.title
    renaming = conversation
  }
}

extension View {
  /// Mount once on the page that hosts conversation rows.
  func conversationRowPrompts(_ prompts: ConversationRowPrompts, appState: AppState) -> some View {
    modifier(ConversationRowPromptsHost(prompts: prompts, appState: appState))
  }
}

private struct ConversationRowPromptsHost: ViewModifier {
  @ObservedObject var prompts: ConversationRowPrompts
  let appState: AppState

  func body(content: Content) -> some View {
    content
      .environmentObject(prompts)
      .shellConfirmation(
        isPresented: Binding(
          get: { prompts.deleting != nil },
          set: { if !$0 { prompts.deleting = nil } }
        ),
        title: "Delete Conversation?",
        message: "This permanently deletes \u{201C}\(prompts.deleteTarget?.displayTitle ?? "this conversation")"
          + "\u{201D}, its transcript and its summary.",
        confirmTitle: "Delete"
      ) {
        guard let conversation = prompts.deleteTarget else { return }
        Task { _ = await appState.deleteConversation(conversation.id) }
      }
      .dismissableSheet(
        isPresented: Binding(
          get: { prompts.renaming != nil },
          set: { if !$0 { prompts.renaming = nil } }
        )
      ) {
        TextPromptSheet(
          title: "Edit Title",
          placeholder: "Title",
          text: $prompts.renameText,
          onConfirm: {
            guard let conversation = prompts.renaming else { return }
            let title = prompts.renameText.trimmingCharacters(in: .whitespacesAndNewlines)
            prompts.renaming = nil
            Task { await appState.updateConversationTitle(conversation.id, title: title) }
          },
          onCancel: { prompts.renaming = nil }
        )
      }
  }
}
