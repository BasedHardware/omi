import OmiKit
import SwiftUI

// Connectors page, ported from `react-native/src/pages/Connectors.tsx`: the
// Explore / Installed / My Apps / Services catalog tabs, per-section empty
// copy, install/remove actions, and the signed-out / unavailable states with
// their exact copy.

public struct ConnectorsPage: View {
    public var onSignIn: (() async -> Void)? = nil
    public var signingIn: Bool = false

    @EnvironmentObject private var store: AppStore
    @State private var catalogTab: String = "Explore"
    @State private var actionError: String?

    private let catalogTabs = ["Explore", "Installed", "My Apps", "Services"]

    public init(onSignIn: (() async -> Void)? = nil, signingIn: Bool = false) {
        self.onSignIn = onSignIn
        self.signingIn = signingIn
    }

    private var snapshot: ConnectorsSnapshot? { store.connectors }
    private var loading: Bool { store.cloudLoading && snapshot == nil }
    private var signedOut: Bool { store.authState == .signedOut }

    private var unavailable: Bool {
        snapshot == nil && !loading && !signedOut
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: Space.lg) {
            tabs
            if loading {
                state {
                    ProgressView().tint(OmiColor.hex(0x888888))
                    Text("Loading apps…")
                        .font(Typography.caption.font)
                        .foregroundColor(Palette.textMuted)
                }
            } else if signedOut || unavailable {
                state {
                    KitIcon(.puzzle, size: 28, color: MobilePalette.textMuted)
                    Text(signedOut ? "Signed out" : "Apps unavailable")
                        .font(TypeStyle(size: 18, lineHeight: 24, weight: .semibold).font)
                        .foregroundColor(Color.white)
                    Text(signedOut
                        ? desktopBackendUnauthorizedCopy : desktopBackendServiceCopy)
                        .font(Typography.caption.font)
                        .foregroundColor(Palette.textMuted)
                        .multilineTextAlignment(.center)
                    if signedOut {
                        Button(action: { Task { await signIn() } }) {
                            Text(signingIn ? "Signing in…" : "Sign in")
                                .font(TypeStyle(size: 13, lineHeight: 18, weight: .semibold).font)
                                .foregroundColor(Color.white)
                                .frame(minHeight: 44)
                                .padding(.horizontal, Space.md)
                                .background(Palette.primary)
                                .clipShape(RoundedRectangle(cornerRadius: Radius.md))
                        }
                        .buttonStyle(KitPressableStyle())
                        .disabled(signingIn)
                        .accessibilityLabel("Sign in")
                    } else {
                        Button(action: { Task { await store.refreshConnectors() } }) {
                            Text("Retry")
                                .font(TypeStyle(size: 13, lineHeight: 18, weight: .semibold).font)
                                .foregroundColor(Color.white)
                                .frame(minHeight: 44)
                                .padding(.horizontal, Space.md)
                                .background(Palette.input)
                                .overlay(
                                    RoundedRectangle(cornerRadius: Radius.md)
                                        .strokeBorder(Palette.line, lineWidth: Borders.width)
                                )
                                .clipShape(RoundedRectangle(cornerRadius: Radius.md))
                        }
                        .buttonStyle(KitPressableStyle())
                        .accessibilityLabel("Retry apps")
                    }
                }
            } else if let snapshot {
                section(title: catalogTab, snapshot: snapshot)
            }
            if let actionError {
                Text(actionError)
                    .font(TypeStyle(size: 13, lineHeight: 18, weight: .regular).font)
                    .foregroundColor(Palette.danger)
                    .accessibilityLabel(actionError)
            }
        }
        .onAppear {
            if snapshot == nil, !signedOut {
                Task { await store.refreshConnectors() }
            }
        }
    }

    private func signIn() async {
        if let onSignIn {
            await onSignIn()
        } else {
            await store.startSignIn()
        }
        await store.refreshConnectors()
    }

    private var tabs: some View {
        HStack(spacing: 8) {
            ForEach(catalogTabs, id: \.self) { tab in
                let isSelected = catalogTab == tab
                Button(action: { catalogTab = tab }) {
                    Text(tab)
                        .font(TypeStyle(size: 13, lineHeight: 18, weight: .semibold).font)
                        .foregroundColor(
                            isSelected ? MobilePalette.background : MobilePalette.textMuted
                        )
                        .frame(maxWidth: .infinity, minHeight: 44)
                        .background(
                            RoundedRectangle(cornerRadius: 14)
                                .fill(isSelected ? MobilePalette.text : MobilePalette.surface)
                        )
                }
                .buttonStyle(KitPressableStyle())
                .animation(KitMotion.slide, value: catalogTab)
                .accessibilityLabel(tab == "My Apps" ? "My apps" : "\(tab) apps")
                .accessibilityAddTraits(isSelected ? [.isSelected] : [])
            }
        }
    }

    private func state<Content: View>(
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(spacing: 12) { content() }
            .frame(maxWidth: .infinity)
            .padding(24)
            .background(MobilePalette.surface)
            .overlay(
                RoundedRectangle(cornerRadius: 22)
                    .strokeBorder(MobilePalette.border, lineWidth: 0.5)
            )
            .clipShape(RoundedRectangle(cornerRadius: 22))
    }

    // MARK: Catalog sections

    private struct CatalogSection {
        let key: String
        let title: String
        let empty: String
        let items: [CloudApp]
    }

    private func sections(_ snapshot: ConnectorsSnapshot) -> [CatalogSection] {
        [
            CatalogSection(
                key: "Explore", title: "Explore",
                empty: "No apps were returned by the catalogue.",
                items: exploreApps(snapshot)
            ),
            CatalogSection(
                key: "Installed", title: "Installed",
                empty: snapshot.enabledError ?? "No installed apps.",
                items: installedApps(snapshot)
            ),
            CatalogSection(
                key: "My Apps", title: "My Apps",
                empty: snapshot.ownerUid == nil
                    ? "Owned apps are unavailable until the account profile loads."
                    : "No apps owned by this account.",
                items: myApps(snapshot, uid: snapshot.ownerUid)
            ),
            CatalogSection(
                key: "Services", title: "Services",
                empty: "No apps with an external service connection were returned.",
                items: serviceApps(snapshot)
            ),
        ]
    }

    private func section(title: String, snapshot: ConnectorsSnapshot) -> some View {
        let matches = sections(snapshot).filter { $0.key == title }
        return ForEach(matches, id: \.key) { section in
            VStack(alignment: .leading, spacing: 12) {
                Text(section.title)
                    .font(TypeStyle(size: 18, lineHeight: 24, weight: .semibold).font)
                    .foregroundColor(Color.white)
                if section.items.isEmpty {
                    Text(section.empty)
                        .font(Typography.caption.font)
                        .foregroundColor(Palette.textMuted)
                } else {
                    ForEach(section.items, id: \.id) { app in
                        ConnectorCard(
                            app: app,
                            busy: false,
                            onToggle: { toggle(app) }
                        )
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func toggle(_ app: CloudApp) {
        actionError = nil
        Task {
            if app.enabled {
                await store.disableConnector(appId: app.id)
            } else {
                await store.enableConnector(appId: app.id)
            }
        }
    }
}

public struct ConnectorCard: View {
    public let app: CloudApp
    public let busy: Bool
    public let onToggle: () -> Void

    public init(app: CloudApp, busy: Bool, onToggle: @escaping () -> Void) {
        self.app = app
        self.busy = busy
        self.onToggle = onToggle
    }

    private var metaCopy: String {
        var parts: [String] = []
        if !app.category.isEmpty { parts.append(app.category) }
        if !app.author.isEmpty { parts.append(app.author) }
        parts.append(app.enabled ? "Installed" : "Not installed")
        return parts.joined(separator: " · ")
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                RoundedRectangle(cornerRadius: 14)
                    .fill(MobilePalette.surfaceRaised)
                    .frame(width: 48, height: 48)
                    .overlay(
                        KitIcon(.puzzle, size: 24, color: MobilePalette.text)
                    )
                VStack(alignment: .leading, spacing: 4) {
                    Text(app.name)
                        .font(TypeStyle(size: 14, lineHeight: 18, weight: .semibold).font)
                        .foregroundColor(OmiColor.hex(0xEEEEEE))
                    if !app.description.isEmpty {
                        Text(app.description)
                            .font(TypeStyle(size: 12, lineHeight: 17, weight: .regular).font)
                            .foregroundColor(OmiColor.hex(0x888888))
                            .lineLimit(2)
                    }
                    Text(metaCopy)
                        .font(TypeStyle(size: 12, lineHeight: 17, weight: .regular).font)
                        .foregroundColor(OmiColor.hex(0x888888))
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            Button(action: onToggle) {
                Text(actionCopy)
                    .font(TypeStyle(size: 13, lineHeight: 18, weight: .semibold).font)
                    .foregroundColor(Color.white)
                    .frame(maxWidth: .infinity).frame(minHeight: 44)
                    .background(Palette.input)
                    .overlay(
                        RoundedRectangle(cornerRadius: Radius.md)
                            .strokeBorder(Palette.line, lineWidth: Borders.width)
                    )
                    .clipShape(RoundedRectangle(cornerRadius: Radius.md))
            }
            .buttonStyle(KitPressableStyle())
            .disabled(busy)
            .accessibilityLabel(app.enabled ? "Remove \(app.name)" : "Install \(app.name)")
        }
        .padding(20)
        .background(MobilePalette.surface)
        .overlay(
            RoundedRectangle(cornerRadius: 22)
                .strokeBorder(MobilePalette.border, lineWidth: 0.5)
        )
        .clipShape(RoundedRectangle(cornerRadius: 22))
    }

    private var actionCopy: String {
        if busy {
            return app.enabled ? "Removing…" : "Installing…"
        }
        return app.enabled ? "Remove" : "Install"
    }
}
