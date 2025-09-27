import SwiftUI

@main
struct omiwatch_Watch_AppApp: App {
    var body: some Scene {
        WindowGroup {
            WatchRecorderView(viewModel: WatchAudioRecorderViewModel())
        }
    }
}
