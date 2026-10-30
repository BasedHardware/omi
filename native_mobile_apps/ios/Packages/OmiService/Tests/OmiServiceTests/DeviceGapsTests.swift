import Foundation
import OmiCore
import OmiDevice
import OmiNetwork
import OmiPersistence
@testable import OmiService
import OmiTestSupport
import Testing

/// A clock the tests move by hand.
@MainActor
final class TestClock {
    var now = Date(timeIntervalSince1970: 1_790_000_000)

    func advance(_ seconds: TimeInterval) {
        now = now.addingTimeInterval(seconds)
    }
}

@MainActor
struct DeviceDiagnosticsTests {
    let clock = TestClock()
    let prefs = freshPreferences()

    func log() -> DeviceDiagnosticsLog {
        let clock = clock
        return DeviceDiagnosticsLog(preferences: prefs, now: { clock.now })
    }

    /// A drop is counted once the Omi is back, with how long it was away.
    @Test func dropsAreTimedUntilTheOmiIsBack() {
        let diagnostics = log()
        diagnostics.connected()
        clock.advance(600)
        diagnostics.signalRead(-70)
        diagnostics.disconnected(reason: "The connection has timed out unexpectedly.", wasConnected: true)
        #expect(diagnostics.summary.drops == 0)
        clock.advance(8)
        diagnostics.connected()
        let drop = diagnostics.events[0]
        #expect(drop.kind == .disconnect)
        #expect(drop.connectedFor == 600)
        #expect(drop.reconnectedAfter == 8)
        #expect(drop.lastRSSI == -70)
        #expect(diagnostics.summary.drops == 1)
        #expect(diagnostics.summary.medianReconnect == 8)
        #expect(!diagnostics.summary.hasTrouble)
    }

    /// Only failed connects in the last day make the verdict "having trouble"; manual ones are no drops.
    @Test func failedConnectsDecideTheVerdict() {
        let diagnostics = log()
        diagnostics.connected()
        diagnostics.disconnected(reason: nil, wasConnected: true, manual: true)
        clock.advance(30)
        diagnostics.connected()
        #expect(diagnostics.summary.drops == 0)
        #expect(diagnostics.events[0].reconnectedAfter == nil)
        diagnostics.disconnected(reason: nil, wasConnected: false)
        #expect(diagnostics.summary.failed == 1)
        #expect(diagnostics.summary.hasTrouble)
        clock.advance(25 * 3600)
        #expect(diagnostics.summary.failed == 1)
        #expect(!diagnostics.summary.hasTrouble)
    }

    @Test func summaryUsesTheMedianAndLongestGap() {
        let events = [3.0, 10, 40].enumerated().map { index, gap in
            DiagnosticsEvent(kind: .disconnect, at: clock.now.addingTimeInterval(Double(index) * 60), reconnectedAfter: gap)
        }
        let summary = DiagnosticsSummary.make(events, now: clock.now.addingTimeInterval(7200), since: clock.now)
        #expect(summary.drops == 3)
        #expect(summary.medianReconnect == 10)
        #expect(summary.longestGap == 40)
        #expect(summary.dropsPerHour == 2)
    }

    /// History survives a relaunch and is kept for 7 days; forgetting the Omi starts over.
    @Test func historyIsKeptForAWeekAndClearedOnForget() {
        let first = log()
        first.connected()
        first.disconnected(reason: "gone", wasConnected: true)
        first.batteryRead(80, charging: false)
        first.batteryRead(80, charging: false)
        clock.advance(16 * 60)
        first.batteryRead(80, charging: false)
        #expect(first.battery.count == 2)
        let relaunched = log()
        #expect(relaunched.events.map(\.reason) == ["gone"])
        #expect(relaunched.battery.count == 2)
        clock.advance(8 * 24 * 3600)
        #expect(log().events.isEmpty)
        relaunched.reset()
        #expect(prefs.string(.deviceDiagnostics) == nil)
    }

    @Test func signalBands() {
        #expect(SignalQuality(rssi: -55) == .excellent)
        #expect(SignalQuality(rssi: -70) == .good)
        #expect(SignalQuality(rssi: -80) == .fair)
        #expect(SignalQuality(rssi: -95) == .weak)
    }

    /// Flutter's schema 2: the backend refuses anything else.
    @Test func bundleIsSchemaTwo() throws {
        let diagnostics = log()
        diagnostics.connected()
        diagnostics.disconnected(reason: "x", wasConnected: true)
        clock.advance(5)
        diagnostics.connected()
        var device = PairedDevice(id: "dev-1", name: "Omi")
        device.firmwareRevision = "3.0.1"
        let environment = DeviceDiagnosticsLog.Environment(appVersion: "1.0", appBuild: "7", osVersion: "26.0", phoneModel: "iPhone18,1")
        let data = diagnostics.bundle(device: device, battery: 64, charging: false, environment: environment)
        let object = try #require(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(object["schema_version"] as? Int == 2)
        #expect(object["device_id"] as? String == "dev-1")
        #expect(object["firmware"] as? String == "3.0.1")
        #expect(object["battery"] as? Int == 64)
        #expect(object["reconnection_count"] as? Int == 1)
        let history = try #require(object["disconnect_history"] as? [[String: Any]])
        #expect(history.first?["time_to_reconnect_ms"] as? Int == 5000)
        #expect(history.first?["event_type"] as? String == "disconnect")
    }
}

@MainActor
struct DeviceStoreDiagnosticsTests {
    @Test func linkEventsAndSignalAreRecorded() {
        let prefs = freshPreferences()
        let id = UUID()
        prefs.set(PairedDevice(id: id.uuidString, name: "Omi").encoded, for: .btDevice)
        let devices = DeviceStore(makeDriver: { FakeDriver() }, preferences: prefs, retryDelay: .seconds(60))
        devices.handle(.connected(id: id, name: "Omi"))
        devices.handle(.rssi(-62))
        devices.handle(.battery(90))
        devices.handle(.disconnected(id: id, error: "Peer removed pairing information"))
        devices.handle(.disconnected(id: id, error: nil))
        #expect(devices.diagnostics.latestSignal == -62)
        #expect(devices.diagnostics.battery.map(\.level) == [90])
        #expect(devices.diagnostics.events.map(\.kind) == [.disconnect, .failedConnect])
        #expect(devices.diagnostics.events.first?.reason == "Peer removed pairing information")
        devices.forget()
        #expect(devices.diagnostics.events.isEmpty)
    }

    /// A lesson sees the press first; the press then does nothing else.
    @Test func interceptorKeepsPressesFromTheirActions() {
        let devices = DeviceStore(makeDriver: { FakeDriver() }, preferences: freshPreferences())
        var actions: [ButtonAction] = []
        var seen: [OmiGATT.ButtonEvent] = []
        devices.onButtonAction = { actions.append($0) }
        devices.buttonInterceptor = { seen.append($0); return true }
        devices.handle(.button(Data([2, 0, 0, 0])))
        #expect(seen == [.doubleTap])
        #expect(actions.isEmpty)
        devices.buttonInterceptor = nil
        devices.handle(.button(Data([2, 0, 0, 0])))
        #expect(actions == [.endConversation])
    }
}

@MainActor
struct ButtonTutorialTests {
    let api = FakeAPIClient()
    let prefs = freshPreferences()

    func make() -> ButtonTutorialStore {
        let devices = DeviceStore(makeDriver: { FakeDriver() }, preferences: prefs)
        let chat = ChatStore(api: api, preferences: prefs)
        let askOmi = AskOmiStore(chat: chat, codec: { .opusFS320 }, haptic: { _ in }, canAsk: { devices.buttonActionsEnabled })
        return ButtonTutorialStore(devices: devices, askOmi: askOmi)
    }

    /// Asking practises the real question, even with button actions turned off.
    @Test func askLessonRecordsAQuestion() async {
        api.deviceActions.replyToVoice([
            .question(ChatMessage(id: "q", text: "What's next?", sender: .user, createdAt: .now)), .chat(.delta("Lunch.")),
        ])
        let tutorial = make()
        let (devices, askOmi) = (tutorial.devices, tutorial.askOmi)
        devices.buttonActionsEnabled = false
        tutorial.begin(.ask)
        devices.handle(.button(Data([1, 0, 0, 0])))
        #expect(askOmi.isListening)
        askOmi.ingest(Data([1, 2]))
        devices.handle(.button(Data([1, 0, 0, 0])))
        await askOmi.sendTask?.value
        #expect(askOmi.lastExchange == AskOmiStore.Exchange(question: "What's next?", answer: "Lunch."))
        tutorial.end(.doublePress)
        #expect(tutorial.lesson == .ask)
        tutorial.end(.ask)
        devices.handle(.button(Data([1, 0, 0, 0])))
        #expect(!askOmi.isListening)
    }

    /// Practice double presses count and save the choice; nothing ends, mutes or stars.
    @Test func doublePressLessonCountsAndSaves() {
        let tutorial = make()
        let devices = tutorial.devices
        var actions: [ButtonAction] = []
        devices.onButtonAction = { actions.append($0) }
        tutorial.begin(.doublePress)
        tutorial.choose(.toggleMute)
        #expect(prefs.integer(.doubleTapAction, default: 0) == 1)
        devices.handle(.button(Data([1, 0, 0, 0])))
        #expect(tutorial.singlePressHint)
        devices.handle(.button(Data([2, 0, 0, 0])))
        devices.handle(.button(Data([2, 0, 0, 0])))
        #expect(!tutorial.singlePressHint)
        #expect(tutorial.doublePresses == 2)
        #expect(actions.isEmpty)
        tutorial.choose(.star)
        #expect(tutorial.doublePresses == 0)
        #expect(tutorial.doublePressAction == .star)
        tutorial.end()
        devices.handle(.button(Data([2, 0, 0, 0])))
        #expect(actions == [.toggleStar])
    }
}

@MainActor
struct SpokenAnswerTests {
    let api = FakeAPIClient()
    let player = FakeSpeechPlayer()

    func make(mode: Int) -> (AskOmiStore, VoicePlaybackStore) {
        let prefs = freshPreferences()
        prefs.set(mode, for: .voiceResponseMode)
        let voice = VoicePlaybackStore(api: api, preferences: prefs, player: player, headphonesConnected: { false })
        let askOmi = AskOmiStore(
            chat: ChatStore(api: api, preferences: prefs), voice: voice, codec: { .opusFS320 }, haptic: { _ in }, canAsk: { true }
        )
        api.deviceActions.replyToVoice([
            .question(ChatMessage(id: "q", text: "Weather?", sender: .user, createdAt: .now)), .chat(.delta("Sunny all day.")),
        ])
        return (askOmi, voice)
    }

    func ask(_ askOmi: AskOmiStore) async {
        askOmi.handle(.askToggle)
        askOmi.ingest(Data([7]))
        askOmi.handle(.askToggle)
        await askOmi.sendTask?.value
    }

    /// "Always": the answer from the Omi's button is read aloud, so no notification goes out.
    @Test func buttonAnswersAreSpokenWhenTheModeAllows() async throws {
        let (askOmi, voice) = make(mode: 2)
        var notified: [String] = []
        askOmi.onAnswer = { notified.append($0) }
        await ask(askOmi)
        try await waitUntil { voice.playingID == nil && !player.played.isEmpty }
        #expect(player.played == ["Sunny all day."])
        #expect(notified.isEmpty)
    }

    /// "Off" (and "headphones only" without headphones): silent, the answer arrives as a notification.
    @Test func silentModesNotifyInstead() async {
        for mode in [0, 1] {
            let (askOmi, _) = make(mode: mode)
            var notified: [String] = []
            askOmi.onAnswer = { notified.append($0) }
            await ask(askOmi)
            #expect(notified == ["Sunny all day."])
        }
        #expect(api.chatExtras.speech.isEmpty)
    }

    /// A new question cuts off the answer still being read.
    @Test func aNewQuestionStopsTheVoice() {
        let (askOmi, _) = make(mode: 2)
        let stops = player.stops
        askOmi.handle(.askToggle)
        #expect(player.stops == stops + 1)
    }

    /// The same answer arriving from the chat and the button plays once.
    @Test func anAnswerAlreadyPlayingIsNotRestarted() {
        let prefs = freshPreferences()
        prefs.set(2, for: .voiceResponseMode)
        let voice = VoicePlaybackStore(api: api, preferences: prefs, player: player, headphonesConnected: { false })
        let message = ChatMessage(id: "a9", text: "Once.", sender: .omi, createdAt: .now)
        #expect(voice.answerArrived(message))
        let stops = player.stops
        #expect(voice.answerArrived(message))
        #expect(player.stops == stops)
    }

    /// Onboarding's preview plays whatever the mode, falling back to the system voice.
    @Test func replyPreviewIgnoresTheModeAndFallsBack() async throws {
        let prefs = freshPreferences()
        prefs.set(0, for: .voiceResponseMode)
        api.chatExtras.speechError = .http(status: 429, body: "")
        let voice = VoicePlaybackStore(api: api, preferences: prefs, player: player, headphonesConnected: { false })
        voice.previewReply("**Hello** there.")
        #expect(voice.playingID == VoicePlaybackStore.replyPreviewID)
        try await waitUntil { voice.playingID == nil }
        #expect(player.spoken == ["Hello there."])
        voice.setReplyMode(.always)
        #expect(voice.replyMode == .always)
    }
}
