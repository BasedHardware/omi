import AppIntents
import Foundation

// The recording card's buttons. Compiled into the app and the widget extension: the extension
// needs the types to draw the buttons, and the system runs a `LiveActivityIntent` in the app's
// process, where the app has installed the handler.

/// End: stops the recording and saves the conversation, which closes the card.
struct StopCaptureIntent: LiveActivityIntent {
    static let title: LocalizedStringResource = "Stop recording"
    static let isDiscoverable = false

    func perform() async throws -> some IntentResult {
        await CaptureIntentAction.run(.stop)
        return .result()
    }
}

/// Stop: holds the audio back and keeps the conversation open (the Omi mutes, the phone releases
/// its microphone).
struct PauseCaptureIntent: LiveActivityIntent {
    static let title: LocalizedStringResource = "Pause recording"
    static let isDiscoverable = false

    func perform() async throws -> some IntentResult {
        await CaptureIntentAction.run(.pause)
        return .result()
    }
}

/// Start after Stop. Turning the phone microphone back on from the Lock Screen starts recording
/// while Omi is in the background, which iOS allows only from an audio recording intent.
struct ResumeCaptureIntent: AudioRecordingIntent, LiveActivityIntent {
    static let title: LocalizedStringResource = "Resume recording"
    static let isDiscoverable = false

    func perform() async throws -> some IntentResult {
        await CaptureIntentAction.run(.resume)
        return .result()
    }
}

/// Where the app plugs in the recording's controls. Nil in the extension and before the app is set up.
@MainActor
enum CaptureIntentAction {
    enum Command: Sendable {
        case stop
        case pause
        case resume
    }

    static var handler: (@MainActor (Command) async -> Void)?

    static func run(_ command: Command) async {
        // A tap can wake an app iOS had suspended; give its setup a moment.
        let deadline = Date.now.addingTimeInterval(5)
        while handler == nil, Date.now < deadline {
            try? await Task.sleep(for: .milliseconds(150))
        }
        await handler?(command)
    }
}
