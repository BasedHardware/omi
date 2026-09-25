import AppKit
import ContextCore
import SwiftUI

/// The metrics every pane shares, so six panes cannot drift into six layouts.
enum SettingsMetrics {
    static let sidebarWidth: CGFloat = 196

    /// **The same rectangle the timeline opens at, and that is the point.**
    ///
    /// Settings opened at 756 × 640 while the timeline opened at 1180 × 760, so the two windows this
    /// app puts on screen were visibly different objects — reported as *"for setting, have the window
    /// size same as timeline and all, this looks off"*. They already share their chrome
    /// (`WindowGlass.wear(_:as: .titled)`), their ground and their corner radius; the size was the
    /// one thing left saying otherwise. Read from `RewindWindow` rather than restated, so the two
    /// cannot drift apart again — which is exactly how they drifted the first time.
    static var windowSize: NSSize { RewindWindow.defaultSize }
    static var minimumSize: NSSize { RewindWindow.minimumSize }

    static let paneHorizontalPadding: CGFloat = 22
    static let paneTopPadding: CGFloat = 18
    static let sectionSpacing: CGFloat = 22
    static let rowSpacing: CGFloat = 2
    static let rowVerticalPadding: CGFloat = 9
    static let iconTile: CGFloat = 26
    static let cardRadius: CGFloat = 10
}

// MARK: - The one row shape

/// A rounded icon tile, a title, a smaller grey subtitle, and a control on the right.
///
/// `docs/rewind-and-settings.md` § Part 2 states this as the single row pattern for all six panes, so
/// it exists once. Everything a pane needs to vary — the control, an optional keyboard hint before it,
/// whether the whole row is pressable — is a parameter rather than a second row type.
struct SettingsRow<Control: View>: View {
    let icon: String
    let title: String
    var subtitle: String?
    /// A chord printed just before the control, e.g. `↵` or `⌘ ⇧ + / −`.
    var shortcutHint: String?
    var isEnabled: Bool = true
    @ViewBuilder var control: () -> Control

    var body: some View {
        HStack(alignment: .center, spacing: 11) {
            SettingsIconTile(symbol: icon)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(Ink.primary)
                if let subtitle, !subtitle.isEmpty {
                    Text(subtitle)
                        .font(.system(size: 11))
                        .foregroundStyle(Ink.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            if let shortcutHint {
                SettingsKeyHint(text: shortcutHint)
            }
            control()
        }
        .padding(.vertical, SettingsMetrics.rowVerticalPadding)
        .padding(.horizontal, 12)
        .opacity(isEnabled ? 1 : 0.55)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

extension SettingsRow where Control == EmptyView {
    init(
        icon: String, title: String, subtitle: String? = nil, shortcutHint: String? = nil,
        isEnabled: Bool = true
    ) {
        self.init(
            icon: icon, title: title, subtitle: subtitle, shortcutHint: shortcutHint,
            isEnabled: isEnabled, control: { EmptyView() })
    }
}

struct SettingsIconTile: View {
    let symbol: String
    var tint: Color = Ink.primary

    var body: some View {
        RoundedRectangle(cornerRadius: 7, style: .continuous)
            .fill(Ink.rowFill)
            .overlay(
                RoundedRectangle(cornerRadius: 7, style: .continuous)
                    .strokeBorder(Ink.separator, lineWidth: 1)
            )
            .overlay(
                Image(systemName: symbol)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(tint)
            )
            .frame(width: SettingsMetrics.iconTile, height: SettingsMetrics.iconTile)
    }
}

/// A printed chord: monospaced, in a faint capsule, never a control.
struct SettingsKeyHint: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.system(size: 10, weight: .semibold, design: .monospaced))
            .foregroundStyle(Ink.secondary)
            .padding(.horizontal, 5)
            .padding(.vertical, 2)
            .background(
                RoundedRectangle(cornerRadius: 4, style: .continuous).fill(Ink.wash)
            )
            .fixedSize()
            .accessibilityLabel(Text("Keyboard shortcut \(text)"))
    }
}

// MARK: - Grouping

/// A titled group of rows on a card, with hairlines between them — the shape a macOS settings pane
/// uses, and the reason the rows themselves draw no background of their own.
struct SettingsSection<Content: View>: View {
    var title: String?
    var footnote: String?
    @ViewBuilder var content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let title {
                Text(title)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Ink.secondary)
                    .textCase(nil)
                    .padding(.horizontal, 4)
            }
            VStack(spacing: 0) { content() }
                .background(
                    RoundedRectangle(cornerRadius: SettingsMetrics.cardRadius, style: .continuous)
                        .fill(Ink.rowFill)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: SettingsMetrics.cardRadius, style: .continuous)
                        .strokeBorder(Ink.separator, lineWidth: 1))
            if let footnote {
                Text(footnote)
                    .font(.system(size: 11))
                    .foregroundStyle(Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 4)
                    .padding(.top, 2)
            }
        }
    }
}

/// The hairline between two rows in a section. Inset so it does not run under the icon tile.
struct SettingsRowDivider: View {
    var body: some View {
        Divider().padding(.leading, 12 + SettingsMetrics.iconTile + 11)
    }
}

/// Lays out rows with dividers between them and none at the ends.
struct SettingsRowStack<Item: Identifiable, RowContent: View>: View {
    let items: [Item]
    @ViewBuilder var row: (Item) -> RowContent

    var body: some View {
        ForEach(Array(items.enumerated()), id: \.element.id) { index, item in
            if index > 0 { SettingsRowDivider() }
            row(item)
        }
    }
}

// MARK: - Controls

/// The switch on the right of a `SettingsRow`, and the **only** switch shape these panes have.
///
/// It exists because of what every one of them used to be: `Toggle("", isOn:)` followed by
/// `.labelsHidden()`. That hides the visual label — which is right, the row's own title is the label
/// a sighted user reads — but the string it hides is also the *accessibility* label, and it was
/// empty. So VoiceOver announced eleven switches across five panes as an unnamed "on"/"off": Launch
/// on Login, Airgap Mode, Sound, Show Dock Icon, the four Timeline controls, Screen Capture, Pause on
/// Inactivity, Exclude Private Tabs and Claude Connection were, to a user not looking at the screen,
/// indistinguishable from each other. Turning off the wrong one of those is turning off capture, or
/// turning off Airgap.
///
/// `Toggle(title, isOn:).labelsHidden()` is the one-word idiom that fixes it, and this type is what
/// makes it unskippable: the pane cannot spell a switch without a title, because there is no
/// initialiser that takes none. `product/invariants` asks for compiler-first boundaries before
/// source scrapes, and this is one — the empty label is no longer expressible.
struct SettingsToggle: View {
    /// The row's own title, verbatim. Two names for one control is worse than one.
    let title: String
    @Binding var isOn: Bool
    /// Run before the write, for the click. A closure rather than an `onChange`, because the sound
    /// is feedback for the press and not for the value settling.
    var onChange: (Bool) -> Void = { _ in }

    var body: some View {
        Toggle(
            title,
            isOn: Binding(
                get: { isOn },
                set: { value in
                    onChange(value)
                    isOn = value
                })
        )
        // Hides the text, keeps the accessibility label. That is the whole distinction this type
        // exists to hold on to.
        .labelsHidden()
        .toggleStyle(.switch)
        .controlSize(.small)
    }
}

/// The four Capture Quality tiles, and the three Appearance tiles: one selectable tile shape, ringed
/// in the accent when chosen.
struct SettingsTile<Content: View>: View {
    let isSelected: Bool
    let action: () -> Void
    @ViewBuilder var content: () -> Content

    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            content()
                .frame(maxWidth: .infinity)
                .padding(.vertical, 8)
                .background(
                    RoundedRectangle(cornerRadius: 9, style: .continuous)
                        .fill(isHovering ? Ink.rowFillHover : Ink.wash)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 9, style: .continuous)
                        .strokeBorder(
                            isSelected ? Ink.accent : Ink.separator,
                            lineWidth: isSelected ? 2 : 1))
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .accessibilityAddTraits(isSelected ? [.isSelected, .isButton] : .isButton)
    }
}

/// One option in a radio group: a filled ring, an icon tile, copy, and nothing else clickable.
struct SettingsRadioRow: View {
    let symbol: String
    let title: String
    let subtitle: String
    let isSelected: Bool
    var isDestructive: Bool = false
    let action: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 11) {
                Image(systemName: isSelected ? "largecircle.fill.circle" : "circle")
                    .font(.system(size: 14))
                    .foregroundStyle(isSelected ? Ink.accent : Ink.secondary)
                SettingsIconTile(symbol: symbol, tint: isDestructive ? Ink.errorRed : Ink.primary)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(Ink.primary)
                    Text(subtitle)
                        .font(.system(size: 11))
                        .foregroundStyle(Ink.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(.vertical, SettingsMetrics.rowVerticalPadding)
            .padding(.horizontal, 12)
            .background(isHovering ? Ink.rowFillHover : Color.clear)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .accessibilityAddTraits(isSelected ? [.isSelected, .isButton] : .isButton)
    }
}

/// A checkbox row for the Exclusions lists: an icon or favicon, a name, and a box that is disabled
/// (and shown checked) for a locked default.
///
/// **The disclosure chevron is drawn by supplying its action, never by a flag.** It used to be
/// `disclosure: Bool`, and a `true` painted a chevron this view had no handler for — the row body had
/// a `.contentShape` and no gesture, so the only thing that expanded a category was a separate button
/// wrapped around the icon tile by the caller. The affordance and the behaviour were in different
/// files and only one of them was where the user aimed. Making the action the thing that draws it puts
/// that beyond a future caller's reach: there is no longer a way to spell "chevron, no handler".
struct SettingsCheckRow<Leading: View>: View {
    let title: String
    var subtitle: String?
    let isChecked: Bool
    let isEnabled: Bool
    /// Non-nil for a row that discloses members. Runs when the labels or the chevron are clicked.
    var onDisclosure: (() -> Void)?
    var isExpanded: Bool = false
    let toggle: () -> Void
    @ViewBuilder var leading: () -> Leading

    @State private var isHovering = false

    var body: some View {
        HStack(spacing: 11) {
            Button(action: toggle) {
                Image(systemName: isChecked ? "checkmark.square.fill" : "square")
                    .font(.system(size: 14))
                    .foregroundStyle(isChecked ? Ink.accent : Ink.secondary)
            }
            .buttonStyle(.plain)
            .disabled(!isEnabled)
            .help(isEnabled ? "" : "Excluded by default and not removable")

            leading()

            // The labels and the chevron are one target when the row discloses anything, and plain
            // text otherwise. Kept out of the checkbox's button so clicking the name never toggles
            // an exclusion by accident — expanding and excluding are different decisions.
            if let onDisclosure {
                Button(action: onDisclosure) {
                    HStack(spacing: 11) {
                        labels
                        Image(systemName: isExpanded ? "chevron.down" : "chevron.right")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundStyle(Ink.secondary)
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(Text(isExpanded ? "Collapse \(title)" : "Expand \(title)"))
            } else {
                labels
            }
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 12)
        // The locked state the reference draws as "a lighter locked-looking state".
        .opacity(isEnabled ? 1 : 0.5)
        .background(isHovering && isEnabled ? Ink.rowFillHover : Color.clear)
        .onHover { isHovering = $0 }
        .contentShape(Rectangle())
        // Unchanged from before the chevron got a handler: the buttons merge into one element whose
        // actions stay reachable, and the disclosure button's own label is what names its action.
        .accessibilityElement(children: .combine)
        .accessibilityLabel(Text(title))
        .accessibilityValue(Text(isChecked ? "Excluded" : "Recorded"))
        .accessibilityHint(Text(isEnabled ? "" : "Excluded by default and not removable"))
    }

    private var labels: some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(title)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(Ink.primary)
                .lineLimit(1)
                .truncationMode(.middle)
            if let subtitle, !subtitle.isEmpty {
                Text(subtitle)
                    .font(.system(size: 10))
                    .foregroundStyle(Ink.secondary)
                    .lineLimit(1)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

extension SettingsCheckRow where Leading == EmptyView {
    init(
        title: String, subtitle: String? = nil, isChecked: Bool, isEnabled: Bool,
        onDisclosure: (() -> Void)? = nil, isExpanded: Bool = false, toggle: @escaping () -> Void
    ) {
        self.init(
            title: title, subtitle: subtitle, isChecked: isChecked, isEnabled: isEnabled,
            onDisclosure: onDisclosure, isExpanded: isExpanded, toggle: toggle,
            leading: { EmptyView() })
    }
}

/// A small app icon for an exclusion row, resolved by bundle identifier.
///
/// Reuses `AppIconCache`, which resolves by identifier through LaunchServices and never by a substring
/// guess — so an icon on this pane is either the right app's or a monogram, never a confident lie.
struct SettingsAppIcon: View {
    let app: ExcludableApp
    var size: CGFloat = 16

    var body: some View {
        RewindAppIcon(appName: app.displayName, bundleId: app.bundleID, size: size)
    }
}

/// A domain's favicon, or its initial.
///
/// **Every fetch goes through `ExclusionEngine.faviconFetch(for:)`**, which is what makes Airgap Mode's
/// promise real: the engine decides whether the request may happen at all, so turning Airgap on
/// suppresses the *request* rather than hiding an image that was already downloaded. The URL is handed
/// out by the engine and never assembled here, so there is no shape of this view that could reach a
/// third-party favicon service — a service would learn every domain the user chose to hide.
///
/// It also names itself to `NetworkEgress` as `.faviconFetch`, and that is not redundancy for its own
/// sake. This is a real `URLSession` reaching a host the app has no other business with, and it is the
/// single client that discloses the user's *own exclusion list* — asking a site for its icon tells
/// that site it was excluded. `NetworkEgress.Client` is the audited list of everything that leaves
/// this Mac, and `AirgapEgressTests` proves the guard over `Client.allCases`; a remote client outside
/// that enumeration is one nobody can check. The two answers agree by construction — both read
/// `ExclusionEngine`'s flag — so this costs a comparison and buys the entry in the list.
struct SettingsFavicon: View {
    let host: String
    var size: CGFloat = 16

    @State private var image: NSImage?
    @State private var isSuppressed = false

    /// Favicons are a third-party signal; they must not be cached to disk or share cookies with the
    /// user's browser. An ephemeral session keeps the request in memory only.
    private static let faviconSession: URLSession = {
        let config = URLSessionConfiguration.ephemeral
        config.urlCache = nil
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        config.httpShouldSetCookies = false
        return URLSession(configuration: config)
    }()

    var body: some View {
        Group {
            if let image {
                Image(nsImage: image).resizable().aspectRatio(contentMode: .fit)
            } else {
                RoundedRectangle(cornerRadius: 4, style: .continuous)
                    .fill(Ink.wash)
                    .overlay(
                        Group {
                            if isSuppressed {
                                Image(systemName: "wifi.slash")
                                    .font(.system(size: size * 0.5))
                                    .foregroundStyle(Ink.secondary)
                            } else {
                                Text(initial)
                                    .font(.system(size: size * 0.55, weight: .semibold))
                                    .foregroundStyle(Ink.secondary)
                            }
                        })
            }
        }
        .frame(width: size, height: size)
        .help(isSuppressed ? "Favicon not fetched — Airgap Mode is on" : host)
        .task(id: host) { await load() }
    }

    private var initial: String {
        guard let first = host.first else { return "?" }
        return String(first).uppercased()
    }

    private func load() async {
        switch ExclusionEngine.shared.faviconFetch(for: host) {
        case .suppressed(let reason):
            image = nil
            guard reason == .airgapMode else {
                // Not a host we could build a URL for. Nothing was suppressed and nothing is owed.
                isSuppressed = false
                return
            }
            noteSuppressed()
        case .allowed(let url):
            // Asked again, after the engine and immediately before the request. The engine answered
            // at one instant and this is the next; Airgap Mode is a live switch, and the one thing a
            // late flip must not do is let a request out that the user has already forbidden.
            guard !NetworkEgress.isSuppressed(.faviconFetch) else {
                image = nil
                noteSuppressed()
                return
            }
            isSuppressed = false
            guard let (data, response) = try? await Self.faviconSession.data(from: url),
                (response as? HTTPURLResponse)?.statusCode == 200,
                let decoded = NSImage(data: data)
            else { return }
            image = decoded
        }
    }

    /// Degraded, never dropped: nothing of the user's is lost or queued — the row simply draws its
    /// monogram, and the icon appears if they ever turn the switch off. The record exists so a
    /// suppression here is visible in the same place as every other one, rather than being the one
    /// refusal the app makes silently.
    ///
    /// Recorded on the transition only. `.task(id:)` re-runs whenever SwiftUI rebuilds this row, and
    /// a pane of excluded domains under Airgap Mode would otherwise write one record per row per
    /// scroll — a log that reports the same standing fact a hundred times is a log nobody reads.
    private func noteSuppressed() {
        guard !isSuppressed else { return }
        isSuppressed = true
        NetworkEgress.recordSuppression(.faviconFetch, outcome: .degraded)
    }
}

// MARK: - Header

/// The big number at the top of the Storage pane.
struct SettingsHeadline: View {
    let value: String
    let caption: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Text(value)
                    .font(.openRunde(30, .semiBold))
                    .foregroundStyle(Ink.primary)
                Text(caption)
                    .font(.system(size: 12))
                    .foregroundStyle(Ink.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
