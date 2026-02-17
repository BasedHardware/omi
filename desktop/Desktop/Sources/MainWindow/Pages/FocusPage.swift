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
            $0.appOrSite.localizedCaseInsensitiveContains(searchText) ||
            $0.description.localizedCaseInsensitiveContains(searchText) ||
            ($0.message?.localizedCaseInsensitiveContains(searchText) ?? false)
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
    @StateObject private var viewModel = FocusViewModel()
    @ObservedObject private var storage = FocusStorage.shared
    @State private var showClearConfirmation = false
    @State private var currentTime = Date()

    // Timer to update countdown displays
    private let countdownTimer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    var body: some View {
        if viewModel.isLoading && storage.sessions.isEmpty {
            // Show loading when initially loading with no cached data
            VStack {
                Spacer()
                ProgressView()
                    .scaleEffect(1.2)
                Text("Loading focus data...")
                    .scaledFont(size: 14)
                    .foregroundColor(OmiColors.textTertiary)
                    .padding(.top, 12)
                Spacer()
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            focusContent
        }
    }

    private var focusContent: some View {
        VStack(spacing: 20) {
            // Header row with title and actions
            HStack {
                // Monitoring status indicator
                HStack(spacing: 8) {
                    Circle()
                        .fill(viewModel.isMonitoring ? Color.green : OmiColors.textTertiary)
                        .frame(width: 8, height: 8)

                    Text(viewModel.isMonitoring ? "Monitoring" : "Not monitoring")
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textTertiary)

                    Text("•")
                        .foregroundColor(OmiColors.textTertiary)

                    Text("\(viewModel.todayCount) sessions today")
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textTertiary)
                }

                Spacer()

                // Actions
                HStack(spacing: 12) {
                    Toggle(isOn: $viewModel.showHistorical) {
                        Text("Show all")
                            .scaledFont(size: 13)
                            .foregroundColor(OmiColors.textSecondary)
                    }
                    .toggleStyle(.switch)
                    .controlSize(.small)

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
                        Image(systemName: "ellipsis.circle")
                            .scaledFont(size: 18)
                            .foregroundColor(OmiColors.textSecondary)
                    }
                    .menuStyle(.borderlessButton)
                }
            }

            // Current status banner (shows detected app, delay, cooldown, or analyzed status)
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

    // MARK: - Delay Status Banner

    private var delayStatusBanner: some View {
        let seconds = delayRemainingSeconds

        return HStack(spacing: 16) {
            // Status icon
            ZStack {
                Circle()
                    .fill(Color.blue.opacity(0.2))
                    .frame(width: 56, height: 56)

                Image(systemName: "clock.fill")
                    .scaledFont(size: 24)
                    .foregroundColor(Color.blue)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("Waiting to Analyze")
                    .scaledFont(size: 20, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                HStack(spacing: 8) {
                    if let app = storage.detectedAppName {
                        Text(app)
                            .scaledFont(size: 14)
                            .foregroundColor(OmiColors.textSecondary)

                        Text("•")
                            .foregroundColor(OmiColors.textTertiary)
                    }

                    Text("Analyzing in \(seconds)s")
                        .scaledFont(size: 14)
                        .foregroundColor(OmiColors.textTertiary)
                }
            }

            Spacer()

            // Countdown indicator
            Text("\(seconds)")
                .scaledFont(size: 24, weight: .bold, design: .monospaced)
                .foregroundColor(Color.blue)
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(Color.blue.opacity(0.08))
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .stroke(Color.blue.opacity(0.2), lineWidth: 1)
                )
        )
    }

    // MARK: - Cooldown Status Banner

    private var cooldownStatusBanner: some View {
        let totalSeconds = cooldownRemainingSeconds
        let minutes = totalSeconds / 60
        let seconds = totalSeconds % 60

        return HStack(spacing: 16) {
            // Status icon
            ZStack {
                Circle()
                    .fill(Color.orange.opacity(0.2))
                    .frame(width: 56, height: 56)

                Image(systemName: "pause.circle.fill")
                    .scaledFont(size: 24)
                    .foregroundColor(Color.orange)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("Cooldown Active")
                    .scaledFont(size: 20, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                HStack(spacing: 8) {
                    if let app = storage.detectedAppName ?? viewModel.currentApp {
                        Text(app)
                            .scaledFont(size: 14)
                            .foregroundColor(OmiColors.textSecondary)

                        Text("•")
                            .foregroundColor(OmiColors.textTertiary)
                    }

                    Text("Next check in \(minutes):\(String(format: "%02d", seconds))")
                        .scaledFont(size: 14)
                        .foregroundColor(OmiColors.textTertiary)
                }
            }

            Spacer()

            // Countdown indicator
            VStack(spacing: 2) {
                Text("\(minutes):\(String(format: "%02d", seconds))")
                    .scaledFont(size: 20, weight: .bold, design: .monospaced)
                    .foregroundColor(Color.orange)
                Text("remaining")
                    .scaledFont(size: 10)
                    .foregroundColor(OmiColors.textTertiary)
            }
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(Color.orange.opacity(0.08))
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .stroke(Color.orange.opacity(0.2), lineWidth: 1)
                )
        )
    }

    // MARK: - Pending Status Banner

    private func pendingStatusBanner(appName: String) -> some View {
        HStack(spacing: 16) {
            // Status icon
            ZStack {
                Circle()
                    .fill(Color.gray.opacity(0.2))
                    .frame(width: 56, height: 56)

                Image(systemName: "eye.fill")
                    .scaledFont(size: 24)
                    .foregroundColor(Color.gray)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("Analyzing...")
                    .scaledFont(size: 20, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Text(appName)
                    .scaledFont(size: 14)
                    .foregroundColor(OmiColors.textSecondary)
            }

            Spacer()

            // Spinner
            ProgressView()
                .scaleEffect(0.8)
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(Color.gray.opacity(0.08))
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .stroke(Color.gray.opacity(0.2), lineWidth: 1)
                )
        )
    }

    // MARK: - Current Status Banner (Analyzed)

    private func currentStatusBanner(_ status: FocusStatus) -> some View {
        // Use detected app as fallback if currentApp isn't set yet
        let appName = viewModel.currentApp ?? storage.detectedAppName

        return HStack(spacing: 16) {
            // Status icon
            ZStack {
                Circle()
                    .fill(status == .focused ? Color.green.opacity(0.2) : Color.orange.opacity(0.2))
                    .frame(width: 56, height: 56)

                Image(systemName: status == .focused ? "eye.fill" : "eye.slash.fill")
                    .scaledFont(size: 24)
                    .foregroundColor(status == .focused ? Color.green : Color.orange)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text(status == .focused ? "Focused" : "Distracted")
                    .scaledFont(size: 20, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                if let app = appName {
                    Text(app)
                        .scaledFont(size: 14)
                        .foregroundColor(OmiColors.textSecondary)
                }
            }

            Spacer()

            // Subtle pulse animation for focused state
            if status == .focused {
                Circle()
                    .fill(Color.green)
                    .frame(width: 12, height: 12)
                    .opacity(0.8)
            }
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(status == .focused
                      ? Color.green.opacity(0.08)
                      : Color.orange.opacity(0.08))
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .stroke(status == .focused
                                ? Color.green.opacity(0.2)
                                : Color.orange.opacity(0.2),
                                lineWidth: 1)
                )
        )
    }

    // MARK: - Stats Section

    private var statsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Today's Summary")
                .scaledFont(size: 14, weight: .semibold)
                .foregroundColor(OmiColors.textSecondary)
                .textCase(.uppercase)

            LazyVGrid(columns: [
                GridItem(.flexible()),
                GridItem(.flexible()),
                GridItem(.flexible()),
                GridItem(.flexible())
            ], spacing: 12) {
                FocusStatCard(
                    title: "Focus Time",
                    value: "\(viewModel.stats.focusedMinutes)",
                    unit: "min",
                    icon: "eye.fill",
                    color: Color.green
                )

                FocusStatCard(
                    title: "Distracted",
                    value: "\(viewModel.stats.distractedMinutes)",
                    unit: "min",
                    icon: "eye.slash.fill",
                    color: Color.orange
                )

                FocusStatCard(
                    title: "Focus Rate",
                    value: String(format: "%.0f", viewModel.stats.focusRate),
                    unit: "%",
                    icon: "chart.pie.fill",
                    color: OmiColors.purplePrimary
                )

                FocusStatCard(
                    title: "Sessions",
                    value: "\(viewModel.stats.sessionCount)",
                    unit: "",
                    icon: "clock.fill",
                    color: OmiColors.info
                )
            }
        }
    }

    // MARK: - Top Distractions

    private var topDistractionsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Top Distractions")
                .scaledFont(size: 14, weight: .semibold)
                .foregroundColor(OmiColors.textSecondary)
                .textCase(.uppercase)

            VStack(spacing: 8) {
                ForEach(viewModel.stats.topDistractions.prefix(5), id: \.appOrSite) { entry in
                    HStack {
                        Image(systemName: "app.fill")
                            .scaledFont(size: 14)
                            .foregroundColor(Color.orange)
                            .frame(width: 24)

                        Text(entry.appOrSite)
                            .scaledFont(size: 14)
                            .foregroundColor(OmiColors.textPrimary)

                        Spacer()

                        Text("\(entry.count)x")
                            .scaledFont(size: 12)
                            .foregroundColor(OmiColors.textTertiary)

                        Text(formatDuration(entry.totalSeconds))
                            .scaledFont(size: 13, weight: .medium)
                            .foregroundColor(OmiColors.textSecondary)
                            .frame(width: 50, alignment: .trailing)
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 10)
                    .background(
                        RoundedRectangle(cornerRadius: 8)
                            .fill(OmiColors.backgroundTertiary.opacity(0.4))
                    )
                }
            }
        }
    }

    // MARK: - History Section

    private var historySection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text(viewModel.showHistorical ? "All Sessions" : "Today's Sessions")
                    .scaledFont(size: 14, weight: .semibold)
                    .foregroundColor(OmiColors.textSecondary)
                    .textCase(.uppercase)

                Spacer()

                // Search field
                HStack(spacing: 8) {
                    Image(systemName: "magnifyingglass")
                        .foregroundColor(OmiColors.textTertiary)
                        .scaledFont(size: 12)

                    TextField("Search...", text: $viewModel.searchText)
                        .textFieldStyle(.plain)
                        .foregroundColor(OmiColors.textPrimary)
                        .scaledFont(size: 13)

                    if !viewModel.searchText.isEmpty {
                        Button {
                            viewModel.searchText = ""
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundColor(OmiColors.textTertiary)
                                .scaledFont(size: 12)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(OmiColors.backgroundTertiary)
                .cornerRadius(6)
                .frame(width: 180)
            }

            if viewModel.filteredSessions.isEmpty {
                emptyHistoryView
            } else {
                LazyVStack(spacing: 8) {
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
        VStack(spacing: 12) {
            Image(systemName: "eye.fill")
                .scaledFont(size: 36)
                .foregroundColor(OmiColors.textTertiary)

            Text("No Sessions Yet")
                .scaledFont(size: 16, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

            Text("Focus sessions will appear here as you work.\nMake sure Focus monitoring is enabled in Settings.")
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textTertiary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 40)
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

// MARK: - Focus Session Row

struct FocusSessionRow: View {
    let session: StoredFocusSession
    let onDelete: () -> Void

    @State private var isHovering = false
    @State private var showDeleteConfirmation = false

    var body: some View {
        HStack(spacing: 12) {
            // Status indicator
            Circle()
                .fill(session.status == .focused ? Color.green : Color.orange)
                .frame(width: 10, height: 10)

            // App/site
            Text(session.appOrSite)
                .scaledFont(size: 14, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)
                .lineLimit(1)
                .frame(width: 120, alignment: .leading)

            // Description
            Text(session.description)
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textSecondary)
                .lineLimit(1)

            Spacer()

            // Message (if any)
            if let message = session.message, !message.isEmpty {
                Text(message)
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textTertiary)
                    .lineLimit(1)
                    .frame(maxWidth: 150, alignment: .trailing)
            }

            // Sync status
            if !session.isSynced {
                Image(systemName: "arrow.triangle.2.circlepath")
                    .scaledFont(size: 11)
                    .foregroundColor(OmiColors.textTertiary)
                    .help("Pending sync")
            }

            // Time
            Text(formatTime(session.createdAt))
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textTertiary)
                .frame(width: 60, alignment: .trailing)

            // Delete button (on hover)
            if isHovering {
                Button {
                    showDeleteConfirmation = true
                } label: {
                    Image(systemName: "trash")
                        .scaledFont(size: 12)
                        .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
                .help("Delete")
                .transition(.opacity)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(isHovering ? OmiColors.backgroundTertiary : OmiColors.backgroundTertiary.opacity(0.4))
        )
        .onHover { hovering in
            isHovering = hovering
            if hovering {
                NSCursor.pointingHand.push()
            } else {
                NSCursor.pop()
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

    private func formatTime(_ date: Date) -> String {
        let calendar = Calendar.current
        if calendar.isDateInToday(date) {
            let formatter = DateFormatter()
            formatter.dateFormat = "h:mm a"
            return formatter.string(from: date)
        } else {
            let formatter = DateFormatter()
            formatter.dateFormat = "M/d h:mm a"
            return formatter.string(from: date)
        }
    }
}

#Preview {
    FocusPage()
        .frame(width: 800, height: 600)
        .background(OmiColors.backgroundPrimary)
}
