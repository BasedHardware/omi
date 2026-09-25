import Foundation
import OSLog

// MARK: - What is about to be captured

/// Whether a window is a private/incognito browsing window.
///
/// Three states rather than a `Bool` because "we could not tell" is the common case and must not be
/// silently spelled as "not private". Safari marks a private window nowhere in its title, so a
/// browser frame arrives here as ``unknown`` unless the app has real evidence — see
/// ``PrivateBrowsing`` for what the title can and cannot prove.
public enum WindowPrivacy: String, Sendable, Equatable, Codable {
    case regular
    case privateBrowsing
    case unknown
}

/// The identity of one capture, as the gate needs to see it.
///
/// Assembled by the caller at capture time and carried, unchanged, all the way to the write — which
/// is what lets a frame that was admitted an hour ago be re-judged against an exclusion the user
/// added a second ago. Every field is optional because the evidence genuinely arrives in pieces: the
/// frontmost application is known before any window is resolved, the title only after, and the URL
/// only when the accessibility tree gave one up.
///
/// `bundleID` is the identity that matters. `appName` is a display name — user-renameable, localised,
/// and trivially spoofable — so it is only ever a *widening* signal here: it can exclude more, never
/// less, and it exists because a queued frame carries no bundle identifier (`Frame` stores
/// `appName`), and because a rebranded password manager still calls itself one.
public struct CaptureSubject: Sendable, Equatable, Codable {
    public var bundleID: String?
    public var appName: String?
    public var windowTitle: String?
    /// The page the window was showing, if anything could read it: normally a bare host.
    ///
    /// **Only ever set from the window whose pixels were captured.** A producer that cannot show the
    /// address belongs to that window must leave this nil, because this field outranks the evidence
    /// beneath it: a wrong address does not merely fail to exclude, it silences the window's own
    /// text as well. See `AXWindowMatch`.
    ///
    /// A full URL still matches — everything here is normalised to a host before it is compared —
    /// but nothing in-tree puts one here any more: a query string is a session token or a document
    /// identifier, and this struct is `Codable` and travels with the capture.
    public var url: String?
    /// The window's own accessibility text — evidence of last resort about which site was on screen.
    ///
    /// It arrives after the window has already been admitted, because reading a window's text costs
    /// an inter-process walk and happens beside OCR rather than in front of it. That timing is the
    /// reason this field exists: without it the text was written to a permanent, searchable database
    /// having never been judged, and an `axText` carrying `gmail.com` was stored unexamined.
    ///
    /// Only ever consulted when ``url`` is nil — see ``ExclusionSet/reason(for:)``.
    public var pageText: String?
    public var privacy: WindowPrivacy

    public init(
        bundleID: String? = nil,
        appName: String? = nil,
        windowTitle: String? = nil,
        url: String? = nil,
        pageText: String? = nil,
        privacy: WindowPrivacy = .unknown
    ) {
        self.bundleID = bundleID
        self.appName = appName
        self.windowTitle = windowTitle
        self.url = url
        self.pageText = pageText
        self.privacy = privacy
    }
}

// MARK: - Why a capture was refused

/// Why this capture must not be read or written.
///
/// Carries the evidence the UI and the tests need, and `logDescription` deliberately carries less:
/// a window excluded *because of* its title or its domain is exactly the one whose title and domain
/// must not be written to a log file. That rule is inherited from ``Redaction`` and tested.
public enum ExclusionReason: Sendable, Equatable {
    /// Excluded before the user did anything, and not user-removable.
    case defaultExcludedApp(bundleID: String)
    case userExcludedApp(bundleID: String)
    /// A category the user ticked, expanded to one of its members.
    case categoryApp(ExclusionCategory, bundleID: String)
    /// Matched on display name because no bundle identifier was available — the write barrier's case.
    case excludedAppName(String)
    case excludedWebsite(pattern: String)
    case privateBrowsing
    /// The pre-existing credential-surface rule in ``Redaction/isSensitiveWindow(app:title:)``.
    case credentialSurface
    /// The stored configuration could not be trusted, so a capture admitted under a different one is
    /// refused rather than written.
    case configurationUnavailable

    /// Safe to log. Never contains a window title or a domain.
    public var logDescription: String {
        switch self {
        case .defaultExcludedApp(let bundleID): "excluded by default: \(bundleID)"
        case .userExcludedApp(let bundleID): "excluded app: \(bundleID)"
        case .categoryApp(let category, let bundleID): "excluded category \(category.rawValue): \(bundleID)"
        case .excludedAppName(let name): "excluded app: \(name)"
        case .excludedWebsite: "excluded website"
        case .privateBrowsing: "private browsing window"
        case .credentialSurface: "credential surface"
        case .configurationUnavailable: "exclusion configuration unavailable"
        }
    }

    /// True when the user cannot lift this exclusion from Settings.
    public var isLocked: Bool {
        switch self {
        case .defaultExcludedApp, .credentialSurface, .configurationUnavailable: true
        default: false
        }
    }
}

// MARK: - Categories

/// A box the user ticks once that stands for many concrete things.
///
/// Categories exist because nobody enumerates their own password managers correctly: the reference
/// shows one "Password Managers ›" row that expands to the member apps, and that row has to be
/// backed by real bundle identifiers rather than by a name search performed at tick time.
public enum ExclusionCategory: String, CaseIterable, Codable, Sendable, Identifiable {
    case passwordManagers
    case banks

    public var id: String { rawValue }

    /// What the category matches, which is also which tab it belongs on.
    public enum Kind: Sendable { case apps, websites }

    public var kind: Kind {
        switch self {
        case .passwordManagers: .apps
        case .banks: .websites
        }
    }

    /// Reference copy, verbatim from `docs/rewind-and-settings.md`.
    public var title: String {
        switch self {
        case .passwordManagers: "Password Managers"
        case .banks: "Banks"
        }
    }

    public var subtitle: String {
        switch self {
        case .passwordManagers: "Password manager apps"
        case .banks: "UK & US banks, neobanks, and fintech"
        }
    }

    /// Ticked on a fresh install.
    ///
    /// Password managers are on because a plaintext OCR of an unlocked vault is the worst single
    /// row this database could hold. Banks is off because it is a broad domain list the user has not
    /// asked for, and an exclusion nobody wanted teaches them to distrust the whole pane.
    public var isDefaultEnabled: Bool {
        switch self {
        case .passwordManagers: true
        case .banks: false
        }
    }
}

// MARK: - An app the user can exclude

public struct ExcludableApp: Sendable, Equatable, Hashable, Codable, Identifiable {
    /// The stable identity. Compared case-folded; stored as the vendor ships it.
    public let bundleID: String
    /// For the list row only. Never the thing matched when a bundle identifier is available.
    public let displayName: String

    public var id: String { bundleID }

    public init(bundleID: String, displayName: String) {
        self.bundleID = bundleID
        self.displayName = displayName
    }

    var foldedBundleID: String { bundleID.lowercased() }
    var foldedDisplayName: String { displayName.lowercased() }
}

/// Whether a bundle identifier is excluded, and whether the user may change that.
public enum AppExclusionState: Sendable, Equatable {
    /// Excluded and not removable — the "lighter locked-looking state" in the reference.
    case lockedExcluded
    case excluded
    case included
}

// MARK: - The catalog

/// The concrete membership behind every default and every category.
///
/// This is the single source of truth for what "excluded by default" means: ``Redaction`` builds its
/// own unconditional refusal list from ``lockedApps`` rather than keeping a second copy, so the two
/// halves of the defence cannot drift apart.
public enum ExclusionCatalog {

    /// Password managers, by bundle identifier.
    ///
    /// Every entry is an application whose entire purpose is to display secrets in plaintext once
    /// unlocked. Apple's two are here because they ship on every Mac and are what the reference shows
    /// as excluded-and-locked: Keychain Access (`com.apple.keychainaccess`) and Passwords
    /// (`com.apple.Passwords`).
    ///
    /// Both 1Password generations are listed because 7 and 8 use unrelated identifiers and a user
    /// mid-migration runs both. `com.1password.browser-support` is the helper that draws the
    /// autofill popover — a separate process, and the one actually frontmost while a credential is
    /// on screen.
    public static let passwordManagers: [ExcludableApp] = [
        ExcludableApp(bundleID: "com.1password.1password", displayName: "1Password"),
        ExcludableApp(bundleID: "com.1password.browser-support", displayName: "1Password Browser Helper"),
        ExcludableApp(bundleID: "com.agilebits.onepassword7", displayName: "1Password 7"),
        ExcludableApp(bundleID: "com.agilebits.onepassword-osx", displayName: "1Password 6"),
        ExcludableApp(bundleID: "com.bitwarden.desktop", displayName: "Bitwarden"),
        ExcludableApp(bundleID: "com.dashlane.Dashlane", displayName: "Dashlane"),
        ExcludableApp(bundleID: "com.lastpass.LastPass", displayName: "LastPass"),
        ExcludableApp(bundleID: "com.lastpass.lastpassmacdesktop", displayName: "LastPass Desktop"),
        ExcludableApp(bundleID: "org.keepassxc.keepassxc", displayName: "KeePassXC"),
        ExcludableApp(bundleID: "in.sinew.Enpass-Desktop", displayName: "Enpass"),
        ExcludableApp(bundleID: "com.nordpass.macos", displayName: "NordPass"),
        ExcludableApp(bundleID: "me.proton.pass.electron", displayName: "Proton Pass"),
        ExcludableApp(bundleID: "com.apple.keychainaccess", displayName: "Keychain Access"),
        ExcludableApp(bundleID: "com.apple.Passwords", displayName: "Passwords"),
    ]

    /// The login screen and the authentication panels the system puts in front of the user.
    ///
    /// `com.apple.loginwindow` is the login screen itself; `com.apple.SecurityAgent` is the process
    /// that draws every "authenticate to continue" sheet, including the one asking for the user's
    /// account password. Both are locked for the same reason as a password manager: the window
    /// exists to hold a credential.
    public static let loginSurfaces: [ExcludableApp] = [
        ExcludableApp(bundleID: "com.apple.loginwindow", displayName: "Login Screen"),
        ExcludableApp(bundleID: "com.apple.SecurityAgent", displayName: "Authentication"),
    ]

    /// Screenshot and screen-share tooling. Their windows are either our own capture UI reflected
    /// back or a picker showing someone else's screen.
    ///
    /// Unconditional in ``Redaction`` and deliberately *not* offered in Settings — nothing is gained
    /// by letting a user opt into recording their own screen recorder.
    public static let screenCaptureTools: [ExcludableApp] = [
        ExcludableApp(bundleID: "com.apple.screencaptureui", displayName: "Screenshot"),
        ExcludableApp(bundleID: "com.apple.ScreenSharing", displayName: "Screen Sharing"),
        ExcludableApp(bundleID: "com.apple.screensharing.agent", displayName: "Screen Sharing Agent"),
        ExcludableApp(bundleID: "com.apple.screensharing.MessagesAgent", displayName: "Screen Sharing"),
        ExcludableApp(bundleID: "pl.maketheweb.cleanshotx", displayName: "CleanShot X"),
        ExcludableApp(bundleID: "com.loom.desktop", displayName: "Loom"),
        ExcludableApp(bundleID: "cc.ffitch.shottr", displayName: "Shottr"),
        ExcludableApp(bundleID: "com.monosnap.monosnap", displayName: "Monosnap"),
        ExcludableApp(bundleID: "com.skitch.skitch", displayName: "Skitch"),
    ]

    /// The reference's **System** group, minus Login Screen which is locked above.
    ///
    /// Offered and unticked, exactly as the reference shows them: these are transient system chrome
    /// rather than credential surfaces, and a user who never wants their notifications read can say
    /// so.
    public static let optionalSystemSurfaces: [ExcludableApp] = [
        ExcludableApp(bundleID: "com.apple.notificationcenterui", displayName: "Notifications"),
        ExcludableApp(bundleID: "com.apple.controlcenter", displayName: "Control Center"),
        ExcludableApp(bundleID: "com.apple.Spotlight", displayName: "Spotlight"),
        ExcludableApp(bundleID: "com.apple.Siri", displayName: "Siri"),
    ]

    /// Everything excluded before the user has done anything, and which they cannot remove.
    ///
    /// "Cannot remove" is the reference's locked state, and it is the right shape for this list: a
    /// user who unticked Keychain Access would be one OCR pass away from a plaintext copy of their
    /// own vault, and no Settings pane should make that reachable by a stray click.
    public static let lockedApps: [ExcludableApp] = passwordManagers + loginSurfaces

    public static let lockedBundleIdentifiers: Set<String> = Set(lockedApps.map(\.foldedBundleID))

    /// Product names that mean "password manager" whatever the bundle identifier says.
    ///
    /// Bundle ids drift across versions and rebrands, and a manager not on the list above still
    /// calls itself one. Every entry over-matches by design — an app named "Bookkeeper" loses its
    /// frames to `keeper` — and that is the cheap side of the trade this file exists to make.
    public static let lockedNameFragments = [
        "password", "keychain", "keepass", "bitwarden", "dashlane", "lastpass", "nordpass",
        "enpass", "keeper", "roboform", "authenticator",
    ]

    /// Banks, neobanks and fintech, UK and US.
    ///
    /// A starting set, not a claim of completeness: the point of the category is that one tick
    /// covers the accounts most people have, and the Websites tab lets them add the rest. Every
    /// entry is a registrable domain, so subdomain matching covers the `online.`, `secure.` and
    /// `banking.` hosts these institutions actually serve their logins from.
    public static let bankDomains: [String] = [
        // US retail and brokerage
        "chase.com", "bankofamerica.com", "wellsfargo.com", "citi.com", "citibank.com",
        "usbank.com", "pnc.com", "capitalone.com", "truist.com", "tdbank.com",
        "schwab.com", "fidelity.com", "vanguard.com", "etrade.com", "ally.com",
        "discover.com", "americanexpress.com", "amex.com", "navyfederal.org", "marcus.com",
        "interactivebrokers.com", "robinhood.com", "wealthfront.com", "betterment.com",
        // UK retail
        "barclays.co.uk", "hsbc.co.uk", "lloydsbank.com", "halifax.co.uk", "natwest.com",
        "rbs.co.uk", "santander.co.uk", "nationwide.co.uk", "tsb.co.uk",
        "co-operativebank.co.uk", "metrobankonline.co.uk", "virginmoney.com",
        // Neobanks, payments, crypto
        "monzo.com", "starlingbank.com", "revolut.com", "wise.com", "chime.com", "sofi.com",
        "paypal.com", "venmo.com", "cash.app", "squareup.com", "stripe.com",
        "klarna.com", "affirm.com", "coinbase.com", "kraken.com", "binance.com",
    ]

    public static func apps(in category: ExclusionCategory) -> [ExcludableApp] {
        switch category {
        case .passwordManagers: passwordManagers
        case .banks: []
        }
    }

    public static func domains(in category: ExclusionCategory) -> [DomainPattern] {
        switch category {
        case .passwordManagers: []
        case .banks: bankPatterns
        }
    }

    /// Normalised once for the process. Re-parsing fifty hosts per capture tick is measurable.
    static let bankPatterns: [DomainPattern] = bankDomains.compactMap(DomainPattern.init)
}

// MARK: - Domains

/// One website exclusion, normalised.
///
/// A pattern is always a host: no scheme, no path, no port, no trailing dot, lower-cased. Storing
/// anything else would put the parsing at match time, on every frame, where a mistake is a leak
/// rather than a rejected keystroke.
public struct DomainPattern: Hashable, Sendable, Codable, Comparable, CustomStringConvertible {
    public let host: String

    /// Nil when nothing host-shaped was typed. Accepts what a user actually pastes: a full URL, a
    /// bare host, `www.` prefixed, `*.example.com`, or an address with a port.
    public init?(_ raw: String) {
        guard let host = DomainMatcher.normalize(raw) else { return nil }
        self.host = host
    }

    /// True when `candidate` is this host or any subdomain of it. Normalises `candidate` first.
    public func matches(_ candidate: String) -> Bool {
        guard let candidate = DomainMatcher.normalize(candidate) else { return false }
        return matches(normalizedHost: candidate)
    }

    /// The hot path: `candidate` must already be normalised.
    ///
    /// Split out because the gate compares one host against every pattern in force on every capture
    /// tick, and normalising the same candidate a few hundred times per frame measured at
    /// milliseconds a frame. Allocation-free on purpose — no `"." + host` per comparison.
    func matches(normalizedHost candidate: String) -> Bool {
        if candidate == host { return true }
        guard candidate.count > host.count, candidate.hasSuffix(host) else { return false }
        let boundary = candidate.index(candidate.endIndex, offsetBy: -(host.count + 1))
        return candidate[boundary] == "."
    }

    public var description: String { host }

    public static func < (lhs: DomainPattern, rhs: DomainPattern) -> Bool { lhs.host < rhs.host }
}

/// Host normalisation and suffix matching — the two places a website exclusion can leak.
///
/// The matching rule is *label-boundary* suffix matching, and the naive spellings of it are both
/// wrong in a way that matters:
///
/// - `candidate.contains(pattern)` excludes nothing it should and everything it should not:
///   `example.com.evil.net` contains `example.com`, and an attacker chooses that host.
/// - `candidate.hasSuffix(pattern)` matches `notexample.com` against `example.com`, so excluding
///   your bank silently stops capture on an unrelated site — and, worse, the same class of bug in
///   the other direction (`hasPrefix`) would *fail* to exclude `login.example.com`.
///
/// So: equality, or a suffix that starts at a dot. Nothing else.
public enum DomainMatcher {

    /// Longest a hostname may be, per DNS. A longer string is not a host and is refused rather than
    /// stored as a pattern that can never match.
    private static let maximumHostLength = 253

    /// Characters that end the authority component of a URL.
    private static let authorityTerminators: Set<Character> = ["/", "?", "#"]

    /// Reduces anything the user can paste, or the accessibility tree can report, to a bare host.
    ///
    /// Deliberately permissive about the *characters* in a host — internationalised domains are
    /// real, and refusing one means the user cannot exclude their own bank — and strict about the
    /// *shape*: whitespace, quotes and separators mean this was prose rather than an address.
    public static func normalize(_ raw: String) -> String? {
        var value = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !value.isEmpty else { return nil }

        // Scheme, then the authority component, then userinfo — in that order, because each one can
        // contain characters that would otherwise be mistaken for the next.
        if let scheme = value.range(of: "://") {
            value = String(value[scheme.upperBound...])
        } else if value.hasPrefix("//") {
            value = String(value.dropFirst(2))
        }
        if let end = value.firstIndex(where: { authorityTerminators.contains($0) }) {
            value = String(value[..<end])
        }
        if let at = value.lastIndex(of: "@") {
            value = String(value[value.index(after: at)...])
        }

        // Port. An IPv6 literal is full of colons, so it is taken whole up to its closing bracket.
        if value.hasPrefix("[") {
            guard let close = value.firstIndex(of: "]") else { return nil }
            value = String(value[...close])
        } else if let colon = value.firstIndex(of: ":") {
            value = String(value[..<colon])
        }

        // `*.example.com` is what a user types when they mean "and its subdomains", which is what
        // every pattern already means.
        while value.hasPrefix("*.") { value = String(value.dropFirst(2)) }
        // A trailing dot is a fully-qualified name — the same host. Dropping it is what stops
        // `example.com.` being a way to slip past an exclusion.
        while value.hasSuffix(".") { value.removeLast() }
        while value.hasPrefix(".") { value.removeFirst() }

        guard !value.isEmpty, value.count <= maximumHostLength else { return nil }
        guard value.unicodeScalars.allSatisfy({ !CharacterSet.whitespacesAndNewlines.contains($0) })
        else { return nil }
        guard !value.contains(where: { forbiddenInHost.contains($0) }) else { return nil }
        guard value.unicodeScalars.contains(where: { CharacterSet.alphanumerics.contains($0) })
        else { return nil }
        // `..` is not a host; it is also the shape a mistyped pattern takes, and it would make the
        // dotted-suffix rule below match on an empty label.
        guard !value.contains("..") else { return nil }

        return value
    }

    /// Characters that prove the string was prose, a query, or a shell word rather than a host.
    private static let forbiddenInHost: Set<Character> = [
        "\"", "'", "`", "<", ">", "\\", ",", ";", "(", ")", "{", "}", "|", "^", "*", "=", "&", "!",
        "?", "#", "/", "@", " ",
    ]

    /// The whole matching rule: equal hosts, or a subdomain at a label boundary.
    public static func matches(pattern: String, candidate: String) -> Bool {
        guard let pattern = normalize(pattern), let candidate = normalize(candidate) else {
            return false
        }
        if candidate == pattern { return true }
        return candidate.hasSuffix("." + pattern)
    }

    /// Host-shaped tokens inside a window title.
    ///
    /// The URL is the authority on which site a frame was showing, and it is not always available:
    /// no browser puts it in the window title, and reading it needs the accessibility tree. Until
    /// the caller has one, a title that names an excluded domain is the only evidence there is —
    /// so it counts. This over-excludes (an article *about* `barclays.co.uk` loses its frame) and
    /// that is the correct direction: the alternative is capturing the bank.
    ///
    /// Titles only, never OCR text. A page mentioning a domain in its body is not a page on it, and
    /// scanning a screenful of text would turn one excluded domain into an unusable database.
    public static func hostCandidates(in text: String, limit: Int = 12) -> [String] {
        var found: [String] = []
        var seen: Set<String> = []
        for token in text.split(whereSeparator: { $0.isWhitespace || tokenBreaks.contains($0) }) {
            guard token.contains("."), let host = normalize(String(token)) else { continue }
            // At least two labels and a plausible TLD, or every `Store.swift` in a window title
            // becomes a host.
            let labels = host.split(separator: ".")
            guard labels.count >= 2, let tld = labels.last, tld.count >= 2 else { continue }
            guard tld.allSatisfy({ $0.isLetter }) else { continue }
            guard seen.insert(host).inserted else { continue }
            found.append(host)
            if found.count >= limit { break }
        }
        return found
    }

    /// Characters that separate words in a window title but are legal inside a URL, so a token has
    /// to be cut on them before it can be read as a host.
    private static let tokenBreaks: Set<Character> = [
        "—", "–", "|", "(", ")", "[", "]", "{", "}", "<", ">", ",", ";", "\"", "'", "«", "»",
    ]
}

// MARK: - Private browsing

/// What a window title can prove about private browsing, and what it cannot.
///
/// **It catches:** Chromium's family (Chrome, Edge, Brave, Arc, Opera) which append `Incognito` or
/// `Private` to the window title, and Firefox, which appends `Private Browsing`.
///
/// **It does not catch:** Safari, which marks a private window nowhere in its title — the only
/// honest signals there are AppleScript or the accessibility tree, both of which live in the app.
/// A Safari private window therefore arrives as ``WindowPrivacy/unknown`` and is captured. That is
/// a real hole and it is named rather than papered over: refusing every window we cannot classify
/// would mean refusing all browsing, and a recorder that captures nothing is not the fail-closed
/// answer to a recorder that captures too much.
public enum PrivateBrowsing {

    /// Localised in English only. A German Chrome says `Inkognito`, and the marker list below does
    /// not know that — the fix is a real per-browser signal from the app, not more translations.
    public static let titleMarkers = [
        "incognito", "private browsing", "private window", "(private)", "inprivate",
    ]

    public static let browserBundleIdentifiers: Set<String> = [
        "com.apple.safari", "com.google.chrome", "com.google.chrome.canary",
        "com.microsoft.edgemac", "com.brave.browser", "org.mozilla.firefox",
        "company.thebrowser.browser", "company.thebrowser.dia", "com.operasoftware.opera",
        "com.vivaldi.vivaldi", "org.chromium.chromium", "com.openai.chat",
        // ChatGPT Atlas. Absent until now, and a real hole rather than a tidy-up: `isBrowser` returns
        // on a bundle-identifier miss WITHOUT falling through to the name-fragment check, so an Atlas
        // frame carrying its identifier was classified as not-a-browser and its private windows were
        // never considered at all. Confirmed as this machine's default http handler through
        // LaunchServices, which makes it the browser most likely to be in front of someone.
        "com.openai.atlas",
    ]

    /// Product names that mean "browser" whatever the bundle identifier says.
    public static let browserNameFragments = [
        "safari", "chrome", "chromium", "firefox", "edge", "brave", "arc", "opera", "vivaldi",
        "browser", "atlas", "dia",
    ]

    /// Whether this is a browser, by bundle id when there is one and by name otherwise.
    ///
    /// Name matching is a *widening* fallback for the write barrier, which has no bundle id: without
    /// it a queued frame from an excluded domain could never be dropped. Public because capture asks
    /// the same question before it spends an accessibility walk looking for a page address — a
    /// second copy of this list is how "it stopped hiding my bank in the browser I added" happens.
    public static func isBrowser(bundleID: String?, appName: String?) -> Bool {
        if let bundleID = bundleID?.lowercased(), !bundleID.isEmpty {
            return browserBundleIdentifiers.contains(bundleID)
        }
        guard let name = appName?.lowercased() else { return false }
        return browserNameFragments.contains { name.contains($0) }
    }

    /// Best evidence from what a capture tick already has in hand.
    ///
    /// `bundleID` is deliberately *not* used to gate the title check. Gating on a known browser would
    /// read better and behave worse: a frame queued for the database carries a display name and no
    /// bundle identifier, so the write barrier would stop being able to classify anything — and a
    /// document window titled "Private Browsing" losing its frame is the harmless direction. The
    /// parameter stays because the honest fix is a real per-browser signal arriving through it.
    public static func classify(bundleID: String?, title: String?) -> WindowPrivacy {
        guard let title = title?.lowercased(), !title.isEmpty else { return .unknown }
        if titleMarkers.contains(where: { title.contains($0) }) { return .privateBrowsing }
        return .unknown
    }
}

// MARK: - Health

/// Whether the stored configuration could be trusted, and what was done about it.
public enum ExclusionHealth: Sendable, Equatable {
    /// A configuration was read and this build understands it.
    case configured
    /// There is no configuration on disk. Every user today, and every fresh install: the safe
    /// defaults apply and nothing is wrong.
    case defaultsOnly
    /// The configuration could not be trusted. More is excluded than the file asked for, never less.
    case failedClosed(FailClosedCause)
    /// The live state is correct but could not be written, so it will not survive a relaunch. The
    /// exclusion is in force *now*, which is the half that matters; the UI has to say the rest.
    case notPersisted(String)

    public var isFailClosed: Bool {
        if case .failedClosed = self { return true }
        return false
    }
}

public enum FailClosedCause: Sendable, Equatable {
    /// The file exists and could not be read at all — permissions, a directory in its place, I/O.
    case unreadable(String)
    /// The file was read and is not a configuration this build can parse.
    case malformed(String)
    /// Written by a newer build, so it may carry exclusions this one cannot express.
    case writtenByNewerVersion(Int)
}

// MARK: - The decision set

/// An immutable snapshot of every exclusion in force, and the decision made from it.
///
/// Pure and `Sendable` on purpose: this is the type the capture tick and the write barrier both
/// read, from different threads, and the type every test in `ExclusionsTests` exercises without
/// touching a disk. ``ExclusionEngine`` is only the mutable box that holds one of these.
public struct ExclusionSet: Sendable, Equatable {
    /// Folded bundle identifiers excluded by default. Never empty — see ``safeDefaults``.
    public let lockedApps: Set<String>
    /// Folded bundle identifiers the user excluded.
    public let userApps: Set<String>
    public let categories: Set<ExclusionCategory>
    public let websites: Set<DomainPattern>
    public let excludePrivateBrowsing: Bool
    public let airgapMode: Bool
    public let health: ExclusionHealth

    /// Display names that must also be refused, for callers that have no bundle identifier.
    ///
    /// Derived, not configured: every locked app, every user-excluded app whose name was recorded,
    /// and every member of an enabled category contributes its own name. This is what makes the
    /// write barrier able to drop a queued `Frame`, which stores `appName` and no bundle id.
    public let excludedDisplayNames: Set<String>
    /// Folded name fragments that mean "password manager" whatever the identifier says.
    public let lockedNameFragments: [String]

    /// Every website pattern in force, categories included.
    ///
    /// Derived once here rather than per capture: rebuilding it on each tick meant re-normalising a
    /// few hundred hosts every three seconds, which measured at milliseconds a frame — real battery
    /// for an answer that cannot change between two reads of an immutable value.
    public let effectiveWebsites: Set<DomainPattern>
    /// Enabled app categories with their membership already folded, for the same reason.
    let categoryApps: [(category: ExclusionCategory, members: Set<String>)]

    init(
        lockedApps: Set<String> = ExclusionCatalog.lockedBundleIdentifiers,
        userApps: Set<String> = [],
        categories: Set<ExclusionCategory> = [],
        websites: Set<DomainPattern> = [],
        excludePrivateBrowsing: Bool = true,
        airgapMode: Bool = false,
        health: ExclusionHealth = .defaultsOnly,
        excludedDisplayNames: Set<String> = [],
        lockedNameFragments: [String] = ExclusionCatalog.lockedNameFragments
    ) {
        self.lockedApps = lockedApps
        self.userApps = userApps
        self.categories = categories
        self.websites = websites
        self.excludePrivateBrowsing = excludePrivateBrowsing
        self.airgapMode = airgapMode
        self.health = health
        self.excludedDisplayNames = excludedDisplayNames
        self.lockedNameFragments = lockedNameFragments

        var patterns = websites
        var apps: [(category: ExclusionCategory, members: Set<String>)] = []
        for category in categories.sorted(by: { $0.rawValue < $1.rawValue }) {
            switch category.kind {
            case .websites: patterns.formUnion(ExclusionCatalog.domains(in: category))
            case .apps:
                apps.append(
                    (category, Set(ExclusionCatalog.apps(in: category).map(\.foldedBundleID))))
            }
        }
        self.effectiveWebsites = patterns
        self.categoryApps = apps
    }

    /// Equality is over the configured inputs; the derived members are a function of them.
    public static func == (lhs: ExclusionSet, rhs: ExclusionSet) -> Bool {
        lhs.lockedApps == rhs.lockedApps && lhs.userApps == rhs.userApps
            && lhs.categories == rhs.categories && lhs.websites == rhs.websites
            && lhs.excludePrivateBrowsing == rhs.excludePrivateBrowsing
            && lhs.airgapMode == rhs.airgapMode && lhs.health == rhs.health
            && lhs.excludedDisplayNames == rhs.excludedDisplayNames
            && lhs.lockedNameFragments == rhs.lockedNameFragments
    }

    /// What a Mac with no configuration file gets: password managers and the login screen already
    /// excluded, private tabs already excluded, and nothing else.
    public static let safeDefaults = ExclusionSet(
        categories: Self.defaultCategories,
        excludePrivateBrowsing: true,
        airgapMode: false,
        health: .defaultsOnly,
        excludedDisplayNames: Self.displayNames(
            userApps: [], categories: Self.defaultCategories)
    )

    /// The categories a Mac starts with, before anything has been written down.
    static let defaultCategories = Set(ExclusionCategory.allCases.filter(\.isDefaultEnabled))

    // MARK: The decision

    /// Why this capture must not be stored, or nil if it may be.
    ///
    /// Ordered so the most specific reason wins, because the reason is what the UI shows and what
    /// the log records — a locked password manager should not be reported as "a private window".
    public func reason(for subject: CaptureSubject) -> ExclusionReason? {
        if let reason = appReason(for: subject) { return reason }
        if excludePrivateBrowsing, effectivePrivacy(of: subject) == .privateBrowsing {
            return .privateBrowsing
        }
        if let reason = websiteReason(for: subject) { return reason }
        return nil
    }

    /// The privacy of a window, using the title when the caller had no better evidence.
    public func effectivePrivacy(of subject: CaptureSubject) -> WindowPrivacy {
        guard subject.privacy == .unknown else { return subject.privacy }
        return PrivateBrowsing.classify(bundleID: subject.bundleID, title: subject.windowTitle)
    }

    public func state(ofBundleID bundleID: String) -> AppExclusionState {
        let folded = bundleID.lowercased()
        if Self.matches(folded, in: lockedApps) { return .lockedExcluded }
        if Self.matches(folded, in: userApps) { return .excluded }
        if categoryMembership(of: folded) != nil { return .excluded }
        return .included
    }

    /// Whether a favicon may be fetched at all. See ``ExclusionEngine/faviconFetch(for:)``.
    public var isFaviconFetchAllowed: Bool { !airgapMode && !health.isFailClosed }

    // MARK: Pieces of the decision

    private func appReason(for subject: CaptureSubject) -> ExclusionReason? {
        if let bundleID = subject.bundleID?.lowercased(), !bundleID.isEmpty {
            if Self.matches(bundleID, in: lockedApps) {
                return .defaultExcludedApp(bundleID: bundleID)
            }
            if Self.matches(bundleID, in: userApps) { return .userExcludedApp(bundleID: bundleID) }
            if let category = categoryMembership(of: bundleID) {
                return .categoryApp(category, bundleID: bundleID)
            }
        }

        guard let name = subject.appName?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
            !name.isEmpty
        else { return nil }

        // The widening half: a display name can only ever exclude more. It is what lets the write
        // barrier refuse a queued frame, which carries no bundle identifier.
        if lockedNameFragments.contains(where: { name.contains($0) }) {
            return .defaultExcludedApp(bundleID: name)
        }
        if excludedDisplayNames.contains(name) { return .excludedAppName(name) }
        return nil
    }

    private func categoryMembership(of foldedBundleID: String) -> ExclusionCategory? {
        for entry in categoryApps where Self.matches(foldedBundleID, in: entry.members) {
            return entry.category
        }
        return nil
    }

    /// Whether an excluded identifier covers this one: the same app, or one of its helper processes.
    ///
    /// The boundary rule is the domain rule again, and for the same reason. `com.acme.vault.helper`
    /// is the process that draws the autofill popover — a different bundle, the one actually
    /// frontmost while a secret is on screen — so excluding `com.acme.vault` has to cover it. And
    /// `com.acme.vaultx` is a different vendor's app, so a bare `hasPrefix` would exclude something
    /// the user never asked to hide. Only a prefix that ends at a `.` counts.
    static func matches(_ foldedBundleID: String, in excluded: Set<String>) -> Bool {
        if excluded.contains(foldedBundleID) { return true }
        // Allocation-free: this runs against every excluded identifier on every capture tick.
        return excluded.contains { parent in
            guard foldedBundleID.count > parent.count, foldedBundleID.hasPrefix(parent) else {
                return false
            }
            return foldedBundleID[foldedBundleID.index(
                foldedBundleID.startIndex, offsetBy: parent.count)] == "."
        }
    }

    /// Three tiers of evidence, weakest last, and the order is the whole design.
    ///
    /// 1. **The address**, when capture could read one *from the window it captured*. Authoritative:
    ///    this is the application stating which page it is showing.
    /// 2. **The window title**, browsers only. Almost never carries a host in practice (0 of 955
    ///    browser frames on this machine's database) but it costs nothing and a browser that does
    ///    put one there is stating the same fact.
    /// 3. **The window's own text**, browsers only, *and only when no host could be read at all.*
    ///
    /// The condition on the third tier is not caution, it is correctness. Page text mentions hosts
    /// constantly — a `t.co` link in a quoted tweet, a sidebar listing every other open tab, a
    /// `gmail.com` in someone's signature — and every one of those is a mention rather than a
    /// destination. Consulting it *beside* an address we already trust would mean a user who
    /// excluded one site lost frames from every unrelated page that happened to name it. Consulting
    /// it when there is no address is the opposite trade: the alternative there is capturing the
    /// bank.
    ///
    /// **What makes that exclusivity safe is that tier 1 is now provably about this window.** It was
    /// not: the address was read from whichever window the application said was focused while the
    /// pixels came from the largest one, so an address belonging to a *different* window could
    /// silence the only tier that measurably fires (133 of 955 frames, against 0 from titles) —
    /// admitting a frame of an excluded site because an unexcluded one happened to be focused.
    /// `AXWindowMatch` is what closed that, and the guard below is the rest of it: silencing is
    /// earned by a host the gate could actually match on, never by the mere presence of a string in
    /// the field. A URL that normalises to nothing — `file:///…`, a fragment, whitespace — leaves
    /// the tier beneath it exactly as loud as if the field had been empty, because that is what it
    /// means.
    private func websiteReason(for subject: CaptureSubject) -> ExclusionReason? {
        let patterns = effectiveWebsites
        guard !patterns.isEmpty else { return nil }

        // Normalised once, then compared against every pattern: the reverse order re-parsed the same
        // host a few hundred times per frame.
        let host = subject.url.flatMap(DomainMatcher.normalize)
        if let host, let pattern = patterns.first(where: { $0.matches(normalizedHost: host) }) {
            return .excludedWebsite(pattern: pattern.host)
        }
        // Browsers only, so a document named after a domain in an editor does not cost its frame.
        guard isBrowser(subject) else { return nil }
        if let title = subject.windowTitle,
            let reason = firstExcluded(in: title, patterns: patterns, limit: 12)
        {
            return reason
        }
        guard host == nil, let pageText = subject.pageText else { return nil }
        return firstExcluded(in: pageText, patterns: patterns, limit: Self.pageTextHostLimit)
    }

    /// The first excluded host named anywhere in `text`, or nil.
    private func firstExcluded(
        in text: String, patterns: Set<DomainPattern>, limit: Int
    ) -> ExclusionReason? {
        for host in DomainMatcher.hostCandidates(in: text, limit: limit) {
            if let pattern = patterns.first(where: { $0.matches(normalizedHost: host) }) {
                return .excludedWebsite(pattern: pattern.host)
            }
        }
        return nil
    }

    /// How many distinct hosts are read out of a window's text before the search gives up.
    ///
    /// A ceiling rather than "all of them" because the text is bounded at thousands of characters
    /// and a page of links would otherwise allocate a host per link on every frame. Well above the
    /// title's twelve, because unlike a title this text is long and the excluded host is not
    /// necessarily near its front — an under-count here is a frame that should have been refused.
    private static let pageTextHostLimit = 64

    /// Whether this subject is a browser, by bundle id when there is one and by name otherwise.
    private func isBrowser(_ subject: CaptureSubject) -> Bool {
        PrivateBrowsing.isBrowser(bundleID: subject.bundleID, appName: subject.appName)
    }

    // MARK: Construction

    /// Builds the set the engine serves from a stored configuration plus its health.
    ///
    /// Health decides which categories are in force, and that is the whole fail-closed rule in one
    /// expression rather than at each read site:
    ///
    /// - **No configuration at all** — a fresh install and every installation that exists today —
    ///   gets ``defaultCategories``. Reading the empty configuration literally would leave Password
    ///   Managers unticked on a Mac nobody had asked anything, which is precisely the default-drift
    ///   this file exists to prevent.
    /// - **A configuration this build understands** is obeyed exactly, including an empty list: the
    ///   user is allowed to untick a category, and their choice is not a missing value.
    /// - **A configuration that cannot be trusted** gets every category, private browsing excluded,
    ///   and no network. Whatever *was* decoded is kept as well — a newer build's file still knows
    ///   which apps the user excluded, and forgetting them is the one direction this must never move
    ///   in.
    static func make(configuration: ExclusionConfiguration, health: ExclusionHealth) -> ExclusionSet {
        let failing = health.isFailClosed
        let categories: Set<ExclusionCategory>
        switch health {
        case .failedClosed: categories = Set(ExclusionCategory.allCases)
        case .defaultsOnly: categories = defaultCategories
        case .configured, .notPersisted: categories = configuration.categories
        }

        return ExclusionSet(
            userApps: Set(configuration.excludedApps.map(\.foldedBundleID)),
            categories: categories,
            websites: Set(configuration.excludedDomains.compactMap(DomainPattern.init)),
            excludePrivateBrowsing: failing || configuration.excludePrivateBrowsing,
            airgapMode: failing || configuration.airgapMode,
            health: health,
            excludedDisplayNames: displayNames(
                userApps: configuration.excludedApps, categories: categories))
    }

    /// Every display name the set must also refuse. See ``excludedDisplayNames``.
    static func displayNames(
        userApps: [ExcludableApp], categories: Set<ExclusionCategory>
    ) -> Set<String> {
        var names = Set(ExclusionCatalog.lockedApps.map(\.foldedDisplayName))
        names.formUnion(userApps.map(\.foldedDisplayName))
        for category in categories where category.kind == .apps {
            names.formUnion(ExclusionCatalog.apps(in: category).map(\.foldedDisplayName))
        }
        names.remove("")
        return names
    }
}

// MARK: - On-disk configuration

/// The user's choices, and only the user's choices.
///
/// The default-excluded set is deliberately absent from this file: what is not written down cannot
/// be edited out, so no hand-edit, migration bug, or truncated write can produce a configuration in
/// which password managers are capturable.
struct ExclusionConfiguration: Codable, Equatable, Sendable {
    static let currentVersion = 1

    var version: Int = currentVersion
    /// Bundle identifiers, with the display name the UI showed, so an app that has since been
    /// uninstalled still renders as a row the user can remove.
    var excludedApps: [ExcludableApp] = []
    var excludedCategories: [String] = []
    var excludedDomains: [String] = []
    var excludePrivateBrowsing: Bool = true
    var airgapMode: Bool = false

    static let empty = ExclusionConfiguration()

    /// Category names this build understands. Unknown strings stay in ``excludedCategories`` and are
    /// written back out untouched: a file written by a newer build must not lose the user's choice
    /// just because an older build round-tripped it.
    var categories: Set<ExclusionCategory> {
        Set(excludedCategories.compactMap(ExclusionCategory.init(rawValue:)))
    }

    mutating func setCategory(_ category: ExclusionCategory, excluded: Bool) {
        excludedCategories.removeAll { $0 == category.rawValue }
        if excluded { excludedCategories.append(category.rawValue) }
    }

    /// Decoding is tolerant of missing keys and strict about wrong types.
    ///
    /// Tolerant, because a field added in a later version must not invalidate a whole file. Strict,
    /// because a key that is present and unreadable means this file is not what it claims to be —
    /// and the caller turns that into ``ExclusionHealth/failedClosed(_:)`` rather than into a
    /// half-applied set of exclusions.
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        version = try container.decodeIfPresent(Int.self, forKey: .version) ?? Self.currentVersion
        excludedApps = try container.decodeIfPresent([ExcludableApp].self, forKey: .excludedApps) ?? []
        excludedCategories =
            try container.decodeIfPresent([String].self, forKey: .excludedCategories) ?? []
        excludedDomains = try container.decodeIfPresent([String].self, forKey: .excludedDomains) ?? []
        excludePrivateBrowsing =
            try container.decodeIfPresent(Bool.self, forKey: .excludePrivateBrowsing) ?? true
        airgapMode = try container.decodeIfPresent(Bool.self, forKey: .airgapMode) ?? false
    }

    init() {}
}

// MARK: - The engine

/// The live exclusion state: one trusted copy, readable from any thread, writable from Settings.
///
/// Three requirements shape this class, and all three are the reason it is not just a `struct` the
/// UI owns:
///
/// - **Default-excluded before any user action.** Construction never depends on a file existing.
///   A `ContextForClaude` install with an empty support directory already refuses password managers
///   and the login screen.
/// - **Immediate effect, including in-flight work.** A mutation lands in memory first and is
///   persisted afterwards, so an exclusion is in force before the write to disk is attempted and
///   whether or not it succeeds. Captures carry a ``CaptureTicket`` stamped with the generation that
///   admitted them, and ``revalidate(_:pageText:)`` re-judges anything stamped under an older one — which is
///   how a frame captured before the click and written after it is still dropped.
/// - **Fail closed.** A configuration that cannot be read or parsed produces *more* exclusions than
///   the file asked for, never fewer, and says so through ``health``.
public final class ExclusionEngine: @unchecked Sendable {

    /// The process-wide engine. Capture, the write barrier and Settings must all read one state —
    /// two copies is how "the user unticked it and it kept recording" happens.
    public static let shared = ExclusionEngine()

    public static var defaultConfigurationURL: URL {
        ContextPaths.supportDirectory.appendingPathComponent("exclusions.json")
    }

    private static let log = Logger(subsystem: ContextPaths.bundleIdentifier, category: "exclusions")

    private let configurationURL: URL
    private let framesRoot: URL
    private let lock = NSLock()

    private var configuration: ExclusionConfiguration
    private var state: ExclusionSet
    private var generationCounter: UInt64 = 1
    private var observers: [UUID: @Sendable (ExclusionSet) -> Void] = [:]
    /// True once the unreadable file has been copied aside, so a repeated save does not overwrite
    /// the copy with the replacement it already made.
    private var hasPreservedUnreadableFile = false

    public init(
        configurationURL: URL = ExclusionEngine.defaultConfigurationURL,
        framesRoot: URL = ContextPaths.framesDirectory
    ) {
        self.configurationURL = configurationURL
        self.framesRoot = framesRoot
        let loaded = Self.load(from: configurationURL)
        self.configuration = loaded.configuration
        self.state = ExclusionSet.make(configuration: loaded.configuration, health: loaded.health)
        if case .failedClosed(let cause) = loaded.health {
            Self.log.error("Exclusions failed closed: \(String(describing: cause), privacy: .public)")
        }
    }

    // MARK: Reading

    public var current: ExclusionSet {
        lock.lock()
        defer { lock.unlock() }
        return state
    }

    /// Bumped by every change. A capture admitted at generation *n* needs no second thought while
    /// the engine is still at *n*.
    public var generation: UInt64 {
        lock.lock()
        defer { lock.unlock() }
        return generationCounter
    }

    public var health: ExclusionHealth {
        lock.lock()
        defer { lock.unlock() }
        return state.health
    }

    public func state(ofBundleID bundleID: String) -> AppExclusionState {
        current.state(ofBundleID: bundleID)
    }

    public func isLocked(bundleID: String) -> Bool {
        ExclusionSet.matches(bundleID.lowercased(), in: ExclusionCatalog.lockedBundleIdentifiers)
    }

    // MARK: Enforcement

    /// The gate. Nil means this capture may proceed; a reason means it must not happen at all.
    ///
    /// Composed in ``CapturePolicy/exclusion(for:using:)`` together with the credential-surface
    /// rules in ``Redaction``, so there is one decision path rather than a user-facing filter beside
    /// a hard-coded one.
    public func exclusionReason(for subject: CaptureSubject) -> ExclusionReason? {
        CapturePolicy.exclusion(for: subject, using: current)
    }

    /// Admits a capture, handing back the ticket that has to travel with it to the write.
    ///
    /// A ticket cannot be constructed anywhere else, which is what makes "every queued frame was
    /// vetted, and knows when" a property of the type rather than a convention.
    public func admit(_ subject: CaptureSubject) -> CaptureAdmission {
        lock.lock()
        let set = state
        let generation = generationCounter
        lock.unlock()

        if let reason = CapturePolicy.exclusion(for: subject, using: set) {
            return .refused(reason)
        }
        return .admitted(CaptureTicket(subject: subject, generation: generation))
    }

    /// Re-judges a capture that was admitted earlier and has not been written yet.
    ///
    /// This is the in-flight half of "an exclusion takes effect immediately". Nil means the capture
    /// may still be written; a reason means it must be dropped, along with anything already on disk
    /// for it (see ``discard(_:reason:)``).
    ///
    /// Cheap in the common case: if nothing has changed since the ticket was issued *and* the
    /// capture learned nothing new about itself, the earlier verdict still stands and no matching is
    /// redone.
    ///
    /// `pageText` is the second half of that, and it is why this is not just a generation check. A
    /// window's accessibility text is read after admission, beside OCR — so evidence about which
    /// site the frame was showing arrives *after* the only decision that ever looked at it. An
    /// unchanged configuration is not a reason to skip judging something the gate has never seen, so
    /// new evidence re-opens the verdict even at the same generation.
    public func revalidate(_ ticket: CaptureTicket, pageText: String? = nil) -> ExclusionReason? {
        lock.lock()
        let set = state
        let generation = generationCounter
        lock.unlock()

        var subject = ticket.subject
        // Only ever *adds*. A ticket's own evidence is what admitted it and cannot be weakened here.
        let grew = subject.pageText == nil && pageText?.isEmpty == false
        if grew { subject.pageText = pageText }

        let stale = ticket.generation != generation
        guard stale || grew else { return nil }
        if let reason = CapturePolicy.exclusion(for: subject, using: set) { return reason }
        // The configuration stopped being trustworthy after this capture was admitted, so what the
        // user actually excluded is now unknown. Dropping one frame is recoverable; writing a frame
        // they excluded is not. Gated on the generation because a capture admitted *while* already
        // fail-closed was judged under exactly this state — refusing it here would refuse
        // everything, for as long as the file stays unreadable.
        if stale, set.health.isFailClosed { return .configurationUnavailable }
        return nil
    }

    /// The barrier for a caller that no longer has a ticket — a `Frame` on its way to the database
    /// carries `appName` and `windowTitle` and nothing else.
    ///
    /// Weaker than ``revalidate(_:pageText:)`` by construction: with no bundle identifier and no URL it can
    /// only match on display name and on hosts named in the title. Prefer the ticket; this exists so
    /// that a caller which lost one still refuses password managers rather than writing them.
    public func shouldDropQueuedFrame(
        appName: String?, windowTitle: String?, url: String? = nil
    ) -> ExclusionReason? {
        let subject = CaptureSubject(appName: appName, windowTitle: windowTitle, url: url)
        return CapturePolicy.exclusion(for: subject, using: current)
    }

    /// Drops a capture that has become excluded, including anything already written for it.
    ///
    /// The image matters whenever a caller reaches here with one: pruning walks the `frames` table,
    /// so a frame dropped at the barrier without this would leave a screenshot of an excluded window
    /// on disk that nothing will ever delete. The screen watcher no longer arrives with one — it
    /// judges before it writes, so an excluded window's bytes are never produced rather than
    /// produced and unlinked, which are different things to anyone holding a backup or a snapshot of
    /// that second. This stays the barrier for any caller that does have bytes on disk, and the log
    /// line for every caller.
    ///
    /// Only ever unlinks inside the frames directory. A refusal is not a licence to delete a path
    /// that arrived from somewhere unexpected.
    public func discard(_ frame: Frame, reason: ExclusionReason) {
        Self.log.info("Dropping queued frame: \(reason.logDescription, privacy: .public)")
        guard let path = frame.imagePath, !path.isEmpty else { return }
        let url = URL(fileURLWithPath: path).standardizedFileURL
        let root = framesRoot.standardizedFileURL
        guard url.path.hasPrefix(root.path + "/") else {
            Self.log.error("Refusing to unlink a frame image outside the frames directory")
            return
        }
        do {
            try FileManager.default.removeItem(at: url)
        } catch CocoaError.fileNoSuchFile {
            // Already gone. Nothing to report: the desired state is exactly this.
        } catch {
            Self.log.error(
                "Could not unlink an excluded frame image: \(error.localizedDescription, privacy: .public)")
        }
    }

    // MARK: Favicons, and the promise Airgap Mode makes

    /// Where the UI may fetch a favicon from, or why it may not.
    ///
    /// Airgap Mode promises to suppress "remote favicon requests", and a UI that hides an image it
    /// already downloaded has not kept that promise — the request is the disclosure. So the decision
    /// is made here, and the URL is *handed out* rather than assembled by the caller: there is no
    /// shape of this API in which a third-party favicon service can be used, because a service would
    /// tell someone else every domain the user chose to hide.
    public func faviconFetch(for host: String) -> FaviconFetch {
        let set = current
        if set.health.isFailClosed { return .suppressed(.configurationUnavailable) }
        if set.airgapMode { return .suppressed(.airgapMode) }
        guard let normalized = DomainMatcher.normalize(host),
            let url = URL(string: "https://\(normalized)/favicon.ico")
        else { return .suppressed(.notAHost) }
        return .allowed(url)
    }

    public var isFaviconFetchAllowed: Bool { current.isFaviconFetchAllowed }

    // MARK: Writing

    /// Excludes or un-excludes one app by bundle identifier.
    ///
    /// Refuses to un-exclude a locked default. That refusal is the point of the locked set: the
    /// reference shows Keychain Access and Passwords with checkboxes the user cannot clear, and a
    /// core that quietly honoured the click would make the UI a lie.
    @discardableResult
    public func setExcluded(
        _ excluded: Bool, bundleID: String, displayName: String? = nil
    ) -> ExclusionMutation {
        let trimmed = bundleID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return .rejected }
        if isLocked(bundleID: trimmed) {
            return excluded ? .unchanged : .refusedLocked
        }

        return mutate { configuration in
            let folded = trimmed.lowercased()
            let existing = configuration.excludedApps.first { $0.foldedBundleID == folded }
            if excluded {
                let name = displayName ?? existing?.displayName ?? trimmed
                guard existing == nil || existing?.displayName != name else { return false }
                configuration.excludedApps.removeAll { $0.foldedBundleID == folded }
                configuration.excludedApps.append(
                    ExcludableApp(bundleID: trimmed, displayName: name))
                return true
            }
            guard existing != nil else { return false }
            configuration.excludedApps.removeAll { $0.foldedBundleID == folded }
            return true
        }
    }

    @discardableResult
    public func setCategory(_ category: ExclusionCategory, excluded: Bool) -> ExclusionMutation {
        mutate { configuration in
            guard configuration.categories.contains(category) != excluded else { return false }
            configuration.setCategory(category, excluded: excluded)
            return true
        }
    }

    /// Adds a website exclusion. Returns the normalised pattern, or nil when nothing host-shaped
    /// was typed — the UI needs to tell those apart to keep a bad entry visible in the field.
    @discardableResult
    public func excludeWebsite(_ raw: String) -> DomainPattern? {
        guard let pattern = DomainPattern(raw) else { return nil }
        mutate { configuration in
            guard !configuration.excludedDomains.contains(pattern.host) else { return false }
            configuration.excludedDomains.append(pattern.host)
            return true
        }
        return pattern
    }

    @discardableResult
    public func allowWebsite(_ pattern: DomainPattern) -> ExclusionMutation {
        mutate { configuration in
            let before = configuration.excludedDomains.count
            configuration.excludedDomains.removeAll { DomainPattern($0) == pattern }
            return configuration.excludedDomains.count != before
        }
    }

    @discardableResult
    public func setExcludePrivateBrowsing(_ excluded: Bool) -> ExclusionMutation {
        mutate { configuration in
            guard configuration.excludePrivateBrowsing != excluded else { return false }
            configuration.excludePrivateBrowsing = excluded
            return true
        }
    }

    /// Airgap Mode, as far as this engine is concerned: no favicon requests.
    ///
    /// Telemetry and update checks are other people's switches; they read the same flag from here so
    /// there is one answer to "are we allowed to touch the network".
    @discardableResult
    public func setAirgapMode(_ enabled: Bool) -> ExclusionMutation {
        mutate { configuration in
            guard configuration.airgapMode != enabled else { return false }
            configuration.airgapMode = enabled
            return true
        }
    }

    /// Re-reads the configuration from disk. For an external edit, or a second process.
    public func reload() {
        let loaded = Self.load(from: configurationURL)
        let set = ExclusionSet.make(configuration: loaded.configuration, health: loaded.health)
        lock.lock()
        configuration = loaded.configuration
        state = set
        generationCounter += 1
        let handlers = Array(observers.values)
        lock.unlock()
        for handler in handlers { handler(set) }
    }

    // MARK: Observation

    /// Live state for the Settings UI. Called on the thread that made the change.
    @discardableResult
    public func addObserver(_ handler: @escaping @Sendable (ExclusionSet) -> Void) -> UUID {
        let id = UUID()
        lock.lock()
        observers[id] = handler
        let set = state
        lock.unlock()
        handler(set)
        return id
    }

    public func removeObserver(_ id: UUID) {
        lock.lock()
        observers[id] = nil
        lock.unlock()
    }

    // MARK: The one mutation path

    /// Applies a change in memory, then tries to persist it — in that order, and never the reverse.
    ///
    /// The order is the requirement: an exclusion has to be in force the instant the user asks for
    /// it, so a slow or failing disk cannot leave capture running on a window they just hid. A write
    /// failure is recorded in ``ExclusionHealth/notPersisted(_:)`` and surfaced, because the user is
    /// owed the truth that it will not survive a relaunch — but it is not a reason to undo it.
    @discardableResult
    private func mutate(_ change: (inout ExclusionConfiguration) -> Bool) -> ExclusionMutation {
        lock.lock()
        var updated = configuration

        // Whatever the current health implies but the file does not yet say is written down first,
        // *before* the caller's change, so the change can still override it. Both cases are the same
        // bug if skipped: the first Settings click would persist a configuration that silently drops
        // an exclusion which had been in force a moment earlier — the default categories on a fresh
        // install, or the extra ones a corrupt file had us apply.
        switch state.health {
        case .defaultsOnly:
            for category in ExclusionSet.defaultCategories {
                updated.setCategory(category, excluded: true)
            }
        case .failedClosed:
            for category in ExclusionCategory.allCases {
                updated.setCategory(category, excluded: true)
            }
            updated.excludePrivateBrowsing = true
            updated.version = ExclusionConfiguration.currentVersion
        case .configured, .notPersisted:
            break
        }

        guard change(&updated) else {
            lock.unlock()
            return .unchanged
        }

        configuration = updated
        generationCounter += 1
        let health = persistLocked(updated)
        state = ExclusionSet.make(configuration: updated, health: health)
        let set = state
        let handlers = Array(observers.values)
        lock.unlock()

        for handler in handlers { handler(set) }
        return .applied
    }

    /// Writes the configuration. Must be called with the lock held.
    private func persistLocked(_ configuration: ExclusionConfiguration) -> ExclusionHealth {
        preserveUnreadableFileLocked()
        do {
            let directory = configurationURL.deletingLastPathComponent()
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            try encoder.encode(configuration).write(to: configurationURL, options: .atomic)
            return .configured
        } catch {
            Self.log.error("Could not save exclusions: \(error.localizedDescription, privacy: .public)")
            return .notPersisted(error.localizedDescription)
        }
    }

    /// Copies a configuration we could not trust aside before replacing it.
    ///
    /// Overwriting it would destroy the only record of exclusions the user really chose — a file that
    /// is unreadable to *this* build is not the same as a meaningless one, and a file from a newer
    /// build says more than this one is about to write back.
    private func preserveUnreadableFileLocked() {
        guard state.health.isFailClosed, !hasPreservedUnreadableFile else { return }
        hasPreservedUnreadableFile = true
        let backup = configurationURL.appendingPathExtension("unreadable")
        try? FileManager.default.removeItem(at: backup)
        do {
            try FileManager.default.copyItem(at: configurationURL, to: backup)
            Self.log.error(
                "Kept the unreadable exclusion configuration at \(backup.lastPathComponent, privacy: .public)")
        } catch {
            // Nothing to preserve, or nowhere to put it. The in-memory state is already fail-closed.
        }
    }

    // MARK: Loading

    private static func load(
        from url: URL
    ) -> (configuration: ExclusionConfiguration, health: ExclusionHealth) {
        // The legacy principal, and the only one that matters on day one: no file at all. Every
        // installation that exists today is this case, and it must get the safe defaults rather than
        // an empty allow-everything set.
        guard FileManager.default.fileExists(atPath: url.path) else {
            return (.empty, .defaultsOnly)
        }

        let data: Data
        do {
            data = try Data(contentsOf: url)
        } catch {
            return (.empty, .failedClosed(.unreadable(error.localizedDescription)))
        }

        do {
            let configuration = try JSONDecoder().decode(ExclusionConfiguration.self, from: data)
            guard configuration.version <= ExclusionConfiguration.currentVersion else {
                // Keep what was decoded: a newer file still tells us which apps and domains the user
                // excluded, and forgetting those would be the one direction this must not move in.
                return (configuration, .failedClosed(.writtenByNewerVersion(configuration.version)))
            }
            return (configuration, .configured)
        } catch {
            return (.empty, .failedClosed(.malformed(String(describing: error))))
        }
    }
}

// MARK: - Engine value types

/// The outcome of a Settings change.
public enum ExclusionMutation: Sendable, Equatable {
    case applied
    /// The state already said this.
    case unchanged
    /// A default exclusion the user is not allowed to lift.
    case refusedLocked
    /// Nothing usable was passed — an empty bundle identifier.
    case rejected
}

/// Proof that a capture passed the gate, and when.
///
/// Only ``ExclusionEngine/admit(_:)`` can make one. That is deliberate: it means a queued capture
/// cannot exist without having been judged, and the barrier before the write always knows which
/// version of the rules judged it.
public struct CaptureTicket: Sendable, Equatable {
    public let subject: CaptureSubject
    let generation: UInt64

    init(subject: CaptureSubject, generation: UInt64) {
        self.subject = subject
        self.generation = generation
    }
}

public enum CaptureAdmission: Sendable, Equatable {
    case admitted(CaptureTicket)
    case refused(ExclusionReason)

    public var ticket: CaptureTicket? {
        if case .admitted(let ticket) = self { return ticket }
        return nil
    }

    public var reason: ExclusionReason? {
        if case .refused(let reason) = self { return reason }
        return nil
    }
}

public enum FaviconSuppression: Sendable, Equatable {
    case airgapMode
    case configurationUnavailable
    case notAHost
}

public enum FaviconFetch: Sendable, Equatable {
    /// Fetch exactly this URL — the domain's own, never a third party's.
    case allowed(URL)
    case suppressed(FaviconSuppression)

    public var url: URL? {
        if case .allowed(let url) = self { return url }
        return nil
    }
}

// MARK: - What the Settings UI renders

/// Everything the Exclusions pane draws, derived in one place so the UI cannot invent a state the
/// engine does not have — in particular the locked rows, which must render as excluded and
/// unclearable.
public struct ExclusionSnapshot: Sendable, Equatable {

    public struct AppRow: Sendable, Equatable, Identifiable {
        public let app: ExcludableApp
        public let state: AppExclusionState
        public var id: String { app.bundleID }
        public var isLocked: Bool { state == .lockedExcluded }
    }

    public struct CategoryRow: Sendable, Equatable, Identifiable {
        public let category: ExclusionCategory
        public let isExcluded: Bool
        public let apps: [AppRow]
        public let domains: [DomainPattern]
        public var id: String { category.rawValue }
        public var title: String { category.title }
        public var subtitle: String { category.subtitle }
    }

    public struct WebsiteRow: Sendable, Equatable, Identifiable {
        public let pattern: DomainPattern
        /// True when a category contributes it, so the row is not individually removable.
        public let fromCategory: ExclusionCategory?
        public var id: String { pattern.host }
        public var isLocked: Bool { fromCategory != nil }
    }

    public var appCategories: [CategoryRow]
    public var websiteCategories: [CategoryRow]
    /// The reference's **Excluded** group: locked defaults first, then the user's own.
    public var excludedApps: [AppRow]
    /// The reference's **System** group.
    public var systemSurfaces: [AppRow]
    public var websites: [WebsiteRow]
    public var excludePrivateBrowsing: Bool
    public var airgapMode: Bool
    public var isFaviconFetchAllowed: Bool
    public var health: ExclusionHealth
}

extension ExclusionEngine {

    /// One consistent read for the whole pane. Taken from a single snapshot of the state, so no two
    /// rows can disagree about what is excluded.
    public func snapshot() -> ExclusionSnapshot {
        lock.lock()
        let set = state
        let configured = configuration.excludedApps
        lock.unlock()

        func row(_ app: ExcludableApp) -> ExclusionSnapshot.AppRow {
            ExclusionSnapshot.AppRow(app: app, state: set.state(ofBundleID: app.bundleID))
        }

        let categories = ExclusionCategory.allCases.map { category in
            ExclusionSnapshot.CategoryRow(
                category: category,
                isExcluded: set.categories.contains(category),
                apps: ExclusionCatalog.apps(in: category).map(row),
                domains: ExclusionCatalog.domains(in: category).sorted())
        }

        let locked = ExclusionCatalog.lockedApps.map(row)
        let user = configured.filter { !isLocked(bundleID: $0.bundleID) }.map(row)

        var websites = set.websites.sorted().map {
            ExclusionSnapshot.WebsiteRow(pattern: $0, fromCategory: nil)
        }
        for category in set.categories where category.kind == .websites {
            websites += ExclusionCatalog.domains(in: category).sorted().map {
                ExclusionSnapshot.WebsiteRow(pattern: $0, fromCategory: category)
            }
        }

        return ExclusionSnapshot(
            appCategories: categories.filter { $0.category.kind == .apps },
            websiteCategories: categories.filter { $0.category.kind == .websites },
            excludedApps: locked + user,
            systemSurfaces: ExclusionCatalog.loginSurfaces.map(row)
                + ExclusionCatalog.optionalSystemSurfaces.map(row),
            websites: websites,
            excludePrivateBrowsing: set.excludePrivateBrowsing,
            airgapMode: set.airgapMode,
            isFaviconFetchAllowed: set.isFaviconFetchAllowed,
            health: set.health)
    }

    /// The apps the user excluded by hand, with the display names they were shown under.
    public func configuredApps() -> [ExcludableApp] {
        lock.lock()
        defer { lock.unlock() }
        return configuration.excludedApps
    }
}
