import Foundation
import Observation
import OmiCore
import OmiDevice
import OmiNetwork
import OmiPersistence
import OmiService

/// Composition root: builds every client and store once and hands them to SwiftUI through
/// `.environment`. Nothing else in the app creates services; there are no singletons.
@MainActor
@Observable
final class AppEnvironment {
    let configuration: AppConfiguration
    let api: any APIClientProtocol
    let session: SessionStore
    let conversations: ConversationsStore
    let tasks: TasksStore
    let goals: GoalsStore
    /// Two-way sync of tasks with an "Omi" list in Apple Reminders.
    let reminders: RemindersSyncStore
    let memories: MemoriesStore
    let chat: ChatStore
    /// Omi's answers read aloud, and the voice preview in Settings › Assistant.
    let voice: VoicePlaybackStore
    let agent: AgentStore
    let capture: CaptureStore
    let devices: DeviceStore
    /// Speaking a question into the chat (the Ask bar's mic): transcription only, nothing saved.
    let dictation: VoiceIntroStore
    let firmware: FirmwareStore
    let sync: SyncStore
    /// The Apple Watch companion: recordings started on the watch.
    let watch: WatchStore
    /// Questions asked by pressing the Omi's button.
    let askOmi: AskOmiStore
    /// The Omi button lessons (onboarding, My Devices › How to use your Omi).
    let buttonTutorial: ButtonTutorialStore
    /// My Devices › Diagnostics: share the bundle or send it to support.
    let diagnosticsReport: DiagnosticsReportStore
    let capabilities: CapabilitiesStore
    let settings: SettingsStore
    /// "Who is this?" prompts, voice-learning switches, ignored voices.
    let voices: VoicesStore
    /// Settings › Developer: webhooks, keys, experimental switches.
    let developer: DeveloperStore
    /// Capture, transcription and sync events (Developer logs, the transcription log).
    let log: DebugLog
    /// The app store: browse, an app's page, reviews, payment.
    let catalog: AppCatalogStore
    /// Where task apps file new tasks.
    let taskApps: TaskAppSettingsStore
    // --- Phone calls (begin) ---
    /// Calls through Omi: Twilio Voice + CallKit (App/PhoneCalls), live transcript, number setup.
    let phoneCalls: PhoneCallStore
    // --- Phone calls (end) ---
    let preferences: Preferences
    let auth: any AuthServicing

    // --- Location, Apple Health, naming voices live (begin) ---

    /// Where recordings start (When In Use), sent with each conversation.
    let location: LocationStore
    /// Settings › Capabilities › Apple Health.
    let health: AppleHealthStore
    /// "Who is this?" on the live transcript.
    let liveSpeakers: LiveSpeakersStore

    // --- Location, Apple Health, naming voices live (end) ---

    /// Settings › Listening › Advanced transcription: the user's own speech-to-text provider.
    let customSTT: CustomSTTSettings

    // The composition root builds every store in one place; the stores keep growing, so does this.
    // swiftlint:disable:next function_body_length
    init(
        configuration: AppConfiguration,
        auth: any AuthServicing,
        api: any APIClientProtocol,
        preferences: Preferences
    ) {
        self.configuration = configuration
        self.api = api
        self.preferences = preferences
        self.auth = auth
        capabilities = CapabilitiesStore(api: api)
        settings = SettingsStore(api: api, preferences: preferences)
        voices = VoicesStore(api: api)
        developer = DeveloperStore(api: api, preferences: preferences, apiBaseURL: configuration.apiBaseURL)
        log = DebugLog(preferences: preferences)
        taskApps = TaskAppSettingsStore(api: api, preferences: preferences)
        session = SessionStore(auth: auth, api: api, configuration: configuration, preferences: preferences)
        conversations = ConversationsStore(api: api, preferences: preferences)
        tasks = TasksStore(api: api, defaults: .standard, log: log)
        (goals, reminders) = (GoalsStore(api: api), Self.makeReminders(api: api, tasks: tasks))
        memories = MemoriesStore(api: api)
        chat = ChatStore(api: api, preferences: preferences)
        voice = VoicePlaybackStore(api: api, preferences: preferences)
        agent = AgentStore(api: api, preferences: preferences)
        let session = session
        capture = CaptureStore(
            api: api, engine: LivePhoneCaptureEngine(
                audioFile: DebugLaunchOptions.current.captureAudioFile,
                fixtureTranscript: DebugLaunchOptions.current.captureTranscript,
                language: { [preferences] in TranscriptionLanguage.recognizer(preferences) }
            ),
            deviceEngine: LiveDeviceTranscriptionEngine(language: { [preferences] in TranscriptionLanguage.recognizer(preferences) }),
            preferences: preferences,
            // The local harness has no server STT; the on-device recognizer stands in.
            // The server transcribes by default, as in production; Settings › Capture switches to the iPhone.
            defaultOnDevice: false,
            userID: {
                switch session.phase {
                case let .ready(userID), let .onboarding(userID): userID
                default: nil
                }
            }
        )
        phoneCalls = Self.makePhoneCalls(api: api, session: session, preferences: preferences, conversations: conversations)
        dictation = VoiceIntroStore(
            api: api,
            recognizer: AppleLiveRecognizer(fixtureTranscript: DebugLaunchOptions.current.captureTranscript),
            phoneInput: PhoneVoiceInput(audioFile: DebugLaunchOptions.current.captureAudioFile),
            deviceInput: { PhoneVoiceInput() }
        )
        devices = Self.makeDevices(preferences: preferences)
        firmware = FirmwareStore(api: api, devices: devices, updater: McuFirmwareUpdater(), preferences: preferences)
        let signedIn = Self.signedInUser(session)
        sync = SyncStore(api: api, directory: SyncStore.defaultDirectory, userID: signedIn)
        // A read off the Omi and an upload both keep the app awake if it is put down mid-transfer.
        sync.lease = .app(name: "OmiSyncTransfer", log: log)
        catalog = AppCatalogStore(api: api, capabilities: capabilities, userID: signedIn)
        watch = Self.makeWatch(capture: capture, session: session, devices: devices)
        askOmi = Self.makeAskOmi(chat: chat, voice: voice, devices: devices, capture: capture, preferences: preferences)
        buttonTutorial = ButtonTutorialStore(devices: devices, askOmi: askOmi)
        diagnosticsReport = DiagnosticsReportStore(api: api, devices: devices)
        // --- Location, Apple Health, naming voices live (begin) ---
        (location, health) = (LocationStore(provider: CoreLocationProvider(), api: api), Self.makeHealth(api, preferences))
        liveSpeakers = Self.makeLiveSpeakers(api: api, capture: capture, location: location)
        // --- Location, Apple Health, naming voices live (end) ---
        customSTT = CustomSTTSettings(preferences: preferences, secrets: KeychainSecretStore())
        wire()
        // Right away: the watch can launch the app in the background to record.
        watch.start()
    }

    private func wire() {
        wireCapture()
        wireDevice()
        wireSync()
        wireButton()
        wireTranscription()
        #if DEBUG
            DebugAskOmi.start(askOmi: askOmi, tutorial: buttonTutorial)
        #endif
    }

    /// The user's own speech-to-text provider takes the audio when one is set.
    private func wireTranscription() {
        let log = log
        capture.customSTT = customSTT
        capture.makeCustomTranscriber = { config in
            CustomTranscriber(config: config, transport: URLSessionCustomSTTTransport(), log: log)
        }
    }

    /// What a background wake-up does (`App/System/BackgroundTasks.swift`).
    func makeBackgroundWork() -> BackgroundWork {
        let sync = sync
        let conversations = conversations
        let tasks = tasks
        let session = session
        return BackgroundWork(
            isSignedIn: {
                // Woken before any window: the persisted session is read here (no network).
                if session.phase == .launching { session.restore() }
                if case .ready = session.phase { return true }
                return false
            },
            uploadRecordings: { await sync.uploadPending() },
            refreshLists: {
                await conversations.load()
                await tasks.load()
            },
            log: log
        )
    }

    /// The signed-in account (sync and the app store act only for it).
    private static func signedInUser(_ session: SessionStore) -> () -> String? {
        {
            if case let .ready(userID) = session.phase { return userID }
            return nil
        }
    }

    // --- Location, Apple Health, naming voices live (begin) ---

    private static func makeHealth(_ api: any APIClientProtocol, _ preferences: Preferences) -> AppleHealthStore {
        AppleHealthStore(api: api, reader: HealthKitReader(), preferences: preferences)
    }

    /// Each recording asks `location` where it starts; the live transcript names voices.
    private static func makeLiveSpeakers(api: any APIClientProtocol, capture: CaptureStore, location: LocationStore) -> LiveSpeakersStore {
        capture.recordingLocation = { await location.snapshotForRecording() }
        return LiveSpeakersStore(api: api, capture: capture)
    }

    // --- Location, Apple Health, naming voices live (end) ---

    /// Recordings started on the Apple Watch, once the session is ready (it may still be restoring
    /// when the watch launched the app); the watch shows the Omi's battery.
    private static func makeWatch(capture: CaptureStore, session: SessionStore, devices: DeviceStore) -> WatchStore {
        WatchStore(
            link: WatchSession(), capture: capture,
            isSignedIn: {
                switch session.phase {
                case .ready: true
                case .launching: nil
                default: false
                }
            },
            omiBattery: { devices.connection == .connected ? devices.battery : nil }
        )
    }

    /// Wearable audio flows into capture; finished conversations refresh the lists.
    private func wireCapture() {
        let capture = capture
        let conversations = conversations
        let tasks = tasks
        let session = session
        // Capture begins in the app; during onboarding the Omi only feeds the voice sample.
        devices.onReady = { codec in
            guard case .ready = session.phase else { return }
            Task { await capture.startDevice(codec: codec) }
        }
        DeviceToolsPerformer.wire(agent: agent, chat: chat, log: log)
        devices.onAudio = { frame in capture.ingestDeviceAudio(frame) }
        devices.onDisconnect = { capture.deviceDisconnected() }
        devices.onDoubleTap = { Task { await capture.endDeviceConversation() } }
        capture.onConversationFinished = {
            await conversations.load()
            await tasks.load()
        }
    }

    /// Export › Reminders adds through EventKit; a sync that changed tasks reloads the list.
    private static func makeReminders(api: any APIClientProtocol, tasks: TasksStore) -> RemindersSyncStore {
        let reminders = RemindersSyncStore(api: api, adapter: EventKitReminders())
        tasks.reminderExporter = { task in await reminders.addReminder(for: task) }
        reminders.onTasksChanged = { await tasks.load() }
        return reminders
    }

    /// The firmware check runs when the Omi reports its version; low battery notifies once.
    private func wireDevice() {
        let firmware = firmware
        let devices = devices
        devices.onDeviceInfo = { firmware.deviceInfoChanged() }
        devices.onLowBattery = { [weak devices] level in DeviceNotifications.lowBattery(level, deviceName: devices?.paired?.name) }
    }

    /// What the Omi recorded while out of range syncs whenever it is connected, next to live audio.
    private func wireSync() {
        let sync = sync
        let capture = capture
        sync.link = devices
        // The phone mic records to a file when it cannot stream (offline, Transcribe later).
        capture.phoneBuffer = sync
        capture.log = log
        devices.onStorage = { sync.handle($0) }
        let startCapture = devices.onReady
        devices.onReady = { codec in
            startCapture?(codec)
            sync.codecKnown()
        }
        devices.onDisconnect = {
            capture.deviceDisconnected()
            sync.deviceDisconnected()
        }
    }

    /// Answers are read aloud as Settings › Assistant › Spoken replies allows. The question is
    /// transcribed on the iPhone in the language the user speaks first.
    private static func makeAskOmi(
        chat: ChatStore, voice: VoicePlaybackStore, devices: DeviceStore, capture: CaptureStore, preferences: Preferences
    ) -> AskOmiStore {
        AskOmiStore(
            chat: chat,
            voice: voice,
            codec: { devices.connection == .connected ? devices.codec : nil },
            haptic: { devices.playHaptic($0) },
            canAsk: { devices.buttonActionsEnabled && !capture.isDeviceMuted },
            recognizer: AppleLiveRecognizer(fixtureTranscript: DebugLaunchOptions.current.askTranscript),
            language: { TranscriptionLanguage.recognizer(preferences) },
            sharedLine: { capture.iPhoneLineFromOmi }
        )
    }

    /// The Omi's button: double tap ends, stars or mutes; a single press asks Omi (`ButtonAction`).
    private func wireButton() {
        let capture = capture
        let askOmi = askOmi
        devices.onButtonAction = { action in
            switch action {
            case .toggleStar: capture.toggleStar()
            case .toggleMute: capture.isDeviceMuted.toggle()
            case .askToggle, .askHoldStart, .askHoldEnd: askOmi.handle(action)
            // `onDoubleTap` (wireCapture) finalizes the conversation.
            case .endConversation: break
            }
        }
        let audio = devices.onAudio
        devices.onAudio = { frame in
            audio?(frame)
            askOmi.ingest(frame)
        }
        let disconnect = devices.onDisconnect
        devices.onDisconnect = {
            disconnect?()
            askOmi.cancel()
        }
        askOmi.onAnswer = { DeviceNotifications.answer($0) }
    }

    // --- Phone calls (begin) ---
    /// A finished call is a new conversation on Home.
    private static func makePhoneCalls(
        api: any APIClientProtocol, session: SessionStore, preferences: Preferences, conversations: ConversationsStore
    ) -> PhoneCallStore {
        let store = PhoneCallStore(
            api: api, engine: TwilioPhoneCallEngine(),
            userID: {
                if case let .ready(userID) = session.phase { return userID }
                return nil
            },
            // Flutter: the primary language when set, otherwise multi-language detection.
            language: { preferences.string(.userPrimaryLanguage) ?? "multi" }
        )
        store.onCallFinished = { await conversations.load() }
        return store
    }
    // --- Phone calls (end) ---

    func makeOnboarding() -> OnboardingStore {
        let auth = auth
        let store = OnboardingStore(
            api: api, preferences: preferences, voice: makeVoiceIntro(),
            buttonTutorial: buttonTutorial, watch: watch, watchPaired: DebugLaunchOptions.current.watchPaired.map { paired in { paired } },
            updateDisplayName: { try? await auth.updateDisplayName($0) }
        )
        if let name = DebugLaunchOptions.current.onboardingStep,
           let step = OnboardingStore.Step.allCases.first(where: { name == "\($0)" }) {
            if step.rawValue > OnboardingStore.Step.hasOmi.rawValue {
                store.hasOmi = DebugLaunchOptions.current.onboardingHasOmi ?? (devices.paired != nil)
            }
            store.step = step
        }
        return store
    }

    /// The Omi driver; `-omiFakeDevice nearby|connected` swaps in a pretend one (Debug only).
    private static func makeDevices(preferences: Preferences) -> DeviceStore {
        switch DebugLaunchOptions.current.fakeDevice {
        case "connected":
            preferences.set(DebugDeviceDriver.pairedJSON, for: .btDevice)
            return DeviceStore(makeDriver: { DebugDeviceDriver() }, preferences: preferences)
        case "nearby":
            preferences.set(nil, for: .btDevice)
            return DeviceStore(makeDriver: { DebugDeviceDriver() }, preferences: preferences)
        default:
            return DeviceStore(makeDriver: { OmiDeviceManager() }, preferences: preferences)
        }
    }

    static func live() -> AppEnvironment {
        let configuration = AppConfiguration.fromInfoDictionary(Bundle.main.infoDictionary ?? [:])
        let auth = FirebaseAuthService(emulator: configuration.authEmulator)
        let api = APIClient(configuration: configuration, tokens: FirebaseTokenProvider())
        return AppEnvironment(configuration: configuration, auth: auth, api: api, preferences: Preferences())
    }
}
