import OmiComponents
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// The app store: kinds as chips, search, category and sort in the filter menu; tap an app for its
/// page. Loading, nothing found and failure each have their own state (failure offers Try again).
struct AppsBrowserScreen: View {
    @Environment(AppCatalogStore.self) private var catalog
    @State private var text = ""

    var body: some View {
        @Bindable var catalog = catalog
        SettingsList {
            Section {
                KindChips(selection: $catalog.query.capability).plainSettingsRow()
            }
            if !catalog.results.isEmpty {
                Section {
                    ForEach(catalog.results) { app in
                        AppRow(app: app)
                            .onAppear { if app.id == catalog.results.last?.id { Task { await catalog.loadMore() } } }
                    }
                    if catalog.isLoading { ProgressView().frame(maxWidth: .infinity) }
                }
            }
        }
        .listSectionSpacing(.compact)
        .overlay { if catalog.results.isEmpty { emptyState } }
        .searchable(text: $text, placement: .navigationBarDrawer(displayMode: .always), prompt: L("nativeSearchApps"))
        .toolbar { ToolbarItem(placement: .topBarTrailing) { filterMenu } }
        .task { await catalog.loadCategories() }
        .task(id: searchKey) {
            try? await Task.sleep(for: .milliseconds(text.isEmpty ? 0 : 300))
            guard !Task.isCancelled else { return }
            catalog.query.text = text
            await catalog.search()
        }
        .refreshable { await catalog.search() }
        .omiPage(L("nativeBrowseApps"))
    }

    private var searchKey: String {
        "\(text)|\(catalog.query.category ?? "")|\(catalog.query.capability ?? "")|\(catalog.query.sort.rawValue)"
    }

    private var isFiltered: Bool {
        !text.isEmpty || catalog.query.category != nil || catalog.query.capability != nil
    }

    @ViewBuilder
    private var emptyState: some View {
        if catalog.isLoading {
            ProgressView().controlSize(.large)
        } else if catalog.searchFailed {
            ContentUnavailableView {
                Label(L("nativeSettingsAppsFailed"), systemImage: "wifi.exclamationmark")
            } description: {
                Text(L("nativeSettingsAppsFailedBody"))
            } actions: {
                Button(L("tryAgain")) { Task { await catalog.search() } }
                    .buttonStyle(.omiPill)
                    .accessibilityIdentifier("apps.retry")
            }
        } else {
            ContentUnavailableView {
                Label(L("nativeNoApps"), systemImage: "square.grid.2x2")
            } description: {
                if isFiltered { Text(L("nativeSettingsAppsNoMatch")) }
            } actions: {
                if isFiltered {
                    Button(L("nativeSettingsClearFilters")) {
                        text = ""
                        catalog.query.category = nil
                        catalog.query.capability = nil
                    }
                    .buttonStyle(.omiPillSubtle)
                }
            }
        }
    }

    private var filterMenu: some View {
        @Bindable var catalog = catalog
        return Menu {
            Picker(L("nativeAppsSort"), selection: $catalog.query.sort) {
                Text(L("nativeAppsSortPopular")).tag(AppQuery.Sort.installs)
                Text(L("nativeAppsSortRating")).tag(AppQuery.Sort.rating)
                Text(L("nativeAppsSortName")).tag(AppQuery.Sort.name)
            }
            Picker(L("nativeAppsCategory"), selection: $catalog.query.category) {
                Text(L("nativeAppsAllCategories")).tag(String?.none)
                ForEach(catalog.categories) { Text($0.title).tag(Optional($0.id)) }
            }
            .pickerStyle(.menu)
        } label: {
            let filtered = catalog.query.category != nil
            Image(systemName: filtered ? "line.3.horizontal.decrease.circle.fill" : "line.3.horizontal.decrease")
        }
        .accessibilityLabel(L("nativeAppsFilter"))
        .accessibilityIdentifier("apps.filter")
    }

    static func kindTitle(_ capability: String) -> String {
        switch capability {
        case "chat": L("nativeAppsKindChat")
        case "memories": L("nativeAppsKindSummaries")
        case "external_integration": L("nativeAppsKindIntegrations")
        case "proactive_notification": L("nativeAppsKindNotifications")
        case "tasks": L("nativeAppsKindTasks")
        default: capability
        }
    }
}

/// All, Chat, Summaries … as one scrolling row of chips.
private struct KindChips: View {
    @Binding var selection: String?

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: DS.Spacing.sm) {
                chip(L("nativeAppsAllKinds"), value: nil)
                ForEach(AppCatalogStore.capabilities, id: \.self) { chip(AppsBrowserScreen.kindTitle($0), value: $0) }
            }
            .padding(.vertical, DS.Spacing.xs)
        }
        .accessibilityIdentifier("apps.kinds")
    }

    private func chip(_ title: String, value: String?) -> some View {
        let selected = selection == value
        return Button {
            DSHaptics.selection()
            selection = value
        } label: {
            Text(title)
                .font(DS.Typography.callout.weight(.medium))
                .foregroundStyle(selected ? DS.Palette.onAccent : DS.Palette.ink)
                .padding(.horizontal, DS.Spacing.md)
                .padding(.vertical, DS.Spacing.sm)
                .background(selected ? DS.Palette.accent : Color.clear, in: Capsule())
                .overlay(Capsule().strokeBorder(selected ? Color.clear : DS.Palette.hairline, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

/// One app in a list: icon, name, one line of what it does, rating; Get or Remove on the right.
struct AppRow: View {
    @Environment(CapabilitiesStore.self) private var store
    let app: OmiApp

    var body: some View {
        HStack(spacing: DS.Spacing.md) {
            NavigationLink { AppDetailScreen(appID: app.id, preview: app) } label: {
                HStack(spacing: DS.Spacing.md) {
                    AppIcon(url: app.imageURL, name: app.name, size: 48)
                    VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                        Text(app.name).font(DS.Typography.cardTitle).lineLimit(1)
                        Text(app.description).font(DS.Typography.caption).foregroundStyle(DS.Palette.inkSecondary).lineLimit(2)
                        if let rating = app.rating, app.ratingCount > 0 {
                            let average = rating.formatted(.number.precision(.fractionLength(1)))
                            Label("\(average) (\(app.ratingCount))", systemImage: "star.fill")
                                .font(DS.Typography.micro)
                                .foregroundStyle(DS.Palette.inkTertiary)
                                .labelStyle(.titleAndIcon)
                        }
                    }
                }
            }
            .accessibilityIdentifier("apps.row.\(app.id)")
            if !app.isPaid || app.isEnabled {
                Button(app.isEnabled ? L("nativeRemove") : L("nativeGet")) {
                    Task { await store.setApp(app, enabled: !app.isEnabled) }
                }
                .buttonStyle(OmiPillButtonStyle(prominent: !app.isEnabled))
                .accessibilityIdentifier("apps.toggle.\(app.id)")
            }
        }
        .padding(.vertical, DS.Spacing.xxs)
    }
}

/// An app's icon, or its initials while the image loads or when there is none.
struct AppIcon: View {
    let url: URL?
    let name: String
    let size: CGFloat

    var body: some View {
        AsyncImage(url: url) { phase in
            if let image = phase.image {
                image.resizable().scaledToFill()
            } else {
                Text(Monogram.initials(name))
                    .font(size >= 44 ? DS.Typography.sectionTitle : DS.Typography.callout)
                    .foregroundStyle(DS.Palette.ink)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .frame(width: size, height: size)
        .clipShape(RoundedRectangle(cornerRadius: size * 0.24, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: size * 0.24, style: .continuous).strokeBorder(DS.Palette.hairline, lineWidth: 1))
        .accessibilityHidden(true)
    }
}
