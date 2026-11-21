package com.friend.ios

import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import com.friend.ios.core.AppConfiguration
import com.friend.ios.network.APIClient
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.persistence.Preferences
import com.friend.ios.service.LocalMemoriesStore
import com.friend.ios.service.LocalPreferences
import com.friend.ios.service.LocalSessionStore
import com.friend.ios.service.stores.MemoriesStore
import com.friend.ios.service.stores.playHaptic
import com.friend.ios.service.stores.SessionStore
// port-home
import com.friend.ios.service.LocalConversationsStore
import com.friend.ios.service.LocalGoalsStore
import com.friend.ios.service.LocalTasksStore
import com.friend.ios.service.stores.ConversationsStore
import com.friend.ios.service.stores.GoalsStore
import com.friend.ios.service.stores.TasksStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import java.net.URI

/**
 * Port of `AppEnvironment.swift`: the composition root. Builds every store once and provides
 * them to the UI (`Provide`). No singletons beyond this object, held by the Application.
 */
class AppEnvironment(context: Context, val configuration: AppConfiguration) {
    /** Stores live as long as the process, on the main thread like `@MainActor` on iOS. */
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    val preferences = Preferences(context)
    val auth = FirebaseAuthService()
    val api: APIClientProtocol = APIClient(configuration, FirebaseTokenProvider())

    val session = SessionStore(auth, api, configuration, preferences)
    val memories = MemoriesStore(api, scope)
    // Chat (port-chat)
    val chat = com.friend.ios.service.stores.ChatStore(api, preferences, scope)
    val agent = com.friend.ios.service.stores.AgentStore(api, preferences, scope)
    // port-home: snoozes, the tidy-up's day and "For you" stops live in `UserDefaults.standard` on iOS.
    private val defaults = context.getSharedPreferences("omi.native", Context.MODE_PRIVATE)
    val conversations = ConversationsStore(api, scope, preferences = preferences, defaults = defaults)
    val tasks = TasksStore(api, defaults = defaults, scope = scope)
    val goals = GoalsStore(api, scope)
    // Settings (port-settings)
    val settings = com.friend.ios.service.stores.SettingsStore(api, preferences, scope, context.cacheDir)
    val voices = com.friend.ios.service.stores.VoicesStore(api) // port-settings A
    // Settings > Apps (port-settings fork B)
    val capabilities = com.friend.ios.service.stores.CapabilitiesStore(api)
    val appCatalog = com.friend.ios.service.stores.AppCatalogStore(api, capabilities, { session.userID })
    val developer = com.friend.ios.service.stores.DeveloperStore(api, preferences, configuration.apiBaseURL.toString())
    /** What capture, transcription and sync did (Settings > Developer > Logs, the transcription log). */
    val log = com.friend.ios.service.DebugLog(preferences, com.friend.ios.service.DebugLog.defaultDirectory(context.filesDir))
    // Capture (and-capture): phone mic -> /v4/listen -> live transcript; the recording notification.
    val microphonePermission = ActivityMicrophonePermission(context.applicationContext)
    val capture = com.friend.ios.service.stores.CaptureStore(
        api = api,
        engine = com.friend.ios.service.LivePhoneCaptureEngine(
            com.friend.ios.audio.PhoneMicCapture(context.applicationContext as android.app.Application), microphonePermission,
            // Debug: `--es omiCaptureAudioFile <path>` plays a 16 kHz PCM16 WAV instead of the microphone.
            audioFile = {
                com.friend.ios.features.components.DebugLaunch.string("omiCaptureAudioFile")
                    ?.takeIf { BuildConfig.DEBUG }?.let { path -> java.io.File(path) }?.takeIf { it.canRead() }
            },
            // and-transcribe: the phone's recognizer (on-device mode, and the live preview) in the user's language.
            makeTranscriber = {
                val app = context.applicationContext
                if (com.friend.ios.audio.OnDeviceTranscriber.isSupported(app)) {
                    com.friend.ios.audio.OnDeviceTranscriber(app, com.friend.ios.service.TranscriptionLanguage.recognizer(preferences))
                } else {
                    null
                }
            },
            onDeviceSupported = { com.friend.ios.audio.OnDeviceTranscriber.isSupported(context.applicationContext) },
        ),
        // The Omi's opus, decoded on the phone, through the same recognizer (on-device mode, the live preview).
        deviceEngine = com.friend.ios.service.LiveDeviceTranscriptionEngine(
            isPermitted = {
                androidx.core.content.ContextCompat.checkSelfPermission(context.applicationContext, android.Manifest.permission.RECORD_AUDIO) ==
                    android.content.pm.PackageManager.PERMISSION_GRANTED
            },
            makeTranscriber = {
                val app = context.applicationContext
                if (com.friend.ios.audio.OnDeviceTranscriber.isSupported(app)) {
                    com.friend.ios.audio.OnDeviceTranscriber(app, com.friend.ios.service.TranscriptionLanguage.recognizer(preferences))
                } else {
                    null
                }
            },
            makeDecoder = com.friend.ios.voice.PlatformOpusDecoder::make,
        ),
        preferences = preferences,
        defaultOnDevice = false,
        userID = { session.userID },
        scope = scope,
        // The session signals Android gives (config callback, audio mode, devices, foregrounding),
        // so a recording never stops without the app knowing why (`CaptureStoreInterruption.kt`).
        audioSession = com.friend.ios.audio.AndroidAudioSessionMonitor(context.applicationContext as android.app.Application),
    ).apply {
        onConversationFinished = { conversations.load() }
        log = { level, tag, message ->
            val warning = level == com.friend.ios.service.stores.CaptureStore.LogLevel.Warning
            if (warning) android.util.Log.w("omi.$tag", message) else android.util.Log.i("omi.$tag", message)
            this@AppEnvironment.log.add(
                if (warning) com.friend.ios.service.DebugLog.Entry.Level.Warning else com.friend.ios.service.DebugLog.Entry.Level.Info, tag, message,
            )
        }
    }
    val liveSpeakers = com.friend.ios.service.stores.LiveSpeakersStore(api, capture)

    // The Omi wearable (and-device). Lazy: the debug launch extras (`omiFakeDevice`) are read after
    // the Application builds this object, and only a screen or the BLE service touches them.
    private val appContext = context.applicationContext
    private val devicesLazy = lazy { makeDevices().also { wireDevice(it) } }
    val devices: com.friend.ios.service.stores.DeviceStore by devicesLazy
    val firmware: com.friend.ios.service.stores.FirmwareStore by lazy {
        com.friend.ios.service.stores.FirmwareStore(
            api, devices, com.friend.ios.device.McuFirmwareUpdater(appContext), preferences, scope,
            download = com.friend.ios.service.stores.FirmwareStore.downloadPackage(appContext.cacheDir),
        )
    }
    val sync: com.friend.ios.service.stores.SyncStore by lazy {
        com.friend.ios.service.stores.SyncStore(
            api, com.friend.ios.service.stores.SyncStore.defaultDirectory(appContext.filesDir), scope, userID = { session.userID },
        ).also {
            it.decodeOpus = com.friend.ios.voice.OpusFileDecoder::decode // play and share Omi recordings (and-askomi)
            // A read off the Omi and an upload both keep the app running if it is put away mid-transfer.
            it.lease = com.friend.ios.system.TransferForegroundService.lease(appContext, it, scope, log)
        }
    }
    /** Ask Omi with the Omi's button (and-askomi); the ask lesson practises with it. */
    val askOmi: com.friend.ios.service.stores.AskOmiStore by lazy { makeAskOmi() }
    val buttonTutorial by lazy { com.friend.ios.service.stores.ButtonTutorialStore(devices, askOmi) }
    val diagnosticsReport by lazy {
        com.friend.ios.service.stores.DiagnosticsReportStore(
            api, devices,
            com.friend.ios.service.stores.DeviceDiagnosticsLog.Environment(
                appVersion = BuildConfig.VERSION_NAME, appBuild = BuildConfig.VERSION_CODE.toString(),
                osVersion = android.os.Build.VERSION.RELEASE, phoneModel = "${android.os.Build.MANUFACTURER} ${android.os.Build.MODEL}",
            ),
        )
    }

    /** The Omi driver; `--es omiFakeDevice nearby|connected` swaps in a pretend one (debug only). */
    private fun makeDevices(): com.friend.ios.service.stores.DeviceStore {
        val fake = if (BuildConfig.DEBUG) com.friend.ios.features.components.DebugLaunch.string("omiFakeDevice") else null
        when (fake) {
            "connected" -> preferences.set(Preferences.Key.BtDevice, DebugDeviceDriver.pairedJSON)
            "nearby" -> preferences.set(Preferences.Key.BtDevice, null)
        }
        val makeDriver: () -> com.friend.ios.device.DeviceDriving =
            if (fake != null) ({ DebugDeviceDriver() }) else ({ com.friend.ios.device.OmiDeviceManager(appContext) })
        return com.friend.ios.service.stores.DeviceStore(makeDriver, preferences, scope).also { store ->
            // Pairing asks for the companion association first (and-askomi); the fake device needs none.
            if (fake == null) store.associate = { address -> companionPairing.associate(address) }
        }
    }

    /** The system's companion association, asked when pairing (and-askomi). */
    val companionPairing = com.friend.ios.system.CompanionPairing(context.applicationContext)

    /**
     * `wireDevice` + `wireSync` + the capture wiring of `AppEnvironment.swift`: audio to capture,
     * offline storage to sync, the firmware check on device info, low battery notifies once.
     */
    private fun wireDevice(devices: com.friend.ios.service.stores.DeviceStore) {
        devices.onReady = { codec ->
            com.friend.ios.network.listen.ListenSocket.Options.Codec.from(codec.listenValue)?.let { listen ->
                scope.launch { capture.startDevice(listen, codec.sampleRate) }
            }
            sync.codecKnown()
        }
        devices.onAudio = { frame ->
            capture.ingestDeviceAudio(frame)
            askOmi.ingest(frame)
        }
        devices.onDisconnect = {
            capture.deviceDisconnected()
            sync.deviceDisconnected()
            askOmi.cancel()
        }
        devices.onDoubleTap = { scope.launch { capture.endDeviceConversation() } }
        // The Omi's button: double tap ends, stars or mutes; a single press asks Omi (`ButtonAction`).
        devices.onButtonAction = { action ->
            when (action) {
                com.friend.ios.service.stores.ButtonAction.ToggleMute -> capture.isDeviceMuted = !capture.isDeviceMuted
                com.friend.ios.service.stores.ButtonAction.ToggleStar -> capture.toggleStar()
                com.friend.ios.service.stores.ButtonAction.AskToggle, com.friend.ios.service.stores.ButtonAction.AskHoldStart,
                com.friend.ios.service.stores.ButtonAction.AskHoldEnd -> askOmi.handle(action)
                // `onDoubleTap` finalizes the conversation.
                com.friend.ios.service.stores.ButtonAction.EndConversation -> Unit
            }
        }
        devices.onDeviceInfo = { firmware.deviceInfoChanged() }
        devices.onLowBattery = { level -> DeviceNotifications.lowBattery(appContext, level, devices.paired?.name) }
        devices.onStorage = { sync.handle(it) }
        sync.link = devices
        // The system started the BLE service on its own (reboot, Omi in range): connect.
        com.friend.ios.ble.OmiBleForegroundService.onStart = { scope.launch { devices.start() } }
        com.friend.ios.ble.OmiBleForegroundService.statusText = {
            com.friend.ios.design.Strings.get(
                appContext,
                if (devices.connection == com.friend.ios.service.stores.DeviceStore.Connection.Connected) "nativeConnected" else "nativeConnecting",
            )
        }
    }

    // The watch (and-wear): recordings started on the Wear OS watch, once the session is ready (it
    // may still be restoring when the watch started the app); the watch shows the Omi's battery.
    val watchSession = WatchSession(appContext, scope)
    val watch = com.friend.ios.service.watch.WatchStore(
        link = watchSession, capture = capture,
        isSignedIn = {
            when (session.phase) {
                is SessionStore.Phase.Ready -> true
                SessionStore.Phase.Launching -> null
                else -> false
            }
        },
        // Only once something built the Omi's store (the debug fake reads launch extras first).
        omiBattery = {
            if (!devicesLazy.isInitialized()) null
            else devices.let { if (it.connection == com.friend.ios.service.stores.DeviceStore.Connection.Connected) it.battery else null }
        },
        scope = scope,
    ).also {
        // Right away: the watch can start the app in the background to record.
        it.start()
    }
    init {
        // The recording notification (the iOS Live Activity), whatever records.
        LiveCaptureNotifier(context.applicationContext, capture, scope, watchName = { watch.info?.name }).start()
    }
    // --- Phone calls (begin) (and-calls) ---
    /** Calls through Omi: Twilio Voice + Telecom (`:calls`), live transcript, number setup. A finished call is a new conversation on Home. */
    val phoneCalls = com.friend.ios.service.stores.PhoneCallStore(
        api = api,
        engine = com.friend.ios.phonecalls.TwilioPhoneCallEngine(appContext, microphonePermission),
        userID = { session.userID },
        // Flutter: the primary language when set, otherwise multi-language detection.
        language = { preferences.string(Preferences.Key.UserPrimaryLanguage) ?: "multi" },
        scope = scope,
    ).apply { onCallFinished = { conversations.load() } }
    init {
        com.friend.ios.phonecalls.PhoneCallForegroundService.channelName = { com.friend.ios.design.Strings.get(appContext, "nativeSettingsPhoneCalls") }
        com.friend.ios.phonecalls.PhoneCallForegroundService.hangUpTitle = { com.friend.ios.design.Strings.get(appContext, "phoneEndCall") }
        com.friend.ios.phonecalls.PhoneCallForegroundService.smallIcon = R.mipmap.ic_stat_launcher
    }
    // --- Phone calls (end) ---

    // Onboarding (and-onboarding)
    /** Spoken replies and their previews (onboarding's voice reply step, Settings > Assistant). */
    val playback = com.friend.ios.service.stores.VoicePlaybackStore(
        preferences, com.friend.ios.voice.SystemSpeechPlayer(appContext), scope,
        synthesize = { text, voiceID -> api.synthesizeSpeech(text, voiceID) },
        headphonesConnected = { com.friend.ios.voice.AudioRoute.isPrivate(appContext) },
    )

    /**
     * Answers are read aloud as Settings > Assistant > Spoken replies allows. The question is
     * transcribed on the phone in the language the user speaks first.
     */
    private fun makeAskOmi(): com.friend.ios.service.stores.AskOmiStore {
        val transcript = com.friend.ios.features.components.DebugLaunch.string("omiAskTranscript")?.takeIf { BuildConfig.DEBUG }
        val store = com.friend.ios.service.stores.AskOmiStore(
            chat = chat,
            scope = scope,
            voice = playback,
            codec = { if (devices.connection == com.friend.ios.service.stores.DeviceStore.Connection.Connected) devices.codec else null },
            haptic = { pulse -> devices.playHaptic(pulse) },
            canAsk = { devices.buttonActionsEnabled && !capture.isDeviceMuted },
            recognizer = transcript?.let { com.friend.ios.voice.ScriptedRecognizer(it) } ?: com.friend.ios.voice.AndroidLiveRecognizer(appContext),
            language = { com.friend.ios.service.TranscriptionLanguage.recognizer(preferences) },
            makeDecoder = com.friend.ios.voice.DeviceVoiceInput::frameDecoder,
        )
        store.onAnswer = { text -> com.friend.ios.system.DeviceNotifications.answer(appContext, text) }
        return store
    }

    // Device tools ("Omi asks") and run-ended notifications (and-askomi).
    val deviceTools = com.friend.ios.system.DeviceToolsPerformer.wire(appContext, agent, chat)
    init {
        // The run Omi works on, outside the app (the iOS agent Live Activity).
        com.friend.ios.system.AgentRunNotifier(appContext, agent, scope).start()
    }
    /** The chat's dictation (iOS `AppEnvironment.dictation`): the phone microphone, words on the phone. */
    val dictation: com.friend.ios.service.stores.VoiceIntroStore by lazy { makeVoiceIntro() }

    /** Onboarding's (and Settings' voice screen's) listening session. */
    fun makeVoiceIntro() = com.friend.ios.service.stores.VoiceIntroStore(
        api, com.friend.ios.voice.AndroidLiveRecognizer(appContext), com.friend.ios.voice.PhoneVoiceInput(appContext),
        deviceInput = { com.friend.ios.voice.DeviceVoiceInput(devices) }, scope = scope,
    )

    /** `-omiOnboardingStep <step>` (and `-omiOnboardingHasOmi`) opens onboarding on that step. */
    fun makeOnboarding(): com.friend.ios.service.stores.OnboardingStore {
        val store = com.friend.ios.service.stores.OnboardingStore(
            api, preferences, scope, voice = makeVoiceIntro(), buttonTutorial = buttonTutorial,
            playback = playback,
            watch = watch,
            watchPaired = { DebugLaunchOptions.current.watchPaired ?: watch.link.isWatchPaired },
            updateDisplayName = { runCatching { auth.updateDisplayName(it) } },
        )
        val options = DebugLaunchOptions.current
        val step = options.onboardingStep?.let { com.friend.ios.service.stores.OnboardingStore.Step.from(it) }
        if (step != null) {
            if (step.ordinal > com.friend.ios.service.stores.OnboardingStore.Step.HasOmi.ordinal) {
                store.hasOmi = options.onboardingHasOmi ?: (devices.paired != null)
            }
            store.step = step
        }
        return store
    }
    // System (and-onboarding): links, push, widgets, launcher shortcuts.
    val deepLinks = com.friend.ios.system.DeepLinkRouter()
    val push = com.friend.ios.system.PushNotifications(context, api, preferences, scope)
    /** Launcher shortcuts and widgets, kept in step with the stores. */
    init {
        com.friend.ios.system.SupportChat.configure()
    }
    val system = com.friend.ios.system.SystemIntegration(context, scope, session, tasks, conversations, push, devices = { devices }).also { it.start() }

    // --- Transcription, offline, health (and-transcribe) (begin) ---
    init {
        // `wireSync` (after `sync` above): the phone mic records to a file when it cannot stream
        // (offline, Transcribe later); Store audio on phone keeps a copy.
        capture.phoneBuffer = com.friend.ios.service.stores.SyncStorePhoneAudio(sync)
    }

    /** Health Connect's permission screen (attached by `MainActivity`). */
    val healthPermission = HealthConnectPermission()
    val health = com.friend.ios.service.stores.AppleHealthStore(api, HealthConnectReader(appContext, healthPermission), preferences)
    val location = com.friend.ios.service.stores.LocationStore(FusedLocationProvider(appContext), api, scope)
    val customSTT = com.friend.ios.service.customstt.CustomSTTSettings(preferences, KeystoreSecretStore(appContext))
    init {
        // Each recording asks `location` where it starts (the listen socket's geolocation header).
        capture.recordingLocation = { location.snapshotForRecording()?.headerValue }
        // `wireTranscription`: the user's own speech-to-text provider takes the audio when one is set.
        capture.customSTT = customSTT
        // The Omi's opus reaches the user's own provider through the platform decoder (as for playback).
        capture.makeOpusDecoder = com.friend.ios.voice.PlatformOpusDecoder::make
        capture.makeCustomTranscriber = { config ->
            com.friend.ios.service.customstt.CustomTranscriber(
                config, com.friend.ios.network.customstt.OkHttpCustomSTTTransport(), scope,
                log = { warning, message ->
                    if (warning) android.util.Log.w("omi.stt", message) else android.util.Log.i("omi.stt", message)
                    log.add(if (warning) com.friend.ios.service.DebugLog.Entry.Level.Warning else com.friend.ios.service.DebugLog.Entry.Level.Info, "stt", message)
                },
            )
        }
        // `OmiApp.swift` scenePhase .active: fresh health numbers for the chat while connected (hourly at most).
        androidx.lifecycle.ProcessLifecycleOwner.get().lifecycle.addObserver(
            androidx.lifecycle.LifecycleEventObserver { _, event ->
                if (event == androidx.lifecycle.Lifecycle.Event.ON_START && session.userID != null) {
                    scope.launch { health.syncIfConnected() }
                }
            },
        )
    }
    // --- Transcription, offline, health (and-transcribe) (end) ---

    @Composable
    fun Provide(content: @Composable () -> Unit) {
        CompositionLocalProvider(
            LocalPreferences provides preferences,
            LocalSessionStore provides session,
            LocalMemoriesStore provides memories,
            // Settings > Voices "Record your voice again": onboarding's voice step (iOS's `voiceScreen`).
            com.friend.ios.features.onboarding.LocalVoiceIntroFactory provides ::makeVoiceIntro,
            // Chat (port-chat)
            com.friend.ios.service.LocalChatStore provides chat,
            com.friend.ios.service.LocalAgentStore provides agent,
            // port-home
            LocalConversationsStore provides conversations,
            LocalTasksStore provides tasks,
            LocalGoalsStore provides goals,
            // Settings (port-settings)
            com.friend.ios.service.LocalSettingsStore provides settings,
            com.friend.ios.service.LocalDeveloperStore provides developer,
            com.friend.ios.service.LocalDebugLog provides log,
            com.friend.ios.service.LocalCapabilitiesStore provides capabilities,
            com.friend.ios.service.LocalAppCatalogStore provides appCatalog,
            com.friend.ios.service.LocalVoicesStore provides voices, // port-settings A
            com.friend.ios.system.LocalDeepLinkRouter provides deepLinks, // system (and-onboarding)
            // Help offers the support chat only when Intercom is configured.
            com.friend.ios.features.settings.LocalSupportChat provides
                (if (com.friend.ios.system.SupportChat.isConfigured) com.friend.ios.system.SupportChat::present else null),
            com.friend.ios.service.LocalDictation provides dictation, // chat dictation (and-onboarding)
            // The Omi wearable (and-device)
            com.friend.ios.service.LocalDeviceStore provides devices,
            com.friend.ios.service.LocalFirmwareStore provides firmware,
            com.friend.ios.service.LocalSyncStore provides sync,
            com.friend.ios.service.LocalButtonTutorialStore provides buttonTutorial,
            com.friend.ios.service.LocalDiagnosticsReportStore provides diagnosticsReport,
            // Capture (and-capture)
            com.friend.ios.service.LocalCaptureStore provides capture,
            com.friend.ios.service.LocalLiveSpeakersStore provides liveSpeakers,
            // The watch (and-wear)
            com.friend.ios.service.LocalWatchStore provides watch,
            com.friend.ios.service.LocalPhoneCallStore provides phoneCalls, // and-calls
            // Ask Omi, spoken answers, read aloud (and-askomi)
            com.friend.ios.service.LocalVoicePlaybackStore provides playback,
            com.friend.ios.service.LocalAskOmiStore provides askOmi,
            // Health Connect, location (and-transcribe)
            com.friend.ios.service.LocalAppleHealthStore provides health,
            com.friend.ios.service.LocalLocationStore provides location,
            com.friend.ios.service.LocalCustomSTTSettings provides customSTT,
            content = content,
        )
    }

    companion object {
        fun configuration(): AppConfiguration = AppConfiguration(
            profile = AppConfiguration.Profile.from(BuildConfig.OMI_APP_PROFILE),
            apiBaseURL = URI(BuildConfig.OMI_API_BASE_URL),
            authEmulator = AppConfiguration.parseHostPort(BuildConfig.OMI_AUTH_EMULATOR_HOST),
            appVersion = BuildConfig.VERSION_NAME,
            appBuild = BuildConfig.VERSION_CODE.toString(),
        )
    }
}
