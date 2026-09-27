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

  /// Items the reader has added from this summary, those in flight, and those whose last attempt
  /// failed (offered again as "Try Again").
  @State private var addedActionItemIDs: Set<String> = []
  @State private var addingActionItemIDs: Set<String> = []
  @State private var failedActionItemIDs: Set<String> = []

  private var activeItems: [ActionItem] {
    conversation.structured.actionItems.filter { !$0.deleted }
  }

  var body: some View {
    if !activeItems.isEmpty {
      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        DetailSectionHeader(title: "Action Items", systemImage: "checklist", count: activeItems.count)

        VStack(alignment: .leading, spacing: 0) {
          ForEach(Array(activeItems.enumerated()), id: \.element.id) { index, item in
            if index > 0 {
              GlassSeparator().padding(.leading, 36)
            }
            row(item)
          }
        }
        .glassCard(cornerRadius: PageGlass.rowRadius)
      }
      // `conversation_detail_prompt prompt=add_task index=N` presses item N's task control.
      .onReceive(
        NotificationCenter.default.publisher(for: .desktopAutomationConversationPromptRequested)
      ) { notification in
        guard notification.userInfo?["conversationId"] as? String == conversation.id,
          notification.userInfo?["prompt"] as? String == "add_task",
          let index = notification.userInfo?["index"] as? Int, activeItems.indices.contains(index)
        else { return }
        let item = activeItems[index]
        let linkedTaskID = onOpenLinkedTask == nil ? nil : item.targetTaskID
        if let linkedTaskID { onOpenLinkedTask?(linkedTaskID) } else { addActionItemToTasks(item) }
      }
    }
  }

  private func row(_ item: ActionItem) -> some View {
    let sourceIDs = ConversationSummarySelection.resolvableSourceIDs(
      item.sourceSegmentIDs, segments: conversation.transcriptSegments)
    let linkedTaskID = onOpenLinkedTask == nil ? nil : item.targetTaskID
    return ConversationActionItemRow(
      item: item,
      taskState: taskState(for: item, linkedTaskID: linkedTaskID),
      transcriptTitle: sourceIDs.isEmpty ? "Transcript" : "Source",
      onTaskAction: {
        if let linkedTaskID {
          onOpenLinkedTask?(linkedTaskID)
        } else {
          addActionItemToTasks(item)
        }
      },
      onOpenTranscript: {
        ConversationDetailAutomationState.shared.requestOpen(
          conversationId: conversation.id,
          showTranscript: true,
          transcriptSegmentIds: sourceIDs
        )
      }
    )
  }

  private func taskState(for item: ActionItem, linkedTaskID: String?) -> ActionItemTaskState {
    if linkedTaskID != nil { return .linked }
    if addedActionItemIDs.contains(item.id) { return .added }
    if addingActionItemIDs.contains(item.id) { return .adding }
    if failedActionItemIDs.contains(item.id) { return .failed }
    return .idle
  }

  /// Explicit, per-item promotion of a summary action item into the task list.
  /// This gesture is the only way an extracted item becomes a task.
  private func addActionItemToTasks(_ item: ActionItem) {
    guard !addedActionItemIDs.contains(item.id), !addingActionItemIDs.contains(item.id) else { return }
    addingActionItemIDs.insert(item.id)
    failedActionItemIDs.remove(item.id)
    Task { @MainActor in
      let created = await TasksStore.shared.createTask(
        description: item.description,
        dueAt: nil,
        priority: nil
      )
      addingActionItemIDs.remove(item.id)
      if created != nil {
        addedActionItemIDs.insert(item.id)
      } else {
        failedActionItemIDs.insert(item.id)
      }
    }
  }
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

/// Apps with memory capability that have not produced a result for this conversation yet.
struct ConversationSuggestedAppsSection: View {
  let apps: [OmiApp]
  let isLoadingApps: Bool
  let reprocessingAppID: String?
  let onSelect: (OmiApp) -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      DetailSectionHeader(title: "Try with Apps", systemImage: "sparkles")

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
