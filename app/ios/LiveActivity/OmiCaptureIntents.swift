// The card's buttons follow the Siri build boundary (contracts/siri/README.md): App Intents
// compile only with Xcode 27, because the required Xcode 26.6 CI build must emit no App Intents
// metadata. Releases are built with Xcode 27.
#if compiler(>=6.4)
import AppIntents

@available(iOS 17.0, *)
struct OmiCaptureIntent: LiveActivityIntent {
    static var title: LocalizedStringResource = "Control Omi recording"
    static var isDiscoverable: Bool = false

    @Parameter(title: "Recording") var recordingId: String
    @Parameter(title: "Conversation") var conversationRevision: Int
    @Parameter(title: "Action") var action: String

    init() {}
    init(recordingId: String, revision: Int, action: String) {
        self.recordingId = recordingId
        self.conversationRevision = revision
        self.action = action
    }

    func perform() async throws -> some IntentResult {
        try await OmiCaptureActionDispatcher.perform(
            recordingId: recordingId, revision: conversationRevision, action: action)
        return .result()
    }
}

/// Start for a stopped phone microphone. Turning the mic back on from the Lock Screen starts a
/// recording while Omi is in the background, which iOS allows only from an audio recording intent.
@available(iOS 18.0, *)
struct OmiCaptureRecordingIntent: AudioRecordingIntent, LiveActivityIntent {
    static var title: LocalizedStringResource = "Start Omi recording"
    static var isDiscoverable: Bool = false

    @Parameter(title: "Recording") var recordingId: String
    @Parameter(title: "Conversation") var conversationRevision: Int

    init() {}
    init(recordingId: String, revision: Int) {
        self.recordingId = recordingId
        self.conversationRevision = revision
    }

    func perform() async throws -> some IntentResult {
        try await OmiCaptureActionDispatcher.perform(
            recordingId: recordingId, revision: conversationRevision, action: "resume")
        return .result()
    }
}
#endif
