import SwiftUI

// MARK: - Navigation Item Model
enum SidebarNavItem: Int, CaseIterable {
    case dashboard = 0
    case conversations = 1
    case chat = 2
    case memories = 3
    case tasks = 4
    case focus = 5
    case advice = 6
    case rewind = 7
    case apps = 8
    case settings = 9
    case permissions = 10
    case device = 11
    case help = 12

    var title: String {
        switch self {
        case .dashboard: return "Dashboard"
        case .conversations: return "Conversations"
        case .chat: return "AI chat"
        case .memories: return "Memories"
        case .tasks: return "Tasks"
        case .focus: return "Focus"
        case .advice: return "Advice"
        case .rewind: return "Rewind"
        case .apps: return "Apps"
        case .settings: return "Settings"
        case .permissions: return "Permissions"
        case .device: return "Device"
        case .help: return "Help from Founder"
        }
    }

    var icon: String {
        switch self {
        case .dashboard: return "house.fill"
        case .conversations: return "text.bubble.fill"
        case .chat: return "bubble.left.and.bubble.right.fill"
        case .memories: return "brain"
        case .tasks: return "checklist"
        case .focus: return "eye.fill"
        case .advice: return "lightbulb.fill"
        case .rewind: return "clock.arrow.circlepath"
        case .apps: return "puzzlepiece.fill"
        case .settings: return "gearshape.fill"
        case .permissions: return "exclamationmark.triangle.fill"
        case .device: return "wave.3.right.circle.fill"
        case .help: return "bubble.left.fill"
        }
    }

    /// Minimum tier level required to access this item (0 = always available)
    var requiredTier: Int {
        switch self {
        case .conversations, .rewind: return 1
        case .memories: return 2
        case .tasks: return 3
        case .chat: return 4
        case .dashboard: return 5
        case .apps: return 6
        default: return 0
        }
    }

    /// Items shown in the main navigation (top section)
    static var mainItems: [SidebarNavItem] {
        [.dashboard, .chat, .memories, .tasks, .rewind, .apps]
    }
}

// MARK: - Sidebar View
struct SidebarView: View {
    @Binding var selectedIndex: Int
    @Binding var isCollapsed: Bool
    @ObservedObject var appState: AppState
    @ObservedObject private var adviceStorage = AdviceStorage.shared
    @ObservedObject private var focusStorage = FocusStorage.shared
    @ObservedObject private var deviceProvider = DeviceProvider.shared
    @ObservedObject private var updaterViewModel = UpdaterViewModel.shared
    @ObservedObject private var crispManager = CrispManager.shared

    // State for Get Omi Widget (shown when no device is paired, dismissible)
    @AppStorage("showGetOmiWidget") private var showGetOmiWidget = true

    // Tier gating (0 = show all, 1-6 = sequential tiers)
    @AppStorage("currentTierLevel") private var currentTierLevel = 0

    // Track newly unlocked items for animation (persisted so it survives settings navigation)
    @State private var newlyUnlockedItems: Set<SidebarNavItem> = []
    @AppStorage("lastSeenTierLevel") private var lastSeenTierLevel = 0

    // Toggle states for quick controls
    @AppStorage("screenAnalysisEnabled") private var screenAnalysisEnabled = true
    @State private var isMonitoring = false
    @State private var isTogglingMonitoring = false
    @State private var isTogglingTranscription = false

    // Page loading states (show spinner in place of icon)
    @State private var isRewindPageLoading = false
    @State private var isConversationsPageLoading = false
    @State private var isTasksPageLoading = false
    @State private var isFocusPageLoading = false
    @State private var isAdvicePageLoading = false
    @State private var isAppsPageLoading = false

    // Drag state
    @State private var dragOffset: CGFloat = 0
    @GestureState private var isDragging = false

    // Constants
    private let expandedWidth: CGFloat = 260
    private let collapsedWidth: CGFloat = 64
    private let iconWidth: CGFloat = 20  // Fixed width for all icons

    private var currentWidth: CGFloat {
        isCollapsed ? collapsedWidth : expandedWidth
    }

    /// Whether a sidebar item is locked at the current tier level
    private func isItemLocked(_ item: SidebarNavItem) -> Bool {
        currentTierLevel != 0 && currentTierLevel < item.requiredTier
    }

    /// Static version: items unlocked at a given tier (used by unlock celebration logic)
    static func visibleItems(for tier: Int) -> [SidebarNavItem] {
        if tier == 0 {
            return SidebarNavItem.mainItems
        }
        return SidebarNavItem.mainItems.filter { $0.requiredTier <= tier }
    }

    /// Color for focus status indicator (green = focused, orange = distracted, nil = no status)
    private var focusStatusColor: Color? {
        guard let status = focusStorage.currentStatus else { return nil }
        return status == .focused ? Color.green : Color.orange
    }

    var body: some View {
        ZStack(alignment: .trailing) {
            VStack(alignment: .leading, spacing: 0) {
                // Header: Logo + Collapse button on same row
                headerSection
                    .padding(.top, 12)
                    .padding(.horizontal, isCollapsed ? 8 : 16)

                // Expand button when collapsed (below logo)
                if isCollapsed {
                    collapsedExpandButton
                        .padding(.horizontal, 8)
                }

                Spacer().frame(height: isCollapsed ? 8 : 16)

                // Main navigation section
                VStack(alignment: .leading, spacing: 0) {
                    // Main navigation items
                    ForEach(SidebarNavItem.mainItems, id: \.rawValue) { item in
                        Group {
                            if item == .conversations {
                                // Conversations - icon shows audio activity when recording
                                // Audio levels wrapped in a separate view to avoid re-rendering the entire sidebar
                                AudioLevelNavItem(
                                    icon: item.icon,
                                    label: item.title,
                                    isSelected: selectedIndex == item.rawValue,
                                    isCollapsed: isCollapsed,
                                    iconWidth: iconWidth,
                                    isOn: appState.isTranscribing,
                                    isToggling: isTogglingTranscription,
                                    isPageLoading: isConversationsPageLoading,
                                    onTap: {
                                        // Show loading immediately when navigating to Conversations
                                        if selectedIndex != item.rawValue {
                                            isConversationsPageLoading = true
                                            // Fallback timeout
                                            DispatchQueue.main.asyncAfter(deadline: .now() + 5.0) {
                                                if isConversationsPageLoading {
                                                    isConversationsPageLoading = false
                                                }
                                            }
                                        }
                                        selectedIndex = item.rawValue
                                        AnalyticsManager.shared.tabChanged(tabName: item.title)
                                    },
                                    onToggle: {
                                        toggleTranscription(enabled: !appState.isTranscribing)
                                    }
                                )
                            } else if item == .rewind {
                                // Rewind - shows pulsing recording icon when both audio and screen are active
                                NavItemWithStatusView(
                                    icon: item.icon,
                                    label: item.title,
                                    isSelected: selectedIndex == item.rawValue,
                                    isCollapsed: isCollapsed,
                                    iconWidth: iconWidth,
                                    isOn: isMonitoring && appState.isTranscribing,
                                    isToggling: isTogglingMonitoring,
                                    isPageLoading: isRewindPageLoading,
                                    onTap: {
                                        // Show loading immediately when navigating to Rewind
                                        if selectedIndex != item.rawValue {
                                            log("SIDEBAR: Rewind tapped, showing loading indicator")
                                            isRewindPageLoading = true
                                            // Fallback timeout in case page load notification never comes
                                            DispatchQueue.main.asyncAfter(deadline: .now() + 5.0) {
                                                if isRewindPageLoading {
                                                    log("SIDEBAR: Rewind loading timeout, clearing indicator")
                                                    isRewindPageLoading = false
                                                }
                                            }
                                        }
                                        selectedIndex = item.rawValue
                                        AnalyticsManager.shared.tabChanged(tabName: item.title)
                                    },
                                    onToggle: {
                                        // Use combined state so toggle matches what's displayed
                                        let isFullyOn = isMonitoring && appState.isTranscribing
                                        toggleMonitoring(enabled: !isFullyOn)
                                    },
                                    showRewindIcon: true
                                )
                            } else {
                                let locked = isItemLocked(item)
                                NavItemView(
                                    icon: item.icon,
                                    label: item.title,
                                    isSelected: !locked && selectedIndex == item.rawValue,
                                    isCollapsed: isCollapsed,
                                    iconWidth: iconWidth,
                                    badge: item == .advice ? adviceStorage.unreadCount : 0,
                                    statusColor: item == .focus ? focusStatusColor : nil,
                                    isLoading: pageLoadingState(for: item),
                                    isLocked: locked,
                                    lockTooltip: locked ? "Unlocks at Tier \(item.requiredTier)" : nil,
                                    onUnlock: {
                                        TierManager.shared.userDidSetTier(item.requiredTier)
                                        setPageLoading(for: item, loading: true)
                                        DispatchQueue.main.asyncAfter(deadline: .now() + 5.0) {
                                            setPageLoading(for: item, loading: false)
                                        }
                                        selectedIndex = item.rawValue
                                        AnalyticsManager.shared.tabChanged(tabName: item.title)
                                    },
                                    onTap: {
                                        // Show loading immediately when navigating
                                        if selectedIndex != item.rawValue {
                                            setPageLoading(for: item, loading: true)
                                            // Fallback timeout
                                            DispatchQueue.main.asyncAfter(deadline: .now() + 5.0) {
                                                setPageLoading(for: item, loading: false)
                                            }
                                        }
                                        selectedIndex = item.rawValue
                                        AnalyticsManager.shared.tabChanged(tabName: item.title)
                                    }
                                )
                            }
                        }
                        .overlay(
                            TierUnlockCelebration(isActive: newlyUnlockedItems.contains(item))
                        )
                    }
                    .animation(.easeOut(duration: 0.4), value: currentTierLevel)

                    Spacer()

                    // Subscription upgrade banner
                    // upgradeToPro

                    // Device status widget (when device paired/connected)
                    if deviceProvider.isConnected || deviceProvider.pairedDevice != nil {
                        Spacer().frame(height: 12)
                        deviceStatusWidget
                    }

                    // Get Omi promo widget (dismissible sales link)
                    if showGetOmiWidget {
                        Spacer().frame(height: 12)
                        getOmiWidget
                    }

                    // Update available widget
                    if updaterViewModel.updateAvailable {
                        Spacer().frame(height: 12)
                        updateAvailableWidget
                            .transition(.opacity)
                    }

                    Spacer().frame(height: 16)

                    // Divider before secondary items
                    Rectangle()
                        .fill(OmiColors.backgroundTertiary.opacity(0.5))
                        .frame(height: 1)

                    Spacer().frame(height: 12)

                    // Permission warning (if any permissions missing)
                    if appState.hasMissingPermissions {
                        permissionWarningButton
                    }

                    // Secondary navigation items
                    if currentTierLevel == 0 || currentTierLevel >= 4 {
                        BottomNavItemView(
                            icon: "gift.fill",
                            label: "Refer a Friend",
                            isCollapsed: isCollapsed,
                            iconWidth: iconWidth,
                            onTap: {
                                if let url = URL(string: "https://affiliate.omi.me") {
                                    NSWorkspace.shared.open(url)
                                }
                            }
                        )
                    }

                    // Help from Founder - navigates to Crisp chat page
                    NavItemView(
                        icon: SidebarNavItem.help.icon,
                        label: SidebarNavItem.help.title,
                        isSelected: selectedIndex == SidebarNavItem.help.rawValue,
                        isCollapsed: isCollapsed,
                        iconWidth: iconWidth,
                        badge: crispManager.unreadCount,
                        onTap: {
                            selectedIndex = SidebarNavItem.help.rawValue
                            crispManager.markAsRead()
                            AnalyticsManager.shared.tabChanged(tabName: SidebarNavItem.help.title)
                        }
                    )

                    // Settings at the very bottom
                    NavItemView(
                        icon: "gearshape.fill",
                        label: "Settings",
                        isSelected: selectedIndex == SidebarNavItem.settings.rawValue,
                        isCollapsed: isCollapsed,
                        iconWidth: iconWidth,
                        onTap: { selectedIndex = SidebarNavItem.settings.rawValue }
                    )

                    Spacer().frame(height: 16)
                }
                .padding(.horizontal, isCollapsed ? 8 : 16)
                .frame(maxHeight: .infinity)
            }
            .frame(maxWidth: currentWidth + dragOffset, maxHeight: .infinity, alignment: .top)
            .background(Color.clear)
            .animation(.easeInOut(duration: 0.2), value: isCollapsed)

            // Drag handle
            Rectangle()
                .fill(Color.clear)
                .frame(width: 8)
                .contentShape(Rectangle())
                .gesture(
                    DragGesture()
                        .updating($isDragging) { _, state, _ in
                            state = true
                        }
                        .onChanged { value in
                            let newWidth = currentWidth + value.translation.width
                            if newWidth < (collapsedWidth + expandedWidth) / 2 {
                                if !isCollapsed {
                                    withAnimation(.easeInOut(duration: 0.2)) {
                                        isCollapsed = true
                                    }
                                }
                            } else {
                                if isCollapsed {
                                    withAnimation(.easeInOut(duration: 0.2)) {
                                        isCollapsed = false
                                    }
                                }
                            }
                        }
                )
                .onHover { hovering in
                    if hovering {
                        NSCursor.resizeLeftRight.push()
                    } else {
                        NSCursor.pop()
                    }
                }
        }
        .frame(width: currentWidth)
        .onAppear {
            syncMonitoringState()
            appState.checkAllPermissions()
            // Check if tier changed while sidebar wasn't visible (e.g. changed in settings, or auto-upgraded on launch)
            checkForDeferredUnlockAnimation()
        }
        .onChange(of: currentTierLevel) { _, newTier in
            // Redirect if current page became locked after tier change
            if let currentItem = SidebarNavItem(rawValue: selectedIndex),
               newTier != 0 && newTier < currentItem.requiredTier,
               selectedIndex != SidebarNavItem.settings.rawValue && selectedIndex != SidebarNavItem.permissions.rawValue && selectedIndex != SidebarNavItem.device.rawValue && selectedIndex != SidebarNavItem.help.rawValue {
                selectedIndex = SidebarNavItem.dashboard.rawValue
            }
            // If sidebar is currently visible (not in settings), play animation immediately
            if selectedIndex != SidebarNavItem.settings.rawValue {
                checkForDeferredUnlockAnimation()
            }
        }
        .onChange(of: selectedIndex) { _, _ in
            // Check tier eligibility on page navigation (at most once per day)
            Task {
                await TierManager.shared.checkTierIfNeeded()
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .assistantMonitoringStateDidChange)) { _ in
            syncMonitoringState()
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            // Refresh permissions when app becomes active (user may have changed them in System Settings)
            appState.checkAllPermissions()
        }
        .onReceive(NotificationCenter.default.publisher(for: .rewindPageDidLoad)) { _ in
            isRewindPageLoading = false
        }
        .onReceive(NotificationCenter.default.publisher(for: .conversationsPageDidLoad)) { _ in
            isConversationsPageLoading = false
        }
        .onReceive(NotificationCenter.default.publisher(for: .tasksPageDidLoad)) { _ in
            isTasksPageLoading = false
        }
        .onReceive(NotificationCenter.default.publisher(for: .focusPageDidLoad)) { _ in
            isFocusPageLoading = false
        }
        .onReceive(NotificationCenter.default.publisher(for: .advicePageDidLoad)) { _ in
            isAdvicePageLoading = false
        }
        .onReceive(NotificationCenter.default.publisher(for: .appsPageDidLoad)) { _ in
            isAppsPageLoading = false
        }
    }

    // MARK: - Header Section (Logo + Collapse Button on same row)
    private var headerSection: some View {
        HStack(spacing: 12) {
            // Omi logo icon - using the herologo from Resources
            if let logoImage = NSImage(contentsOf: Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png")!) {
                Image(nsImage: logoImage)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .frame(width: iconWidth, height: iconWidth)
            } else {
                // Fallback SF Symbol
                Image(systemName: "circle.fill")
                    .scaledFont(size: 17)
                    .foregroundColor(OmiColors.purplePrimary)
                    .frame(width: iconWidth)
            }

            if !isCollapsed {
                // Brand name
                Text(Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String ?? "Omi")
                    .scaledFont(size: 22, weight: .bold)
                    .foregroundColor(OmiColors.textPrimary)
                    .tracking(-0.5)

                Spacer()

                // Collapse button
                Button(action: {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        isCollapsed.toggle()
                    }
                }) {
                    Image(systemName: "sidebar.left")
                        .scaledFont(size: 17)
                        .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
                .help("Collapse sidebar")
            } else {
                // When collapsed, just show collapse button below logo
                Spacer()
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 11)
    }

    // Collapse button for collapsed state (shown separately)
    private var collapsedExpandButton: some View {
        Button(action: {
            withAnimation(.easeInOut(duration: 0.2)) {
                isCollapsed.toggle()
            }
        }) {
            Image(systemName: "sidebar.left")
                .scaledFont(size: 17)
                .foregroundColor(OmiColors.textTertiary)
                .frame(width: iconWidth)
        }
        .buttonStyle(.plain)
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .help("Expand sidebar")
    }

    private var proBadge: some View {
        Text("Pro")
            .scaledFont(size: 11, weight: .semibold)
            .foregroundColor(OmiColors.purplePrimary)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(OmiColors.purplePrimary.opacity(0.15))
                    .overlay(
                        RoundedRectangle(cornerRadius: 6)
                            .stroke(OmiColors.purplePrimary.opacity(0.3), lineWidth: 1)
                    )
            )
    }

    // MARK: - Upgrade to Pro
//    private var upgradeToPro: some View {
//        Button(action: {
//            if let url = URL(string: "https://omi.me/pricing") {
//                NSWorkspace.shared.open(url)
//            }
//        }) {
//            HStack(spacing: 12) {
//                Image(systemName: "bolt.fill")
//                    .scaledFont(size: 17)
//                    .foregroundColor(.white)
//                    .frame(width: iconWidth)
//
//                if !isCollapsed {
//                    Text("Upgrade to Pro")
//                        .scaledFont(size: 14, weight: .semibold)
//                        .foregroundColor(.white)
//
//                    Spacer()
//                }
//            }
//            .padding(.horizontal, 12)
//            .padding(.vertical, 11)
//            .background(
//                RoundedRectangle(cornerRadius: 10)
//                    .fill(OmiColors.purpleGradient)
//            )
//        }
//        .buttonStyle(.plain)
//        .help("Upgrade to Pro")
//    }

    // MARK: - Get Omi Widget (Sales link to omi.me)
    private var getOmiWidget: some View {
        Button(action: {
            if let url = URL(string: "https://www.omi.me") {
                NSWorkspace.shared.open(url)
            }
        }) {
            HStack(spacing: 12) {
                // Omi device image
                if let deviceImage = OmiDeviceImage.shared {
                    Image(nsImage: deviceImage)
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .frame(width: 24, height: 24)
                } else {
                    // Fallback SF Symbol
                    Image(systemName: "wave.3.right.circle.fill")
                        .scaledFont(size: 17)
                        .foregroundColor(OmiColors.purplePrimary)
                        .frame(width: iconWidth)
                }

                if !isCollapsed {
                    // Text content
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Get Omi Device")
                            .scaledFont(size: 13, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)

                        Text("Your wearable AI companion")
                            .scaledFont(size: 11)
                            .foregroundColor(OmiColors.textTertiary.opacity(0.8))
                    }

                    Spacer()

                    Button(action: {
                        withAnimation {
                            showGetOmiWidget = false
                        }
                    }) {
                        Image(systemName: "xmark")
                            .scaledFont(size: 10, weight: .medium)
                            .foregroundColor(OmiColors.textTertiary)
                            .padding(6)
                    }
                    .buttonStyle(.plain)
                    .help("Dismiss")
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 11)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(OmiColors.backgroundTertiary.opacity(0.6))
                    .overlay(
                        RoundedRectangle(cornerRadius: 10)
                            .stroke(OmiColors.backgroundQuaternary.opacity(0.3), lineWidth: 1)
                    )
            )
        }
        .buttonStyle(.plain)
        .help(isCollapsed ? "Get Omi Device" : "")
    }

    // MARK: - Update Available Widget
    @State private var updateGlowAnimating = false

    private var updateAvailableWidget: some View {
        Button(action: {
            updaterViewModel.checkForUpdates()
        }) {
            HStack(spacing: 12) {
                Image(systemName: "arrow.down.circle.fill")
                    .scaledFont(size: 17)
                    .foregroundColor(.white)
                    .frame(width: iconWidth)

                if !isCollapsed {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Update Available")
                            .scaledFont(size: 13, weight: .semibold)
                            .foregroundColor(.white)

                        if !updaterViewModel.availableVersion.isEmpty {
                            Text("v\(updaterViewModel.availableVersion)")
                                .scaledFont(size: 11)
                                .foregroundColor(.white.opacity(0.8))
                        }
                    }

                    Spacer()

                    Image(systemName: "chevron.right")
                        .scaledFont(size: 12)
                        .foregroundColor(.white.opacity(0.7))
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 11)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(OmiColors.purplePrimary)
            )
            .shadow(color: OmiColors.purplePrimary.opacity(updateGlowAnimating ? 0.7 : 0.3), radius: 8)
        }
        .buttonStyle(.plain)
        .help(isCollapsed ? "Update Available — click to install" : "")
        .onAppear {
            withAnimation(.easeInOut(duration: 1.2).repeatForever(autoreverses: true)) {
                updateGlowAnimating = true
            }
        }
    }

    // MARK: - Device Status Widget
    private var deviceStatusWidget: some View {
        Button(action: {
            // Navigate to Settings > Device tab via notification
            NotificationCenter.default.post(name: .navigateToDeviceSettings, object: nil)
        }) {
            HStack(spacing: 12) {
                // Device icon with status indicator
                ZStack(alignment: .bottomTrailing) {
                    // Device image or icon
                    if let deviceImage = OmiDeviceImage.shared {
                        Image(nsImage: deviceImage)
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .frame(width: 24, height: 24)
                            .opacity(deviceProvider.isConnected ? 1.0 : 0.5)
                    } else {
                        Image(systemName: "wave.3.right.circle.fill")
                            .scaledFont(size: 17)
                            .foregroundColor(deviceProvider.isConnected ? OmiColors.purplePrimary : OmiColors.textTertiary)
                            .frame(width: iconWidth)
                    }

                    // Connection status dot
                    Circle()
                        .fill(deviceProvider.isConnected ? Color.green : Color.orange)
                        .frame(width: 8, height: 8)
                        .offset(x: 2, y: 2)
                }

                if !isCollapsed {
                    // Text content
                    VStack(alignment: .leading, spacing: 2) {
                        if let device = deviceProvider.connectedDevice ?? deviceProvider.pairedDevice {
                            Text(device.displayName)
                                .scaledFont(size: 13, weight: .semibold)
                                .foregroundColor(OmiColors.textPrimary)
                                .lineLimit(1)

                            HStack(spacing: 6) {
                                if deviceProvider.isConnected {
                                    if deviceProvider.batteryLevel >= 0 {
                                        // Battery indicator
                                        Image(systemName: batteryIconName(level: deviceProvider.batteryLevel))
                                            .scaledFont(size: 10)
                                            .foregroundColor(batteryColor(level: deviceProvider.batteryLevel))
                                        Text("\(deviceProvider.batteryLevel)%")
                                            .scaledFont(size: 11)
                                            .foregroundColor(batteryColor(level: deviceProvider.batteryLevel))
                                    } else {
                                        Text("Connected")
                                            .scaledFont(size: 11)
                                            .foregroundColor(.green)
                                    }
                                } else {
                                    Text("Disconnected")
                                        .scaledFont(size: 11)
                                        .foregroundColor(.orange)
                                }
                            }
                        }
                    }

                    Spacer()

                    Image(systemName: "chevron.right")
                        .scaledFont(size: 12)
                        .foregroundColor(OmiColors.textTertiary)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 11)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(selectedIndex == SidebarNavItem.device.rawValue
                          ? OmiColors.backgroundTertiary.opacity(0.8)
                          : OmiColors.backgroundTertiary.opacity(0.6))
                    .overlay(
                        RoundedRectangle(cornerRadius: 10)
                            .stroke(deviceProvider.isConnected
                                    ? Color.green.opacity(0.3)
                                    : OmiColors.backgroundQuaternary.opacity(0.3), lineWidth: 1)
                    )
            )
        }
        .buttonStyle(.plain)
        .help(isCollapsed ? (deviceProvider.connectedDevice?.displayName ?? "Device Settings") : "")
    }

    private func batteryIconName(level: Int) -> String {
        switch level {
        case 0..<10: return "battery.0"
        case 10..<35: return "battery.25"
        case 35..<60: return "battery.50"
        case 60..<85: return "battery.75"
        default: return "battery.100"
        }
    }

    private func batteryColor(level: Int) -> Color {
        switch level {
        case 0..<20: return .red
        case 20..<40: return .orange
        default: return .green
        }
    }

    // MARK: - Permission Warning Button

    // Check if any permission is specifically denied (not just missing)
    private var hasPermissionDenied: Bool {
        appState.isMicrophonePermissionDenied() || appState.isScreenRecordingPermissionDenied() || appState.isNotificationPermissionDenied() || appState.isAccessibilityPermissionDenied()
    }

    @State private var permissionPulse = false

    private var permissionWarningButton: some View {
        VStack(spacing: 6) {
            // Screen Recording permission (primary for Rewind)
            // Also show if ScreenCaptureKit is broken (TCC says yes but SCK says no)
            if !appState.hasScreenRecordingPermission || appState.isScreenCaptureKitBroken {
                screenRecordingPermissionRow
            }

            // Microphone permission
            if !appState.hasMicrophonePermission {
                microphonePermissionRow
            }

            // Notification permission (show if disabled OR if banners are off)
            if !appState.hasNotificationPermission || appState.isNotificationBannerDisabled {
                notificationPermissionRow
            }

            // Accessibility permission (also show if broken: TCC says yes but AX calls fail)
            if !appState.hasAccessibilityPermission || appState.isAccessibilityBroken {
                accessibilityPermissionRow
            }
        }
        .padding(.bottom, 8)
        .onAppear {
            // Start pulsing animation when denied
            if hasPermissionDenied {
                withAnimation(.easeInOut(duration: 0.8).repeatForever(autoreverses: true)) {
                    permissionPulse = true
                }
            }
        }
        .onChange(of: hasPermissionDenied) { _, denied in
            if denied {
                withAnimation(.easeInOut(duration: 0.8).repeatForever(autoreverses: true)) {
                    permissionPulse = true
                }
            } else {
                permissionPulse = false
            }
        }
    }

    private var screenRecordingPermissionRow: some View {
        let isDenied = appState.isScreenRecordingPermissionDenied()
        let isBroken = appState.isScreenCaptureKitBroken  // TCC yes but SCK no
        let needsReset = isBroken  // Show reset when broken
        let color: Color = (isDenied || isBroken) ? .red : OmiColors.warning

        return HStack(spacing: 8) {
            Image(systemName: (isDenied || isBroken) ? "rectangle.on.rectangle.slash" : "rectangle.on.rectangle")
                .scaledFont(size: 15)
                .foregroundColor(color)
                .frame(width: iconWidth)
                .scaleEffect(permissionPulse && (isDenied || isBroken) ? 1.1 : 1.0)

            if !isCollapsed {
                Text(isBroken ? "Screen Recording (Reset Required)" : "Screen Recording")
                    .scaledFont(size: 13, weight: .medium)
                    .foregroundColor(color)
                    .lineLimit(1)

                Spacer()

                Button(action: {
                    if needsReset {
                        // Track reset button click
                        AnalyticsManager.shared.screenCaptureResetClicked(source: "sidebar_button")
                        // Reset and restart to fix broken ScreenCaptureKit state
                        ScreenCaptureService.resetScreenCapturePermissionAndRestart()
                    } else {
                        // Request both traditional TCC and ScreenCaptureKit permissions
                        ScreenCaptureService.requestAllScreenCapturePermissions()
                        // Also open settings for manual grant if needed
                        ScreenCaptureService.openScreenRecordingPreferences()
                    }
                }) {
                    Text(needsReset ? "Reset" : "Grant")
                        .scaledFont(size: 11, weight: .semibold)
                        .foregroundColor(.white)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 4)
                        .background(
                            RoundedRectangle(cornerRadius: 6)
                                .fill(color)
                        )
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 9)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(color.opacity(permissionPulse && (isDenied || isBroken) ? 0.25 : 0.15))
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(color.opacity(0.3), lineWidth: (isDenied || isBroken) ? 2 : 1)
                )
        )
        .help(isCollapsed ? (isBroken ? "Screen Recording needs reset" : "Screen Recording permission required") : "")
    }

    private var microphonePermissionRow: some View {
        let isDenied = appState.isMicrophonePermissionDenied()
        let color: Color = isDenied ? .red : OmiColors.warning

        return HStack(spacing: 8) {
            Image(systemName: isDenied ? "mic.slash.fill" : "mic.fill")
                .scaledFont(size: 15)
                .foregroundColor(color)
                .frame(width: iconWidth)
                .scaleEffect(permissionPulse && isDenied ? 1.1 : 1.0)

            if !isCollapsed {
                Text("Microphone")
                    .scaledFont(size: 13, weight: .medium)
                    .foregroundColor(color)
                    .lineLimit(1)

                Spacer()

                Button(action: {
                    if isDenied {
                        // Go to permissions page for reset options
                        selectedIndex = SidebarNavItem.permissions.rawValue
                    } else {
                        // Request permission directly
                        appState.requestMicrophonePermission()
                    }
                }) {
                    Text(isDenied ? "Fix" : "Grant")
                        .scaledFont(size: 11, weight: .semibold)
                        .foregroundColor(.white)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 4)
                        .background(
                            RoundedRectangle(cornerRadius: 6)
                                .fill(color)
                        )
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 9)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(color.opacity(permissionPulse && isDenied ? 0.25 : 0.15))
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(color.opacity(0.3), lineWidth: isDenied ? 2 : 1)
                )
        )
        .help(isCollapsed ? "Microphone permission required" : "")
    }

    private var notificationPermissionRow: some View {
        let isDenied = appState.isNotificationPermissionDenied()
        let isBannerDisabled = appState.isNotificationBannerDisabled
        let needsAttention = isDenied || isBannerDisabled
        let color: Color = needsAttention ? OmiColors.warning : OmiColors.warning

        return HStack(spacing: 8) {
            Image(systemName: isDenied ? "bell.slash.fill" : (isBannerDisabled ? "bell.badge.slash.fill" : "bell.fill"))
                .scaledFont(size: 15)
                .foregroundColor(color)
                .frame(width: iconWidth)
                .scaleEffect(permissionPulse && needsAttention ? 1.1 : 1.0)

            if !isCollapsed {
                Text(isBannerDisabled ? "Banners Off" : "Notifications")
                    .scaledFont(size: 13, weight: .medium)
                    .foregroundColor(color)
                    .lineLimit(1)

                Spacer()

                Button(action: {
                    if isBannerDisabled {
                        // Banners are off — user needs to change notification style in System Settings
                        appState.openNotificationPreferences()
                    } else {
                        // Auth is not authorized — try lsregister repair first, then fall back to System Settings
                        AnalyticsManager.shared.notificationRepairTriggered(
                            reason: "sidebar_fix_button",
                            previousStatus: "not_authorized",
                            currentStatus: "not_authorized"
                        )
                        appState.repairNotificationAndFallback()
                    }
                }) {
                    Text("Fix")
                        .scaledFont(size: 11, weight: .semibold)
                        .foregroundColor(.white)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 4)
                        .background(
                            RoundedRectangle(cornerRadius: 6)
                                .fill(color)
                        )
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 9)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(color.opacity(permissionPulse && isDenied ? 0.25 : 0.15))
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(color.opacity(0.3), lineWidth: isDenied ? 2 : 1)
                )
        )
        .help(isCollapsed ? "Notification permission required" : "")
    }

    private var accessibilityPermissionRow: some View {
        let isDenied = appState.isAccessibilityPermissionDenied()
        let isBroken = appState.isAccessibilityBroken  // TCC yes but AX calls fail
        let needsReset = isBroken  // Show reset when broken
        let color: Color = (isDenied || isBroken) ? .red : OmiColors.warning

        return HStack(spacing: 8) {
            Image(systemName: (isDenied || isBroken) ? "hand.raised.slash.fill" : "hand.raised.fill")
                .scaledFont(size: 15)
                .foregroundColor(color)
                .frame(width: iconWidth)
                .scaleEffect(permissionPulse && (isDenied || isBroken) ? 1.1 : 1.0)

            if !isCollapsed {
                Text(isBroken ? "Accessibility (Reset Required)" : "Accessibility")
                    .scaledFont(size: 13, weight: .medium)
                    .foregroundColor(color)
                    .lineLimit(1)

                Spacer()

                Button(action: {
                    if needsReset {
                        // Reset and restart to fix broken accessibility state
                        appState.resetAccessibilityPermissionAndRestart()
                    } else {
                        // Trigger the permission request, which will also open settings
                        appState.triggerAccessibilityPermission()
                    }
                }) {
                    Text(needsReset ? "Reset" : (isDenied ? "Fix" : "Grant"))
                        .scaledFont(size: 11, weight: .semibold)
                        .foregroundColor(.white)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 4)
                        .background(
                            RoundedRectangle(cornerRadius: 6)
                                .fill(color)
                        )
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 9)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(color.opacity(permissionPulse && (isDenied || isBroken) ? 0.25 : 0.15))
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(color.opacity(0.3), lineWidth: (isDenied || isBroken) ? 2 : 1)
                )
        )
        .help(isCollapsed ? (isBroken ? "Accessibility needs reset" : "Accessibility permission required") : "")
    }

    // MARK: - Toggle Handlers

    private func toggleTranscription(enabled: Bool) {
        // Check microphone permission
        if enabled && !appState.hasMicrophonePermission {
            return
        }

        // Show loading immediately
        isTogglingTranscription = true

        // Track setting change
        AnalyticsManager.shared.settingToggled(setting: "transcription", enabled: enabled)

        // Persist the setting first for immediate feedback
        AssistantSettings.shared.transcriptionEnabled = enabled

        if enabled {
            appState.startTranscription()
        } else {
            appState.stopTranscription()
        }

        // Small delay to show the loading state visually
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
            isTogglingTranscription = false
        }
    }

    private func toggleMonitoring(enabled: Bool) {
        if enabled {
            // Refresh permission cache before checking (may be stale after user granted access)
            ProactiveAssistantsPlugin.shared.refreshScreenRecordingPermission()
        }

        if enabled && !ProactiveAssistantsPlugin.shared.hasScreenRecordingPermission {
            isMonitoring = false
            // Request both traditional TCC and ScreenCaptureKit permissions
            ScreenCaptureService.requestAllScreenCapturePermissions()
            ProactiveAssistantsPlugin.shared.openScreenRecordingPreferences()
            return
        }

        // Show loading immediately and update state optimistically
        isTogglingMonitoring = true
        isMonitoring = enabled

        // Track setting change
        AnalyticsManager.shared.settingToggled(setting: "monitoring", enabled: enabled)

        // Persist the setting
        screenAnalysisEnabled = enabled
        AssistantSettings.shared.screenAnalysisEnabled = enabled

        // Also toggle audio transcription to match (Rewind bundles both)
        if enabled && !appState.isTranscribing {
            appState.startTranscription()
        } else if !enabled && appState.isTranscribing {
            appState.stopTranscription()
        }

        if enabled {
            ProactiveAssistantsPlugin.shared.startMonitoring { success, _ in
                DispatchQueue.main.async {
                    isTogglingMonitoring = false
                    if !success {
                        // Revert on failure including persistent setting
                        isMonitoring = false
                        screenAnalysisEnabled = false
                        AssistantSettings.shared.screenAnalysisEnabled = false
                    }
                }
            }
        } else {
            ProactiveAssistantsPlugin.shared.stopMonitoring()
            // Small delay to show the loading state visually
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                isTogglingMonitoring = false
            }
        }
    }

    private func syncMonitoringState() {
        let pluginState = ProactiveAssistantsPlugin.shared.isMonitoring
        isMonitoring = pluginState
        // Keep persistent setting in sync when monitoring stops due to errors
        if !pluginState && screenAnalysisEnabled {
            screenAnalysisEnabled = false
            AssistantSettings.shared.screenAnalysisEnabled = false
        }
    }

    // MARK: - Page Loading Helpers

    private func pageLoadingState(for item: SidebarNavItem) -> Bool {
        switch item {
        case .tasks: return isTasksPageLoading
        case .focus: return isFocusPageLoading
        case .advice: return isAdvicePageLoading
        case .apps: return isAppsPageLoading
        default: return false
        }
    }

    private func setPageLoading(for item: SidebarNavItem, loading: Bool) {
        switch item {
        case .tasks: isTasksPageLoading = loading
        case .focus: isFocusPageLoading = loading
        case .advice: isAdvicePageLoading = loading
        case .apps: isAppsPageLoading = loading
        default: break
        }
    }

    // MARK: - Tier Unlock Animation

    /// Compare lastSeenTierLevel to currentTierLevel and animate any newly visible items.
    /// Called on onAppear (returning from settings) and onChange when sidebar is visible.
    private func checkForDeferredUnlockAnimation() {
        guard lastSeenTierLevel != currentTierLevel else { return }

        let oldVisible = Self.visibleItems(for: lastSeenTierLevel)
        let newVisible = Self.visibleItems(for: currentTierLevel)
        let unlocked = Set(newVisible).subtracting(Set(oldVisible))

        // Update lastSeen immediately so we don't re-trigger
        lastSeenTierLevel = currentTierLevel

        guard !unlocked.isEmpty else { return }

        // Small delay so the sidebar has time to render before animating
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
            withAnimation(.easeOut(duration: 0.4)) {
                newlyUnlockedItems = unlocked
            }
            // Clear after full celebration plays (highlight 0.3s + confetti 1.5s + text 1.5s + buffer)
            DispatchQueue.main.asyncAfter(deadline: .now() + 4.0) {
                withAnimation(.easeOut(duration: 0.5)) {
                    newlyUnlockedItems = []
                }
            }
        }
    }
}

// MARK: - Nav Item View
struct NavItemView: View {
    let icon: String
    let label: String
    let isSelected: Bool
    let isCollapsed: Bool
    let iconWidth: CGFloat
    var badge: Int = 0
    var statusColor: Color? = nil
    var isLoading: Bool = false
    var isLocked: Bool = false
    var lockTooltip: String? = nil
    var onUnlock: (() -> Void)? = nil
    let onTap: () -> Void

    @State private var isHovered = false
    @State private var isLockHovered = false

    /// Foreground color for icon and text when locked
    private var lockedColor: Color { OmiColors.textQuaternary.opacity(0.45) }

    var body: some View {
        HStack(spacing: 12) {
            ZStack(alignment: .topTrailing) {
                if isLoading && !isLocked {
                    ProgressView()
                        .scaleEffect(0.5)
                        .frame(width: iconWidth, height: 17)
                } else {
                    Image(systemName: icon)
                        .scaledFont(size: 17)
                        .foregroundColor(isLocked ? lockedColor : (isSelected ? OmiColors.textPrimary : OmiColors.textTertiary))
                        .frame(width: iconWidth)
                }

                // Badge on icon (collapsed = dot, expanded = count)
                if badge > 0 && !isLocked {
                    if isCollapsed {
                        Circle()
                            .fill(OmiColors.purplePrimary)
                            .frame(width: 8, height: 8)
                            .offset(x: 4, y: -4)
                    } else {
                        Text("\(badge)")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundColor(.white)
                            .frame(minWidth: 14, minHeight: 14)
                            .background(OmiColors.purplePrimary)
                            .clipShape(Circle())
                            .offset(x: 6, y: -6)
                    }
                }

                // Status indicator when collapsed (for Focus, hidden when locked)
                if isCollapsed, let color = statusColor, !isLocked {
                    Circle()
                        .fill(color)
                        .frame(width: 8, height: 8)
                        .offset(x: 4, y: -4)
                }

                // Lock badge when collapsed — clickable
                if isCollapsed && isLocked {
                    lockIcon(size: 8)
                        .offset(x: 4, y: -4)
                }
            }

            if !isCollapsed {
                Text(label)
                    .scaledFont(size: 14, weight: isSelected ? .medium : .regular)
                    .foregroundColor(isLocked ? lockedColor : (isSelected ? OmiColors.textPrimary : OmiColors.textSecondary))

                Spacer()

                if isLocked {
                    // Clickable lock icon
                    lockIcon(size: 10)
                } else {
                    // Status indicator when expanded (for Focus)
                    if let color = statusColor {
                        Circle()
                            .fill(color)
                            .frame(width: 8, height: 8)
                    }

                    // Badge count now shown on icon (see ZStack above)
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 11)
        .contentShape(Rectangle())
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(isLocked ? Color.clear : (isSelected
                      ? OmiColors.backgroundTertiary.opacity(0.8)
                      : (isHovered ? OmiColors.backgroundTertiary.opacity(0.5) : Color.clear)))
        )
        .onTapGesture {
            guard !isLocked else { return }
            log("SIDEBAR: NavItem '\(label)' tapped at mouse position: \(NSEvent.mouseLocation)")
            onTap()
        }
        .onHover { hovering in
            isHovered = isLocked ? false : hovering
        }
        .padding(.bottom, 2)
        .help(isCollapsed ? label : "")
    }

    /// Lock icon that reacts on hover and unlocks on click
    private func lockIcon(size: CGFloat) -> some View {
        Image(systemName: isLockHovered ? "lock.open.fill" : "lock.fill")
            .scaledFont(size: size)
            .foregroundColor(isLockHovered ? OmiColors.purplePrimary : lockedColor)
            .padding(4)
            .contentShape(Rectangle())
            .onHover { hovering in
                withAnimation(.easeInOut(duration: 0.15)) {
                    isLockHovered = hovering
                }
            }
            .onTapGesture {
                onUnlock?()
            }
            .help("Click to unlock")
    }
}

// MARK: - Nav Item With Status Icon View
/// Navigation item that shows status via icon color/animation instead of a toggle
struct NavItemWithStatusView: View {
    let icon: String
    let label: String
    let isSelected: Bool
    let isCollapsed: Bool
    let iconWidth: CGFloat
    let isOn: Bool
    let isToggling: Bool
    var isPageLoading: Bool = false
    let onTap: () -> Void
    let onToggle: () -> Void

    // Optional audio levels for conversations
    var micLevel: Float = 0
    var systemLevel: Float = 0
    var showAudioBars: Bool = false

    // Optional Rewind pulsing icon
    var showRewindIcon: Bool = false

    @State private var isHovered = false

    /// Icon color based on state
    private var iconColor: Color {
        if isOn {
            return isSelected ? OmiColors.textPrimary : OmiColors.textTertiary
        } else {
            return OmiColors.error
        }
    }

    var body: some View {
        HStack(spacing: 12) {
            // Icon area - tappable to toggle
            ZStack(alignment: .topTrailing) {
                // Show loading spinner in place of icon when loading
                if isToggling || isPageLoading {
                    ProgressView()
                        .scaleEffect(0.5)
                        .frame(width: iconWidth, height: 17)
                } else if showAudioBars && isOn {
                    // Show audio bars when active and enabled for conversations
                    SidebarAudioLevelIcon(
                        micLevel: micLevel,
                        systemLevel: systemLevel,
                        isActive: true
                    )
                    .frame(width: iconWidth)
                } else if showRewindIcon {
                    // Show pulsing Rewind icon
                    SidebarRewindIcon(isActive: isOn)
                        .frame(width: iconWidth)
                } else {
                    Image(systemName: icon)
                        .scaledFont(size: 17)
                        .foregroundColor(iconColor)
                        .frame(width: iconWidth)
                }

                // Status indicator when collapsed and off
                if isCollapsed && !isOn && !isToggling && !isPageLoading {
                    Circle()
                        .fill(OmiColors.error)
                        .frame(width: 6, height: 6)
                        .offset(x: 3, y: -3)
                }
            }
            .contentShape(Rectangle())
            .onTapGesture {
                if !isToggling {
                    onToggle()
                }
            }

            if !isCollapsed {
                Text(label)
                    .scaledFont(size: 14, weight: isSelected ? .medium : .regular)
                    .foregroundColor(isSelected ? OmiColors.textPrimary : OmiColors.textSecondary)
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)

                Spacer(minLength: 4)
            }
        }
        .padding(.leading, 12)
        .padding(.trailing, isCollapsed ? 12 : 8)
        .padding(.vertical, 11)
        .contentShape(Rectangle())
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(isSelected
                      ? OmiColors.backgroundTertiary.opacity(0.8)
                      : (isHovered ? OmiColors.backgroundTertiary.opacity(0.5) : Color.clear))
        )
        .onTapGesture {
            log("SIDEBAR: NavItemWithStatus '\(label)' row tapped at mouse position: \(NSEvent.mouseLocation)")
            onTap()
        }
        .onHover { hovering in
            isHovered = hovering
        }
        .padding(.bottom, 2)
        .help(isCollapsed ? "\(label) (\(isOn ? "On" : "Off")) - Click icon to toggle" : "Click icon to toggle")
    }
}

// MARK: - Custom Sidebar Toggle
struct SidebarToggle: View {
    @Binding var isOn: Bool

    private let width: CGFloat = 36
    private let height: CGFloat = 20
    private let circleSize: CGFloat = 16
    private let padding: CGFloat = 2

    var body: some View {
        ZStack(alignment: isOn ? .trailing : .leading) {
            // Track - purple when on, red when off
            Capsule()
                .fill(isOn ? OmiColors.purplePrimary : OmiColors.error)
                .frame(width: width, height: height)

            // Thumb
            Circle()
                .fill(Color.white)
                .frame(width: circleSize, height: circleSize)
                .padding(padding)
                .shadow(color: .black.opacity(0.15), radius: 1, x: 0, y: 1)
        }
        .animation(.easeInOut(duration: 0.15), value: isOn)
        .onTapGesture {
            isOn.toggle()
        }
    }
}

// MARK: - Sidebar Audio Level Icon
/// Compact audio level indicator that fits in the sidebar icon space
struct SidebarAudioLevelIcon: View {
    let micLevel: Float
    let systemLevel: Float
    let isActive: Bool

    private let barCount = 4
    private let iconSize: CGFloat = 17

    /// Combined audio level (max of mic and system)
    private var combinedLevel: Float {
        max(micLevel, systemLevel)
    }

    var body: some View {
        HStack(spacing: 2) {
            ForEach(0..<barCount, id: \.self) { index in
                SidebarAudioBar(
                    level: combinedLevel,
                    index: index,
                    totalBars: barCount,
                    isActive: isActive
                )
            }
        }
        .frame(width: iconSize, height: iconSize)
    }
}

private struct SidebarAudioBar: View {
    let level: Float
    let index: Int
    let totalBars: Int
    let isActive: Bool

    private let minHeight: CGFloat = 4
    private let maxHeight: CGFloat = 14
    private let barWidth: CGFloat = 3

    private var barHeight: CGFloat {
        guard isActive else { return minHeight }

        // Boost low levels for visibility
        let boostedLevel = pow(CGFloat(level), 0.5) * 2.0
        let clampedLevel = min(1.0, boostedLevel)

        // Center bars slightly taller
        let centerOffset = abs(CGFloat(index) - CGFloat(totalBars - 1) / 2.0) / (CGFloat(totalBars) / 2.0)
        let variation = 1.0 - (centerOffset * 0.3)

        let scaledLevel = clampedLevel * variation
        let randomVariation = CGFloat.random(in: 0.9...1.1)

        let height = minHeight + (maxHeight - minHeight) * scaledLevel * randomVariation
        return max(minHeight, min(maxHeight, height))
    }

    private var barColor: Color {
        guard isActive else { return OmiColors.textTertiary.opacity(0.5) }

        let boostedLevel = min(1.0, pow(CGFloat(level), 0.5) * 2.0)
        if boostedLevel > 0.5 {
            return OmiColors.purplePrimary
        } else if boostedLevel > 0.15 {
            return OmiColors.textPrimary
        } else if boostedLevel > 0.02 {
            return OmiColors.textSecondary
        }
        return OmiColors.textTertiary
    }

    var body: some View {
        RoundedRectangle(cornerRadius: 1)
            .fill(barColor)
            .frame(width: barWidth, height: barHeight)
            .animation(.easeOut(duration: 0.08), value: level)
    }
}

// MARK: - Sidebar Rewind Icon
/// Animated recording indicator for Rewind when capturing
struct SidebarRewindIcon: View {
    let isActive: Bool

    private let iconSize: CGFloat = 17

    @State private var isPulsing = false

    var body: some View {
        ZStack {
            // Outer pulsing ring when active
            if isActive {
                Circle()
                    .stroke(OmiColors.purplePrimary.opacity(0.3), lineWidth: 2)
                    .frame(width: iconSize, height: iconSize)
                    .scaleEffect(isPulsing ? 1.4 : 1.0)
                    .opacity(isPulsing ? 0 : 0.8)
            }

            // Inner recording dot
            Circle()
                .fill(isActive ? OmiColors.purplePrimary : OmiColors.error)
                .frame(width: isActive ? 10 : 8, height: isActive ? 10 : 8)
        }
        .frame(width: iconSize, height: iconSize)
        .onAppear {
            if isActive {
                startPulsing()
            }
        }
        .onChange(of: isActive) { _, newValue in
            if newValue {
                startPulsing()
            } else {
                isPulsing = false
            }
        }
    }

    private func startPulsing() {
        withAnimation(.easeOut(duration: 1.0).repeatForever(autoreverses: false)) {
            isPulsing = true
        }
    }
}

// MARK: - Tier Unlock Celebration
/// Multi-phase celebration overlay: highlight → confetti → glowing text
struct TierUnlockCelebration: View {
    let isActive: Bool

    @State private var phase: CelebrationPhase = .idle

    enum CelebrationPhase {
        case idle, highlight, confetti, text, done
    }

    var body: some View {
        ZStack {
            // Phase 1: Purple highlight border
            if phase == .highlight || phase == .confetti || phase == .text {
                RoundedRectangle(cornerRadius: 10)
                    .stroke(OmiColors.purplePrimary, lineWidth: phase == .highlight ? 2.5 : 1.5)
                    .shadow(color: OmiColors.purplePrimary.opacity(phase == .highlight ? 0.8 : 0.3), radius: phase == .highlight ? 12 : 4)
                    .transition(.opacity)
            }

            // Phase 2: Confetti particles
            if phase == .confetti || phase == .text {
                ConfettiView()
                    .allowsHitTesting(false)
                    .transition(.opacity)
            }

            // Phase 3: Glowing "Unlocked!" text
            if phase == .text {
                Text("Unlocked!")
                    .scaledFont(size: 11, weight: .bold)
                    .foregroundColor(.white)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(
                        Capsule()
                            .fill(OmiColors.purplePrimary)
                            .shadow(color: OmiColors.purplePrimary.opacity(0.8), radius: 8)
                    )
                    .transition(.scale(scale: 0.5).combined(with: .opacity))
                    .offset(x: 30, y: -8)
            }
        }
        .onChange(of: isActive) { _, active in
            if active {
                startCelebration()
            } else {
                withAnimation(.easeOut(duration: 0.3)) {
                    phase = .idle
                }
            }
        }
    }

    private func startCelebration() {
        // Phase 1: Highlight (immediate)
        withAnimation(.easeOut(duration: 0.3)) {
            phase = .highlight
        }
        // Phase 2: Confetti (after 0.4s)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
            withAnimation(.easeOut(duration: 0.3)) {
                phase = .confetti
            }
        }
        // Phase 3: Text (after 1.0s)
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
            withAnimation(.spring(response: 0.4, dampingFraction: 0.6)) {
                phase = .text
            }
        }
    }
}

// MARK: - Confetti View
/// Burst of small colored particles that animate outward from center
struct ConfettiView: View {
    @State private var animate = false
    @State private var fadeOut = false

    // Pre-computed particle configs (fixed set for reliable animation)
    private let particleConfigs: [(color: Color, size: CGFloat, angle: Double, distance: CGFloat, rotation: Double, isRect: Bool)] = {
        let colors: [Color] = [
            OmiColors.purplePrimary, OmiColors.purplePrimary.opacity(0.7),
            .yellow, .green, .pink, .cyan, .orange, .mint, .indigo
        ]
        return (0..<18).map { _ in
            (
                color: colors.randomElement()!,
                size: CGFloat.random(in: 3...6),
                angle: Double.random(in: 0...(2 * .pi)),
                distance: CGFloat.random(in: 40...120),
                rotation: Double.random(in: 0...720),
                isRect: Bool.random()
            )
        }
    }()

    var body: some View {
        GeometryReader { geo in
            let cx = geo.size.width / 2
            let cy = geo.size.height / 2

            ZStack {
                ForEach(0..<particleConfigs.count, id: \.self) { i in
                    let p = particleConfigs[i]
                    Group {
                        if p.isRect {
                            RoundedRectangle(cornerRadius: 1)
                                .fill(p.color)
                        } else {
                            Circle()
                                .fill(p.color)
                        }
                    }
                    .frame(width: p.size, height: p.size * (p.isRect ? 2 : 1))
                    .rotationEffect(.degrees(animate ? p.rotation : 0))
                    .offset(
                        x: animate ? cos(p.angle) * p.distance : 0,
                        y: animate ? sin(p.angle) * p.distance - 20 : 0
                    )
                    .scaleEffect(animate ? (fadeOut ? 0.1 : 1.0) : 0.1)
                    .opacity(fadeOut ? 0 : 1)
                    .position(x: cx, y: cy)
                }
            }
        }
        .onAppear {
            // Burst outward
            withAnimation(.easeOut(duration: 0.7)) {
                animate = true
            }
            // Fade out
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.9) {
                withAnimation(.easeOut(duration: 0.5)) {
                    fadeOut = true
                }
            }
        }
    }
}

// MARK: - Bottom Nav Item View
struct BottomNavItemView: View {
    let icon: String
    let label: String
    let isCollapsed: Bool
    let iconWidth: CGFloat
    let onTap: () -> Void

    @State private var isHovered = false

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .scaledFont(size: 17)
                .foregroundColor(OmiColors.textTertiary)
                .frame(width: iconWidth)

            if !isCollapsed {
                Text(label)
                    .scaledFont(size: 14, weight: .regular)
                    .foregroundColor(OmiColors.textSecondary)

                Spacer()
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 11)
        .contentShape(Rectangle())
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(isHovered ? OmiColors.backgroundTertiary.opacity(0.5) : Color.clear)
        )
        .onTapGesture {
            log("SIDEBAR: BottomNavItem '\(label)' tapped at mouse position: \(NSEvent.mouseLocation)")
            onTap()
        }
        .onHover { hovering in
            isHovered = hovering
        }
        .padding(.bottom, 2)
        .help(isCollapsed ? label : "")
    }
}

// MARK: - Audio Level Nav Item Wrapper

/// Isolates AudioLevelMonitor observation so audio level changes
/// only re-render this small wrapper, not the entire SidebarView.
private struct AudioLevelNavItem: View {
    let icon: String
    let label: String
    let isSelected: Bool
    let isCollapsed: Bool
    let iconWidth: CGFloat
    let isOn: Bool
    let isToggling: Bool
    var isPageLoading: Bool = false
    let onTap: () -> Void
    let onToggle: () -> Void

    @ObservedObject private var audioLevels = AudioLevelMonitor.shared

    var body: some View {
        NavItemWithStatusView(
            icon: icon,
            label: label,
            isSelected: isSelected,
            isCollapsed: isCollapsed,
            iconWidth: iconWidth,
            isOn: isOn,
            isToggling: isToggling,
            isPageLoading: isPageLoading,
            onTap: onTap,
            onToggle: onToggle,
            micLevel: audioLevels.microphoneLevel,
            systemLevel: audioLevels.systemLevel,
            showAudioBars: true
        )
    }
}

// MARK: - Cached Omi Device Image

/// Cache the Omi device WebP image so it's decoded once, not on every SwiftUI body evaluation.
/// The original 1383x1383 WebP was being re-decoded by CoreAnimation every render frame.
enum OmiDeviceImage {
    static let shared: NSImage? = {
        guard let url = Bundle.resourceBundle.url(forResource: "omi-with-rope-no-padding", withExtension: "webp") else {
            return nil
        }
        return NSImage(contentsOf: url)
    }()
}
