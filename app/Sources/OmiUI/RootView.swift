import Foundation
import OmiKit
import SwiftUI

// Cross-platform app model and root shell. This is the integration seam the
// orchestrator port (chat state, reads, tasks, devices, onboarding) builds
// on; the shell here is the starting point that the ported surfaces replace.

@MainActor
@Observable
public final class AppModel {
    public private(set) var route: MobileRoute
    public private(set) var signedIn: Bool

    public init(route: MobileRoute = .home, signedIn: Bool = false) {
        self.route = route
        self.signedIn = signedIn
    }

    public func select(_ route: MobileRoute) {
        self.route = route
    }

    public func updateSignedIn(_ signedIn: Bool) {
        self.signedIn = signedIn
    }
}

public struct RootView: View {
    public let model: AppModel

    public init(model: AppModel) {
        self.model = model
    }

    public var body: some View {
        TabView(selection: Binding(
            get: { model.route },
            set: { model.select($0) }
        )) {
            destination(.home)
                .tabItem { tabLabel("Home", icon: "house") }
                .tag(MobileRoute.home)
            destination(.chat)
                .tabItem { tabLabel("Conversations", icon: "bubble.left") }
                .tag(MobileRoute.chat)
            destination(.tasks)
                .tabItem { tabLabel("Tasks", icon: "checkmark.circle") }
                .tag(MobileRoute.tasks)
            destination(.settings)
                .tabItem { tabLabel("Settings", icon: "gearshape") }
                .tag(MobileRoute.settings)
            destination(.apps)
                .tabItem { tabLabel("Apps", icon: "square.grid.2x2") }
                .tag(MobileRoute.apps)
        }
    }

    private func tabLabel(_ title: String, icon: String) -> some View {
        // Icons return with the shared design kit; text keeps the skeleton
        // within the SkipUI-transpilable surface.
        Text(title)
    }

    @ViewBuilder
    private func destination(_ route: MobileRoute) -> some View {
        Text(route.rawValue)
            .font(Typography.title.font)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Palette.canvas)
    }
}
