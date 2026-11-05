import SwiftUI

@main
struct OmiWatchApp: App {
    @State private var recorder = WatchRecorder()

    var body: some Scene {
        WindowGroup {
            RecorderView(recorder: recorder)
        }
    }
}
