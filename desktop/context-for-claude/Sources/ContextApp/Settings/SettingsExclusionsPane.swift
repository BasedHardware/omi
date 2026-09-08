import AppKit
import ContextCore
import SwiftUI

/// Keeps the pane in step with `ExclusionEngine`, which is the only exclusions model in this app.
///
/// The engine is the source of truth and the enforcer, so the pane never keeps its own copy of what is
/// excluded — it re-snapshots on every change. That is why an exclusion is visibly in force the instant
/// it is clicked: nothing here has to be told, because nothing here remembers.
@MainActor
final class ExclusionsObserver: ObservableObject {
    @Published private(set) var snapshot: ExclusionSnapshot

    private var token: UUID?

    init(engine: ExclusionEngine = .shared) {
        self.snapshot = engine.snapshot()
        self.token = engine.addObserver { [weak self] _ in
            // The engine calls back on whichever thread made the change.
            Task { @MainActor in self?.snapshot = engine.snapshot() }
        }
    }

    deinit {
        if let token { ExclusionEngine.shared.removeObserver(token) }
    }

    func refresh() {
        snapshot = ExclusionEngine.shared.snapshot()
    }
}

/// Exclusions: a search field, an `Apps | Websites` segmented control, and the sections in the
/// reference's order.
///
/// Every checkbox goes straight to `ExclusionEngine`, so a locked default is refused by the core
/// (`ExclusionMutation.refusedLocked`) as well as being undrawable here — the row's checkbox is
/// disabled because `ExclusionsPaneModel.Row.isRemovable` says so, and that in turn reads the
/// snapshot's `isLocked`. There is no second list of what is locked in this file.
struct SettingsExclusionsPane: View {
    @ObservedObject var exclusions: ExclusionsObserver

    @State private var tab: ExclusionsPaneModel.Tab = .apps
    @State private var query = ""
    @State private var expandedCategories: Set<String> = []
    @State private var recentApps: [ExcludableApp] = []
    @State private var allApps: [ExcludableApp] = []
    @State private var recentDomains: [String] = []
    @State private var isLoadingInventory = true

    /// A zero-height marker at the head of the list, so "put it back at the top" is a scroll to a real
    /// view rather than an offset guess.
    private static let topAnchor = "exclusions.top"

    private func scrollToTop(_ proxy: ScrollViewProxy) {
        proxy.scrollTo(Self.topAnchor, anchor: .top)
    }

    private var model: ExclusionsPaneModel {
        ExclusionsPaneModel.make(
            tab: tab,
            snapshot: exclusions.snapshot,
            recentApps: recentApps,
            allApps: allApps,
            recentDomains: recentDomains,
            query: query)
    }

    var body: some View {
        VStack(spacing: 10) {
            controlsBar

            // What an exclusion does and does not stop. Above the list rather than in a section
            // footnote because it qualifies every row on both tabs, and because a user reads it
            // before choosing rather than after.
            Text(ExclusionsPaneModel.scopeNote)
                .font(.system(size: 11))
                .foregroundStyle(Ink.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, SettingsMetrics.paneHorizontalPadding)

            if case .failedClosed(let cause) = model.health {
                healthBanner(cause)
            }

            // `ScrollViewReader` is not decoration here. **All Applications** is six hundred rows on a
            // real Mac and it arrives *after* first render, from `loadInventory()`. When the content
            // height jumps by that much, SwiftUI keeps its own anchor and the pane opened scrolled into
            // the middle of the alphabet — with no way back, because a `ScrollView` does not answer Home
            // without focus. Every input that changes what the list contains therefore puts it back at
            // the top explicitly.
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: SettingsMetrics.sectionSpacing) {
                        Color.clear.frame(height: 0).id(Self.topAnchor)

                        if let addable = model.addableDomain {
                            addDomainRow(addable)
                        }

                        ForEach(model.sections) { section in
                            SettingsSection(title: section.title, footnote: section.footnote) {
                                sectionRows(section)
                            }
                        }

                        if model.sections.isEmpty {
                            Text("Nothing matches “\(query)”.")
                                .font(.system(size: 12))
                                .foregroundStyle(Ink.secondary)
                                .padding(.horizontal, 4)
                        }

                        if isLoadingInventory {
                            HStack(spacing: 8) {
                                ProgressView().controlSize(.small)
                                Text("Reading what is installed and what was recorded…")
                                    .font(.system(size: 11))
                                    .foregroundStyle(Ink.secondary)
                            }
                            .padding(.horizontal, 4)
                        }
                    }
                    .padding(.horizontal, SettingsMetrics.paneHorizontalPadding)
                    .padding(.bottom, 24)
                }
                .onChange(of: tab) { _, _ in scrollToTop(proxy) }
                .onChange(of: query) { _, _ in scrollToTop(proxy) }
                .onChange(of: allApps.count) { _, _ in scrollToTop(proxy) }
                .onChange(of: recentApps.count) { _, _ in scrollToTop(proxy) }
            }
        }
        .padding(.top, SettingsMetrics.paneTopPadding)
        .task { await loadInventory() }
    }

    // MARK: - Chrome

    private var controlsBar: some View {
        HStack(spacing: 10) {
            Picker("Exclusions list", selection: $tab) {
                ForEach(ExclusionsPaneModel.Tab.allCases) { Text($0.title).tag($0) }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .frame(width: 180)

            Spacer(minLength: 0)

            HStack(spacing: 5) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 10))
                    .foregroundStyle(Ink.secondary)
                TextField(tab.searchPlaceholder, text: $query)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .onSubmit { addTypedDomain() }
                if !query.isEmpty {
                    Button {
                        query = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .font(.system(size: 10))
                            .foregroundStyle(Ink.secondary)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 5)
            .background(Capsule().fill(Ink.wash))
            .overlay(Capsule().strokeBorder(Ink.hairline, lineWidth: 1))
            .frame(width: 210)
        }
        .padding(.horizontal, SettingsMetrics.paneHorizontalPadding)
    }

    /// Fail-closed is the one state on this pane the user must not have to infer: more is being
    /// excluded than they asked for, and their own choices are not being read.
    private func healthBanner(_ cause: FailClosedCause) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 12))
                .foregroundStyle(Ink.errorRed)
            VStack(alignment: .leading, spacing: 2) {
                Text("Exclusions are running on safe defaults")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Ink.primary)
                Text(
                    "Your exclusions file could not be read (\(String(describing: cause))), so more is "
                        + "being excluded than you chose, not less. Changes here apply now but may not survive a relaunch."
                )
                .font(.system(size: 11))
                .foregroundStyle(Ink.secondary)
                .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
            Button("Reload") {
                ExclusionEngine.shared.reload()
                exclusions.refresh()
            }
            .controlSize(.small)
        }
        .padding(11)
        .background(
            RoundedRectangle(cornerRadius: SettingsMetrics.cardRadius, style: .continuous)
                .fill(Ink.errorRed.opacity(0.10))
        )
        .padding(.horizontal, SettingsMetrics.paneHorizontalPadding)
    }

    private func addDomainRow(_ pattern: DomainPattern) -> some View {
        SettingsSection {
            SettingsRow(
                icon: "plus.circle",
                title: "Add \(pattern.host)",
                subtitle: "Excludes \(pattern.host) and every subdomain of it."
            ) {
                Button("Add") { addTypedDomain() }
                    .controlSize(.small)
                    .buttonStyle(.borderedProminent)
            }
        }
    }

    // MARK: - Rows

    @ViewBuilder
    private func sectionRows(_ section: ExclusionsPaneModel.Section) -> some View {
        ForEach(Array(section.rows.enumerated()), id: \.element.id) { index, row in
            if index > 0 { SettingsRowDivider() }
            rowView(row)
        }
    }

    @ViewBuilder
    private func rowView(_ row: ExclusionsPaneModel.Row) -> some View {
        switch row {
        case .category(let id, let category, let isExcluded, let memberCount):
            VStack(spacing: 0) {
                SettingsCheckRow(
                    title: category.title,
                    subtitle: category.subtitle,
                    isChecked: isExcluded,
                    isEnabled: true,
                    // The whole label area and the chevron expand the category now. The only
                    // affordance used to be the icon tile — the chevron the user aims at was drawn
                    // by `SettingsCheckRow` and had no gesture at all — so the row looked expandable
                    // everywhere and was expandable in one 26 pt square nothing pointed at.
                    onDisclosure: memberCount > 0 ? { toggleExpansion(id) } : nil,
                    isExpanded: expandedCategories.contains(id)
                ) {
                    Sound.effect(.click)
                    ExclusionEngine.shared.setCategory(category, excluded: !isExcluded)
                } leading: {
                    SettingsIconTile(symbol: category.kind == .apps ? "key.horizontal" : "building.columns")
                }

                if expandedCategories.contains(id) {
                    categoryMembers(category)
                }
            }

        case .app(let app, let state):
            SettingsCheckRow(
                title: app.displayName,
                subtitle: app.bundleID,
                isChecked: state != .included,
                isEnabled: state != .lockedExcluded
            ) {
                Sound.effect(.click)
                ExclusionEngine.shared.setExcluded(
                    state == .included, bundleID: app.bundleID, displayName: app.displayName)
            } leading: {
                SettingsAppIcon(app: app)
            }

        case .website(let pattern, let fromCategory):
            SettingsCheckRow(
                title: pattern.host,
                subtitle: fromCategory.map { "From \($0.title)" },
                isChecked: true,
                isEnabled: fromCategory == nil
            ) {
                Sound.effect(.click)
                ExclusionEngine.shared.allowWebsite(pattern)
            } leading: {
                SettingsFavicon(host: pattern.host)
            }

        case .recentDomain(let host):
            SettingsCheckRow(
                title: host,
                subtitle: nil,
                isChecked: false,
                isEnabled: true
            ) {
                Sound.effect(.click)
                ExclusionEngine.shared.excludeWebsite(host)
            } leading: {
                SettingsFavicon(host: host)
            }

        case .privateTabs(let isOn):
            SettingsRow(
                icon: "eyeglasses",
                title: ExclusionsPaneModel.privateTabsTitle,
                subtitle: ExclusionsPaneModel.privateTabsSubtitle
            ) {
                SettingsToggle(
                    title: ExclusionsPaneModel.privateTabsTitle,
                    isOn: Binding(
                        get: { isOn },
                        set: { ExclusionEngine.shared.setExcludePrivateBrowsing($0) }),
                    onChange: { _ in Sound.effect(.click) })
            }
        }
    }

    /// The expanded members of a category, drawn read-only: they are excluded *because* the category is
    /// ticked, and offering a checkbox that the engine would refuse would make the row a lie.
    @ViewBuilder
    private func categoryMembers(_ category: ExclusionCategory) -> some View {
        let apps = ExclusionCatalog.apps(in: category)
        let domains = ExclusionCatalog.domains(in: category)
        VStack(alignment: .leading, spacing: 3) {
            ForEach(apps) { app in
                HStack(spacing: 7) {
                    SettingsAppIcon(app: app, size: 13)
                    Text(app.displayName)
                        .font(.system(size: 11))
                        .foregroundStyle(Ink.secondary)
                    Spacer(minLength: 0)
                }
            }
            ForEach(domains, id: \.host) { domain in
                HStack(spacing: 7) {
                    SettingsFavicon(host: domain.host, size: 13)
                    Text(domain.host)
                        .font(.system(size: 11))
                        .foregroundStyle(Ink.secondary)
                    Spacer(minLength: 0)
                }
            }
        }
        .padding(.leading, 12 + 20 + SettingsMetrics.iconTile)
        .padding(.trailing, 12)
        .padding(.bottom, 8)
    }

    // MARK: - Actions

    private func toggleExpansion(_ id: String) {
        Sound.effect(.click)
        if expandedCategories.contains(id) {
            expandedCategories.remove(id)
        } else {
            expandedCategories.insert(id)
        }
    }

    /// Adds the typed domain, and clears the field only on success — a rejected entry stays visible so
    /// the user can see what was wrong with it rather than watching it vanish.
    private func addTypedDomain() {
        guard tab == .websites, let pattern = model.addableDomain else { return }
        if ExclusionEngine.shared.excludeWebsite(pattern.host) != nil {
            Sound.effect(.click)
            query = ""
        }
    }

    private func loadInventory() async {
        let installed = await Task.detached(priority: .utility) {
            ExclusionInventory.installedApplications()
        }.value

        // Read-only, and its own connection: the pane must never contend with the writer capture is
        // using. The read-only initialiser throws when there is no database yet or when it predates
        // this binary's queries, so both of those cost two discovery lists rather than the pane.
        let discovery = await Task.detached(priority: .utility) {
            () -> (apps: [ExcludableApp], domains: [String]) in
            guard let store = try? ContextStore(readOnly: true) else { return ([], []) }
            return (
                (try? ExclusionInventory.recentlyRecordedApps(store)) ?? [],
                (try? ExclusionInventory.recentlyRecordedDomains(store)) ?? []
            )
        }.value
        let recorded = discovery.apps
        let domains = discovery.domains

        allApps = installed
        recentApps = recorded
        recentDomains = domains
        isLoadingInventory = false
    }
}
