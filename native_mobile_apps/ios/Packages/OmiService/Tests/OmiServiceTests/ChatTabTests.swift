import Foundation
import ImageIO
import OmiCore
import OmiNetwork
@testable import OmiService
import OmiTestSupport
import Testing
import UniformTypeIdentifiers

/// The chat tab: one pinned thread, "Omi asks" in it, and the cards the app draws.
@MainActor
struct ChatTabSessionTests {
    func makeChat(_ api: FakeAPIClient) -> ChatStore {
        api.existingSessions = [("main", "Chat")]
        return ChatStore(api: api, preferences: freshPreferences())
    }

    @Test func typedQuestionsGoToThePinnedSession() async {
        let api = FakeAPIClient()
        let chat = makeChat(api)
        chat.send("Hi")
        await chat.streamTask?.value
        #expect(api.devApps.sentSessions == ["main"])
    }

    /// A question the iPhone could not transcribe is written down by the backend and asked in the
    /// pinned session (not via v2/voice-messages, which picks the newest session without an app).
    @Test func serverTranscribedQuestionsGoToThePinnedSession() async {
        let api = FakeAPIClient()
        api.deviceActions.replyToVoice([
            .question(ChatMessage(id: "q", text: "What's next?", sender: .user, createdAt: .now)), .chat(.delta("Lunch at 1.")),
        ])
        let chat = makeChat(api)
        let answer = await chat.ask(voiceFile: "audio.bin", audio: Data([1, 2]))
        #expect(answer == .answered("Lunch at 1."))
        #expect(api.devApps.sentSessions == ["main"])
        #expect(api.chatExtras.sentTexts == ["What's next?"])
        #expect(chat.messages.suffix(2).map(\.text) == ["What's next?", "Lunch at 1."])
    }

    @Test func silenceAsksNothing() async {
        let api = FakeAPIClient()
        api.deviceActions.replyToVoice([.noSpeech])
        let chat = makeChat(api)
        #expect(await chat.ask(voiceFile: "audio.bin", audio: Data([1])) == .noSpeech)
        #expect(api.chatExtras.sentTexts.isEmpty)
    }

    /// A run never becomes the backend's "current" main chat: its thread has the run app id, and
    /// the main chat keeps its pin after it.
    @Test func runsDoNotMoveThePin() async {
        let api = FakeAPIClient()
        let prefs = freshPreferences()
        api.existingSessions = [("main", "Chat")]
        let chat = ChatStore(api: api, preferences: prefs)
        #expect(await chat.resolveMainSession() == "main")
        await AgentStore(api: api, preferences: prefs).takeOver(Fixtures.tasks[2], conversationTitle: nil)
        #expect(api.chatSessions.isEmpty)
        #expect(await chat.resolveMainSession() == "main")
    }

    @Test func stopEndsARunAsStopped() async throws {
        let api = FakeAPIClient()
        let agent = AgentStore(api: api, preferences: freshPreferences())
        api.deviceToolWait = .seconds(30)
        let request = DeviceToolRequest(id: "call-stop", toolName: "propose_message", recipients: ["Anna"], text: "Hi")
        api.agentScript = [.step("Drafting"), .deviceTool(request)]
        agent.deviceTools = FakeDeviceTools()
        let task = Fixtures.tasks[2]
        let running = Task { await agent.takeOver(task, conversationTitle: nil) }
        try await waitUntil { agent.deviceToolRequests[task.id] != nil }
        agent.stop(task.id)
        await running.value
        #expect(agent.runs[task.id]?.failure == .stopped)
        #expect(agent.runs[task.id]?.finishedAt != nil)
        #expect(agent.deviceToolRequests.isEmpty)
    }
}

@MainActor
struct ChatDeviceToolTests {
    let request = DeviceToolRequest(id: "call-9", toolName: "propose_message", recipients: ["Anna"], text: "Thursday 7 pm?")

    @Test func mainChatDeclaresTheDeviceTools() async {
        let api = FakeAPIClient()
        api.existingSessions = [("main", "Chat")]
        let chat = ChatStore(api: api, preferences: freshPreferences())
        chat.deviceTools = FakeDeviceTools()
        chat.send("Text Anna")
        await chat.streamTask?.value
        #expect(api.chatExtras.sentDeviceTools == [["propose_message", "search_contacts", "request_permission"]])
    }

    @Test func noToolsWithoutAPhoneToRunThem() async {
        let api = FakeAPIClient()
        let chat = ChatStore(api: api, preferences: freshPreferences())
        chat.send("Hi")
        await chat.streamTask?.value
        #expect(api.chatExtras.sentDeviceTools == [[]])
    }

    /// The question shows under its answer; nothing reaches the agent before the tap.
    @Test func omiAsksWaitsForTheTap() async throws {
        let api = FakeAPIClient()
        api.existingSessions = [("main", "Chat")]
        api.chatExtras.script = [.step("Drafting the message"), .deviceTool(request), .done(Self.done("Anna has it."))]
        let tools = FakeDeviceTools()
        let chat = ChatStore(api: api, preferences: freshPreferences())
        chat.deviceTools = tools
        chat.send("Ask Anna about Thursday")
        try await waitUntil { chat.pendingDeviceTool != nil }
        let answerID = try #require(chat.messages.last?.id)
        #expect(chat.pendingDeviceToolMessageID == answerID)
        #expect(chat.askedMessageIDs == [answerID])
        #expect(api.deviceToolResults.isEmpty)
        #expect(tools.log.isEmpty)
        await chat.answerDeviceTool(.send(text: "Thursday 7 pm works?"))
        await chat.streamTask?.value
        #expect(tools.log == ["compose:Anna:Thursday 7 pm works?"])
        #expect(api.deviceToolResults["call-9"] == DeviceToolResult(ok: true, status: "sent"))
        #expect(chat.pendingDeviceTool == nil)
        #expect(chat.messages.last?.text == "Anna has it.")
        #expect(chat.visibleMessages(query: "", filter: .approvals).map(\.id) == [answerID])
    }

    @Test func notNowTellsTheAgent() async throws {
        let api = FakeAPIClient()
        api.chatExtras.script = [.deviceTool(request), .done(Self.done("Okay."))]
        let chat = ChatStore(api: api, preferences: freshPreferences())
        chat.deviceTools = FakeDeviceTools()
        chat.send("Ask Anna")
        try await waitUntil { chat.pendingDeviceTool != nil }
        await chat.answerDeviceTool(.decline)
        await chat.streamTask?.value
        let result = try #require(api.deviceToolResults["call-9"])
        #expect(!result.ok && result.reason == "declined")
    }

    /// The agent gave up waiting: the card goes when the turn ends.
    @Test func theCardGoesWhenTheTurnEnds() async throws {
        let api = FakeAPIClient()
        api.deviceToolWait = .milliseconds(30)
        api.chatExtras.script = [.deviceTool(request), .done(Self.done("I drafted it for you."))]
        let chat = ChatStore(api: api, preferences: freshPreferences())
        chat.deviceTools = FakeDeviceTools()
        chat.send("Ask Anna")
        await chat.streamTask?.value
        #expect(chat.pendingDeviceTool == nil)
        #expect(api.deviceToolResults.isEmpty)
    }

    static func done(_ text: String) -> ChatMessage {
        ChatMessage(id: "reply-x", text: text, sender: .omi, createdAt: Fixtures.now)
    }
}

struct ChatCardDetectionTests {
    /// The backend's own texts (`calendar_tools.py`, `gmail_tools.py`, `apple_health_tools.py`).
    @Test func backendNotConnectedTexts() {
        let calendar = "Google Calendar is not connected. Please connect your Google Calendar from settings to view your events."
        let gmail = "Gmail is not connected. Please connect your Google account from settings to view your emails."
        let health = "Apple Health is not connected. Please connect Apple Health from settings on your iPhone to view your health data."
        #expect(ChatCardDetector.missingConnections(text: calendar) == ["google_calendar"])
        #expect(ChatCardDetector.missingConnections(text: gmail) == ["gmail"])
        #expect(ChatCardDetector.missingConnections(text: health) == ["apple_health"])
    }

    @Test func modelParaphrases() {
        let answer = "It looks like your Google Calendar isn’t connected right now. Want me to guide you through setting it up?"
        #expect(ChatCardDetector.missingConnections(text: answer) == ["google_calendar"])
        #expect(ChatCardDetector.missingConnections(text: "Dein Google Kalender ist nicht verbunden.") == ["google_calendar"])
    }

    @Test func connectedAnswersAreNotCards() {
        #expect(ChatCardDetector.missingConnections(text: "Your Google Calendar shows two meetings tomorrow.").isEmpty)
        #expect(ChatCardDetector.missingConnections(text: "I checked Gmail: nothing new from Anna.").isEmpty)
        #expect(ChatCardDetector.missingConnections(text: "You are not connected to Anna on LinkedIn.").isEmpty)
    }

    @Test func taskStepsAreRecognized() {
        #expect(ChatCardDetector.touchedTasks(steps: ["Searching memories", "Creating action item"]))
        #expect(ChatCardDetector.touchedTasks(steps: ["Updating action item"]))
        #expect(ChatCardDetector.touchedTasks(steps: ["update_action_item_tool"]))
        #expect(!ChatCardDetector.touchedTasks(steps: ["Checking action items", "Searching conversations"]))
    }

    @Test func taskChangesAreAddedAndCompleted() {
        let before = [Fixtures.task("a", "Call Anna"), Fixtures.task("b", "Book venue")]
        var done = before[1]
        done.isCompleted = true
        let after = [before[0], done, Fixtures.task("c", "Buy oat milk")]
        #expect(ChatCardDetector.taskChanges(before: before, after: after) == [
            .taskCompleted(id: "b", title: "Book venue"), .taskAdded(id: "c", title: "Buy oat milk"),
        ])
    }
}

@MainActor
struct ChatTaskCardTests {
    @Test func aTaskTheAgentAddedShowsAndCanBeUndone() async throws {
        let api = FakeAPIClient()
        let tasks = TasksStore(api: api)
        await tasks.load()
        api.chatExtras.script = [.step("Creating action item"), .done(ChatDeviceToolTests.done("I added it."))]
        api.chatExtras.tasksAfterTurn = Fixtures.tasks + [Fixtures.task("t-new", "Buy oat milk")]
        let chat = ChatStore(api: api, preferences: freshPreferences())
        chat.tasks = tasks
        chat.send("Add a task: buy oat milk")
        await chat.streamTask?.value
        let answerID = try #require(chat.messages.last?.id)
        #expect(chat.cards(for: answerID) == [.taskAdded(id: "t-new", title: "Buy oat milk")])
        #expect(chat.visibleMessages(query: "", filter: .jobs).map(\.id) == [answerID])
        await chat.undo(.taskAdded(id: "t-new", title: "Buy oat milk"), in: answerID)
        #expect(api.editLog.contains("delete-task:t-new"))
        #expect(chat.cards(for: answerID).isEmpty)
    }

    @Test func noTaskStepNoReload() async {
        let api = FakeAPIClient()
        let tasks = TasksStore(api: api)
        await tasks.load()
        let pages = api.pageRequests.count
        let chat = ChatStore(api: api, preferences: freshPreferences())
        chat.tasks = tasks
        chat.send("Hi")
        await chat.streamTask?.value
        #expect(api.pageRequests.count == pages)
        let lastID = chat.messages.last?.id ?? ""
        #expect(chat.cards(for: lastID).isEmpty)
    }

    /// A stored answer about a missing connection keeps its card, once, on the newest one.
    @Test func connectCardsFromHistoryStayOnTheNewest() async {
        let text = "Google Calendar is not connected. Please connect your Google Calendar from settings."
        let api = FakeAPIClient()
        api.chatArchive = [
            ChatMessage(id: "a1", text: text, sender: .omi, createdAt: Fixtures.now.addingTimeInterval(-60)),
            ChatMessage(id: "q", text: "And now?", sender: .user, createdAt: Fixtures.now.addingTimeInterval(-30)),
            ChatMessage(id: "a2", text: text, sender: .omi, createdAt: Fixtures.now),
        ]
        api.existingSessions = [("main", "Chat")]
        let chat = ChatStore(api: api, preferences: freshPreferences())
        await chat.loadHistory()
        #expect(chat.cards(for: "a2") == [.connect("google_calendar")])
        #expect(chat.cards(for: "a1").isEmpty)
    }
}

struct ChatImageEncoderTests {
    /// A photo as the iPhone stores it (HEIC) leaves as a JPEG the backend takes, scaled down.
    @Test func heicBecomesJPEG() throws {
        let heic = try #require(Self.image(width: 3000, height: 1500, type: .heic))
        #expect(ChatImageEncoder.isHEIC(heic))
        let jpeg = try #require(ChatImageEncoder.jpeg(from: heic))
        #expect(jpeg.prefix(2) == Data([0xFF, 0xD8]))
        #expect(!ChatImageEncoder.isHEIC(jpeg))
        let source = try #require(CGImageSourceCreateWithData(jpeg as CFData, nil))
        let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any]
        #expect(properties?[kCGImagePropertyPixelWidth] as? Int == ChatImageEncoder.maxSide)
        #expect(properties?[kCGImagePropertyPixelHeight] as? Int == ChatImageEncoder.maxSide / 2)
    }

    @Test func pngAndNamesToo() throws {
        let png = try #require(Self.image(width: 40, height: 20, type: .png))
        #expect(ChatImageEncoder.jpeg(from: png)?.prefix(2) == Data([0xFF, 0xD8]))
        #expect(ChatImageEncoder.jpeg(from: Data("not an image".utf8)) == nil)
        #expect(ChatImageEncoder.jpegName(for: "IMG_0042.HEIC") == "IMG_0042.jpg")
        #expect(ChatImageEncoder.jpegName(for: nil).hasSuffix(".jpg"))
    }

    @MainActor
    @Test func attachedPhotosUploadAsJPEG() async throws {
        let api = FakeAPIClient()
        let chat = ChatStore(api: api, preferences: freshPreferences())
        let heic = try #require(Self.image(width: 100, height: 100, type: .heic))
        #expect(chat.attachImage(data: heic, filename: "IMG_1.HEIC"))
        try await waitUntil { chat.attachments.first?.file != nil }
        #expect(chat.attachments.first?.mimeType == "image/jpeg")
        #expect(api.chatExtras.uploads == ["IMG_1.jpg"])
    }

    static func image(width: Int, height: Int, type: UTType) -> Data? {
        let space = CGColorSpaceCreateDeviceRGB()
        guard let context = CGContext(
            data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0, space: space,
            bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue
        ) else { return nil }
        context.setFillColor(CGColor(red: 0.2, green: 0.5, blue: 0.8, alpha: 1))
        context.fill(CGRect(x: 0, y: 0, width: width, height: height))
        guard let image = context.makeImage() else { return nil }
        let output = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(output, type.identifier as CFString, 1, nil) else { return nil }
        CGImageDestinationAddImage(destination, image, nil)
        return CGImageDestinationFinalize(destination) ? output as Data : nil
    }
}
