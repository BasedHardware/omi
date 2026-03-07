import SwiftUI

// MARK: - Task Detail Button

/// Small inline info button with hover preview and click-to-open detail modal.
/// Hover shows a popover preview; click opens the full detail sheet.
/// The popover stays open while the cursor is on the button OR the popover itself.
struct TaskDetailButton: View {
    let task: TaskActionItem
    @Binding var showDetail: Bool
    @State private var showTooltip = false
    @State private var isButtonHovered = false
    @State private var isPopoverHovered = false
    @State private var dismissWork: DispatchWorkItem?

    var body: some View {
        Button {
            dismissNow()
            showDetail = true
        } label: {
            Image(systemName: "info.circle")
                .scaledFont(size: 10)
                .foregroundColor(showTooltip ? OmiColors.textSecondary : OmiColors.textTertiary)
        }
        .buttonStyle(.plain)
        .onHover { hovering in
            isButtonHovered = hovering
            scheduleHoverUpdate()
        }
        .popover(isPresented: $showTooltip, attachmentAnchor: .rect(.bounds), arrowEdge: .bottom) {
            TaskDetailTooltip(task: task, isPopoverHovered: $isPopoverHovered)
                .onHover { hovering in
                    isPopoverHovered = hovering
                    scheduleHoverUpdate()
                }
        }
    }

    private func scheduleHoverUpdate() {
        dismissWork?.cancel()
        if isButtonHovered || isPopoverHovered {
            showTooltip = true
        } else {
            // Short delay so the cursor can travel from button to popover
            let work = DispatchWorkItem { showTooltip = false }
            dismissWork = work
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.25, execute: work)
        }
    }

    private func dismissNow() {
        dismissWork?.cancel()
        showTooltip = false
    }
}

// MARK: - Task Detail Tooltip

/// Compact hover preview showing all task fields
private struct TaskDetailTooltip: View {
    let task: TaskActionItem
    @Binding var isPopoverHovered: Bool

    private var metadata: [String: Any] {
        task.parsedMetadata ?? [:]
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 6) {
                // Core fields
                tooltipRow("Status", task.completed ? "Completed" : "Active")
                if let category = task.category {
                    tooltipRow("Category", category.capitalized)
                }
                if !task.tags.isEmpty {
                    tooltipRow("Tags", task.tags.joined(separator: ", "))
                }
                if let priority = task.priority {
                    tooltipRow("Priority", priority.capitalized)
                }
                if let source = task.source {
                    tooltipRow("Source", "\(task.sourceLabel) (\(source))")
                }
                if let app = task.sourceApp {
                    tooltipRow("App", app)
                }
                if let window = task.windowTitle {
                    tooltipRow("Window", window)
                }
                tooltipRow("Created", {
                    let f = DateFormatter()
                    f.dateStyle = .medium
                    f.timeStyle = .short
                    return f.string(from: task.createdAt)
                }())
                if let dueAt = task.dueAt {
                    tooltipRow("Due", {
                        let f = DateFormatter()
                        f.dateStyle = .medium
                        f.timeStyle = .short
                        return f.string(from: dueAt)
                    }())
                }
                if let goalId = task.goalId {
                    tooltipRow("Goal", goalId)
                }

                // Context
                if let ctx = task.contextSummary, !ctx.isEmpty {
                    tooltipBlock("Context", ctx)
                }
                if let act = task.currentActivity, !act.isEmpty {
                    tooltipBlock("Activity", act)
                }

                // Agent
                if let status = task.agentStatus {
                    tooltipRow("Agent", status.capitalized)
                }

                // All metadata (compact)
                ForEach(allMetadataEntries, id: \.key) { entry in
                    if entry.value.count > 60 || entry.value.contains("\n") {
                        tooltipBlock(entry.label, entry.value)
                    } else {
                        tooltipRow(entry.label, entry.value)
                    }
                }
            }
            .padding(10)
        }
        .frame(maxWidth: 350, maxHeight: 400)
    }

    private struct MetadataEntry: Identifiable {
        let key: String
        let label: String
        let value: String
        var id: String { key }
    }

    /// All metadata entries, skipping keys already shown as direct fields
    private var allMetadataEntries: [MetadataEntry] {
        let skip: Set<String> = [
            "tags", "source_app", "window_title", "confidence",
            "source_category", "source_subcategory",
            "context_summary", "current_activity",
        ]
        guard let meta = task.parsedMetadata else { return [] }
        return meta
            .filter { !skip.contains($0.key) }
            .compactMap { entry in
                let display: String
                if let str = entry.value as? String, !str.isEmpty {
                    display = str
                } else if let num = entry.value as? NSNumber {
                    display = num.stringValue
                } else if let arr = entry.value as? [String] {
                    display = arr.joined(separator: ", ")
                } else {
                    return nil
                }
                let label = entry.key
                    .replacingOccurrences(of: "_", with: " ")
                    .capitalized
                return MetadataEntry(key: entry.key, label: label, value: display)
            }
            .sorted { $0.key < $1.key }
    }

    private func tooltipRow(_ label: String, _ value: String) -> some View {
        HStack(alignment: .top, spacing: 6) {
            Text(label)
                .scaledFont(size: 11, weight: .medium)
                .foregroundColor(OmiColors.textTertiary)
                .frame(width: 70, alignment: .trailing)

            Text(value)
                .scaledFont(size: 11)
                .foregroundColor(OmiColors.textPrimary)
        }
    }

    private func tooltipBlock(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .scaledFont(size: 11, weight: .medium)
                .foregroundColor(OmiColors.textTertiary)
                .padding(.leading, 76)

            Text(value)
                .scaledFont(size: 11)
                .foregroundColor(OmiColors.textPrimary)
                .padding(.leading, 76)
        }
    }
}

// MARK: - Task Detail View

/// Modal showing rich metadata for tasks from sentry_feedback, omi-analytics, screenshot sources
struct TaskDetailView: View {
    let task: TaskActionItem
    var onDismiss: (() -> Void)? = nil

    @Environment(\.dismiss) private var environmentDismiss

    private var metadata: [String: Any] {
        task.parsedMetadata ?? [:]
    }

    private func dismissSheet() {
        if let onDismiss = onDismiss {
            onDismiss()
        } else {
            environmentDismiss()
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header
            header

            Divider()

            // Content
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    // Task description
                    taskInfoSection

                    // Core fields (always shown)
                    coreFieldsSection

                    // Context at extraction time
                    if task.contextSummary != nil || task.currentActivity != nil ||
                       metadata["context_summary"] != nil || metadata["current_activity"] != nil || metadata["reasoning"] != nil {
                        contextSection
                    }

                    // Agent work
                    if task.agentStatus != nil || task.agentPlan != nil {
                        agentSection
                    }

                    // Sentry section
                    if metadata["sentry_issue_url"] != nil || metadata["sentry_issue_id"] != nil {
                        sentrySection
                    }

                    // Reporter section
                    if metadata["reporter_name"] != nil || metadata["reporter_email"] != nil || metadata["feedback_type"] != nil {
                        reporterSection
                    }

                    // Analysis section (omi-analytics)
                    if metadata["original_message"] != nil || metadata["creation_reason"] != nil || metadata["key_findings"] != nil || metadata["search_summary"] != nil {
                        analysisSection
                    }

                    // App Info section (sentry)
                    if metadata["app_version"] != nil || metadata["os"] != nil || metadata["device_model"] != nil {
                        appInfoSection
                    }

                    // Source section (screenshot metadata)
                    if metadata["source_app"] != nil || metadata["confidence"] != nil || metadata["inferred_deadline"] != nil || metadata["window_title"] != nil {
                        sourceSection
                    }

                    // Catch-all: render any metadata keys not covered by sections above
                    if !remainingMetadata.isEmpty {
                        remainingMetadataSection
                    }
                }
                .padding(20)
            }
        }
        .frame(width: 550, height: 600)
        .background(OmiColors.backgroundPrimary)
    }

    // MARK: - Header

    private var header: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text("Task Details")
                    .scaledFont(size: 16, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                if let source = task.source {
                    Text(source)
                        .scaledFont(size: 11, weight: .medium)
                        .foregroundColor(OmiColors.textTertiary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(
                            RoundedRectangle(cornerRadius: 4)
                                .fill(OmiColors.backgroundSecondary)
                        )
                }
            }

            Spacer()

            DismissButton(action: dismissSheet)
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 16)
    }

    // MARK: - Task Info

    private var taskInfoSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            sectionHeader("Task")

            Text(task.description)
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textPrimary)
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(OmiColors.backgroundSecondary)
                )
        }
    }

    // MARK: - Core Fields

    private var coreFieldsSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            sectionHeader("Details")

            VStack(alignment: .leading, spacing: 6) {
                if let category = task.category {
                    detailRow("Category", category.capitalized)
                }
                if !task.tags.isEmpty {
                    detailRow("Tags", task.tags.joined(separator: ", "))
                }
                if let priority = task.priority {
                    detailRow("Priority", priority.capitalized)
                }
                detailRow("Status", task.completed ? "Completed" : "Active")
                if let source = task.source {
                    detailRow("Source", "\(task.sourceLabel) (\(source))")
                }
                if let app = task.sourceApp {
                    detailRow("Source App", app)
                }
                if let window = task.windowTitle {
                    detailRow("Window", window)
                }
                detailRow("Created", {
                    let f = DateFormatter()
                    f.dateStyle = .medium
                    f.timeStyle = .short
                    return f.string(from: task.createdAt)
                }())
                if let dueAt = task.dueAt {
                    detailRow("Due", {
                        let f = DateFormatter()
                        f.dateStyle = .medium
                        f.timeStyle = .short
                        return f.string(from: dueAt)
                    }())
                }
                if let completedAt = task.completedAt {
                    detailRow("Completed", {
                        let f = DateFormatter()
                        f.dateStyle = .medium
                        f.timeStyle = .short
                        return f.string(from: completedAt)
                    }())
                }
                if let goalId = task.goalId {
                    detailRow("Goal", goalId)
                }
                if let convId = task.conversationId {
                    detailRow("Conversation", convId)
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(OmiColors.backgroundSecondary)
            )
        }
    }

    // MARK: - Agent

    private var agentSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            sectionHeader("Agent")

            VStack(alignment: .leading, spacing: 6) {
                if let status = task.agentStatus {
                    detailRow("Status", status.capitalized)
                }
                if let files = task.agentEditedFiles, !files.isEmpty {
                    detailBlock("Edited Files", files.joined(separator: "\n"))
                }
                if let plan = task.agentPlan, !plan.isEmpty {
                    detailBlock("Plan", String(plan.prefix(2000)))
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(OmiColors.backgroundSecondary)
            )
        }
    }

    // MARK: - Sentry

    private var sentrySection: some View {
        VStack(alignment: .leading, spacing: 8) {
            sectionHeader("Sentry")

            VStack(alignment: .leading, spacing: 6) {
                if let issueId = metadata["sentry_issue_id"] as? String {
                    detailRow("Issue ID", issueId)
                }

                if let urlString = metadata["sentry_issue_url"] as? String,
                   let url = URL(string: urlString) {
                    HStack {
                        Text("Link")
                            .scaledFont(size: 12, weight: .medium)
                            .foregroundColor(OmiColors.textSecondary)
                            .frame(width: 100, alignment: .leading)

                        Button {
                            NSWorkspace.shared.open(url)
                        } label: {
                            HStack(spacing: 4) {
                                Text("Open in Sentry")
                                    .scaledFont(size: 12)
                                Image(systemName: "arrow.up.right.square")
                                    .scaledFont(size: 10)
                            }
                            .foregroundColor(.blue)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(OmiColors.backgroundSecondary)
            )
        }
    }

    // MARK: - Reporter

    private var reporterSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            sectionHeader("Reporter")

            VStack(alignment: .leading, spacing: 6) {
                if let name = metadata["reporter_name"] as? String {
                    detailRow("Name", name)
                }
                if let email = metadata["reporter_email"] as? String {
                    detailRow("Email", email)
                }
                if let type = metadata["feedback_type"] as? String {
                    detailRow("Type", type.capitalized)
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(OmiColors.backgroundSecondary)
            )
        }
    }

    // MARK: - Analysis (omi-analytics)

    private var analysisSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            sectionHeader("Analysis")

            VStack(alignment: .leading, spacing: 10) {
                if let reason = metadata["creation_reason"] as? String {
                    detailBlock("Reason", reason)
                }
                if let original = metadata["original_message"] as? String {
                    detailBlock("Original Message", original)
                }
                if let findings = metadata["key_findings"] as? String {
                    detailBlock("Key Findings", findings)
                } else if let findings = metadata["key_findings"] as? [String] {
                    detailBlock("Key Findings", findings.joined(separator: "\n"))
                }
                if let summary = metadata["search_summary"] as? String {
                    detailBlock("Search Summary", summary)
                }
                if let files = metadata["relevant_files"] as? [String] {
                    detailBlock("Relevant Files", files.joined(separator: "\n"))
                } else if let files = metadata["relevant_files"] as? String {
                    detailBlock("Relevant Files", files)
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(OmiColors.backgroundSecondary)
            )
        }
    }

    // MARK: - Context (screenshot)

    private var contextSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            sectionHeader("Context")

            VStack(alignment: .leading, spacing: 10) {
                // Prefer direct task fields, fall back to metadata
                if let summary = task.contextSummary ?? metadata["context_summary"] as? String {
                    detailBlock("Summary", summary)
                }
                if let activity = task.currentActivity ?? metadata["current_activity"] as? String {
                    detailBlock("Current Activity", activity)
                }
                if let reasoning = metadata["reasoning"] as? String {
                    detailBlock("Reasoning", reasoning)
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(OmiColors.backgroundSecondary)
            )
        }
    }

    // MARK: - App Info (sentry)

    private var appInfoSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            sectionHeader("App Info")

            VStack(alignment: .leading, spacing: 6) {
                if let version = metadata["app_version"] as? String {
                    detailRow("Version", version)
                }
                if let build = metadata["app_build"] as? String {
                    detailRow("Build", build)
                }
                if let os = metadata["os"] as? String {
                    detailRow("OS", os)
                }
                if let device = metadata["device_model"] as? String {
                    detailRow("Device", device)
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(OmiColors.backgroundSecondary)
            )
        }
    }

    // MARK: - Source (screenshot)

    private var sourceSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            sectionHeader("Source")

            VStack(alignment: .leading, spacing: 6) {
                if let app = metadata["source_app"] as? String {
                    detailRow("App", app)
                }
                if let confidence = metadata["confidence"] as? Double {
                    detailRow("Confidence", "\(Int(confidence * 100))%")
                }
                if let deadline = metadata["inferred_deadline"] as? String {
                    detailRow("Deadline", deadline)
                }
                if let window = metadata["window_title"] as? String {
                    detailRow("Window", window)
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(OmiColors.backgroundSecondary)
            )
        }
    }

    // MARK: - Remaining Metadata (catch-all)

    /// Keys already rendered by dedicated sections above
    private static let handledMetadataKeys: Set<String> = [
        // Core fields section (shown via task properties)
        "tags", "source_app", "window_title", "confidence",
        "source_category", "source_subcategory",
        // Context section
        "context_summary", "current_activity", "reasoning",
        // Sentry section
        "sentry_issue_url", "sentry_issue_id",
        // Reporter section
        "reporter_name", "reporter_email", "feedback_type",
        // Analysis section
        "original_message", "creation_reason", "key_findings",
        "search_summary", "relevant_files",
        // App Info section
        "app_version", "app_build", "os", "device_model",
        // Source section
        "inferred_deadline",
    ]

    /// Metadata entries not handled by any dedicated section
    private var remainingMetadata: [(key: String, value: String)] {
        guard let meta = task.parsedMetadata else { return [] }
        return meta
            .filter { !Self.handledMetadataKeys.contains($0.key) }
            .compactMap { entry in
                let display: String
                if let str = entry.value as? String, !str.isEmpty {
                    display = str
                } else if let num = entry.value as? NSNumber {
                    display = num.stringValue
                } else if let arr = entry.value as? [String] {
                    display = arr.joined(separator: "\n")
                } else {
                    return nil
                }
                return (key: entry.key, value: display)
            }
            .sorted { $0.key < $1.key }
    }

    private var remainingMetadataSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            sectionHeader("Other Info")

            VStack(alignment: .leading, spacing: 10) {
                ForEach(remainingMetadata, id: \.key) { entry in
                    let label = entry.key
                        .replacingOccurrences(of: "_", with: " ")
                        .capitalized
                    if entry.value.count > 80 || entry.value.contains("\n") {
                        detailBlock(label, entry.value)
                    } else {
                        detailRow(label, entry.value)
                    }
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(OmiColors.backgroundSecondary)
            )
        }
    }

    // MARK: - Helpers

    private func sectionHeader(_ title: String) -> some View {
        Text(title)
            .scaledFont(size: 13, weight: .semibold)
            .foregroundColor(OmiColors.textSecondary)
    }

    private func detailRow(_ label: String, _ value: String) -> some View {
        HStack(alignment: .top) {
            Text(label)
                .scaledFont(size: 12, weight: .medium)
                .foregroundColor(OmiColors.textSecondary)
                .frame(width: 100, alignment: .leading)

            Text(value)
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textPrimary)
                .textSelection(.enabled)
                .if_available_writingToolsNone()
        }
    }

    private func detailBlock(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .scaledFont(size: 12, weight: .medium)
                .foregroundColor(OmiColors.textSecondary)

            Text(value)
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textPrimary)
                .textSelection(.enabled)
                .if_available_writingToolsNone()
        }
    }
}
