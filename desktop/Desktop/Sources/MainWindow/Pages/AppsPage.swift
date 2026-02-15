import SwiftUI
import AppKit

// MARK: - Safe Dismiss Button
/// A dismiss button that prevents click-through to underlying views on macOS.
/// Uses onTapGesture with async delay to ensure the click is fully consumed before dismissing.
/// The key is to wait for the full mouse event cycle to complete before triggering dismiss.
struct SafeDismissButton: View {
    let dismiss: DismissAction
    var icon: String = "xmark"
    var showBackground: Bool = true

    @State private var isPressed = false

    var body: some View {
        Image(systemName: icon)
            .scaledFont(size: 14, weight: .medium)
            .foregroundColor(isPressed ? OmiColors.textTertiary : OmiColors.textSecondary)
            .frame(width: 28, height: 28)
            .background(showBackground ? OmiColors.backgroundSecondary : Color.clear)
            .clipShape(Circle())
            .contentShape(Circle())
            .opacity(isPressed ? 0.7 : 1.0)
            .onTapGesture {
                guard !isPressed else { return } // Prevent double-tap
                isPressed = true

                let mouseLocation = NSEvent.mouseLocation
                log("DISMISS: Tap gesture fired at mouse position: \(mouseLocation)")

                // Consume the click by resigning first responder
                NSApp.keyWindow?.makeFirstResponder(nil)

                // Post a mouse-up event to ensure any pending click is consumed
                if let window = NSApp.keyWindow {
                    let event = NSEvent.mouseEvent(
                        with: .leftMouseUp,
                        location: window.mouseLocationOutsideOfEventStream,
                        modifierFlags: [],
                        timestamp: ProcessInfo.processInfo.systemUptime,
                        windowNumber: window.windowNumber,
                        context: nil,
                        eventNumber: 0,
                        clickCount: 1,
                        pressure: 0
                    )
                    if let event = event {
                        window.sendEvent(event)
                        log("DISMISS: Sent synthetic mouse-up event")
                    }
                }

                // Use async with longer delay to ensure mouse event fully completes
                Task { @MainActor in
                    log("DISMISS: Starting 250ms delay before dismiss")
                    // Longer delay to ensure mouse-up event is fully processed
                    try? await Task.sleep(nanoseconds: 250_000_000) // 250ms
                    log("DISMISS: Delay complete, calling dismiss()")
                    log("DISMISS: Mouse position before dismiss: \(NSEvent.mouseLocation)")
                    dismiss()
                    log("DISMISS: dismiss() called")
                }
            }
    }
}

// MARK: - Dismiss Button (Action-based)
/// A dismiss button that takes a closure instead of a DismissAction.
/// Used for overlay-based sheets where the dismiss is controlled externally.
struct DismissButton: View {
    let action: () -> Void
    var icon: String = "xmark"
    var showBackground: Bool = true

    @State private var isPressed = false

    var body: some View {
        Image(systemName: icon)
            .scaledFont(size: 14, weight: .medium)
            .foregroundColor(isPressed ? OmiColors.textTertiary : OmiColors.textSecondary)
            .frame(width: 28, height: 28)
            .background(showBackground ? OmiColors.backgroundSecondary : Color.clear)
            .clipShape(Circle())
            .contentShape(Circle())
            .opacity(isPressed ? 0.7 : 1.0)
            .onTapGesture {
                guard !isPressed else { return }
                isPressed = true

                log("DISMISS_BUTTON: Tap gesture fired")

                // Consume the click by resigning first responder
                NSApp.keyWindow?.makeFirstResponder(nil)

                // Small delay then dismiss
                Task { @MainActor in
                    try? await Task.sleep(nanoseconds: 50_000_000) // 50ms
                    log("DISMISS_BUTTON: Calling action")
                    withAnimation(.easeOut(duration: 0.2)) {
                        action()
                    }
                }
            }
    }
}

struct AppsPage: View {
    @ObservedObject var appProvider: AppProvider
    @State private var searchText = ""
    @State private var selectedApp: OmiApp?
    @State private var showPersonaPage = false
    @State private var viewAllSection: String? = nil  // "featured", "integrations", "notifications"

    var body: some View {
        VStack(spacing: 0) {
            // Search bar
            searchBar
                .padding()

            Divider()
                .background(OmiColors.backgroundTertiary)

            // Content
            if appProvider.isLoading {
                loadingShimmerView
            } else if appProvider.apps.isEmpty && appProvider.popularApps.isEmpty {
                emptyView
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 24) {
                        if !searchText.isEmpty || hasActiveFilters {
                            // Show filtered/search results in a flat grid
                            if appProvider.isSearching {
                                // Loading state for category filter
                                VStack(spacing: 16) {
                                    ProgressView()
                                        .scaleEffect(1.2)
                                    Text("Loading...")
                                        .scaledFont(size: 14)
                                        .foregroundColor(OmiColors.textTertiary)
                                }
                                .frame(maxWidth: .infinity, minHeight: 200)
                            } else if filteredApps.isEmpty {
                                VStack(spacing: 12) {
                                    Image(systemName: "magnifyingglass")
                                        .scaledFont(size: 32)
                                        .foregroundColor(OmiColors.textTertiary)
                                    Text("No apps found")
                                        .scaledFont(size: 16, weight: .medium)
                                        .foregroundColor(OmiColors.textSecondary)
                                }
                                .frame(maxWidth: .infinity, minHeight: 200)
                            } else {
                                // Back button for "See more" view
                                if viewAllSection != nil {
                                    Button(action: { viewAllSection = nil }) {
                                        HStack(spacing: 6) {
                                            Image(systemName: "chevron.left")
                                                .scaledFont(size: 12, weight: .medium)
                                            Text("Back")
                                                .scaledFont(size: 13, weight: .medium)
                                        }
                                        .foregroundColor(OmiColors.textSecondary)
                                    }
                                    .buttonStyle(.plain)
                                }

                                AppGridSection(
                                    title: filterResultsTitle,
                                    apps: filteredApps,
                                    appProvider: appProvider,
                                    onSelectApp: { selectedApp = $0 }
                                )

                                // Infinite scroll: load more when reaching bottom
                                if appProvider.hasMoreCategoryApps {
                                    HStack {
                                        Spacer()
                                        if appProvider.isLoadingMore {
                                            ProgressView()
                                                .scaleEffect(0.8)
                                            Text("Loading more...")
                                                .scaledFont(size: 13)
                                                .foregroundColor(OmiColors.textTertiary)
                                        } else {
                                            Color.clear
                                                .frame(height: 1)
                                                .onAppear {
                                                    Task {
                                                        await appProvider.loadMoreCategoryApps()
                                                    }
                                                }
                                        }
                                        Spacer()
                                    }
                                    .padding(.vertical, 16)
                                }
                            }
                        } else {
                            // Featured section (apps marked as is_popular in backend)
                            if !appProvider.popularApps.isEmpty {
                                HorizontalAppSection(
                                    title: "Featured",
                                    apps: Array(appProvider.popularApps.prefix(6)),
                                    appProvider: appProvider,
                                    onSelectApp: { selectedApp = $0 },
                                    showSeeMore: appProvider.popularApps.count >= 6,
                                    onSeeMore: { viewAllSection = "featured" }
                                )
                            }

                            // Integrations section (external_integration capability)
                            if !appProvider.integrationApps.isEmpty {
                                HorizontalAppSection(
                                    title: "Integrations",
                                    apps: Array(appProvider.integrationApps.prefix(6)),
                                    appProvider: appProvider,
                                    onSelectApp: { selectedApp = $0 },
                                    showSeeMore: appProvider.integrationApps.count >= 6,
                                    onSeeMore: { viewAllSection = "integrations" }
                                )
                            }

                            // Realtime Notifications section (proactive_notification capability)
                            if !appProvider.notificationApps.isEmpty {
                                HorizontalAppSection(
                                    title: "Realtime Notifications",
                                    apps: Array(appProvider.notificationApps.prefix(6)),
                                    appProvider: appProvider,
                                    onSelectApp: { selectedApp = $0 },
                                    showSeeMore: appProvider.notificationApps.count >= 6,
                                    onSeeMore: { viewAllSection = "notifications" }
                                )
                            }
                        }
                    }
                    .padding()
                }
            }
        }
        .background(OmiColors.backgroundPrimary)
        .onChange(of: searchText) { _, newValue in
            appProvider.searchQuery = newValue
            // Clear filters when searching
            if !newValue.isEmpty {
                viewAllSection = nil
                if appProvider.selectedCategory != nil {
                    appProvider.clearCategoryFilter()
                }
            }
            Task {
                // Debounce search
                try? await Task.sleep(for: .milliseconds(300))
                if appProvider.searchQuery == newValue {
                    await appProvider.searchApps()
                }
            }
        }
        .dismissableSheet(item: $selectedApp) { app in
            AppDetailSheet(app: app, appProvider: appProvider, onDismiss: { selectedApp = nil })
                .frame(width: 500, height: 650)
                .onAppear {
                    AnalyticsManager.shared.appDetailViewed(appId: app.id, appName: app.name)
                }
        }
        .dismissableSheet(isPresented: $showPersonaPage) {
            PersonaPage(onDismiss: {
                showPersonaPage = false
            })
            .frame(width: 500, height: 650)
        }
        .onAppear {
            // If apps are already loaded, notify sidebar to clear loading indicator
            if !appProvider.isLoading {
                NotificationCenter.default.post(name: .appsPageDidLoad, object: nil)
            }
        }
    }

    private var searchBar: some View {
        HStack(spacing: 10) {
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundColor(OmiColors.textTertiary)

                TextField("Search apps...", text: $searchText)
                    .textFieldStyle(.plain)
                    .foregroundColor(OmiColors.textPrimary)

                if !searchText.isEmpty {
                    Button(action: { searchText = "" }) {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(OmiColors.textTertiary)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(10)
            .background(OmiColors.backgroundSecondary)
            .cornerRadius(10)

            // Filter toggles
            FilterToggle(
                icon: "arrow.down.circle",
                label: "Installed",
                isActive: appProvider.showInstalledOnly
            ) {
                viewAllSection = nil
                appProvider.showInstalledOnly.toggle()
                Task { await appProvider.searchApps() }
            }

            // Category dropdown
            Menu {
                Button(action: {
                    viewAllSection = nil
                    appProvider.clearCategoryFilter()
                }) {
                    HStack {
                        Text("All Categories")
                        if appProvider.selectedCategory == nil {
                            Image(systemName: "checkmark")
                        }
                    }
                }

                Divider()

                ForEach(appProvider.categories) { category in
                    Button(action: {
                        viewAllSection = nil
                        appProvider.selectedCategory = category.id
                        Task { await appProvider.fetchAppsForCategory(category.id) }
                    }) {
                        HStack {
                            Text(category.title)
                            if appProvider.selectedCategory == category.id {
                                Image(systemName: "checkmark")
                            }
                        }
                    }
                }
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "line.3.horizontal.decrease.circle")
                        .scaledFont(size: 12)
                    Text(selectedCategoryLabel)
                        .scaledFont(size: 13)
                    Image(systemName: "chevron.down")
                        .scaledFont(size: 9, weight: .medium)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(OmiColors.backgroundSecondary)
                .foregroundColor(appProvider.selectedCategory != nil ? OmiColors.textPrimary : OmiColors.textSecondary)
                .cornerRadius(8)
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(appProvider.selectedCategory != nil ? OmiColors.border : Color.clear, lineWidth: 1)
                )
            }
            .menuStyle(.borderlessButton)
            .fixedSize()

            Spacer()

            // Create buttons (compact)
            HStack(spacing: 8) {
                SmallHeaderButton(
                    icon: "app.badge.fill",
                    label: "Create App",
                    color: OmiColors.purplePrimary
                ) {
                    if let url = URL(string: "https://docs.omi.me/docs/developer/apps/Introduction") {
                        NSWorkspace.shared.open(url)
                    }
                }

                SmallHeaderButton(
                    icon: "person.crop.circle.fill",
                    label: "My Clone",
                    color: .blue
                ) {
                    showPersonaPage = true
                }
            }
        }
    }

    private var hasActiveFilters: Bool {
        appProvider.selectedCategory != nil || viewAllSection != nil
    }

    private var selectedCategoryLabel: String {
        if let categoryId = appProvider.selectedCategory,
           let category = appProvider.categories.first(where: { $0.id == categoryId }) {
            return category.title
        }
        return "Category"
    }

    /// Apps for the selected category (from API) or search results or "See more" section
    private var filteredApps: [OmiApp] {
        // "See more" section takes priority
        if let section = viewAllSection {
            switch section {
            case "featured": return appProvider.popularApps
            case "integrations": return appProvider.integrationApps
            case "notifications": return appProvider.notificationApps
            default: return []
            }
        }
        if appProvider.selectedCategory != nil {
            return appProvider.categoryFilteredApps ?? []
        }
        return appProvider.apps
    }

    private var filterResultsTitle: String {
        let apps = filteredApps
        // "See more" section title
        if let section = viewAllSection {
            let title = switch section {
            case "featured": "Featured"
            case "integrations": "Integrations"
            case "notifications": "Realtime Notifications"
            default: "Apps"
            }
            return "\(title) (\(apps.count))"
        }
        if !searchText.isEmpty {
            return "Search Results (\(apps.count))"
        }
        if let categoryId = appProvider.selectedCategory,
           let category = appProvider.categories.first(where: { $0.id == categoryId }) {
            return "\(category.title) (\(apps.count))"
        }
        return "Results (\(apps.count))"
    }


    private var loadingShimmerView: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // Shimmer sections
                ForEach(0..<3, id: \.self) { _ in
                    VStack(alignment: .leading, spacing: 12) {
                        ShimmerView()
                            .frame(width: 120, height: 24)
                            .cornerRadius(6)

                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 16) {
                                ForEach(0..<4, id: \.self) { _ in
                                    ShimmerAppCard()
                                }
                            }
                        }
                    }
                }
            }
            .padding()
        }
    }

    private var emptyView: some View {
        VStack(spacing: 16) {
            Image(systemName: "square.grid.2x2")
                .scaledFont(size: 48)
                .foregroundColor(OmiColors.textTertiary)

            Text("No apps found")
                .scaledFont(size: 20, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

            if !searchText.isEmpty {
                Text("Try a different search term")
                    .foregroundColor(OmiColors.textTertiary)

                Button("Clear Search") {
                    searchText = ""
                }
                .buttonStyle(.bordered)
            } else {
                Text("Apps will appear here once available")
                    .foregroundColor(OmiColors.textTertiary)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - Shimmer Views

struct ShimmerView: View {
    @State private var isAnimating = false

    var body: some View {
        Rectangle()
            .fill(
                LinearGradient(
                    colors: [
                        OmiColors.backgroundSecondary,
                        OmiColors.backgroundTertiary,
                        OmiColors.backgroundSecondary
                    ],
                    startPoint: .leading,
                    endPoint: .trailing
                )
            )
            .mask(Rectangle())
            .offset(x: isAnimating ? 200 : -200)
            .animation(.linear(duration: 1.5).repeatForever(autoreverses: false), value: isAnimating)
            .onAppear { isAnimating = true }
    }
}

struct ShimmerAppCard: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ShimmerView()
                .frame(width: 60, height: 60)
                .cornerRadius(12)

            ShimmerView()
                .frame(width: 80, height: 14)
                .cornerRadius(4)

            ShimmerView()
                .frame(width: 60, height: 12)
                .cornerRadius(4)
        }
        .frame(width: 100)
    }
}

// MARK: - Filter Toggle

struct FilterToggle: View {
    let icon: String
    let label: String
    let isActive: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: icon)
                    .scaledFont(size: 12)
                Text(label)
                    .scaledFont(size: 13)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(isActive ? Color.white : OmiColors.backgroundSecondary)
            .foregroundColor(isActive ? Color.black : OmiColors.textSecondary)
            .cornerRadius(8)
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(isActive ? OmiColors.border : Color.clear, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Small Header Button

struct SmallHeaderButton: View {
    let icon: String
    let label: String
    let color: Color
    let action: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: icon)
                    .scaledFont(size: 12)
                    .foregroundColor(color)
                Text(label)
                    .scaledFont(size: 12, weight: .medium)
                    .foregroundColor(OmiColors.textSecondary)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(isHovering ? OmiColors.backgroundTertiary : OmiColors.backgroundSecondary)
            .cornerRadius(6)
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
    }
}

// MARK: - Horizontal App Section

struct HorizontalAppSection: View {
    let title: String
    let apps: [OmiApp]
    let appProvider: AppProvider
    let onSelectApp: (OmiApp) -> Void
    var showSeeMore: Bool = false
    var onSeeMore: (() -> Void)? = nil
    var onViewAll: (() -> Void)? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(title)
                .scaledFont(size: 18, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 16) {
                    ForEach(apps) { app in
                        CompactAppCard(app: app, appProvider: appProvider, onSelect: { onSelectApp(app) })
                    }

                    // "See more" button inline with cards
                    if showSeeMore, let onSeeMore = onSeeMore {
                        Button(action: onSeeMore) {
                            VStack(spacing: 6) {
                                ZStack {
                                    RoundedRectangle(cornerRadius: 14)
                                        .fill(OmiColors.backgroundSecondary)
                                        .frame(width: 56, height: 56)
                                    Image(systemName: "chevron.right")
                                        .scaledFont(size: 18, weight: .medium)
                                        .foregroundColor(OmiColors.textSecondary)
                                }
                                Text("See more")
                                    .scaledFont(size: 11)
                                    .foregroundColor(OmiColors.textTertiary)
                            }
                            .frame(width: 70)
                        }
                        .buttonStyle(.plain)
                    } else if let onViewAll = onViewAll {
                        Button(action: onViewAll) {
                            VStack(spacing: 6) {
                                ZStack {
                                    RoundedRectangle(cornerRadius: 14)
                                        .fill(OmiColors.backgroundSecondary)
                                        .frame(width: 56, height: 56)
                                    Image(systemName: "chevron.right")
                                        .scaledFont(size: 18, weight: .medium)
                                        .foregroundColor(OmiColors.textSecondary)
                                }
                                Text("View all")
                                    .scaledFont(size: 11)
                                    .foregroundColor(OmiColors.textTertiary)
                            }
                            .frame(width: 70)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
    }
}

// MARK: - Grid App Section

struct AppGridSection: View {
    let title: String
    let apps: [OmiApp]
    let appProvider: AppProvider
    let onSelectApp: (OmiApp) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(title)
                .scaledFont(size: 18, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

            LazyVGrid(columns: [
                GridItem(.flexible(), spacing: 16),
                GridItem(.flexible(), spacing: 16),
                GridItem(.flexible(), spacing: 16)
            ], spacing: 16) {
                ForEach(apps) { app in
                    AppCard(app: app, appProvider: appProvider, onSelect: { onSelectApp(app) })
                }
            }
        }
    }
}

// MARK: - Compact App Card (for horizontal scroll)

struct CompactAppCard: View {
    let app: OmiApp
    let appProvider: AppProvider
    let onSelect: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: onSelect) {
            VStack(alignment: .center, spacing: 8) {
                // App icon
                AsyncImage(url: URL(string: app.image)) { phase in
                    switch phase {
                    case .success(let image):
                        image
                            .resizable()
                            .aspectRatio(contentMode: .fill)
                    default:
                        appIconPlaceholder
                    }
                }
                .frame(width: 60, height: 60)
                .clipShape(RoundedRectangle(cornerRadius: 14))
                .shadow(color: .black.opacity(0.1), radius: 4, y: 2)

                VStack(spacing: 2) {
                    Text(app.name)
                        .scaledFont(size: 12, weight: .medium)
                        .foregroundColor(OmiColors.textPrimary)
                        .lineLimit(1)

                    // Rating and installs
                    HStack(spacing: 3) {
                        if let rating = app.formattedRating {
                            Image(systemName: "star.fill")
                                .scaledFont(size: 8)
                                .foregroundColor(.yellow)
                            Text(rating)
                                .scaledFont(size: 10)
                                .foregroundColor(OmiColors.textTertiary)
                        }
                        if let installs = app.formattedInstalls {
                            if app.formattedRating != nil {
                                Text("·")
                                    .scaledFont(size: 10)
                                    .foregroundColor(OmiColors.textTertiary)
                            }
                            Text(installs)
                                .scaledFont(size: 10)
                                .foregroundColor(OmiColors.textTertiary)
                        }
                    }
                }

                // Get/Open button
                SmallAppButton(app: app, appProvider: appProvider, onOpen: onSelect)
            }
            .frame(width: 90)
            .padding(.vertical, 8)
            .background(isHovering ? OmiColors.backgroundSecondary.opacity(0.5) : Color.clear)
            .cornerRadius(12)
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
    }

    private var appIconPlaceholder: some View {
        RoundedRectangle(cornerRadius: 14)
            .fill(OmiColors.backgroundTertiary)
            .overlay(
                Image(systemName: "app.fill")
                    .foregroundColor(OmiColors.textTertiary)
            )
    }
}

// MARK: - Small App Button

struct SmallAppButton: View {
    let app: OmiApp
    let appProvider: AppProvider
    var onOpen: (() -> Void)? = nil

    var body: some View {
        Button(action: {
            if app.enabled {
                // If already enabled, open the app detail
                onOpen?()
            } else {
                // If not enabled, enable it
                Task { await appProvider.toggleApp(app) }
            }
        }) {
            if appProvider.isAppLoading(app.id) {
                ProgressView()
                    .scaleEffect(0.6)
                    .frame(width: 50, height: 22)
            } else {
                Text(app.enabled ? "Open" : "Install")
                    .scaledFont(size: 11, weight: .medium)
                    .foregroundColor(.black)
                    .frame(width: 50, height: 22)
                    .background(Color.white)
                    .cornerRadius(11)
                    .overlay(
                        RoundedRectangle(cornerRadius: 11)
                            .stroke(OmiColors.border, lineWidth: 1)
                    )
            }
        }
        .buttonStyle(.plain)
        .disabled(appProvider.isAppLoading(app.id))
    }
}

// MARK: - App Card (Full)

struct AppCard: View {
    let app: OmiApp
    let appProvider: AppProvider
    let onSelect: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: onSelect) {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 12) {
                    // App icon
                    AsyncImage(url: URL(string: app.image)) { phase in
                        switch phase {
                        case .success(let image):
                            image
                                .resizable()
                                .aspectRatio(contentMode: .fill)
                        default:
                            appIconPlaceholder
                        }
                    }
                    .frame(width: 50, height: 50)
                    .clipShape(RoundedRectangle(cornerRadius: 12))

                    VStack(alignment: .leading, spacing: 4) {
                        Text(app.name)
                            .scaledFont(size: 14, weight: .medium)
                            .foregroundColor(OmiColors.textPrimary)
                            .lineLimit(1)

                        Text(app.author)
                            .scaledFont(size: 12)
                            .foregroundColor(OmiColors.textTertiary)
                            .lineLimit(1)
                    }

                    Spacer()
                }

                Text(app.description)
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textSecondary)
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)

                HStack {
                    // Rating and installs
                    HStack(spacing: 6) {
                        if let rating = app.formattedRating {
                            HStack(spacing: 3) {
                                Image(systemName: "star.fill")
                                    .scaledFont(size: 10)
                                    .foregroundColor(.yellow)
                                Text(rating)
                                    .scaledFont(size: 11)
                                    .foregroundColor(OmiColors.textTertiary)
                            }
                        }
                        if let installs = app.formattedInstalls {
                            HStack(spacing: 3) {
                                Image(systemName: "arrow.down.circle")
                                    .scaledFont(size: 10)
                                    .foregroundColor(OmiColors.textTertiary)
                                Text(installs)
                                    .scaledFont(size: 11)
                                    .foregroundColor(OmiColors.textTertiary)
                            }
                        }
                    }

                    Spacer()

                    // Get/Open button
                    AppActionButton(app: app, appProvider: appProvider, onOpen: onSelect)
                }
            }
            .padding(14)
            .background(isHovering ? OmiColors.backgroundSecondary : OmiColors.backgroundPrimary)
            .cornerRadius(12)
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(OmiColors.backgroundTertiary, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .onHover { hovering in
            isHovering = hovering
        }
    }

    private var appIconPlaceholder: some View {
        RoundedRectangle(cornerRadius: 12)
            .fill(OmiColors.backgroundTertiary)
            .overlay(
                Image(systemName: "app.fill")
                    .foregroundColor(OmiColors.textTertiary)
            )
    }
}

// MARK: - App Action Button

struct AppActionButton: View {
    let app: OmiApp
    let appProvider: AppProvider
    var onOpen: (() -> Void)? = nil

    var body: some View {
        Button(action: {
            if app.enabled {
                // If already enabled, open the app detail
                onOpen?()
            } else {
                // If not enabled, enable it
                Task { await appProvider.toggleApp(app) }
            }
        }) {
            if appProvider.isAppLoading(app.id) {
                ProgressView()
                    .scaleEffect(0.7)
                    .frame(width: 60, height: 28)
            } else {
                Text(app.enabled ? "Open" : "Install")
                    .scaledFont(size: 12, weight: .medium)
                    .foregroundColor(.black)
                    .frame(width: 60, height: 28)
                    .background(Color.white)
                    .cornerRadius(14)
                    .overlay(
                        RoundedRectangle(cornerRadius: 14)
                            .stroke(OmiColors.border, lineWidth: 1)
                    )
            }
        }
        .buttonStyle(.plain)
        .disabled(appProvider.isAppLoading(app.id))
    }
}

// MARK: - Filter Sheet

struct AppFilterSheet: View {
    @ObservedObject var appProvider: AppProvider
    var onDismiss: (() -> Void)? = nil

    @Environment(\.dismiss) private var environmentDismiss

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
            HStack {
                Text("Filters")
                    .scaledFont(size: 18, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                if hasActiveFilters {
                    Button("Clear All") {
                        appProvider.clearFilters()
                        Task { await appProvider.searchApps() }
                    }
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textSecondary)
                }

                DismissButton(action: dismissSheet)
            }
            .padding()

            Divider()
                .background(OmiColors.backgroundTertiary)

            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    // Categories
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Category")
                            .scaledFont(size: 14, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)

                        FlowLayout(spacing: 8) {
                            ForEach(appProvider.categories) { category in
                                FilterChip(
                                    label: category.title,
                                    isSelected: appProvider.selectedCategory == category.id
                                ) {
                                    if appProvider.selectedCategory == category.id {
                                        appProvider.selectedCategory = nil
                                    } else {
                                        appProvider.selectedCategory = category.id
                                    }
                                    Task { await appProvider.searchApps() }
                                }
                            }
                        }
                    }

                    // Capabilities
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Capability")
                            .scaledFont(size: 14, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)

                        FlowLayout(spacing: 8) {
                            ForEach(appProvider.capabilities) { capability in
                                FilterChip(
                                    label: capability.title,
                                    isSelected: appProvider.selectedCapability == capability.id
                                ) {
                                    if appProvider.selectedCapability == capability.id {
                                        appProvider.selectedCapability = nil
                                    } else {
                                        appProvider.selectedCapability = capability.id
                                    }
                                    Task { await appProvider.searchApps() }
                                }
                            }
                        }
                    }

                    // Other filters
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Other")
                            .scaledFont(size: 14, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)

                        Toggle("Show installed only", isOn: $appProvider.showInstalledOnly)
                            .toggleStyle(SwitchToggleStyle(tint: OmiColors.purplePrimary))
                            .foregroundColor(OmiColors.textSecondary)
                            .onChange(of: appProvider.showInstalledOnly) { _, _ in
                                Task { await appProvider.searchApps() }
                            }
                    }
                }
                .padding()
            }
        }
        .frame(width: 400, height: 450)
        .background(OmiColors.backgroundPrimary)
    }

    private var hasActiveFilters: Bool {
        appProvider.selectedCategory != nil ||
        appProvider.selectedCapability != nil ||
        appProvider.showInstalledOnly
    }
}

// MARK: - Filter Chip

struct FilterChip: View {
    let label: String
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(label)
                .scaledFont(size: 13)
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(isSelected ? Color.white : OmiColors.backgroundSecondary)
                .foregroundColor(isSelected ? OmiColors.textPrimary : OmiColors.textSecondary)
                .cornerRadius(20)
                .overlay(
                    RoundedRectangle(cornerRadius: 20)
                        .stroke(isSelected ? OmiColors.border : Color.clear, lineWidth: 1)
                )
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Category Apps Sheet

struct CategoryAppsSheet: View {
    let category: OmiAppCategory
    let appProvider: AppProvider
    let onSelectApp: (OmiApp) -> Void
    var onDismiss: (() -> Void)? = nil

    @Environment(\.dismiss) private var environmentDismiss

    private func dismissSheet() {
        if let onDismiss = onDismiss {
            onDismiss()
        } else {
            environmentDismiss()
        }
    }

    var categoryApps: [OmiApp] {
        appProvider.apps(forCategory: category.id)
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                DismissButton(action: dismissSheet, icon: "chevron.left", showBackground: false)

                Text(category.title)
                    .scaledFont(size: 18, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                Text("\(categoryApps.count) apps")
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textTertiary)
            }
            .padding()

            Divider()
                .background(OmiColors.backgroundTertiary)

            ScrollView {
                LazyVGrid(columns: [
                    GridItem(.flexible(), spacing: 16),
                    GridItem(.flexible(), spacing: 16)
                ], spacing: 16) {
                    ForEach(categoryApps) { app in
                        AppCard(app: app, appProvider: appProvider, onSelect: { onSelectApp(app) })
                    }
                }
                .padding()
            }
        }
        .background(OmiColors.backgroundPrimary)
    }
}

// MARK: - App Detail Sheet

struct AppDetailSheet: View {
    let app: OmiApp
    let appProvider: AppProvider
    var onDismiss: (() -> Void)? = nil

    @Environment(\.dismiss) private var environmentDismiss
    @State private var reviews: [OmiAppReview] = []
    @State private var isLoadingReviews = false
    @State private var showAddReview = false
    @State private var userReview: OmiAppReview?

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
            HStack {
                Spacer()

                DismissButton(action: dismissSheet)
            }
            .padding()

            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    // App header
                    HStack(spacing: 16) {
                        AsyncImage(url: URL(string: app.image)) { phase in
                            switch phase {
                            case .success(let image):
                                image
                                    .resizable()
                                    .aspectRatio(contentMode: .fill)
                            default:
                                RoundedRectangle(cornerRadius: 16)
                                    .fill(OmiColors.backgroundTertiary)
                            }
                        }
                        .frame(width: 80, height: 80)
                        .clipShape(RoundedRectangle(cornerRadius: 16))

                        VStack(alignment: .leading, spacing: 6) {
                            Text(app.name)
                                .scaledFont(size: 24, weight: .bold)
                                .foregroundColor(OmiColors.textPrimary)

                            Text(app.author)
                                .scaledFont(size: 14)
                                .foregroundColor(OmiColors.textTertiary)

                            HStack(spacing: 12) {
                                if let rating = app.formattedRating {
                                    HStack(spacing: 4) {
                                        Image(systemName: "star.fill")
                                            .foregroundColor(.yellow)
                                        Text("\(rating) (\(app.ratingCount))")
                                    }
                                    .scaledFont(size: 13)
                                    .foregroundColor(OmiColors.textSecondary)
                                }

                                Text("\(app.installs) installs")
                                    .scaledFont(size: 13)
                                    .foregroundColor(OmiColors.textSecondary)
                            }
                        }

                        Spacer()

                        // Action button
                        Button(action: {
                            Task {
                                await appProvider.toggleApp(app)
                            }
                        }) {
                            if appProvider.isAppLoading(app.id) {
                                ProgressView()
                                    .frame(width: 100, height: 36)
                            } else {
                                Text(app.enabled ? "Disable" : "Install")
                                    .scaledFont(size: 14, weight: .semibold)
                                    .foregroundColor(app.enabled ? .white : .black)
                                    .frame(width: 100, height: 36)
                                    .background(app.enabled ? OmiColors.error : Color.white)
                                    .cornerRadius(18)
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 18)
                                            .stroke(app.enabled ? Color.clear : OmiColors.border, lineWidth: 1)
                                    )
                            }
                        }
                        .buttonStyle(.plain)
                    }

                    Divider()
                        .background(OmiColors.backgroundTertiary)

                    // Description
                    VStack(alignment: .leading, spacing: 8) {
                        Text("About")
                            .scaledFont(size: 16, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)

                        Text(app.description)
                            .scaledFont(size: 14)
                            .foregroundColor(OmiColors.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }

                    // Capabilities
                    if !app.capabilities.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Capabilities")
                                .scaledFont(size: 16, weight: .semibold)
                                .foregroundColor(OmiColors.textPrimary)

                            FlowLayout(spacing: 8) {
                                ForEach(app.capabilities, id: \.self) { capability in
                                    CapabilityBadge(capability: capability)
                                }
                            }
                        }
                    }

                    // Category
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Category")
                            .scaledFont(size: 16, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)

                        Text(app.category.replacingOccurrences(of: "-", with: " ").capitalized)
                            .scaledFont(size: 14)
                            .foregroundColor(OmiColors.textSecondary)
                    }

                    Divider()
                        .background(OmiColors.backgroundTertiary)

                    // Add Review Section
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Text("Reviews")
                                .scaledFont(size: 16, weight: .semibold)
                                .foregroundColor(OmiColors.textPrimary)

                            Spacer()

                            if userReview == nil {
                                Button(action: { showAddReview = true }) {
                                    HStack(spacing: 4) {
                                        Image(systemName: "plus")
                                            .scaledFont(size: 12, weight: .medium)
                                        Text("Add Review")
                                            .scaledFont(size: 13, weight: .medium)
                                    }
                                    .foregroundColor(OmiColors.textSecondary)
                                }
                                .buttonStyle(.plain)
                            }
                        }

                        // User's own review (if exists)
                        if let userReview = userReview {
                            VStack(alignment: .leading, spacing: 8) {
                                HStack {
                                    Text("Your Review")
                                        .scaledFont(size: 13, weight: .medium)
                                        .foregroundColor(OmiColors.textPrimary)

                                    Spacer()

                                    Button(action: { showAddReview = true }) {
                                        Text("Edit")
                                            .scaledFont(size: 12, weight: .medium)
                                            .foregroundColor(OmiColors.textTertiary)
                                    }
                                    .buttonStyle(.plain)
                                }

                                ReviewCard(review: userReview)
                            }
                        }

                        // Other reviews
                        let otherReviews = reviews.filter { $0.uid != userReview?.uid }
                        if !otherReviews.isEmpty {
                            ForEach(otherReviews.prefix(3)) { review in
                                ReviewCard(review: review)
                            }
                        } else if userReview == nil && reviews.isEmpty {
                            Text("No reviews yet. Be the first to review this app!")
                                .scaledFont(size: 13)
                                .foregroundColor(OmiColors.textTertiary)
                                .padding(.vertical, 8)
                        }
                    }
                }
                .padding()
            }
        }
        .frame(width: 500, height: 600)
        .background(OmiColors.backgroundPrimary)
        .task {
            await loadReviews()
        }
        .dismissableSheet(isPresented: $showAddReview) {
            AddReviewSheet(
                app: app,
                existingReview: userReview,
                onReviewSubmitted: { review in
                    userReview = review
                    // Refresh reviews to get updated list
                    Task { await loadReviews() }
                },
                onDismiss: { showAddReview = false }
            )
            .frame(width: 400, height: 500)
        }
    }

    private func loadReviews() async {
        isLoadingReviews = true
        defer { isLoadingReviews = false }

        do {
            reviews = try await APIClient.shared.getAppReviews(appId: app.id)
            // Check if current user has a review
            if let currentUserId = AuthState.shared.userId {
                userReview = reviews.first { $0.uid == currentUserId }
            }
        } catch {
            // Silently fail - reviews are optional
        }
    }
}

// MARK: - Add Review Sheet

struct AddReviewSheet: View {
    let app: OmiApp
    let existingReview: OmiAppReview?
    let onReviewSubmitted: (OmiAppReview) -> Void
    var onDismiss: (() -> Void)? = nil

    @Environment(\.dismiss) private var environmentDismiss
    @State private var selectedRating: Int
    @State private var reviewText: String
    @State private var isSubmitting = false
    @State private var errorMessage: String?

    private let maxReviewLength = 500

    init(app: OmiApp, existingReview: OmiAppReview?, onReviewSubmitted: @escaping (OmiAppReview) -> Void, onDismiss: (() -> Void)? = nil) {
        self.app = app
        self.existingReview = existingReview
        self.onReviewSubmitted = onReviewSubmitted
        self.onDismiss = onDismiss
        _selectedRating = State(initialValue: existingReview?.score ?? 0)
        _reviewText = State(initialValue: existingReview?.review ?? "")
    }

    private func dismissSheet() {
        if let onDismiss = onDismiss {
            onDismiss()
        } else {
            environmentDismiss()
        }
    }

    var isFormValid: Bool {
        selectedRating > 0 && !reviewText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                // Placeholder for symmetry
                Color.clear
                    .frame(width: 28, height: 28)

                Spacer()

                Text(existingReview != nil ? "Edit Review" : "Add Review")
                    .scaledFont(size: 16, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                DismissButton(action: dismissSheet)
            }
            .padding()

            Divider()
                .background(OmiColors.backgroundTertiary)

            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    // App info
                    HStack(spacing: 12) {
                        AsyncImage(url: URL(string: app.image)) { phase in
                            switch phase {
                            case .success(let image):
                                image
                                    .resizable()
                                    .aspectRatio(contentMode: .fill)
                            default:
                                RoundedRectangle(cornerRadius: 12)
                                    .fill(OmiColors.backgroundTertiary)
                            }
                        }
                        .frame(width: 50, height: 50)
                        .clipShape(RoundedRectangle(cornerRadius: 12))

                        VStack(alignment: .leading, spacing: 4) {
                            Text(app.name)
                                .scaledFont(size: 16, weight: .semibold)
                                .foregroundColor(OmiColors.textPrimary)

                            Text(app.author)
                                .scaledFont(size: 13)
                                .foregroundColor(OmiColors.textTertiary)
                        }

                        Spacer()
                    }

                    // Star Rating Picker
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Your Rating")
                            .scaledFont(size: 14, weight: .medium)
                            .foregroundColor(OmiColors.textPrimary)

                        StarRatingPicker(rating: $selectedRating)
                    }

                    // Review Text
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Text("Your Review")
                                .scaledFont(size: 14, weight: .medium)
                                .foregroundColor(OmiColors.textPrimary)

                            Spacer()

                            Text("\(reviewText.count)/\(maxReviewLength)")
                                .scaledFont(size: 12)
                                .foregroundColor(reviewText.count > maxReviewLength ? OmiColors.error : OmiColors.textTertiary)
                        }

                        ZStack(alignment: .topLeading) {
                            TextEditor(text: $reviewText)
                                .scaledFont(size: 14)
                                .foregroundColor(OmiColors.textPrimary)
                                .scrollContentBackground(.hidden)
                                .frame(minHeight: 120, maxHeight: 200)
                                .padding(12)
                                .background(OmiColors.backgroundSecondary)
                                .cornerRadius(10)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 10)
                                        .stroke(OmiColors.backgroundTertiary, lineWidth: 1)
                                )
                                .onChange(of: reviewText) { _, newValue in
                                    if newValue.count > maxReviewLength {
                                        reviewText = String(newValue.prefix(maxReviewLength))
                                    }
                                }

                            if reviewText.isEmpty {
                                Text("Share your experience with this app...")
                                    .scaledFont(size: 14)
                                    .foregroundColor(OmiColors.textTertiary)
                                    .padding(.leading, 17)
                                    .padding(.top, 20)
                                    .allowsHitTesting(false)
                            }
                        }
                    }

                    // Error message
                    if let errorMessage = errorMessage {
                        HStack(spacing: 8) {
                            Image(systemName: "exclamationmark.circle.fill")
                                .foregroundColor(OmiColors.error)
                            Text(errorMessage)
                                .scaledFont(size: 13)
                                .foregroundColor(OmiColors.error)
                        }
                    }

                    // Submit button
                    Button(action: submitReview) {
                        HStack {
                            if isSubmitting {
                                ProgressView()
                                    .scaleEffect(0.8)
                                    .tint(OmiColors.textPrimary)
                            } else {
                                Text(existingReview != nil ? "Update Review" : "Submit Review")
                                    .scaledFont(size: 14, weight: .semibold)
                            }
                        }
                        .foregroundColor(OmiColors.textPrimary)
                        .frame(maxWidth: .infinity)
                        .frame(height: 44)
                        .background(isFormValid ? Color.white : Color.white.opacity(0.5))
                        .cornerRadius(10)
                        .overlay(
                            RoundedRectangle(cornerRadius: 10)
                                .stroke(OmiColors.border, lineWidth: 1)
                        )
                    }
                    .buttonStyle(.plain)
                    .disabled(!isFormValid || isSubmitting)
                }
                .padding()
            }
        }
        .frame(width: 400, height: 480)
        .background(OmiColors.backgroundPrimary)
    }

    private func submitReview() {
        guard isFormValid else { return }

        isSubmitting = true
        errorMessage = nil

        Task {
            do {
                let review = try await APIClient.shared.submitAppReview(
                    appId: app.id,
                    score: selectedRating,
                    review: reviewText.trimmingCharacters(in: .whitespacesAndNewlines)
                )
                await MainActor.run {
                    onReviewSubmitted(review)
                    dismissSheet()
                }
            } catch {
                await MainActor.run {
                    errorMessage = "Failed to submit review. Please try again."
                    isSubmitting = false
                }
            }
        }
    }
}

// MARK: - Star Rating Picker

struct StarRatingPicker: View {
    @Binding var rating: Int
    var maxRating: Int = 5
    var starSize: CGFloat = 32

    @State private var hoverRating: Int = 0

    var body: some View {
        HStack(spacing: 8) {
            ForEach(1...maxRating, id: \.self) { star in
                Image(systemName: starImage(for: star))
                    .scaledFont(size: starSize)
                    .foregroundColor(starColor(for: star))
                    .onTapGesture {
                        withAnimation(.easeInOut(duration: 0.15)) {
                            rating = star
                        }
                    }
                    .onHover { hovering in
                        hoverRating = hovering ? star : 0
                    }
                    .scaleEffect(scaleEffect(for: star))
                    .animation(.easeInOut(duration: 0.1), value: hoverRating)
            }

            if rating > 0 {
                Text(ratingLabel)
                    .scaledFont(size: 14, weight: .medium)
                    .foregroundColor(OmiColors.textSecondary)
                    .padding(.leading, 8)
            }
        }
    }

    private func starImage(for star: Int) -> String {
        let effectiveRating = hoverRating > 0 ? hoverRating : rating
        return star <= effectiveRating ? "star.fill" : "star"
    }

    private func starColor(for star: Int) -> Color {
        let effectiveRating = hoverRating > 0 ? hoverRating : rating
        return star <= effectiveRating ? .yellow : OmiColors.textTertiary.opacity(0.5)
    }

    private func scaleEffect(for star: Int) -> CGFloat {
        if hoverRating == star {
            return 1.15
        }
        return 1.0
    }

    private var ratingLabel: String {
        switch rating {
        case 1: return "Poor"
        case 2: return "Fair"
        case 3: return "Good"
        case 4: return "Very Good"
        case 5: return "Excellent"
        default: return ""
        }
    }
}

// MARK: - Capability Badge

struct CapabilityBadge: View {
    let capability: String

    var icon: String {
        switch capability {
        case "chat": return "bubble.left.and.bubble.right"
        case "memories": return "brain"
        case "persona": return "person.crop.circle"
        case "external_integration": return "link"
        case "proactive_notification": return "bell"
        default: return "app"
        }
    }

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
                .scaledFont(size: 10)
            Text(capability.replacingOccurrences(of: "_", with: " ").capitalized)
                .scaledFont(size: 12)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(OmiColors.backgroundSecondary)
        .foregroundColor(OmiColors.textSecondary)
        .cornerRadius(16)
    }
}

// MARK: - Review Card

struct ReviewCard: View {
    let review: OmiAppReview

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                // Rating stars
                HStack(spacing: 2) {
                    ForEach(1...5, id: \.self) { star in
                        Image(systemName: star <= review.score ? "star.fill" : "star")
                            .scaledFont(size: 10)
                            .foregroundColor(star <= review.score ? .yellow : OmiColors.textTertiary)
                    }
                }

                Spacer()

                Text(review.ratedAt, style: .date)
                    .scaledFont(size: 11)
                    .foregroundColor(OmiColors.textTertiary)
            }

            Text(review.review)
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textSecondary)
                .lineLimit(3)

            if let response = review.response {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Developer Response")
                        .scaledFont(size: 11, weight: .medium)
                        .foregroundColor(OmiColors.textTertiary)

                    Text(response)
                        .scaledFont(size: 12)
                        .foregroundColor(OmiColors.textSecondary)
                        .lineLimit(2)
                }
                .padding(10)
                .background(OmiColors.backgroundSecondary)
                .cornerRadius(8)
            }
        }
        .padding(12)
        .background(OmiColors.backgroundSecondary.opacity(0.5))
        .cornerRadius(10)
    }
}

// MARK: - Flow Layout Helper

struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let result = FlowResult(in: proposal.width ?? 0, subviews: subviews, spacing: spacing)
        return result.size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let result = FlowResult(in: bounds.width, subviews: subviews, spacing: spacing)
        for (index, subview) in subviews.enumerated() {
            let idealSize = subview.sizeThatFits(.unspecified)
            let subProposal: ProposedViewSize = idealSize.width > bounds.width
                ? ProposedViewSize(width: bounds.width, height: nil)
                : .unspecified
            subview.place(at: CGPoint(x: bounds.minX + result.positions[index].x,
                                       y: bounds.minY + result.positions[index].y),
                          proposal: subProposal)
        }
    }

    struct FlowResult {
        var size: CGSize = .zero
        var positions: [CGPoint] = []

        init(in maxWidth: CGFloat, subviews: Subviews, spacing: CGFloat) {
            var x: CGFloat = 0
            var y: CGFloat = 0
            var rowHeight: CGFloat = 0

            for subview in subviews {
                var size = subview.sizeThatFits(.unspecified)

                // Constrain oversized items to available width
                if size.width > maxWidth {
                    size = subview.sizeThatFits(ProposedViewSize(width: maxWidth, height: nil))
                }

                if x + size.width > maxWidth && x > 0 {
                    x = 0
                    y += rowHeight + spacing
                    rowHeight = 0
                }

                positions.append(CGPoint(x: x, y: y))
                rowHeight = max(rowHeight, size.height)
                x += size.width + spacing
                self.size.width = max(self.size.width, min(x, maxWidth))
            }

            self.size.height = y + rowHeight
        }
    }
}

// MARK: - Dismissable Sheet
/// A sheet that can be dismissed by clicking outside the content area.
/// This provides macOS-friendly modal behavior where clicking the dimmed background dismisses the sheet.

struct DismissableSheetModifier<SheetContent: View>: ViewModifier {
    @Binding var isPresented: Bool
    let sheetContent: () -> SheetContent

    func body(content: Content) -> some View {
        content
            .overlay {
                if isPresented {
                    // Dimmed background that dismisses on tap
                    Color.black.opacity(0.3)
                        .ignoresSafeArea()
                        .onTapGesture {
                            log("DISMISSABLE_SHEET: Background tapped, dismissing")
                            withAnimation(.easeOut(duration: 0.2)) {
                                isPresented = false
                            }
                        }
                        .transition(.opacity)

                    // Sheet content centered
                    sheetContent()
                        .background(OmiColors.backgroundPrimary)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                        .shadow(color: .black.opacity(0.3), radius: 20, x: 0, y: 10)
                        .transition(.scale(scale: 0.95).combined(with: .opacity))
                }
            }
            .animation(.easeOut(duration: 0.2), value: isPresented)
    }
}

extension View {
    /// Presents a sheet that can be dismissed by clicking outside the content area.
    func dismissableSheet<Content: View>(
        isPresented: Binding<Bool>,
        @ViewBuilder content: @escaping () -> Content
    ) -> some View {
        self.modifier(DismissableSheetModifier(isPresented: isPresented, sheetContent: content))
    }

    /// Presents an item-based sheet that can be dismissed by clicking outside the content area.
    func dismissableSheet<Item: Identifiable, Content: View>(
        item: Binding<Item?>,
        @ViewBuilder content: @escaping (Item) -> Content
    ) -> some View {
        self.modifier(DismissableSheetItemModifier(item: item, sheetContent: content))
    }
}

/// Item-based version of DismissableSheetModifier for optional item bindings.
struct DismissableSheetItemModifier<Item: Identifiable, SheetContent: View>: ViewModifier {
    @Binding var item: Item?
    let sheetContent: (Item) -> SheetContent

    func body(content: Content) -> some View {
        content
            .overlay {
                if let presentedItem = item {
                    // Dimmed background that dismisses on tap
                    Color.black.opacity(0.3)
                        .ignoresSafeArea()
                        .onTapGesture {
                            log("DISMISSABLE_SHEET: Background tapped, dismissing item")
                            withAnimation(.easeOut(duration: 0.2)) {
                                item = nil
                            }
                        }
                        .transition(.opacity)

                    // Sheet content centered
                    sheetContent(presentedItem)
                        .background(OmiColors.backgroundPrimary)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                        .shadow(color: .black.opacity(0.3), radius: 20, x: 0, y: 10)
                        .transition(.scale(scale: 0.95).combined(with: .opacity))
                }
            }
            .animation(.easeOut(duration: 0.2), value: item?.id != nil)
    }
}

// MARK: - Create App Card
/// Simple card button for creating apps or persona

struct CreateAppCard: View {
    let icon: String
    let iconColor: Color
    let title: String
    let onTap: () -> Void

    @State private var isHovering = false

    var body: some View {
        HStack(spacing: 12) {
            // Icon
            ZStack {
                RoundedRectangle(cornerRadius: 12)
                    .fill(iconColor.opacity(0.15))
                    .frame(width: 44, height: 44)

                Image(systemName: icon)
                    .scaledFont(size: 20)
                    .foregroundColor(iconColor)
            }

            Text(title)
                .scaledFont(size: 14, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

            Spacer()

            Image(systemName: "chevron.right")
                .scaledFont(size: 12, weight: .medium)
                .foregroundColor(OmiColors.textTertiary)
        }
        .padding(12)
        .frame(maxWidth: .infinity)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(isHovering ? OmiColors.backgroundSecondary : OmiColors.backgroundPrimary)
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .stroke(iconColor.opacity(0.3), lineWidth: 1)
                )
        )
        .contentShape(Rectangle())
        .onTapGesture {
            onTap()
        }
        .onHover { isHovering = $0 }
    }
}

#Preview {
    AppsPage(appProvider: AppProvider())
        .frame(width: 900, height: 700)
}
