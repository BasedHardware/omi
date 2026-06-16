import SwiftUI

// MARK: - Insight View Model

@MainActor
class InsightViewModel: ObservableObject {
    @Published var selectedCategory: InsightCategory? = nil
    @Published var searchText = ""
    @Published var showDismissed = false

    private let storage = InsightStorage.shared

    var filteredInsights: [StoredInsight] {
        var result = showDismissed ? storage.insightHistory : storage.visibleInsights

        // Filter by category
        if let category = selectedCategory {
            result = result.filter { $0.insight.category == category }
        }

        // Filter by search text
        if !searchText.isEmpty {
            result = result.filter {
                $0.insight.insight.localizedCaseInsensitiveContains(searchText) ||
                $0.contextSummary.localizedCaseInsensitiveContains(searchText) ||
                $0.currentActivity.localizedCaseInsensitiveContains(searchText)
            }
        }

        return result
    }

    var totalCount: Int {
        storage.visibleInsights.count
    }

    var unreadCount: Int {
        storage.unreadCount
    }

    func markAsRead(_ id: String) {
        storage.markAsRead(id)
        objectWillChange.send()
    }

    func markAllAsRead() {
        storage.markAllAsRead()
        objectWillChange.send()
    }

    func dismissInsight(_ id: String) {
        storage.dismissInsight(id)
        objectWillChange.send()
    }

    func deleteInsight(_ id: String) {
        storage.deleteInsight(id)
        objectWillChange.send()
    }

    func clearAll() {
        storage.clearAll()
        objectWillChange.send()
    }

    func countForCategory(_ category: InsightCategory?) -> Int {
        let base = showDismissed ? storage.insightHistory : storage.visibleInsights
        if let category = category {
            return base.filter { $0.insight.category == category }.count
        }
        return base.count
    }
}

// MARK: - Insight Page

struct InsightPage: View {
    @StateObject private var viewModel = InsightViewModel()
    @ObservedObject private var storage = InsightStorage.shared
    @State private var selectedInsight: StoredInsight? = nil
    @State private var showClearConfirmation = false

    var body: some View {
        VStack(spacing: 0) {
            // Header
            header

            // Filter bar
            filterBar

            // Content
            if storage.insightHistory.isEmpty {
                emptyState
            } else if viewModel.filteredInsights.isEmpty {
                noResultsView
            } else {
                insightList
            }
        }
        .background(Color.clear)
        .dismissableSheet(item: $selectedInsight) { item in
            insightDetailSheet(item)
                .frame(width: 450, height: 500)
        }
        .confirmationDialog(
            "Clear All Insights",
            isPresented: $showClearConfirmation,
            titleVisibility: .visible
        ) {
            Button("Clear All", role: .destructive) {
                viewModel.clearAll()
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Are you sure you want to clear all insight history? This cannot be undone.")
        }
        .onAppear {
            // Advice uses local storage, so it's immediately ready
            NotificationCenter.default.post(name: .insightPageDidLoad, object: nil)
        }
    }

    // MARK: - Header

    private var header: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text("Insights")
                    .scaledFont(size: 24, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                HStack(spacing: 8) {
                    Text("\(viewModel.totalCount) insights")
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textTertiary)

                    if viewModel.unreadCount > 0 {
                        Text("\(viewModel.unreadCount) new")
                            .scaledFont(size: 12, weight: .medium)
                            .foregroundColor(OmiColors.textPrimary)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 2)
                            .background(OmiColors.textPrimary.opacity(0.15))
                            .cornerRadius(4)
                    }
                }
            }

            Spacer()

            // Actions
            HStack(spacing: 12) {
                if viewModel.unreadCount > 0 {
                    Button {
                        viewModel.markAllAsRead()
                    } label: {
                        HStack(spacing: 6) {
                            Image(systemName: "checkmark.circle")
                            Text("Mark All Read")
                        }
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textSecondary)
                    }
                    .buttonStyle(.plain)
                }

                Menu {
                    Toggle("Show Dismissed", isOn: $viewModel.showDismissed)

                    Divider()

                    Button(role: .destructive) {
                        showClearConfirmation = true
                    } label: {
                        Label("Clear All History", systemImage: "trash")
                    }
                    .disabled(storage.insightHistory.isEmpty)
                } label: {
                    Image(systemName: "ellipsis.circle")
                        .scaledFont(size: 18)
                        .foregroundColor(OmiColors.textSecondary)
                }
                .menuStyle(.borderlessButton)
            }
        }
        .padding(.horizontal, 24)
        .padding(.top, 20)
        .padding(.bottom, 16)
    }

    // MARK: - Filter Bar

    private var filterBar: some View {
        VStack(spacing: 12) {
            // Search field
            HStack(spacing: 10) {
                Image(systemName: "magnifyingglass")
                    .foregroundColor(OmiColors.textTertiary)

                TextField("Search insights...", text: $viewModel.searchText)
                    .textFieldStyle(.plain)
                    .foregroundColor(OmiColors.textPrimary)

                if !viewModel.searchText.isEmpty {
                    Button {
                        viewModel.searchText = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(OmiColors.textTertiary)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(OmiColors.backgroundTertiary)
            .cornerRadius(8)

            // Category tabs
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    categoryTab(nil, "All")

                    ForEach(InsightCategory.allCases, id: \.self) { category in
                        categoryTab(category, category.displayName)
                    }
                }
            }
        }
        .padding(.horizontal, 24)
        .padding(.bottom, 16)
    }

    private func categoryTab(_ category: InsightCategory?, _ title: String) -> some View {
        let isSelected = viewModel.selectedCategory == category
        let count = viewModel.countForCategory(category)

        return Button {
            viewModel.selectedCategory = category
        } label: {
            HStack(spacing: 6) {
                if let cat = category {
                    Image(systemName: cat.icon)
                        .scaledFont(size: 11)
                }

                Text(title)
                    .scaledFont(size: 13, weight: isSelected ? .semibold : .regular)

                if count > 0 {
                    Text("\(count)")
                        .scaledFont(size: 11, weight: .medium)
                        .foregroundColor(isSelected ? OmiColors.textPrimary : OmiColors.textTertiary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(
                            Capsule()
                                .fill(isSelected ? OmiColors.textPrimary.opacity(0.15) : OmiColors.textTertiary.opacity(0.1))
                        )
                }
            }
            .foregroundColor(isSelected ? OmiColors.textPrimary : OmiColors.textSecondary)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(isSelected ? OmiColors.textPrimary.opacity(0.15) : Color.clear)
            .cornerRadius(6)
        }
        .buttonStyle(.plain)
    }

    // MARK: - Insight List

    private var insightList: some View {
        ScrollView {
            LazyVStack(spacing: 12) {
                ForEach(viewModel.filteredInsights) { item in
                    InsightCard(
                        insight: item,
                        onTap: {
                            viewModel.markAsRead(item.id)
                            selectedInsight = item
                        },
                        onDismiss: {
                            viewModel.dismissInsight(item.id)
                        },
                        onDelete: {
                            viewModel.deleteInsight(item.id)
                        }
                    )
                }
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 24)
        }
    }

    // MARK: - Empty States

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "lightbulb.fill")
                .scaledFont(size: 48)
                .foregroundColor(OmiColors.textTertiary)

            Text("No Insights Yet")
                .scaledFont(size: 20, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

            Text("Proactive insights from your AI assistant will appear here.\nMake sure the Insight Assistant is enabled in Settings.")
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textTertiary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)

            // Info about where to enable
            HStack(spacing: 8) {
                Image(systemName: "info.circle")
                    .scaledFont(size: 13)
                Text("Go to Settings > Proactive Assistants to configure")
                    .scaledFont(size: 13)
            }
            .foregroundColor(OmiColors.textTertiary)
            .padding(.top, 8)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var noResultsView: some View {
        VStack(spacing: 12) {
            Image(systemName: "magnifyingglass")
                .scaledFont(size: 36)
                .foregroundColor(OmiColors.textTertiary)

            Text("No Results")
                .scaledFont(size: 18, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

            Text("Try a different search or filter")
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textTertiary)

            if viewModel.selectedCategory != nil || !viewModel.searchText.isEmpty {
                Button("Clear Filters") {
                    viewModel.selectedCategory = nil
                    viewModel.searchText = ""
                }
                .buttonStyle(.bordered)
                .tint(OmiColors.textSecondary)
                .padding(.top, 8)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Detail Sheet

    private func insightDetailSheet(_ insight: StoredInsight) -> some View {
        VStack(alignment: .leading, spacing: 20) {
            // Header
            HStack {
                HStack(spacing: 8) {
                    Image(systemName: insight.insight.category.icon)
                        .scaledFont(size: 14)
                    Text(insight.insight.category.displayName)
                        .scaledFont(size: 14, weight: .medium)
                }
                .foregroundColor(categoryColor(insight.insight.category))
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(categoryColor(insight.insight.category).opacity(0.15))
                .cornerRadius(6)

                Spacer()

                Button {
                    selectedInsight = nil
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .scaledFont(size: 20)
                        .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
            }

            // Main advice
            Text(insight.insight.insight)
                .scaledFont(size: 18, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)

            // Reasoning
            if let reasoning = insight.insight.reasoning {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Why this insight?")
                        .scaledFont(size: 12, weight: .semibold)
                        .foregroundColor(OmiColors.textTertiary)
                        .textCase(.uppercase)

                    Text(reasoning)
                        .scaledFont(size: 14)
                        .foregroundColor(OmiColors.textSecondary)
                        .textSelection(.enabled)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(12)
                .background(OmiColors.backgroundTertiary)
                .cornerRadius(8)
            }

            // Context
            VStack(alignment: .leading, spacing: 12) {
                Text("Context")
                    .scaledFont(size: 12, weight: .semibold)
                    .foregroundColor(OmiColors.textTertiary)
                    .textCase(.uppercase)

                VStack(alignment: .leading, spacing: 8) {
                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: "app.fill")
                            .scaledFont(size: 12)
                            .foregroundColor(OmiColors.textTertiary)
                            .frame(width: 16)

                        Text(insight.insight.sourceApp)
                            .scaledFont(size: 14)
                            .foregroundColor(OmiColors.textSecondary)
                            .textSelection(.enabled)
                    }

                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: "figure.walk")
                            .scaledFont(size: 12)
                            .foregroundColor(OmiColors.textTertiary)
                            .frame(width: 16)

                        Text(insight.currentActivity)
                            .scaledFont(size: 14)
                            .foregroundColor(OmiColors.textSecondary)
                            .textSelection(.enabled)
                    }

                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: "doc.text")
                            .scaledFont(size: 12)
                            .foregroundColor(OmiColors.textTertiary)
                            .frame(width: 16)

                        Text(insight.contextSummary)
                            .scaledFont(size: 14)
                            .foregroundColor(OmiColors.textSecondary)
                            .textSelection(.enabled)
                    }
                }
            }
            .padding(12)
            .background(OmiColors.backgroundTertiary)
            .cornerRadius(8)

            // Footer
            HStack {
                // Confidence
                HStack(spacing: 4) {
                    Image(systemName: "chart.bar.fill")
                        .scaledFont(size: 11)
                    Text("\(Int(insight.insight.confidence * 100))% confidence")
                        .scaledFont(size: 12)
                }
                .foregroundColor(OmiColors.textTertiary)

                Spacer()

                // Date
                Text(formatDate(insight.createdAt))
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textTertiary)
            }
        }
        .padding(24)
        .frame(width: 450)
        .background(OmiColors.backgroundSecondary)
    }

    // MARK: - Helpers

    private func categoryColor(_ category: InsightCategory) -> Color {
        return OmiColors.textSecondary
    }

    private func formatDate(_ date: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return formatter.localizedString(for: date, relativeTo: Date())
    }
}

// MARK: - Insight Card

struct InsightCard: View {
    let insight: StoredInsight
    let onTap: () -> Void
    let onDismiss: () -> Void
    let onDelete: () -> Void

    @State private var isHovering = false
    @State private var showDeleteConfirmation = false

    private var categoryColor: Color {
        return OmiColors.textSecondary
    }

    var body: some View {
        Button(action: onTap) {
            HStack(alignment: .top, spacing: 12) {
                // Category icon
                ZStack {
                    Circle()
                        .fill(categoryColor.opacity(0.15))
                        .frame(width: 36, height: 36)

                    Image(systemName: insight.insight.category.icon)
                        .scaledFont(size: 16)
                        .foregroundColor(categoryColor)
                }

                // Content
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        // Unread indicator
                        if !insight.isRead {
                            Circle()
                                .fill(OmiColors.textPrimary)
                                .frame(width: 8, height: 8)
                        }

                        Text(insight.insight.insight)
                            .scaledFont(size: 14, weight: insight.isRead ? .regular : .medium)
                            .foregroundColor(OmiColors.textPrimary)
                            .lineLimit(2)
                            .multilineTextAlignment(.leading)

                        Spacer()
                    }

                    HStack(spacing: 12) {
                        // Source app
                        HStack(spacing: 4) {
                            Image(systemName: "app.fill")
                                .scaledFont(size: 10)
                            Text(insight.insight.sourceApp)
                                .scaledFont(size: 11)
                        }
                        .foregroundColor(OmiColors.textTertiary)

                        // Confidence
                        HStack(spacing: 4) {
                            Image(systemName: "chart.bar.fill")
                                .scaledFont(size: 10)
                            Text("\(Int(insight.insight.confidence * 100))%")
                                .scaledFont(size: 11)
                        }
                        .foregroundColor(OmiColors.textTertiary)

                        Spacer()

                        // Date
                        Text(formatDate(insight.createdAt))
                            .scaledFont(size: 11)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                }

                // Actions (on hover)
                if isHovering {
                    HStack(spacing: 8) {
                        Button {
                            onDismiss()
                        } label: {
                            Image(systemName: "eye.slash")
                                .scaledFont(size: 14)
                                .foregroundColor(OmiColors.textTertiary)
                        }
                        .buttonStyle(.plain)
                        .help("Dismiss")

                        Button {
                            showDeleteConfirmation = true
                        } label: {
                            Image(systemName: "trash")
                                .scaledFont(size: 14)
                                .foregroundColor(OmiColors.textTertiary)
                        }
                        .buttonStyle(.plain)
                        .help("Delete")
                    }
                    .transition(.opacity)
                }
            }
            .padding(14)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(isHovering ? OmiColors.backgroundTertiary : OmiColors.backgroundTertiary.opacity(0.6))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(
                        insight.isDismissed ? OmiColors.textTertiary.opacity(0.3) : Color.clear,
                        lineWidth: 1
                    )
            )
            .opacity(insight.isDismissed ? 0.6 : 1.0)
        }
        .buttonStyle(.plain)
        .onHover { hovering in
            isHovering = hovering
            if hovering {
                NSCursor.pointingHand.push()
            } else {
                NSCursor.pop()
            }
        }
        .confirmationDialog(
            "Delete Insight",
            isPresented: $showDeleteConfirmation,
            titleVisibility: .visible
        ) {
            Button("Delete", role: .destructive) {
                onDelete()
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Are you sure you want to delete this insight?")
        }
    }

    private func formatDate(_ date: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return formatter.localizedString(for: date, relativeTo: Date())
    }
}

#Preview {
    InsightPage()
        .frame(width: 800, height: 600)
        .background(OmiColors.backgroundPrimary)
}
