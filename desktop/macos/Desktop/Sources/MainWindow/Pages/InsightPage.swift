import OmiTheme
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
        $0.insight.insight.localizedCaseInsensitiveContains(searchText)
          || $0.contextSummary.localizedCaseInsensitiveContains(searchText)
          || $0.currentActivity.localizedCaseInsensitiveContains(searchText)
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
  @Environment(\.sbTheme) private var sb

  private let contentMaxWidth: CGFloat = 820

  var body: some View {
    VStack(spacing: 0) {
      // Fixed top: header + search + filter chips
      VStack(spacing: 18) {
        header
        filterBar
      }
      .frame(maxWidth: contentMaxWidth, alignment: .leading)
      .frame(maxWidth: .infinity)
      .padding(.horizontal, 28)
      .padding(.top, 24)
      .padding(.bottom, 16)

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
    HStack(alignment: .firstTextBaseline) {
      VStack(alignment: .leading, spacing: 6) {
        Text("Insights")
          .geist(size: 28, weight: .semibold, tracking: 28 * -0.02)
          .foregroundStyle(sb.ink)

        HStack(spacing: 8) {
          Text("\(viewModel.totalCount.formatted()) insights")
            .geistMono(size: 12.5, tracking: 0)
            .foregroundStyle(sb.ink(.w35))

          if viewModel.unreadCount > 0 {
            Text("\(viewModel.unreadCount) new")
              .geistMono(size: 11.5, weight: .medium, tracking: 0)
              .foregroundStyle(sb.ink)
              .padding(.horizontal, 8)
              .padding(.vertical, 2)
              .background(
                Capsule().fill(sb.ink(.w12))
              )
          }
        }
      }

      Spacer(minLength: 12)

      // Actions
      HStack(spacing: 12) {
        if viewModel.unreadCount > 0 {
          SBOutlineButton(title: "Mark all read", size: 13) {
            viewModel.markAllAsRead()
          }
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
          Image(systemName: "ellipsis")
            .font(.system(size: 15, weight: .semibold))
            .foregroundStyle(sb.ink(.w55))
            .frame(width: 34, height: 34)
            .background(
              RoundedRectangle(cornerRadius: 9, style: .continuous)
                .stroke(sb.ink(.w12), lineWidth: 1)
            )
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
      }
    }
  }

  // MARK: - Filter Bar

  private var filterBar: some View {
    VStack(spacing: 14) {
      // Search field
      HStack(spacing: 10) {
        Image(systemName: "magnifyingglass")
          .font(.system(size: 13, weight: .medium))
          .foregroundStyle(sb.ink(.w35))

        ZStack(alignment: .leading) {
          if viewModel.searchText.isEmpty {
            Text("Search insights…")
              .geist(size: 14)
              .foregroundStyle(sb.ink(.w35))
          }
          TextField("", text: $viewModel.searchText)
            .textFieldStyle(.plain)
            .geist(size: 14)
            .foregroundStyle(sb.ink)
        }

        if !viewModel.searchText.isEmpty {
          Button {
            viewModel.searchText = ""
          } label: {
            Image(systemName: "xmark.circle.fill")
              .font(.system(size: 13))
              .foregroundStyle(sb.ink(.w35))
          }
          .buttonStyle(.plain)
        }
      }
      .padding(.horizontal, 12)
      .padding(.vertical, 10)
      .background(
        RoundedRectangle(cornerRadius: 10, style: .continuous)
          .fill(sb.ink(.w06))
      )
      .overlay(
        RoundedRectangle(cornerRadius: 10, style: .continuous)
          .stroke(sb.ink(.w12), lineWidth: 1)
      )

      // Category chips
      ScrollView(.horizontal, showsIndicators: false) {
        HStack(spacing: 8) {
          categoryChip(nil, "All")

          ForEach(InsightCategory.allCases, id: \.self) { category in
            categoryChip(category, category.displayName)
          }
        }
        .padding(.vertical, 1)
      }
    }
  }

  private func categoryChip(_ category: InsightCategory?, _ title: String) -> some View {
    let isSelected = viewModel.selectedCategory == category
    let count = viewModel.countForCategory(category)

    return Button {
      viewModel.selectedCategory = category
    } label: {
      HStack(spacing: 7) {
        Text(title)
          .geist(size: 13, weight: isSelected ? .medium : .regular)
          .foregroundStyle(isSelected ? sb.ink : sb.ink(.w55))

        if count > 0 {
          Text("\(count)")
            .geistMono(size: 11, tracking: 0)
            .foregroundStyle(isSelected ? sb.ink(.w7) : sb.ink(.w35))
        }
      }
      .padding(.horizontal, 12)
      .padding(.vertical, 7)
      .background(
        RoundedRectangle(cornerRadius: 8, style: .continuous)
          .fill(isSelected ? sb.ink(.w12) : sb.ink(.w06))
      )
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
      .frame(maxWidth: contentMaxWidth)
      .frame(maxWidth: .infinity)
      .padding(.horizontal, 28)
      .padding(.top, 4)
      .padding(.bottom, 32)
    }
  }

  // MARK: - Empty States

  private var emptyState: some View {
    VStack(spacing: 16) {
      Image(systemName: "lightbulb")
        .font(.system(size: 40, weight: .light))
        .foregroundStyle(sb.ink(.w25))

      Text("No insights yet")
        .geist(size: 17, weight: .semibold)
        .foregroundStyle(sb.ink(.w85))

      Text(
        "Proactive insights from Omi will appear here as you work.\nEnable the Insight Assistant to start seeing them."
      )
      .geist(size: 13.5)
      .foregroundStyle(sb.ink(.w45))
      .multilineTextAlignment(.center)
      .lineSpacing(2)

      HStack(spacing: 7) {
        Image(systemName: "gearshape")
          .font(.system(size: 12))
        Text("Settings → Proactive Assistants")
          .geist(size: 12.5)
      }
      .foregroundStyle(sb.ink(.w35))
      .padding(.top, 4)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .padding(.horizontal, 40)
  }

  private var noResultsView: some View {
    VStack(spacing: 14) {
      Image(systemName: "magnifyingglass")
        .font(.system(size: 32, weight: .light))
        .foregroundStyle(sb.ink(.w25))

      Text("No results")
        .geist(size: 16, weight: .semibold)
        .foregroundStyle(sb.ink(.w85))

      Text("Try a different search or filter.")
        .geist(size: 13.5)
        .foregroundStyle(sb.ink(.w45))

      if viewModel.selectedCategory != nil || !viewModel.searchText.isEmpty {
        SBOutlineButton(title: "Clear filters", size: 13) {
          viewModel.selectedCategory = nil
          viewModel.searchText = ""
        }
        .padding(.top, 4)
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
            .font(.system(size: 12, weight: .medium))
          Text(insight.insight.category.displayName)
            .geist(size: 12.5, weight: .medium)
        }
        .foregroundStyle(sb.ink(.w7))
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(
          RoundedRectangle(cornerRadius: 8, style: .continuous)
            .fill(sb.ink(.w06))
        )

        Spacer()

        Button {
          selectedInsight = nil
        } label: {
          Image(systemName: "xmark.circle.fill")
            .font(.system(size: 18))
            .foregroundStyle(sb.ink(.w35))
        }
        .buttonStyle(.plain)
      }

      // Main advice
      Text(insight.insight.insight)
        .geist(size: 16, weight: .medium)
        .foregroundStyle(sb.ink(.w9))
        .lineSpacing(3)
        .textSelection(.enabled)
        .fixedSize(horizontal: false, vertical: true)

      // Reasoning
      if let reasoning = insight.insight.reasoning {
        VStack(alignment: .leading, spacing: 8) {
          SBSectionLabel(text: "Why this insight")

          Text(reasoning)
            .geist(size: 13.5)
            .foregroundStyle(sb.ink(.w7))
            .lineSpacing(2)
            .textSelection(.enabled)
            .fixedSize(horizontal: false, vertical: true)
        }
        .padding(14)
        .sbCard(radius: 12)
      }

      // Context
      VStack(alignment: .leading, spacing: 12) {
        SBSectionLabel(text: "Context")

        VStack(alignment: .leading, spacing: 10) {
          contextRow("app", insight.insight.sourceApp)
          contextRow("figure.walk", insight.currentActivity)
          contextRow("doc.text", insight.contextSummary)
        }
      }
      .padding(14)
      .sbCard(radius: 12)

      Spacer(minLength: 0)

      // Footer
      HStack {
        HStack(spacing: 5) {
          Image(systemName: "chart.bar")
            .font(.system(size: 11))
          Text("\(Int(insight.insight.confidence * 100))% confidence")
            .geistMono(size: 11.5, tracking: 0)
        }
        .foregroundStyle(sb.ink(.w35))

        Spacer()

        Text(formatDate(insight.createdAt))
          .geistMono(size: 11.5, tracking: 0)
          .foregroundStyle(sb.ink(.w35))
      }
    }
    .padding(24)
    .frame(width: 450)
    .background(sb.background)
  }

  private func contextRow(_ icon: String, _ text: String) -> some View {
    HStack(alignment: .top, spacing: 10) {
      Image(systemName: icon)
        .font(.system(size: 12))
        .foregroundStyle(sb.ink(.w35))
        .frame(width: 16)

      Text(text)
        .geist(size: 13.5)
        .foregroundStyle(sb.ink(.w7))
        .textSelection(.enabled)
        .fixedSize(horizontal: false, vertical: true)
    }
  }

  // MARK: - Helpers

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
  @Environment(\.sbTheme) private var sb

  var body: some View {
    Button(action: onTap) {
      HStack(alignment: .top, spacing: 14) {
        // Category icon tile
        ZStack {
          RoundedRectangle(cornerRadius: 9, style: .continuous)
            .fill(sb.ink(.w06))
            .frame(width: 36, height: 36)

          Image(systemName: insight.insight.category.icon)
            .font(.system(size: 15, weight: .medium))
            .foregroundStyle(sb.ink(.w45))
        }

        // Content
        VStack(alignment: .leading, spacing: 6) {
          HStack(alignment: .top, spacing: 8) {
            if !insight.isRead {
              Circle()
                .fill(sb.ink)
                .frame(width: 7, height: 7)
                .padding(.top, 6)
            }

            Text(insight.insight.insight)
              .geist(size: 15, weight: insight.isRead ? .regular : .medium)
              .foregroundStyle(sb.ink(.w9))
              .lineSpacing(2)
              .lineLimit(2)
              .multilineTextAlignment(.leading)

            Spacer(minLength: 0)
          }

          HStack(spacing: 10) {
            metaLabel("app", insight.insight.sourceApp)

            Text("·")
              .geistMono(size: 12, tracking: 0)
              .foregroundStyle(sb.ink(.w25))

            metaLabel("chart.bar", "\(Int(insight.insight.confidence * 100))%")

            Spacer(minLength: 8)

            Text(formatDate(insight.createdAt))
              .geistMono(size: 12, tracking: 0)
              .foregroundStyle(sb.ink(.w35))
          }
        }

        // Hover actions
        if isHovering {
          HStack(spacing: 6) {
            hoverAction("eye.slash", help: "Dismiss") { onDismiss() }
            hoverAction("trash", help: "Delete") { showDeleteConfirmation = true }
          }
          .transition(.opacity)
        }
      }
      .padding(16)
      .frame(maxWidth: .infinity, alignment: .leading)
      .sbCard(radius: 14, stroke: isHovering ? .w14 : .w09)
      .opacity(insight.isDismissed ? 0.55 : 1.0)
    }
    .buttonStyle(.plain)
    .animation(SBMotion.standard, value: isHovering)
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

  private func metaLabel(_ icon: String, _ text: String) -> some View {
    HStack(spacing: 4) {
      Image(systemName: icon)
        .font(.system(size: 10))
      Text(text)
        .geistMono(size: 12, tracking: 0)
    }
    .foregroundStyle(sb.ink(.w35))
  }

  private func hoverAction(_ icon: String, help: String, action: @escaping () -> Void) -> some View {
    Button(action: action) {
      Image(systemName: icon)
        .font(.system(size: 13))
        .foregroundStyle(sb.ink(.w45))
        .frame(width: 26, height: 26)
        .background(
          RoundedRectangle(cornerRadius: 7, style: .continuous)
            .fill(sb.ink(.w06))
        )
    }
    .buttonStyle(.plain)
    .help(help)
  }

  private func formatDate(_ date: Date) -> String {
    let formatter = RelativeDateTimeFormatter()
    formatter.unitsStyle = .abbreviated
    return formatter.localizedString(for: date, relativeTo: Date())
  }
}

#if canImport(PreviewsMacros)
  #Preview {
    InsightPage()
      .frame(width: 800, height: 600)
      .background(OmiColors.backgroundPrimary)
  }
#endif
