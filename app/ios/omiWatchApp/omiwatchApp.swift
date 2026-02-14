import SwiftUI

enum AppLaunchMode: Equatable {
    case home
    case record
    case deviceRecord
    case ask
}

@main
struct omiwatch_Watch_AppApp: App {
    @State private var launchMode: AppLaunchMode = .home

    var body: some Scene {
        WindowGroup {
            switch launchMode {
            case .home:
                WatchRecorderView(viewModel: WatchAudioRecorderViewModel())
            case .record:
                WatchRecorderView(viewModel: WatchAudioRecorderViewModel(), autoStartRecording: true)
            case .deviceRecord:
                WatchRecorderView(viewModel: WatchAudioRecorderViewModel(), autoStartDeviceRecording: true)
            case .ask:
                AskQuestionView()
            }
        }
        .onOpenURL { url in
            switch url.host {
            case "record":
                launchMode = .record
            case "device-record":
                launchMode = .deviceRecord
            case "ask":
                launchMode = .ask
            default:
                launchMode = .home
            }
        }
    }
}
