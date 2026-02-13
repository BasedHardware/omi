import SwiftUI

// MARK: - Advice View Model

@MainActor
class AdviceViewModel: ObservableObject {
    @Published var selectedCategory: AdviceCategory? = nil
    @Published var searchText = ""
    @Published var showDismissed = false

    private let storage = AdviceStorage.shared

    var filteredAdvice: [StoredAdvice] {
        var result = showDismissed ? storage.adviceHistory : storage.visibleAdvice

        // Filter by category
        if let category = selectedCategory {
            result = result.filter { $0.advice.category == category }
        }

        // Filter by search text
        if !searchText.isEmpty {
            result = result.filter {
                $0.advice.advice.localizedCaseInsensitiveContains(searchText) ||
                $0.contextSummary.localizedCaseInsensitiveContains(searchText) ||
                $0.currentActivity.localizedCaseInsensitiveContains(searchText)
            }
        }

        return result
    }

    var totalCount: Int {
        storage.visibleAdvice.count
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

    func dismissAdvice(_ id: String) {
        storage.dismissAdvice(id)
        objectWillChange.send()
    }

    func deleteAdvice(_ id: String) {
        storage.deleteAdvice(id)
        objectWillChange.send()
    }

    func clearAll() {
        storage.clearAll()
        objectWillChange.send()
    }

    func countForCategory(_ category: AdviceCategory?) -> Int {
        let base = showDismissed ? storage.adviceHistory : storage.visibleAdvice
        if let category = category {
            return base.filter { $0.advice.category == category }.count
        }
        return base.count
    }
}

// MARK: - Advice Page

struct AdvicePage: View {
    @StateObject private var viewModel = AdviceViewModel()
    @ObservedObject private var storage = AdviceStorage.shared
    @State private var selectedAdvice: StoredAdvice? = nil
    @State private var showClearConfirmation = false

    var body: some View {
        VStack(spacing: 0) {
            // Header
            header

            // Filter bar
            filterBar

            // Content
            if storage.adviceHistory.isEmpty {
                emptyState
            } else if viewModel.filteredAdvice.isEmpty {
                noResultsView
            } else {
                adviceList
            }
        }
        .background(Color.clear)
        .dismissableSheet(item: $selectedAdvice) { advice in
            adviceDetailSheet(advice)
                .frame(width: 450, height: 500)
        }
        .confirmationDialog(
            "Clear All Advice",
            isPresented: $showClearConfirmation,
            titleVisibility: .visible
        ) {
            Button("Clear All", role: .destructive) {
                viewModel.clearAll()
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Are you sure you want to clear all advice history? This cannot be undone.")
        }
        .onAppear {
            // Advice uses local storage, so it's immediately ready
            NotificationCenter.default.post(name: .advicePageDidLoad, object: nil)
        }
    }

    // MARK: - Header

    private var header: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text("Advice")
                    .font(.system(size: 24, weight: .semibold))
                    .foregroundColor(OmiColors.textPrimary)

                HStack(spacing: 8) {
                    Text("\(viewModel.totalCount) tips")
                        .font(.system(size: 13))
                        .foregroundColor(OmiColors.textTertiary)

                    if viewModel.unreadCount > 0 {
                        Text("\(viewModel.unreadCount) new")
                            .font(.system(size: 12, weight: .medium))
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
                        .font(.system(size: 13))
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
                    .disabled(storage.adviceHistory.isEmpty)
                } label: {
                    Image(systemName: "ellipsis.circle")
                        .font(.system(size: 18))
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

                TextField("Search advice...", text: $viewModel.searchText)
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

                    ForEach(AdviceCategory.allCases, id: \.self) { category in
                        categoryTab(category, category.displayName)
                    }
                }
            }
        }
        .padding(.horizontal, 24)
        .padding(.bottom, 16)
    }

    private func categoryTab(_ category: AdviceCategory?, _ title: String) -> some View {
        let isSelected = viewModel.selectedCategory == category
        let count = viewModel.countForCategory(category)

        return Button {
            viewModel.selectedCategory = category
        } label: {
            HStack(spacing: 6) {
                if let cat = category {
                    Image(systemName: cat.icon)
                        .font(.system(size: 11))
                }

                Text(title)
                    .font(.system(size: 13, weight: isSelected ? .semibold : .regular))

                if count > 0 {
                    Text("\(count)")
                        .font(.system(size: 11, weight: .medium))
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

    // MARK: - Advice List

    private var adviceList: some View {
        ScrollView {
            LazyVStack(spacing: 12) {
                ForEach(viewModel.filteredAdvice) { advice in
                    AdviceCard(
                        advice: advice,
                        onTap: {
                            viewModel.markAsRead(advice.id)
                            selectedAdvice = advice
                        },
                        onDismiss: {
                            viewModel.dismissAdvice(advice.id)
                        },
                        onDelete: {
                            viewModel.deleteAdvice(advice.id)
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
                .font(.system(size: 48))
                .foregroundColor(OmiColors.textTertiary)

            Text("No Advice Yet")
                .font(.system(size: 20, weight: .semibold))
                .foregroundColor(OmiColors.textPrimary)

            Text("Proactive advice from your AI assistant will appear here.\nMake sure the Advice Assistant is enabled in Settings.")
                .font(.system(size: 14))
                .foregroundColor(OmiColors.textTertiary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)

            // Info about where to enable
            HStack(spacing: 8) {
                Image(systemName: "info.circle")
                    .font(.system(size: 13))
                Text("Go to Settings > Proactive Assistants to configure")
                    .font(.system(size: 13))
            }
            .foregroundColor(OmiColors.textTertiary)
            .padding(.top, 8)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var noResultsView: some View {
        VStack(spacing: 12) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 36))
                .foregroundColor(OmiColors.textTertiary)

            Text("No Results")
                .font(.system(size: 18, weight: .semibold))
                .foregroundColor(OmiColors.textPrimary)

            Text("Try a different search or filter")
                .font(.system(size: 14))
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

    private func adviceDetailSheet(_ advice: StoredAdvice) -> some View {
        VStack(alignment: .leading, spacing: 20) {
            // Header
            HStack {
                HStack(spacing: 8) {
                    Image(systemName: advice.advice.category.icon)
                        .font(.system(size: 14))
                    Text(advice.advice.category.displayName)
                        .font(.system(size: 14, weight: .medium))
                }
                .foregroundColor(categoryColor(advice.advice.category))
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(categoryColor(advice.advice.category).opacity(0.15))
                .cornerRadius(6)

                Spacer()

                Button {
                    selectedAdvice = nil
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 20))
                        .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
            }

            // Main advice
            Text(advice.advice.advice)
                .font(.system(size: 18, weight: .medium))
                .foregroundColor(OmiColors.textPrimary)
                .fixedSize(horizontal: false, vertical: true)

            // Reasoning
            if let reasoning = advice.advice.reasoning {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Why this advice?")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(OmiColors.textTertiary)
                        .textCase(.uppercase)

                    Text(reasoning)
                        .font(.system(size: 14))
                        .foregroundColor(OmiColors.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(12)
                .background(OmiColors.backgroundTertiary)
                .cornerRadius(8)
            }

            // Context
            VStack(alignment: .leading, spacing: 12) {
                Text("Context")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(OmiColors.textTertiary)
                    .textCase(.uppercase)

                VStack(alignment: .leading, spacing: 8) {
                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: "app.fill")
                            .font(.system(size: 12))
                            .foregroundColor(OmiColors.textTertiary)
                            .frame(width: 16)

                        Text(advice.advice.sourceApp)
                            .font(.system(size: 14))
                            .foregroundColor(OmiColors.textSecondary)
                    }

                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: "figure.walk")
                            .font(.system(size: 12))
                            .foregroundColor(OmiColors.textTertiary)
                            .frame(width: 16)

                        Text(advice.currentActivity)
                            .font(.system(size: 14))
                            .foregroundColor(OmiColors.textSecondary)
                    }

                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: "doc.text")
                            .font(.system(size: 12))
                            .foregroundColor(OmiColors.textTertiary)
                            .frame(width: 16)

                        Text(advice.contextSummary)
                            .font(.system(size: 14))
                            .foregroundColor(OmiColors.textSecondary)
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
                        .font(.system(size: 11))
                    Text("\(Int(advice.advice.confidence * 100))% confidence")
                        .font(.system(size: 12))
                }
                .foregroundColor(OmiColors.textTertiary)

                Spacer()

                // Date
                Text(formatDate(advice.createdAt))
                    .font(.system(size: 12))
                    .foregroundColor(OmiColors.textTertiary)
            }
        }
        .padding(24)
        .frame(width: 450)
        .background(OmiColors.backgroundSecondary)
    }

    // MARK: - Helpers

    private func categoryColor(_ category: AdviceCategory) -> Color {
        return OmiColors.textSecondary
    }

    private func formatDate(_ date: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return formatter.localizedString(for: date, relativeTo: Date())
    }
}

// MARK: - Advice Card

struct AdviceCard: View {
    let advice: StoredAdvice
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

                    Image(systemName: advice.advice.category.icon)
                        .font(.system(size: 16))
                        .foregroundColor(categoryColor)
                }

                // Content
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        // Unread indicator
                        if !advice.isRead {
                            Circle()
                                .fill(OmiColors.textPrimary)
                                .frame(width: 8, height: 8)
                        }

                        Text(advice.advice.advice)
                            .font(.system(size: 14, weight: advice.isRead ? .regular : .medium))
                            .foregroundColor(OmiColors.textPrimary)
                            .lineLimit(2)
                            .multilineTextAlignment(.leading)

                        Spacer()
                    }

                    HStack(spacing: 12) {
                        // Source app
                        HStack(spacing: 4) {
                            Image(systemName: "app.fill")
                                .font(.system(size: 10))
                            Text(advice.advice.sourceApp)
                                .font(.system(size: 11))
                        }
                        .foregroundColor(OmiColors.textTertiary)

                        // Confidence
                        HStack(spacing: 4) {
                            Image(systemName: "chart.bar.fill")
                                .font(.system(size: 10))
                            Text("\(Int(advice.advice.confidence * 100))%")
                                .font(.system(size: 11))
                        }
                        .foregroundColor(OmiColors.textTertiary)

                        Spacer()

                        // Date
                        Text(formatDate(advice.createdAt))
                            .font(.system(size: 11))
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
                                .font(.system(size: 14))
                                .foregroundColor(OmiColors.textTertiary)
                        }
                        .buttonStyle(.plain)
                        .help("Dismiss")

                        Button {
                            showDeleteConfirmation = true
                        } label: {
                            Image(systemName: "trash")
                                .font(.system(size: 14))
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
                        advice.isDismissed ? OmiColors.textTertiary.opacity(0.3) : Color.clear,
                        lineWidth: 1
                    )
            )
            .opacity(advice.isDismissed ? 0.6 : 1.0)
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
            "Delete Advice",
            isPresented: $showDeleteConfirmation,
            titleVisibility: .visible
        ) {
            Button("Delete", role: .destructive) {
                onDelete()
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Are you sure you want to delete this advice?")
        }
    }

    private func formatDate(_ date: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return formatter.localizedString(for: date, relativeTo: Date())
    }
}

#Preview {
    AdvicePage()
        .frame(width: 800, height: 600)
        .background(OmiColors.backgroundPrimary)
}
