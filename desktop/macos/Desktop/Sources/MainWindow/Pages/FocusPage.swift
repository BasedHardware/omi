import OmiTheme
import SwiftUI

// MARK: - Focus View Model

@MainActor
class FocusViewModel: ObservableObject {
  @Published var searchText = ""
  @Published var showHistorical = false
  @Published var isLoading = false

  private let storage = FocusStorage.shared
  private let settings = FocusAssistantSettings.shared

  var filteredSessions: [StoredFocusSession] {
    let base = showHistorical ? storage.sessions : storage.todaySessions

    guard !searchText.isEmpty else { return base }

    return base.filter {
      $0.appOrSite.localizedCaseInsensitiveContains(searchText)
        || $0.description.localizedCaseInsensitiveContains(searchText)
        || ($0.message?.localizedCaseInsensitiveContains(searchText) ?? false)
    }
  }

  var currentStatus: FocusStatus? {
    storage.currentStatus
  }

  var currentApp: String? {
    storage.currentApp
  }

  /// The detected app name (updated immediately on app switch, before analysis)
  var detectedAppName: String? {
    storage.detectedAppName
  }

  /// When the analysis delay period will end (nil if not in delay)
  var delayEndTime: Date? {
    storage.delayEndTime
  }

  /// When the analysis cooldown period will end (nil if not in cooldown)
  var cooldownEndTime: Date? {
    storage.cooldownEndTime
  }

  var stats: FocusDayStats {
    storage.todayStats
  }

  var isMonitoring: Bool {
    settings.isEnabled
  }

  var todayCount: Int {
    storage.todaySessions.count
  }

  func deleteSession(_ id: String) {
    storage.deleteSession(id)
    objectWillChange.send()
  }

  func clearAll() {
    storage.clearAll()
    objectWillChange.send()
  }

  func refresh(force: Bool = false) async {
    // Skip redundant reload if storage already has cached data
    // FocusStorage.init() already loads from UserDefaults + SQLite
    if !force && !storage.sessions.isEmpty {
      NotificationCenter.default.post(name: .focusPageDidLoad, object: nil)
      return
    }
    isLoading = true
    await storage.refreshFromBackend()
    await MainActor.run {
      isLoading = false
      objectWillChange.send()
      NotificationCenter.default.post(name: .focusPageDidLoad, object: nil)
    }
  }
}

// MARK: - Focus Page

struct FocusPage: View {
  @Environment(\.sbTheme) private var sb
  @StateObject private var viewModel = FocusViewModel()
  @ObservedObject private var storage = FocusStorage.shared
  @State private var showClearConfirmation = false
  @State private var currentTime = Date()

  // Timer to update countdown displays
  private let countdownTimer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

  var body: some View {
    focusContent
      .overlay {
        if viewModel.isLoading && storage.sessions.isEmpty {
          initialLoadingOverlay
        }
      }
  }

  /// Keep the page geometry in place during its first refresh. Replacing the
  /// whole page with a spinner makes the header and content jump into place.
  private var initialLoadingOverlay: some View {
    ZStack {
      Color.clear
      VStack(spacing: 14) {
        ProgressView()
          .scaleEffect(1.1)
          .tint(sb.ink(.w55))
        Text("Loading focus data…")
          .geist(size: 14)
          .foregroundStyle(sb.ink(.w45))
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .allowsHitTesting(false)
  }

  private var focusContent: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 30) {
        // Page header — title, monitoring status, actions
        header

        // Current status banner (detected app, delay, cooldown, or analyzed status)
        statusBanner

        // Today's summary stats
        statsSection

        // Top distractions (if any)
        if !viewModel.stats.topDistractions.isEmpty {
          topDistractionsSection
        }

        // Session history
        historySection
      }
      .frame(maxWidth: 760, alignment: .leading)
      .frame(maxWidth: .infinity)
      .padding(.top, 28)
      .padding(.horizontal, 28)
      .padding(.bottom, 40)
    }
    .background(Color.clear)
    .confirmationDialog(
      "Clear All History",
      isPresented: $showClearConfirmation,
      titleVisibility: .visible
    ) {
      Button("Clear All", role: .destructive) {
        viewModel.clearAll()
      }
      Button("Cancel", role: .cancel) {}
    } message: {
      Text("Are you sure you want to clear all focus history? This cannot be undone.")
    }
    .task {
      await viewModel.refresh()
    }
    .onReceive(countdownTimer) { time in
      // Only update if there's an active countdown to avoid unnecessary re-renders
      if storage.delayEndTime != nil || storage.cooldownEndTime != nil {
        currentTime = time
      }
    }
  }

  // MARK: - Header

  private var header: some View {
    HStack(alignment: .top, spacing: 16) {
      VStack(alignment: .leading, spacing: 6) {
        Text("Focus")
          .geist(size: 28, weight: .semibold, tracking: 28 * -0.02)
          .foregroundStyle(sb.ink)

        HStack(spacing: 8) {
          Circle()
            .fill(viewModel.isMonitoring ? Color.green.opacity(0.9) : sb.ink(.w25))
            .frame(width: 7, height: 7)

          Text(viewModel.isMonitoring ? "Monitoring" : "Not monitoring")
            .geist(size: 13)
            .foregroundStyle(sb.ink(.w45))

          Text("·")
            .geist(size: 13)
            .foregroundStyle(sb.ink(.w25))

          Text("\(viewModel.todayCount) session\(viewModel.todayCount == 1 ? "" : "s") today")
            .geist(size: 13)
            .foregroundStyle(sb.ink(.w45))
        }
      }

      Spacer(minLength: 12)

      // Actions
      HStack(spacing: 16) {
        HStack(spacing: 8) {
          Text("Show all")
            .geist(size: 13)
            .foregroundStyle(sb.ink(.w55))
          SBToggleSwitch(isOn: $viewModel.showHistorical)
        }

        Menu {
          Button {
            Task { await viewModel.refresh(force: true) }
          } label: {
            Label("Refresh", systemImage: "arrow.clockwise")
          }

          Divider()

          Button(role: .destructive) {
            showClearConfirmation = true
          } label: {
            Label("Clear All History", systemImage: "trash")
          }
          .disabled(storage.sessions.isEmpty)
        } label: {
          Image(systemName: "ellipsis")
            .font(.system(size: 15, weight: .semibold))
            .foregroundStyle(sb.ink(.w55))
            .frame(width: 30, height: 26)
            .background(
              RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(sb.ink(.w04))
            )
            .overlay(
              RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(sb.ink(.w09), lineWidth: 1)
            )
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
      }
    }
  }

  // MARK: - Countdown Helpers

  /// Compute remaining seconds for delay countdown (reactive to currentTime)
  private var delayRemainingSeconds: Int {
    guard let endTime = storage.delayEndTime else { return 0 }
    return max(0, Int(endTime.timeIntervalSince(currentTime)))
  }

  /// Compute remaining seconds for cooldown countdown (reactive to currentTime)
  private var cooldownRemainingSeconds: Int {
    guard let endTime = storage.cooldownEndTime else { return 0 }
    return max(0, Int(endTime.timeIntervalSince(currentTime)))
  }

  // MARK: - Status Banner

  @ViewBuilder
  private var statusBanner: some View {
    if storage.delayEndTime != nil && delayRemainingSeconds > 0 {
      // In delay period - show countdown
      delayStatusBanner
    } else if storage.cooldownEndTime != nil && cooldownRemainingSeconds > 0 {
      // In cooldown period - show cooldown countdown
      cooldownStatusBanner
    } else if let status = viewModel.currentStatus {
      // Normal analyzed status
      currentStatusBanner(status)
    } else if let detectedApp = storage.detectedAppName {
      // Have detected app but no status yet
      pendingStatusBanner(appName: detectedApp)
    }
  }

  /// Shared glass shell for every status banner: a leading "big number" slot, a
  /// dot + headline, muted subtext, and an optional trailing view.
  private func statusCard<Leading: View, Trailing: View>(
    dot: Color,
    headline: String,
    subtext: String?,
    @ViewBuilder leading: () -> Leading,
    @ViewBuilder trailing: () -> Trailing
  ) -> some View {
    HStack(spacing: 20) {
      leading()

      VStack(alignment: .leading, spacing: 5) {
        HStack(spacing: 8) {
          Circle()
            .fill(dot)
            .frame(width: 7, height: 7)
          Text(headline)
            .geist(size: 17, weight: .semibold)
            .foregroundStyle(sb.ink)
        }
        if let subtext {
          Text(subtext)
            .geist(size: 13)
            .foregroundStyle(sb.ink(.w45))
            .lineLimit(1)
        }
      }

      Spacer(minLength: 12)

      trailing()
    }
    .padding(22)
    .sbCard(radius: 16)
  }

  // MARK: - Delay Status Banner

  private var delayStatusBanner: some View {
    let seconds = delayRemainingSeconds
    let app = storage.detectedAppName

    return statusCard(
      dot: sb.ink(.w45),
      headline: "Waiting to analyze",
      subtext: {
        if let app { return "\(app)  ·  analyzing in \(seconds)s" }
        return "Analyzing in \(seconds)s"
      }()
    ) {
      VStack(alignment: .leading, spacing: 0) {
        Text("\(seconds)")
          .geistMono(size: 40, weight: .semibold)
          .foregroundStyle(sb.ink(.w85))
        Text("SEC")
          .geistMono(size: 10, weight: .medium, tracking: 10 * 0.1)
          .foregroundStyle(sb.ink(.w35))
      }
    } trailing: {
      EmptyView()
    }
  }

  // MARK: - Cooldown Status Banner

  private var cooldownStatusBanner: some View {
    let totalSeconds = cooldownRemainingSeconds
    let minutes = totalSeconds / 60
    let seconds = totalSeconds % 60
    let app = storage.detectedAppName ?? viewModel.currentApp

    return statusCard(
      dot: Color.orange.opacity(0.9),
      headline: "Cooldown active",
      subtext: {
        if let app { return "\(app)  ·  next check soon" }
        return "Next check soon"
      }()
    ) {
      VStack(alignment: .leading, spacing: 0) {
        Text("\(minutes):\(String(format: "%02d", seconds))")
          .geistMono(size: 34, weight: .semibold)
          .foregroundStyle(sb.ink(.w85))
        Text("REMAINING")
          .geistMono(size: 10, weight: .medium, tracking: 10 * 0.1)
          .foregroundStyle(sb.ink(.w35))
      }
    } trailing: {
      EmptyView()
    }
  }

  // MARK: - Pending Status Banner

  private func pendingStatusBanner(appName: String) -> some View {
    statusCard(
      dot: sb.ink(.w35),
      headline: "Analyzing…",
      subtext: appName
    ) {
      ProgressView()
        .scaleEffect(0.8)
        .tint(sb.ink(.w45))
        .frame(width: 44, height: 44)
    } trailing: {
      EmptyView()
    }
  }

  // MARK: - Current Status Banner (Analyzed)

  private func currentStatusBanner(_ status: FocusStatus) -> some View {
    // Use detected app as fallback if currentApp isn't set yet
    let appName = viewModel.currentApp ?? storage.detectedAppName
    let focused = status == .focused

    return statusCard(
      dot: focused ? Color.green.opacity(0.9) : Color.orange.opacity(0.9),
      headline: focused ? "Focused" : "Distracted",
      subtext: appName
    ) {
      VStack(alignment: .leading, spacing: 0) {
        Text(String(format: "%.0f", viewModel.stats.focusRate))
          .geist(size: 40, weight: .semibold)
          .foregroundStyle(sb.ink(.w85))
        Text("FOCUS RATE")
          .geistMono(size: 10, weight: .medium, tracking: 10 * 0.1)
          .foregroundStyle(sb.ink(.w35))
      }
    } trailing: {
      EmptyView()
    }
  }

  // MARK: - Stats Section

  private var statsSection: some View {
    VStack(alignment: .leading, spacing: 14) {
      SBSectionLabel(text: "Today's summary")

      HStack(spacing: 16) {
        SBStatTile(
          value: "\(viewModel.stats.focusedMinutes)",
          unit: "min",
          label: "Focus time",
          dot: Color.green.opacity(0.9)
        )
        SBStatTile(
          value: "\(viewModel.stats.distractedMinutes)",
          unit: "min",
          label: "Distracted",
          dot: Color.orange.opacity(0.9)
        )
        SBStatTile(
          value: String(format: "%.0f", viewModel.stats.focusRate),
          unit: "%",
          label: "Focus rate",
          dot: nil
        )
        SBStatTile(
          value: "\(viewModel.stats.sessionCount)",
          unit: "",
          label: "Sessions",
          dot: nil
        )
      }
    }
  }

  // MARK: - Top Distractions

  private var topDistractionsSection: some View {
    VStack(alignment: .leading, spacing: 6) {
      SBSectionLabel(text: "Top distractions")

      VStack(spacing: 0) {
        ForEach(viewModel.stats.topDistractions.prefix(5), id: \.appOrSite) { entry in
          FocusHairlineRow {
            Circle()
              .fill(Color.orange.opacity(0.9))
              .frame(width: 6, height: 6)

            Text(entry.appOrSite)
              .geist(size: 15)
              .foregroundStyle(sb.ink(.w85))
              .lineLimit(1)

            Spacer(minLength: 12)

            Text("\(entry.count)×")
              .geistMono(size: 12, tracking: 0)
              .foregroundStyle(sb.ink(.w35))

            Text(formatDuration(entry.totalSeconds))
              .geistMono(size: 13, weight: .medium, tracking: 0)
              .foregroundStyle(sb.ink(.w7))
              .frame(width: 56, alignment: .trailing)
          }
        }
      }
    }
  }

  // MARK: - History Section

  private var historySection: some View {
    VStack(alignment: .leading, spacing: 6) {
      HStack(alignment: .center) {
        SBSectionLabel(text: viewModel.showHistorical ? "All sessions" : "Today's sessions")

        Spacer()

        // Search field
        HStack(spacing: 7) {
          Image(systemName: "magnifyingglass")
            .font(.system(size: 11, weight: .medium))
            .foregroundStyle(sb.ink(.w35))

          TextField("Search…", text: $viewModel.searchText)
            .textFieldStyle(.plain)
            .geist(size: 13)
            .foregroundStyle(sb.ink)

          if !viewModel.searchText.isEmpty {
            Button {
              viewModel.searchText = ""
            } label: {
              Image(systemName: "xmark.circle.fill")
                .font(.system(size: 12))
                .foregroundStyle(sb.ink(.w35))
            }
            .buttonStyle(.plain)
          }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .frame(width: 190)
        .background(
          RoundedRectangle(cornerRadius: 9, style: .continuous)
            .fill(sb.ink(.w06))
        )
        .overlay(
          RoundedRectangle(cornerRadius: 9, style: .continuous)
            .stroke(sb.ink(.w12), lineWidth: 1)
        )
      }
      .padding(.bottom, 4)

      if viewModel.filteredSessions.isEmpty {
        emptyHistoryView
      } else {
        LazyVStack(spacing: 0) {
          ForEach(viewModel.filteredSessions) { session in
            FocusSessionRow(
              session: session,
              onDelete: { viewModel.deleteSession(session.id) }
            )
          }
        }
      }
    }
  }

  private var emptyHistoryView: some View {
    VStack(spacing: 14) {
      SBLogo(size: 30, opacity: 0.5)

      Text("No sessions yet")
        .geist(size: 17, weight: .semibold)
        .foregroundStyle(sb.ink(.w85))

      Text("Focus sessions appear here as you work.\nEnable Focus monitoring in Settings to begin.")
        .geist(size: 13.5)
        .foregroundStyle(sb.ink(.w45))
        .multilineTextAlignment(.center)
        .lineSpacing(2)

      SBInkButton(title: "Refresh") {
        Task { await viewModel.refresh(force: true) }
      }
      .padding(.top, 4)
    }
    .frame(maxWidth: .infinity)
    .padding(.vertical, 48)
  }

  // MARK: - Helpers

  private func formatDuration(_ seconds: Int) -> String {
    let minutes = seconds / 60
    if minutes < 60 {
      return "\(minutes)m"
    }
    let hours = minutes / 60
    let remainingMinutes = minutes % 60
    return "\(hours)h \(remainingMinutes)m"
  }
}

// MARK: - SB Stat Tile

private struct SBStatTile: View {
  @Environment(\.sbTheme) private var sb
  let value: String
  let unit: String
  let label: String
  var dot: Color? = nil

  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      HStack(alignment: .firstTextBaseline, spacing: 4) {
        Text(value)
          .geist(size: 34, weight: .semibold, tracking: 34 * -0.02)
          .foregroundStyle(sb.ink)
        if !unit.isEmpty {
          Text(unit)
            .geist(size: 14, weight: .medium)
            .foregroundStyle(sb.ink(.w38))
        }
      }

      HStack(spacing: 6) {
        if let dot {
          Circle()
            .fill(dot)
            .frame(width: 5, height: 5)
        }
        Text(label.uppercased())
          .geistMono(size: 11, weight: .medium, tracking: 11 * 0.08)
          .foregroundStyle(sb.ink(.w35))
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .padding(.horizontal, 20)
    .padding(.vertical, 22)
    .sbCard(radius: 16)
  }
}

// MARK: - Focus Hairline Row (shared list primitive with hover fill)

/// A hover-highlighting list row with a hairline separator underneath. Used by
/// the Top Distractions list and (via `FocusSessionRow`) the session history.
private struct FocusHairlineRow<Content: View>: View {
  @Environment(\.sbTheme) private var sb
  var onHover: ((Bool) -> Void)? = nil
  @ViewBuilder var content: () -> Content

  @State private var isHovering = false

  var body: some View {
    VStack(spacing: 0) {
      HStack(spacing: 12) {
        content()
      }
      .padding(.horizontal, 10)
      .padding(.vertical, 12)
      .background(
        RoundedRectangle(cornerRadius: 10, style: .continuous)
          .fill(isHovering ? sb.ink(.w04) : Color.clear)
      )
      .contentShape(Rectangle())
      .onHover { hovering in
        isHovering = hovering
        onHover?(hovering)
      }

      Rectangle()
        .fill(sb.ink(.w07))
        .frame(height: 1)
        .padding(.horizontal, 10)
    }
  }
}

// MARK: - Focus Session Row

struct FocusSessionRow: View {
  @Environment(\.sbTheme) private var sb
  let session: StoredFocusSession
  let onDelete: () -> Void

  @State private var isHovering = false
  @State private var showDeleteConfirmation = false

  var body: some View {
    FocusHairlineRow(onHover: { isHovering = $0 }) {
      // Status indicator
      Circle()
        .fill(session.status == .focused ? Color.green.opacity(0.9) : Color.orange.opacity(0.9))
        .frame(width: 7, height: 7)

      // App/site + description
      VStack(alignment: .leading, spacing: 2) {
        Text(session.appOrSite)
          .geist(size: 15)
          .foregroundStyle(sb.ink(.w9))
          .lineLimit(1)

        if !session.description.isEmpty {
          Text(session.description)
            .geist(size: 12.5)
            .foregroundStyle(sb.ink(.w38))
            .lineLimit(1)
        }
      }

      Spacer(minLength: 12)

      // Message (if any)
      if let message = session.message, !message.isEmpty {
        Text(message)
          .geist(size: 12.5)
          .foregroundStyle(sb.ink(.w35))
          .lineLimit(1)
          .frame(maxWidth: 160, alignment: .trailing)
      }

      // Sync status
      if !session.isSynced {
        Image(systemName: "arrow.triangle.2.circlepath")
          .font(.system(size: 11))
          .foregroundStyle(sb.ink(.w35))
          .help("Pending sync")
      }

      // Time
      Text(formatTime(session.createdAt))
        .geistMono(size: 12, tracking: 0)
        .foregroundStyle(sb.ink(.w35))
        .frame(width: 66, alignment: .trailing)

      // Delete button (on hover)
      if isHovering {
        Button {
          showDeleteConfirmation = true
        } label: {
          Image(systemName: "trash")
            .font(.system(size: 12))
            .foregroundStyle(sb.ink(.w45))
        }
        .buttonStyle(.plain)
        .help("Delete")
        .transition(.opacity)
      }
    }
    .confirmationDialog(
      "Delete Session",
      isPresented: $showDeleteConfirmation,
      titleVisibility: .visible
    ) {
      Button("Delete", role: .destructive) {
        onDelete()
      }
      Button("Cancel", role: .cancel) {}
    } message: {
      Text("Are you sure you want to delete this session?")
    }
  }

  private static let timeFormatter: DateFormatter = {
    let f = DateFormatter()
    f.dateFormat = "h:mm a"
    return f
  }()
  private static let dateTimeFormatter: DateFormatter = {
    let f = DateFormatter()
    f.dateFormat = "M/d h:mm a"
    return f
  }()

  private func formatTime(_ date: Date) -> String {
    if Calendar.current.isDateInToday(date) {
      return Self.timeFormatter.string(from: date)
    } else {
      return Self.dateTimeFormatter.string(from: date)
    }
  }
}

#if canImport(PreviewsMacros)
  #Preview {
    FocusPage()
      .frame(width: 800, height: 600)
      .background(Color.black)
  }
#endif
