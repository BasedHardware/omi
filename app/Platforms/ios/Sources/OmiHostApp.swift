import SwiftUI

import OmiKit
import OmiUI

// iOS host shell. Bootstrap + injection + URL plumbing only; all product UI
// comes from OmiUI.RootView driving OmiUI.AppModel.
//
// Injection contract (see ../README.md):
//   - OmiKit.Policy.bridge defaults to DefaultPolicyBridge, which links the
//     real native-core C++ through CNativeCore — nothing to replace on iOS.
//   - Session/auth callbacks arrive via the app-specific
//     `omi-rnruntime://auth/callback` scheme (docs/auth-and-sessions.md);
//     the native Firebase session module (to be ported from
//     react-native/ios/RnRuntime/OmiAuthModule) owns the exchange.

@main
struct OmiHostApp: App {
    @State private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView(model: model)
                .onOpenURL { url in
                    handleCallback(url)
                }
        }
    }

    /// The auth callback route is `omi-rnruntime://auth/callback?...`.
    /// Non-auth URLs are ignored here — hosts carry no product logic.
    private func handleCallback(_ url: URL) {
        guard url.scheme?.lowercased() == "omi-rnruntime",
              url.host == "auth",
              url.path == "/callback" || url.path.isEmpty else {
            return
        }
        // The OmiKit session/auth seam receives the query (code, state) once
        // the native session module is injected; today the model only learns
        // about a completed sign-in through updateSignedIn(_:) by the module
        // that owns the exchange.
    }
}
