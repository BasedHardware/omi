#if canImport(OpenSwiftUI)
import OpenSwiftUI
import OmiKit
import OmiUI

// The OpenSwiftUI-facing shell for the Linux host. This file compiles against
// OpenSwiftUI's own `View` protocol (not Apple SwiftUI), so it is the place
// where OpenSwiftUI API coverage is exercised for the views this host needs.
//
// STATUS (honest): this is a bootstrap shell, not the product surface. The
// product surface is `OmiUI.RootView`, which conforms to Apple's
// `SwiftUI.View`; bridging a SwiftUI-shaped view tree into OpenSwiftUI's
// view graph is the `OmiUIAdapter` seam (see `OmiUIAdapter.swift`) and is
// blocked on upstream work (windowing + text layout on Linux). The shell
// keeps the host compile-verifiable against OpenSwiftUI today.
enum OmiOpenSwiftUIShell {
    /// Entrypoint for the future windowing integration. Upstream's Linux
    /// renderer is stdout-only today (one terminal frame, no window, no text
    /// layout), so `run` reports status rather than claiming a UI.
    @MainActor
    static func run(store: AppStore) async {
        let shell = OmiShellStatusView(signedIn: store.authState == .signedIn)
        _ = shell // view graph owned by the future host window
        print("omi-linux-host: OpenSwiftUI shell armed (stdout renderer upstream; no windowing yet)")
    }
}

/// Exercises the OpenSwiftUI view API surface the product surface will need
/// first (`VStack`, `Text`, `Color`, layout padding) so API regressions in
/// upstream fail this host's build, not a later integration.
struct OmiShellStatusView: View {
    let signedIn: Bool

    var body: some View {
        VStack(spacing: 8) {
            Text(signedIn ? "Omi — signed in" : "Omi — signed out")
            Text("Desktop surface pending: OpenSwiftUI windowing + OmiUI adapter")
                .padding()
        }
    }
}
#endif
