import SwiftUI

// MARK: - Task Detail Button

/// Small inline info button shown on task rows that have rich metadata
struct TaskDetailButton: View {
    @Binding var showDetail: Bool

    var body: some View {
        Button {
            showDetail = true
        } label: {
            Image(systemName: "info.circle")
                .font(.system(size: 10))
                .foregroundColor(OmiColors.textTertiary)
                .frame(width: 20, height: 20)
        }
        .buttonStyle(.plain)
        .help("View Task Details")
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

                    // Context section (screenshot)
                    if metadata["context_summary"] != nil || metadata["current_activity"] != nil || metadata["reasoning"] != nil {
                        contextSection
                    }

                    // App Info section (sentry)
                    if metadata["app_version"] != nil || metadata["os"] != nil || metadata["device_model"] != nil {
                        appInfoSection
                    }

                    // Source section (screenshot)
                    if metadata["source_app"] != nil || metadata["confidence"] != nil || metadata["inferred_deadline"] != nil || metadata["window_title"] != nil {
                        sourceSection
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
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(OmiColors.textPrimary)

                if let source = task.source {
                    Text(source)
                        .font(.system(size: 11, weight: .medium))
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
                .font(.system(size: 14))
                .foregroundColor(OmiColors.textPrimary)
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
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(OmiColors.textSecondary)
                            .frame(width: 100, alignment: .leading)

                        Button {
                            NSWorkspace.shared.open(url)
                        } label: {
                            HStack(spacing: 4) {
                                Text("Open in Sentry")
                                    .font(.system(size: 12))
                                Image(systemName: "arrow.up.right.square")
                                    .font(.system(size: 10))
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
                if let summary = metadata["context_summary"] as? String {
                    detailBlock("Summary", summary)
                }
                if let activity = metadata["current_activity"] as? String {
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

    // MARK: - Helpers

    private func sectionHeader(_ title: String) -> some View {
        Text(title)
            .font(.system(size: 13, weight: .semibold))
            .foregroundColor(OmiColors.textSecondary)
    }

    private func detailRow(_ label: String, _ value: String) -> some View {
        HStack(alignment: .top) {
            Text(label)
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(OmiColors.textSecondary)
                .frame(width: 100, alignment: .leading)

            Text(value)
                .font(.system(size: 12))
                .foregroundColor(OmiColors.textPrimary)
                .textSelection(.enabled)
                .if_available_writingToolsNone()
        }
    }

    private func detailBlock(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(OmiColors.textSecondary)

            Text(value)
                .font(.system(size: 12))
                .foregroundColor(OmiColors.textPrimary)
                .textSelection(.enabled)
                .if_available_writingToolsNone()
        }
    }
}
