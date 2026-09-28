import OmiKit
import SwiftUI

// Composition root. Hosts inject a wired `AppStore` (see
// `App/AppServices.swift`) via `.environmentObject`; this view selects the
// platform surface and starts the store. Desktop platforms render
// `DesktopSurface` (the v5/v5.1 desktop IA from docs/desktop-app.md); iOS
// and Android render `MobileAppSurface` (docs/mobile.md) — matching the RN
// tree, where the desktop app shipped on macOS and MobileAppSurface on
// phones.
public struct RootView: View {
    @EnvironmentObject private var store: AppStore

    public init() {}

    public var body: some View {
        surface
            .task { store.start() }
    }

    @ViewBuilder
    private var surface: some View {
        #if os(iOS) || os(Android)
        MobileAppSurface()
        #else
        DesktopSurface()
        #endif
    }
}
