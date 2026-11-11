import AppKit
import ContextCore
import Foundation
// Same precedent as `Backend/ScreenActivityUploader.swift`: the two discovery queries below are
// aggregates the pane needs and `RewindQueries` does not have, so they are written here against the
// store's own `read` seam rather than by materialising a week of frames.
import GRDB

/// Everything the Exclusions pane draws, derived from `ExclusionSnapshot` and nothing else.
///
/// There is exactly one exclusions model in this app and it is `ExclusionEngine`. This file is a
/// *projection* of its snapshot into sections and rows, so the pane cannot invent a state the engine
/// does not have — in particular it cannot render a locked row as removable, because `isRemovable`
/// below is derived from `AppRow.isLocked` rather than decided here.
struct ExclusionsPaneModel: Equatable {

    enum Tab: String, CaseIterable, Identifiable, Sendable {
        case apps
        case websites

        var id: String { rawValue }
        var title: String {
            switch self {
            case .apps: "Apps"
            case .websites: "Websites"
            }
        }

        var searchPlaceholder: String {
            switch self {
            case .apps: "Search"
            case .websites: "Search or add domain"
            }
        }
    }

    /// One drawable row. Every case carries whether the user may change it, which is the only piece
    /// of state on this pane that matters more than the copy.
    enum Row: Equatable, Identifiable {
        /// A category the user ticks once, expandable to its members.
        case category(id: String, category: ExclusionCategory, isExcluded: Bool, memberCount: Int)
        /// One application.
        case app(app: ExcludableApp, state: AppExclusionState)
        /// One website exclusion already in force.
        case website(pattern: DomainPattern, fromCategory: ExclusionCategory?)
        /// A domain seen in capture that is *not* excluded, offered with a favicon.
        case recentDomain(host: String)
        /// The Exclude Private Tabs switch.
        case privateTabs(isOn: Bool)

        var id: String {
            switch self {
            case .category(let id, _, _, _): "category:\(id)"
            case .app(let app, _): "app:\(app.bundleID)"
            case .website(let pattern, _): "site:\(pattern.host)"
            case .recentDomain(let host): "recent:\(host)"
            case .privateTabs: "privateTabs"
            }
        }

        /// False for the locked defaults — password managers, the login screen, and any domain a
        /// ticked category contributes. The engine refuses those mutations anyway
        /// (`ExclusionMutation.refusedLocked`); this is what stops the UI offering them at all.
        var isRemovable: Bool {
            switch self {
            case .app(_, let state): state != .lockedExcluded
            case .website(_, let fromCategory): fromCategory == nil
            case .category, .recentDomain, .privateTabs: true
            }
        }

        var isChecked: Bool {
            switch self {
            case .category(_, _, let isExcluded, _): isExcluded
            case .app(_, let state): state != .included
            case .website: true
            case .recentDomain: false
            case .privateTabs(let isOn): isOn
            }
        }

        /// What the search field matches against.
        var searchText: String {
            switch self {
            case .category(_, let category, _, _): category.title + " " + category.subtitle
            case .app(let app, _): app.displayName + " " + app.bundleID
            case .website(let pattern, _): pattern.host
            case .recentDomain(let host): host
            case .privateTabs: "exclude private tabs browsing incognito"
            }
        }
    }

    struct Section: Equatable, Identifiable {
        let id: String
        let title: String
        /// Shown under the header when the section needs a caveat of its own.
        let footnote: String?
        let rows: [Row]

        init(id: String, title: String, footnote: String? = nil, rows: [Row]) {
            self.id = id
            self.title = title
            self.footnote = footnote
            self.rows = rows
        }
    }

    let tab: Tab
    let sections: [Section]
    /// Set when the search text normalises to a host that is not already excluded, so the Websites
    /// tab can offer "Add <host>" — which is what makes the placeholder's promise true.
    let addableDomain: DomainPattern?
    let health: ExclusionHealth

    /// Copy for `I39`.
    ///
    /// Written against what `PrivateBrowsing` can actually prove. The reference says "Works across all
    /// supported browsers", which for us would be an overclaim in two directions at once: some
    /// browsers mark a private window nowhere in the title so they cannot be detected at all, and the
    /// markers (`Incognito`, `InPrivate`, `Private Browsing`) are the English strings, so a localised
    /// Chrome is invisible too. Naming the browsers it does work for is both more useful and true.
    static let privateTabsTitle = "Exclude Private Tabs"

    /// The browsers whose private windows this genuinely catches: they append an English marker from
    /// ``PrivateBrowsing/titleMarkers`` to the window title.
    static let privateBrowsingDetectableBrowsers = ["Chrome", "Edge", "Brave", "Firefox"]

    /// The browsers whose private windows this cannot catch, because their window titles carry no
    /// browser chrome for a marker to appear in.
    ///
    /// **Arc is here on measurement, not assumption.** It was listed as detectable, and it never was:
    /// across 925 Arc frames in the real database on this machine the window title is the bare page
    /// title — `Context for Claude`, `Anthropic`, `LinkedIn`, `(9) Home / X` — with no browser name,
    /// no window state and therefore no marker any string in `titleMarkers` could ever match. The one
    /// row that matched `Arc` at all matched inside the word "Archit". `OpenExternally` reached the
    /// same conclusion about the same titles from the other direction. Safari is here for the reason
    /// `PrivateBrowsing` already documents.
    static let privateBrowsingUndetectableBrowsers = ["Arc", "Safari"]

    static var privateTabsSubtitle: String {
        "Skips \(sentenceList(privateBrowsingDetectableBrowsers)) private windows, recognised from the "
            + "window title. \(sentenceList(privateBrowsingUndetectableBrowsers)) private windows cannot "
            + "be detected — their titles carry no marker to recognise — and the check only recognises "
            + "English titles."
    }

    /// What this pane does and does not cover, stated where the user is choosing.
    ///
    /// An exclusion suppresses the *screen* side of capture and only that: `ScreenWatcher` is the one
    /// caller of `ExclusionEngine.admit`/`revalidate`, and everything behind that ticket — the
    /// screenshot, its OCR, the window title and the accessibility text — is dropped together. No
    /// audio path consults the engine at all (`MicCapture` and `SystemAudioCapture` never ask it), so
    /// a user who excludes their therapy portal and keeps talking is still being transcribed. A
    /// privacy pane that leaves that to be inferred is the kind of omission the exclusion is being
    /// made to prevent. The one control that does stop audio is named, so the note is actionable
    /// rather than only a caveat.
    ///
    /// **Apps and sites are not refused at the same point, and the note says so.** It used to claim
    /// that for both "its window title, on-screen text and accessibility text are never read", which
    /// is true of an app and cannot be true of a site. An app is judged from the bundle identifier
    /// alone, by the `exclusionReason` call `ScreenWatcher` makes *before* it resolves a window — so
    /// nothing about it is ever read. A site has no identity until something is read: `ScreenWatcher`
    /// scrubs the window title and walks the accessibility tree for the page address, and only then
    /// asks `admit`. In the ordinary case that is enough and the frame is refused before any
    /// screenshot is taken. In the fallback case — no address readable, which `websiteReason` tier 3
    /// exists for — the screenshot is captured, OCR'd and the accessibility text collected first, and
    /// `revalidate` refuses on that evidence at the write barrier; `discard` then unlinks the image
    /// that was already written. Nothing excluded is stored either way, which is the promise worth
    /// making, and it is a smaller promise than "never read".
    static let scopeNote =
        "Exclusions cover screen capture. An excluded app is refused before anything about it is "
        + "read — no screenshot, no window title, no text. An excluded site has to be recognised "
        + "before it can be refused, so the window title and page address are read first; when "
        + "neither identifies the site, the screenshot and its text are read too, then deleted "
        + "instead of stored. Audio is not covered: microphone and system-audio transcription keep "
        + "running for an excluded app. Pause from the menu bar to stop everything."

    /// `A, B and C` — Oxford-less, which is how the rest of this pane's copy reads.
    private static func sentenceList(_ items: [String]) -> String {
        guard let last = items.last else { return "" }
        guard items.count > 1 else { return last }
        return items.dropLast().joined(separator: ", ") + " and " + last
    }

    // MARK: - Derivation

    /// Builds the pane.
    ///
    /// - Parameters:
    ///   - snapshot: one consistent read of the engine, so no two rows can disagree.
    ///   - recentApps: apps actually seen in capture recently, newest first.
    ///   - allApps: every application on this Mac, alphabetical.
    ///   - recentDomains: hosts actually seen in capture, most frequent first.
    ///   - query: the search field.
    static func make(
        tab: Tab,
        snapshot: ExclusionSnapshot,
        recentApps: [ExcludableApp] = [],
        allApps: [ExcludableApp] = [],
        recentDomains: [String] = [],
        query: String = ""
    ) -> ExclusionsPaneModel {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        let sections: [Section]
        var addable: DomainPattern?

        switch tab {
        case .apps:
            sections = appSections(
                snapshot: snapshot, recentApps: recentApps, allApps: allApps,
                // Nil until the inventory has been read, which is what keeps the list from filtering
                // against an empty set and briefly showing nothing.
                installed: allApps.isEmpty ? nil : Set(allApps.map { $0.bundleID.lowercased() }))
        case .websites:
            sections = websiteSections(snapshot: snapshot, recentDomains: recentDomains)
            if let pattern = DomainPattern(trimmed),
                !snapshot.websites.contains(where: { $0.pattern == pattern })
            {
                addable = pattern
            }
        }

        return ExclusionsPaneModel(
            tab: tab,
            sections: filter(sections, query: trimmed),
            addableDomain: addable,
            health: snapshot.health)
    }

    /// Reference order, and it is an order rather than a set: Categories first because one tick there
    /// stands for many rows below it, then what is already excluded, then the system surfaces, then
    /// the two discovery lists — recent before exhaustive, because the app the user wants to hide is
    /// almost always one they just used.
    /// - Parameter installed: bundle ids present on this Mac, case-folded, or nil when the inventory has
    ///   not been read yet.
    private static func appSections(
        snapshot: ExclusionSnapshot,
        recentApps: [ExcludableApp],
        allApps: [ExcludableApp],
        installed: Set<String>?
    ) -> [Section] {
        var sections: [Section] = []

        sections.append(
            Section(
                id: "categories",
                title: "Categories",
                rows: snapshot.appCategories.map { row in
                    .category(
                        id: row.id, category: row.category, isExcluded: row.isExcluded,
                        memberCount: row.apps.count)
                }))

        // The login surfaces are in the engine's `excludedApps` *and* its `systemSurfaces`, because they
        // are both locked defaults and system chrome. The reference lists them once, under **System**
        // ("Login Screen (checked)"), so the Excluded section drops anything System is about to draw.
        // One app, one checkbox: two rows for one bundle id is two chances to disagree about its state.
        let systemIDs = Set(snapshot.systemSurfaces.map { $0.app.bundleID.lowercased() })
        var excludedRows = snapshot.excludedApps.filter { !systemIDs.contains($0.app.bundleID.lowercased()) }

        // A locked row for an app the user does not have is noise that buries the sections they came
        // for: the catalog names fourteen password managers, and listing all fourteen pushed **System**,
        // **Recently Recorded** and **All Applications** off the first two screens. The reference shows
        // only Keychain Access and Passwords for exactly this reason. Hiding a row changes nothing about
        // enforcement — the engine still refuses every one of them, installed or not — so the footnote
        // says how many are covered rather than letting the shorter list imply a narrower promise.
        var hiddenLockedCount = 0
        if let installed {
            let before = excludedRows.count
            excludedRows = excludedRows.filter {
                !$0.isLocked || installed.contains($0.app.bundleID.lowercased())
            }
            hiddenLockedCount = before - excludedRows.count
        }

        sections.append(
            Section(
                id: "excluded",
                title: "Excluded",
                footnote: lockedFootnote(hiddenLockedCount: hiddenLockedCount, rows: excludedRows),
                rows: excludedRows.map { .app(app: $0.app, state: $0.state) }))

        sections.append(
            Section(
                id: "system",
                title: "System",
                rows: snapshot.systemSurfaces.map { .app(app: $0.app, state: $0.state) }))

        // Built from the engine's **whole** excluded set rather than from the rows drawn above. A locked
        // app hidden from Excluded for not being installed must still never reappear under a discovery
        // heading, because there it would render as an ordinary clearable checkbox — and the engine
        // refuses that click, so the row would be a lie.
        var seen = systemIDs.union(snapshot.excludedApps.map { $0.app.bundleID.lowercased() })

        let recent = recentApps.filter { seen.insert($0.bundleID.lowercased()).inserted }
        if !recent.isEmpty {
            sections.append(
                Section(
                    id: "recent",
                    title: "Recently Recorded",
                    rows: recent.map { .app(app: $0, state: snapshot.state(of: $0.bundleID)) }))
        }

        let remaining = allApps.filter { seen.insert($0.bundleID.lowercased()).inserted }
        if !remaining.isEmpty {
            sections.append(
                Section(
                    id: "all",
                    title: "All Applications",
                    rows: remaining.map { .app(app: $0, state: snapshot.state(of: $0.bundleID)) }))
        }

        return sections
    }

    /// States the promise the shortened list would otherwise understate.
    static func lockedFootnote(hiddenLockedCount: Int, rows: [ExclusionSnapshot.AppRow]) -> String? {
        let base = "Password managers are excluded by default and cannot be removed."
        guard hiddenLockedCount > 0 else { return rows.contains(where: \.isLocked) ? base : nil }
        return base + " \(hiddenLockedCount) more are covered but are not installed on this Mac."
    }

    private static func websiteSections(
        snapshot: ExclusionSnapshot,
        recentDomains: [String]
    ) -> [Section] {
        var sections: [Section] = []

        sections.append(
            Section(
                id: "categories",
                title: "Categories",
                rows: snapshot.websiteCategories.map { row in
                    .category(
                        id: row.id, category: row.category, isExcluded: row.isExcluded,
                        memberCount: row.domains.count)
                }))

        sections.append(
            Section(
                id: "privateTabs",
                title: "Private Browsing",
                rows: [.privateTabs(isOn: snapshot.excludePrivateBrowsing)]))

        if !snapshot.websites.isEmpty {
            sections.append(
                Section(
                    id: "excluded",
                    title: "Excluded",
                    rows: snapshot.websites.map {
                        .website(pattern: $0.pattern, fromCategory: $0.fromCategory)
                    }))
        }

        let excluded = Set(snapshot.websites.map(\.pattern.host))
        let recent = recentDomains.filter { !excluded.contains($0) }
        sections.append(
            Section(
                id: "recent",
                title: "Recently Recorded",
                // An empty list needs a reason, or it reads as a broken feature. It is genuinely empty
                // whenever nothing browsed recently left a readable address: this database has no URL
                // column, so an address has to be recoverable from the window title or the
                // accessibility text of a browser frame, and plenty of browsing leaves neither.
                footnote: recent.isEmpty ? Self.noRecentDomainsNote : nil,
                rows: recent.map { .recentDomain(host: $0) }))

        return sections
    }

    static let noRecentDomainsNote =
        "No addresses could be read from recent browsing yet. Capture stores no URLs, so a site only "
        + "appears here once its address shows up in a browser's window title or accessibility text. "
        + "You can add any domain with the field above."

    /// Drops rows that do not match, then sections left empty.
    ///
    /// The search filters *list* rows only. `Exclude Private Tabs` is a setting rather than a list
    /// entry, so it always survives — on the Websites tab the field doubles as "add domain", and having
    /// a privacy switch vanish because the user started typing a hostname would hide a setting behind
    /// an unrelated action.
    private static func filter(_ sections: [Section], query: String) -> [Section] {
        guard !query.isEmpty else { return sections }
        let needle = query.lowercased()
        return sections.compactMap { section in
            let rows = section.rows.filter { row in
                if case .privateTabs = row { return true }
                return row.searchText.lowercased().contains(needle)
            }
            // A footnote-only section (the empty Recently Recorded note) is not a match for a search.
            guard !rows.isEmpty else { return nil }
            return Section(id: section.id, title: section.title, footnote: section.footnote, rows: rows)
        }
    }
}

extension ExclusionSnapshot {
    /// The state of a bundle id as the derived rows need it, taken from this snapshot rather than
    /// from a second read of the engine — two reads is how one pane shows two answers.
    func state(of bundleID: String) -> AppExclusionState {
        let folded = bundleID.lowercased()
        if let row = (excludedApps + systemSurfaces).first(where: { $0.app.bundleID.lowercased() == folded }) {
            return row.state
        }
        for category in appCategories where category.isExcluded {
            if category.apps.contains(where: { $0.app.bundleID.lowercased() == folded }) {
                return category.apps.first { $0.app.bundleID.lowercased() == folded }?.state ?? .excluded
            }
        }
        return .included
    }
}

// MARK: - What is on this Mac, and what capture has seen

/// The two discovery lists: apps installed here, and apps/domains capture actually recorded.
///
/// Both are real reads. `I35`/`I36` want icons and an alphabetical inventory, and `I40` wants domains
/// the user has genuinely visited — an invented list would be a privacy control pointing at nothing.
enum ExclusionInventory {

    /// The directories an application can live in on macOS. `/System/Library/CoreServices` is here for
    /// the same reason `AppIconCache` lists it: Finder and several system agents live there.
    static let applicationDirectories = [
        "/Applications",
        "/Applications/Utilities",
        "/System/Applications",
        "/System/Applications/Utilities",
        "/System/Library/CoreServices",
        NSHomeDirectory() + "/Applications",
    ]

    /// Every application bundle found on this Mac, alphabetical by display name.
    ///
    /// Reads `CFBundleIdentifier` straight from each `Info.plist` rather than guessing one from the
    /// name: `AppIconCache` documents what fabricated identifiers cost, and an exclusion keyed on a
    /// guessed identifier would silently protect nothing.
    static func installedApplications(
        directories: [String] = applicationDirectories
    ) -> [ExcludableApp] {
        let fileManager = FileManager.default
        var byIdentifier: [String: ExcludableApp] = [:]

        for directory in directories {
            guard let names = try? fileManager.contentsOfDirectory(atPath: directory) else { continue }
            for name in names where name.hasSuffix(".app") {
                let url = URL(fileURLWithPath: directory).appendingPathComponent(name)
                guard let bundle = Bundle(url: url),
                    let identifier = bundle.bundleIdentifier,
                    !identifier.isEmpty
                else { continue }
                let display =
                    (bundle.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String)
                    ?? (bundle.object(forInfoDictionaryKey: "CFBundleName") as? String)
                    ?? String(name.dropLast(4))
                // First win: /Applications before /System, which is the order a user thinks in.
                if byIdentifier[identifier.lowercased()] == nil {
                    byIdentifier[identifier.lowercased()] = ExcludableApp(
                        bundleID: identifier, displayName: display)
                }
            }
        }

        return byIdentifier.values.sorted {
            $0.displayName.localizedCaseInsensitiveCompare($1.displayName) == .orderedAscending
        }
    }

    /// Apps capture has recorded in the last `days`, most recent first.
    ///
    /// Bounded by a `GROUP BY` in SQL rather than by materialising frames: a week of capture is tens
    /// of thousands of rows and the pane needs a couple of dozen names.
    static func recentlyRecordedApps(
        _ store: ContextStore,
        days: Int = 7,
        limit: Int = 40,
        now: Double = Date().timeIntervalSince1970
    ) throws -> [ExcludableApp] {
        let since = now - Double(days) * 86_400
        return try store.read { db in
            let rows = try Row.fetchAll(
                db,
                sql: """
                    SELECT appName, MAX(bundleId) AS bundleId, MAX(capturedAt) AS lastSeen
                    FROM frames
                    WHERE capturedAt >= ? AND appName IS NOT NULL AND TRIM(appName) <> ''
                    GROUP BY appName
                    ORDER BY lastSeen DESC
                    LIMIT ?
                    """,
                arguments: [since, limit])
            // A row with no bundle id predates the column that added one, and is dropped rather than
            // given a fabricated identifier: `AppIconCache` documents what inventing one costs, and
            // an exclusion keyed on a guessed identifier silently protects nothing.
            return rows.compactMap { row -> ExcludableApp? in
                guard let name: String = row["appName"],
                    let bundleID: String = row["bundleId"],
                    !bundleID.trimmingCharacters(in: .whitespaces).isEmpty
                else { return nil }
                return ExcludableApp(bundleID: bundleID, displayName: name)
            }
        }
    }

    /// Browsers whose bundle identifier `PrivateBrowsing` does not list yet.
    ///
    /// `PrivateBrowsing.browserBundleIdentifiers` in `ContextCore` is the canonical set and should absorb
    /// these — ChatGPT Atlas is a Chromium browser and is on this Mac, and its absence there is a hole in
    /// *private-window detection*, not only in this list. Kept here rather than duplicated silently so the
    /// gap is visible; this is a discovery heuristic and decides no exclusion.
    static let additionalBrowserBundleIdentifiers: Set<String> = ["com.openai.atlas"]

    static var browserBundleIdentifiers: Set<String> {
        // **Case-folded.** The canonical set is spelled in lower case; the database stores identifiers as
        // the vendor ships them — `company.thebrowser.Browser`, `com.google.Chrome` — so a raw
        // `contains` matched nothing at all and this list came back empty on a machine with a month of
        // browsing in it. Both sides are folded here, once.
        Set(
            PrivateBrowsing.browserBundleIdentifiers.union(additionalBrowserBundleIdentifiers)
                .map { $0.lowercased() })
    }

    /// Hosts capture has seen in browser windows, most frequent first.
    ///
    /// The schema has no URL column, so the evidence is the accessibility text of browser frames —
    /// which is where the address bar's contents land — plus the window title. `DomainMatcher`
    /// extracts the hosts, so nothing here parses a URL by hand.
    static func recentlyRecordedDomains(
        _ store: ContextStore,
        days: Int = 30,
        rowLimit: Int = 1_500,
        limit: Int = 24,
        now: Double = Date().timeIntervalSince1970
    ) throws -> [String] {
        let since = now - Double(days) * 86_400
        let browsers = browserBundleIdentifiers
        var counts: [String: Int] = [:]

        try store.read { db in
            let rows = try Row.fetchAll(
                db,
                sql: """
                    SELECT bundleId, windowTitle, axText FROM frames
                    WHERE capturedAt >= ?
                      AND (windowTitle LIKE '%.%' OR axText LIKE '%.%')
                    ORDER BY capturedAt DESC
                    LIMIT ?
                    """,
                arguments: [since, rowLimit])
            for row in rows {
                // Only browsers: a host-shaped string in an editor's window title is a filename, and
                // a domain the user never visited has no business in a list of sites they can hide.
                guard let bundleID: String = row["bundleId"],
                    browsers.contains(bundleID.lowercased())
                else { continue }
                let title: String? = row["windowTitle"]
                let axText: String? = row["axText"]
                for text in [title, axText].compactMap({ $0 }) {
                    for host in DomainMatcher.hostCandidates(in: text) {
                        counts[host, default: 0] += 1
                    }
                }
            }
        }

        return counts.sorted { lhs, rhs in
            lhs.value == rhs.value ? lhs.key < rhs.key : lhs.value > rhs.value
        }
        .prefix(limit)
        .map(\.key)
    }
}
