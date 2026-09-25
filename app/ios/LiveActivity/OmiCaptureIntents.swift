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
