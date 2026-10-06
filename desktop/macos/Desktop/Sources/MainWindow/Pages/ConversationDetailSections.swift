import OmiTheme
import SwiftUI

// The conversation detail's summary-pane sections that own no page state: action items, other
// apps' results, and the apps that could summarize this conversation. The detail view composes
// them; each takes what it shows and the closures for what it asks the page to do.

// MARK: - Action Items

/// Action items extracted from the conversation. Nothing here is a task until the reader says so
/// (I1): each row carries its own "Add to Tasks", and that gesture is the only promotion path.
/// The row (`ConversationActionItemRow`) shows its controls on hover or focus, and keeps a task
/// state the reader must see (adding, added, failed, linked) on screen.
struct ConversationActionItemsSection: View {
  let conversation: ServerConversation
  var onOpenLinkedTask: ((String) -> Void)?
  let onTaskAdded: (OmiAPI.SummaryTaskReference, String) -> Void
  @StateObject private var promoter = ConversationSummaryTaskPromoter()

  /// Completion-toggle state for items promoted in this view; Add-to-Tasks flight and
  /// failure states live on the canonical promoter (index-keyed).
  @State private var addedActionItemIDs: Set<String> = []
  @State private var failedActionItemIDs: Set<String> = []
  @State private var completedOverrides: [String: Bool] = [:]
  @State private var createdTasks: [String: TaskActionItem] = [:]
  @State private var createdTaskCompletion: [String: Bool] = [:]
  @State private var togglingActionItemIDs: Set<String> = []

  private var activeIndices: [Int] {
    conversation.structured.actionItems.indices.filter { !conversation.structured.actionItems[$0].deleted }
  }

  var body: some View {
    if !activeIndices.isEmpty {
      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        DetailSectionHeader(title: "Action items", systemImage: "checklist", count: activeIndices.count)

        VStack(alignment: .leading, spacing: 0) {
          ForEach(Array(activeIndices.enumerated()), id: \.element) { offset, index in
            if offset > 0 {
              GlassSeparator().padding(.leading, 36)
            }
            row(index)
          }
        }
        .glassCard(cornerRadius: PageGlass.rowRadius)
        if let error = promoter.error {
          Text(error)
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.errorRed)
            .accessibilityIdentifier("summary-task-promotion-error")
        }
      }
      // `conversation_detail_prompt prompt=add_task index=N` presses item N's task control.
      .onReceive(
        NotificationCenter.default.publisher(for: .desktopAutomationConversationPromptRequested)
      ) { notification in
        guard notification.userInfo?["conversationId"] as? String == conversation.id,
          notification.userInfo?["prompt"] as? String == "add_task",
          let visibleIndex = notification.userInfo?["index"] as? Int, activeIndices.indices.contains(visibleIndex)
        else { return }
        let index = activeIndices[visibleIndex]
        taskAction(index)
      }
    }
  }

  private func row(_ index: Int) -> some View {
    var item = conversation.structured.actionItems[index]
    let identity = actionItemIdentity(item)
    // Keyed by the row's identity, not ActionItem.id (the description): two rows
    // that share a description are separate commitments with separate overrides.
    item.completed = completedOverrides[identity] ?? item.completed
    let sourceIDs = ConversationSummarySelection.resolvableSourceIDs(
      item.sourceSegmentIDs, segments: conversation.transcriptSegments)
    let linkedTaskID = item.targetTaskID
    return ConversationActionItemRow(
      item: item,
      taskState: taskState(index: index, identity: identity, linkedTaskID: linkedTaskID),
      transcriptTitle: sourceIDs.isEmpty ? "Transcript" : "Source",
      onTaskAction: { taskAction(index) },
      onOpenTranscript: {
        ConversationDetailAutomationState.shared.requestOpen(
          conversationId: conversation.id,
          showTranscript: true,
          transcriptSegmentIds: sourceIDs
        )
      },
      onToggleCompleted: { toggleCompletion(item, index: index, identity: identity) }
    )
  }

  private func taskState(index: Int, identity: String, linkedTaskID: String?) -> ActionItemTaskState {
    if linkedTaskID != nil { return onOpenLinkedTask == nil ? .added : .linked }
    if addedActionItemIDs.contains(identity) { return .added }
    if promoter.adding.contains(index) { return .adding }
    if promoter.failed.contains(index) || failedActionItemIDs.contains(identity) { return .failed }
    return .idle
  }

  private func actionItemIdentity(_ item: ActionItem) -> String {
    // Segment IDs are evidence references, not identities: one segment can carry
    // several commitments, and the backend allows multiple identical items in a
    // conversation. Bind the item's own content so distinct rows stay distinct.
    let due = item.dueAt.map { "\($0.timeIntervalSince1970)" } ?? ""
    return "\(item.sourceSegmentIDs.joined(separator: "|"))|\(item.description)|\(due)"
  }

  /// Explicit, per-item promotion of a summary action item into the task list.
  /// This gesture is the only way an extracted item becomes a task; the canonical
  /// candidate path persists the link (targetTaskID) server-side.
  private func taskAction(_ index: Int) {
    let item = conversation.structured.actionItems[index]
    if let taskID = item.targetTaskID {
      onOpenLinkedTask?(taskID)
      return
    }
    let selected = OmiAPI.SummaryTaskReference(
      actionItemIndex: index, conversationId: conversation.id, expectedDescription: item.description)
    Task { @MainActor in
      guard let taskID = await promoter.promote(selected) else { return }
      onTaskAdded(selected, taskID)
      await SuggestedTasksStore.shared.load()
      await TasksStore.shared.refreshDashboardTasksFromServer()
    }
  }

  private func toggleCompletion(_ item: ActionItem, index: Int, identity: String) {
    guard !togglingActionItemIDs.contains(identity) else { return }
    togglingActionItemIDs.insert(identity)
    let next = !item.completed
    Task { @MainActor in
      defer { togglingActionItemIDs.remove(identity) }
      var task = createdTasks[identity]
      var taskIsCompleted = createdTaskCompletion[identity]
      if let cached = task {
        // createTask returns the row's local id (local_<rowid>); the background
        // create-sync replaces it with the backend id in SQLite. Re-read the row
        // so a toggle in the same view addresses the backend task, never the
        // stale local-only id (whose toggle would silently skip the server).
        if let synced = try? await ActionItemStorage.shared.getLocalActionItem(byBackendId: cached.id) {
          task = synced
          taskIsCompleted = synced.completed
        }
      }
      if task == nil, let targetTaskID = item.targetTaskID {
        task = try? await APIClient.shared.getActionItem(id: targetTaskID)
        guard task != nil else {
          failedActionItemIDs.insert(identity)
          return
        }
        taskIsCompleted = task?.completed
      }
      if task == nil && next {
        // Completion-created tasks go through the canonical promoter, exactly
        // like "Add to Tasks": the backend mints the task and persists the
        // conversation's targetTaskID link in one transaction. The canonical
        // path creates open tasks (completed: false), so a check-off promotes
        // first and then toggles the durable, backend-addressable task.
        let selected = OmiAPI.SummaryTaskReference(
          actionItemIndex: index, conversationId: conversation.id, expectedDescription: item.description)
        guard let taskID = await promoter.promote(selected) else {
          // The summary must not show completed when no completed task exists.
          failedActionItemIDs.insert(identity)
          return
        }
        onTaskAdded(selected, taskID)
        let fetched = try? await APIClient.shared.getActionItem(id: taskID)
        guard let created = fetched else {
          failedActionItemIDs.insert(identity)
          return
        }
        task = created
        taskIsCompleted = created.completed
        createdTasks[identity] = created
        createdTaskCompletion[identity] = created.completed
        addedActionItemIDs.insert(identity)
      }
      if let task, let taskIsCompleted, taskIsCompleted != next {
        let toggleInput = TaskActionItem(
          id: task.id, description: task.description, completed: taskIsCompleted, createdAt: task.createdAt,
          dueAt: task.dueAt, conversationId: task.conversationId, source: task.source, priority: task.priority)
        // Only the summary reflects a task mutation that actually took effect;
        // TasksStore reports false when the toggle failed and rolled back.
        let toggled = await TasksStore.shared.toggleTask(toggleInput)
        guard toggled else {
          failedActionItemIDs.insert(identity)
          return
        }
        createdTaskCompletion[identity] = next
      }
      do {
        let body = SetConversationActionItemStatusBody(itemsIdx: [index], values: [next])
        let _: ConversationActionItemStatusResponse = try await APIClient.shared.patch(
          "v1/conversations/\(conversation.id)/action-items", body: body)
        if let task { createdTasks[identity] = task }
        completedOverrides[identity] = next
      } catch {
        // The task mutation took effect but the conversation PATCH failed; put
        // the task back so Tasks and the summary cannot disagree after reload.
        if let task, let taskIsCompleted, taskIsCompleted != next {
          let rollbackInput = TaskActionItem(
            id: task.id, description: task.description, completed: next, createdAt: task.createdAt,
            dueAt: task.dueAt, conversationId: task.conversationId, source: task.source, priority: task.priority)
          if await TasksStore.shared.toggleTask(rollbackInput) {
            createdTaskCompletion[identity] = taskIsCompleted
          }
        }
        failedActionItemIDs.insert(identity)
      }
    }
  }
}

private struct SetConversationActionItemStatusBody: Encodable {
  let itemsIdx: [Int]
  let values: [Bool]
  enum CodingKeys: String, CodingKey {
    case itemsIdx = "items_idx"
    case values
  }
}

private struct ConversationActionItemStatusResponse: Decodable {
  let status: String
}

// MARK: - App Insights

/// Results from apps other than the one that owns the summary.
struct ConversationAppInsightsSection: View {
  let rows: [ConversationSummarySelection.Secondary]
  let apps: [OmiApp]
  let isReprocessing: Bool
  let onReprocess: () -> Void

  var body: some View {
    if !rows.isEmpty {
      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        DetailSectionHeader(title: "App Insights", systemImage: "square.grid.2x2") {
          Button(action: onReprocess) {
            DetailQuietButtonLabel(title: "Reprocess", systemImage: "arrow.triangle.2.circlepath")
          }
          .buttonStyle(.plain)
          .disabled(isReprocessing)
          .help("Run this conversation through another app")
        }

        ForEach(rows) { row in
          AppResultCard(result: row.result, app: apps.first { $0.id == row.result.appId })
        }
      }
    }
  }
}

// MARK: - Try with Apps

enum ConversationSuggestedAppsDisclosure {
  static let initiallyExpanded = false
}

/// Apps with memory capability that have not produced a result for this conversation yet.
struct ConversationSuggestedAppsSection: View {
  let apps: [OmiApp]
  let isLoadingApps: Bool
  let reprocessingAppID: String?
  let onSelect: (OmiApp) -> Void
  @State private var isExpanded = ConversationSuggestedAppsDisclosure.initiallyExpanded

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      Button {
        isExpanded.toggle()
      } label: {
        HStack(spacing: OmiSpacing.xs) {
          DetailSectionHeader(title: "Try with Apps", systemImage: "sparkles")
          Image(systemName: isExpanded ? "chevron.down" : "chevron.right")
            .scaledFont(size: OmiType.caption, weight: .semibold)
            .foregroundColor(Ink.secondary)
        }
        .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .accessibilityIdentifier("conversation-try-with-apps-disclosure")
      .accessibilityValue(isExpanded ? "Expanded" : "Collapsed")

      if isExpanded {
        if apps.isEmpty && !isLoadingApps {
          Text("Enable apps with memory capability to get more insights from your conversations.")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
            .fixedSize(horizontal: false, vertical: true)
        } else {
          ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: OmiSpacing.sm) {
              ForEach(apps) { app in
                SuggestedAppCard(
                  app: app,
                  isLoading: reprocessingAppID == app.id,
                  onTap: { onSelect(app) }
                )
              }
            }
          }
        }
      }
    }
  }
}

// MARK: - App Result Card

struct AppResultCard: View {
  let result: AppResponse
  let app: OmiApp?

  @State private var isExpanded = false

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      // Header
      HStack(spacing: OmiSpacing.sm) {
        if let app = app {
          AsyncImage(url: URL(string: app.image)) { phase in
            switch phase {
            case .success(let image):
              image
                .resizable()
                .aspectRatio(contentMode: .fill)
            default:
              RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                .fill(Ink.rowFillHover)
            }
          }
          .frame(width: 32, height: 32)
          .clipShape(RoundedRectangle(cornerRadius: OmiChrome.elementRadius))

          VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
            Text(app.name)
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundColor(Ink.primary)

            Text(app.author)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)
          }
        } else {
          Image(systemName: "app.fill")
            .scaledFont(size: OmiType.subheading)
            .foregroundColor(Ink.secondary)
            .frame(width: 32, height: 32)
            .background(Ink.rowFillHover)
            .clipShape(RoundedRectangle(cornerRadius: OmiChrome.elementRadius))

          Text("App")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(Ink.primary)
        }

        Spacer()

        Button(action: { OmiMotion.withGated { isExpanded.toggle() } }) {
          Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
        }
        .buttonStyle(.plain)
      }

      // Settled app output has the same document semantics as the primary summary.
      let content =
        isExpanded || result.content.count < 200
        ? result.content : String(result.content.prefix(200)) + "\u{2026}"
      OmiMarkdown(text: content, sender: .ai, appKitProseSelection: true, documentProse: true)
        .frame(maxWidth: .infinity, alignment: .leading)

      // "Generated by" footer
      if let app = app {
        HStack(spacing: OmiSpacing.xs) {
          AsyncImage(url: URL(string: app.image)) { phase in
            switch phase {
            case .success(let image):
              image
                .resizable()
                .aspectRatio(contentMode: .fill)
            default:
              RoundedRectangle(cornerRadius: OmiChrome.stripRadius)
                .fill(Ink.rowFillHover)
            }
          }
          .frame(width: 16, height: 16)
          .clipShape(RoundedRectangle(cornerRadius: OmiChrome.stripRadius))

          Text("Generated by \(app.name)")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
        }
        .padding(.horizontal, OmiSpacing.sm)
        .padding(.vertical, OmiSpacing.xxs)
        .background(
          Capsule()
            .fill(Ink.rowFillHover.opacity(0.6))
        )
      }
    }
    .padding(OmiSpacing.md)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
        .fill(Ink.rowFill)
    )
  }
}

// MARK: - Suggested App Card

struct SuggestedAppCard: View {
  let app: OmiApp
  let isLoading: Bool
  let onTap: () -> Void

  @State private var isHovering = false

  var body: some View {
    Button(action: onTap) {
      VStack(spacing: OmiSpacing.sm) {
        ZStack {
          AsyncImage(url: URL(string: app.image)) { phase in
            switch phase {
            case .success(let image):
              image
                .resizable()
                .aspectRatio(contentMode: .fill)
            default:
              RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
                .fill(Ink.rowFillHover)
            }
          }
          .frame(width: 56, height: 56)
          .clipShape(RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius))

          if isLoading {
            RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
              .fill(Color.black.opacity(0.5))
              .frame(width: 56, height: 56)

            ProgressView()
              .controlSize(.small)
              .tint(Ink.surface)
          }
        }

        Text(app.name)
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(Ink.primary)
          .lineLimit(1)
          .help(app.name)
      }
      .frame(width: 80)
      .padding(.vertical, OmiSpacing.sm)
      .padding(.horizontal, OmiSpacing.sm)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
          .fill(isHovering ? Ink.rowFillHover : Ink.rowFill)
      )
    }
    .buttonStyle(.plain)
    .disabled(isLoading)
    .onHover { isHovering = $0 }
  }

}
