import SwiftUI

private let relayContract = "omi-relay-contract:v1|native-seam:cpp-interop|payload:bounded|gap:explicit"

@main
struct SwiftNativeShell: App {
    var body: some Scene {
        WindowGroup("Omi Swift Native Spike") {
            VStack(spacing: 12) {
                Text("SwiftUI native shell")
                    .font(.title)
                Text(relayContract)
                    .font(.caption)
                    .textSelection(.enabled)
            }
            .padding(32)
        }
    }
}
