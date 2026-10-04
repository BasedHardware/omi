import Foundation
import OmiKit
import OmiUI

// Linux host entry point. Boots the injected AppStore over the real OmiKit
// services (`OmiBootstrap.makeServices()`) and starts it — the same lifecycle
// `RootView.task { store.start() }` runs once a UI host owns the view.
//
// Rendering: per the platform decision (README.md), the desktop UI layer for
// Linux is OpenSwiftUI (`https://github.com/OpenSwiftUIProject/OpenSwiftUI`).
// Upstream, OpenSwiftUI on Linux currently ships only the stdout renderer —
// there is no window/event-loop integration yet — so this entry point is the
// non-rendering bootstrap that the future OpenSwiftUI host shell (GTK/
// Wayland/X11 integration) will wrap. `OmiOpenSwiftUIShell.swift` carries the
// `#if canImport(OpenSwiftUI)` view shell, and `OmiUIAdapter.swift` documents
// the RootView adapter seam.
@main
struct OmiLinuxApp {
    static func main() async {
        let store = await MainActor.run { AppStore(services: OmiBootstrap.makeServices()) }
        await MainActor.run { store.start() }
        #if canImport(OpenSwiftUI)
        await OmiOpenSwiftUIShell.run(store: store)
        #else
        // Without OpenSwiftUI on the toolchain the process is a service-less
        // headless bootstrap: it holds no session server and exits honestly.
        print(
            "omi-linux-host: bootstrap complete; OpenSwiftUI module not present, "
                + "no UI host available (see app/Platforms/linux/README.md)")
        #endif
    }
}
