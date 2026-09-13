//
//  ConversationDetailRequestIdentity.swift — when the open detail must re-load.
//
//  Extracted from `ConversationDetailView.swift` (a frozen line-count file) when
//  the token stopped keying on `updatedAt`: the summary revision it carries
//  instead is a policy of its own, and `ConversationsPage` reads the same token
//  to decide whether a refreshed list row may replace the open selection.
//

/// Summary-pane content that must restart the detail load when it changes.
///
/// `updatedAt` is a Firestore document revision — any write bumps it, including
/// writes that change nothing the summary pane renders. Keying detail work on
/// it let a background list refresh remount the summary mid-read: the loaded
/// detail was dropped, the seed row re-laid-out, and the detail refetched,
/// which reads as the summary flashing 2–3 times while scrolling a long
/// conversation (FC-selection-overlay-layout-loop class). This revision carries
/// only what the pane actually renders, so volatile metadata no longer bounces
/// the request token while the reader stays on the same conversation.
struct ConversationSummaryRevision: Hashable {
  let primaryContent: String
  let sectionBodies: [String]
  let actionItemDescriptions: [String]
  let secondaryResultContents: [String]

  init(conversation: ServerConversation) {
    primaryContent = ConversationSummarySelection.primarySummary(for: conversation).content
    sectionBodies = conversation.structured.sections.map(\.bodyMarkdown)
    actionItemDescriptions = conversation.structured.actionItems
      .filter { !$0.deleted }
      .map(\.description)
    secondaryResultContents = ConversationSummarySelection.secondaryResults(for: conversation).map(\.content)
  }

  init(
    primaryContent: String,
    sectionBodies: [String] = [],
    actionItemDescriptions: [String] = [],
    secondaryResultContents: [String] = []
  ) {
    self.primaryContent = primaryContent
    self.sectionBodies = sectionBodies
    self.actionItemDescriptions = actionItemDescriptions
    self.secondaryResultContents = secondaryResultContents
  }
}

/// A parent can replace a conversation row without changing its identity
/// (rename, folder move, processing completion, reprocessed summary). Keying
/// detail work only by ID leaves the open panel pinned to the old value, so
/// these visible revisions participate in the request identity as well.
/// `updatedAt` deliberately does not: it moves on writes that change nothing
/// here, and it alone was enough to remount the summary mid-read (see
/// ``ConversationSummaryRevision``).
struct ConversationDetailRequestToken: Hashable {
  let conversationID: String
  let title: String
  let folderID: String?
  let status: String
  let summaryRevision: ConversationSummaryRevision

  init(conversation: ServerConversation) {
    self.init(
      conversationID: conversation.id,
      title: conversation.title,
      folderID: conversation.folderId,
      status: String(describing: conversation.status),
      summaryRevision: ConversationSummaryRevision(conversation: conversation)
    )
  }

  init(
    conversationID: String,
    title: String,
    folderID: String?,
    status: String,
    summaryRevision: ConversationSummaryRevision
  ) {
    self.conversationID = conversationID
    self.title = title
    self.folderID = folderID
    self.status = status
    self.summaryRevision = summaryRevision
  }
}
