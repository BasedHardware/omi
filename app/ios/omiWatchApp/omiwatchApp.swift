import SwiftUI

@main
struct omiwatch_Watch_AppApp: App {
    @StateObject private var viewModel = WatchAudioRecorderViewModel()

    var body: some Scene {
        WindowGroup {
            WatchRecorderView(viewModel: viewModel)
        }
    }
}
