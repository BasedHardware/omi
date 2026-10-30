import AppIntents
import Foundation
import OmiCore
import OmiService

/// Hands the app's one environment to what iOS creates on its own: App Intents (Siri, Shortcuts,
/// Spotlight), quick actions and the scene delegate. Set once in `OmiApp.init`; everything here runs
/// in the app's process, on the stores the screens use.
@MainActor
enum AppIntentsBridge {
    static var environment: AppEnvironment?
    static var router: DeepLinkRouter?

    /// The signed-in environment. When Siri launched the app in the background the shell never
    /// appeared, so the session is restored here (as `RootView` does on screen).
    static func signedIn() async throws -> AppEnvironment {
        let deadline = ContinuousClock.now.advanced(by: .seconds(5))
        while environment == nil, ContinuousClock.now < deadline {
            try? await Task.sleep(for: .milliseconds(100))
        }
        guard let environment else { throw IntentMessage.notReady }
        if environment.session.phase == .launching { environment.session.restore() }
        guard case .ready = environment.session.phase else { throw IntentMessage.signedOut }
        return environment
    }

    static func catalog() async throws -> SiriCatalog {
        let environment = try await signedIn()
        return SiriCatalog(
            conversations: environment.conversations, tasks: environment.tasks,
            memories: environment.memories, chat: environment.chat
        )
    }

    /// Opens a place in the app (the shell takes it once it is on screen).
    static func open(_ link: DeepLink) {
        router?.open(link)
    }
}

/// What Siri says when an intent cannot do its job; thrown so Shortcuts sees a failure too.
enum IntentMessage: Error, CustomLocalizedStringResourceConvertible {
    case notReady
    case signedOut
    case notSaved
    case unknownTask
    case empty

    var localizedStringResource: LocalizedStringResource {
        switch self {
        case .notReady: LocalizedStringResource("Open Omi and try again.", table: "AppIntents")
        case .signedOut: LocalizedStringResource("Open Omi and sign in first.", table: "AppIntents")
        case .notSaved: LocalizedStringResource("Omi couldn't save that right now.", table: "AppIntents")
        case .unknownTask: LocalizedStringResource("That task isn't in Omi anymore.", table: "AppIntents")
        case .empty: LocalizedStringResource("There was nothing to save.", table: "AppIntents")
        }
    }

    init(_ failure: SiriCatalog.Failure) {
        switch failure {
        case .empty: self = .empty
        case .notSaved: self = .notSaved
        case .unknownTask: self = .unknownTask
        }
    }
}
