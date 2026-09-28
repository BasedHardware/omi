import Foundation
import OmiKit

// Port of `react-native/src/app/AppOrchestrator.tsx` intent layer — the
// session gate (useOnboarding.ts), cloud reads + pagination
// (useDesktopReads.ts), chat (chatClient.ts sequencing), task mutations
// (useTaskMutations.ts), devices (useNativeDevices.ts), and preferences /
// connectors (desktopSettingsClient.ts / desktopCloudClient.ts). All state
// lives on `AppStore` (AppContracts.swift); this extension owns the
// transitions, fences, and error copy. Web-only platform machinery (the web
// audio graph, localStorage, Animated drivers) has no native equivalent here
// and is skipped with a comment where the TS had it.

/// Marshals a service callback onto the store's actor before any @Published
/// state is touched.
func marshalToMainActor(_ body: @escaping @MainActor @Sendable () -> Void) {
    Task { @MainActor in body() }
}

func appNowMilliseconds() -> Int64 {
    Int64(Date().timeIntervalSince1970 * 1000)
}

/// Session gate: cloud reads and chat need onboarding done AND a session the
/// user can use right now (a returning signed-out user sits in the
/// Welcome-back card instead).
extension AppStore {
    var sessionReady: Bool {
        onboardingRequired == false && !returningUser
    }

    // MARK: - Lifecycle (host bootstrap contract)

    /// Begins the session probe, preference load, reads refresh, and device
    /// stream consumption. Idempotent.
    public func start() {
        guard !runtime.started else { return }
        runtime.started = true
        // Order mirrors the TS orchestrator: hydrate persisted settings
        // first, then probe the session against the loaded onboarding
        // marker, then probe capture availability.
        runtime.streamTasks.append(Task {
            await loadPreferencesTask()
            await probeOnboarding()
            if let rewind = services.rewindCapture {
                await probeRewindAvailability(rewind)
            }
        })
        startDeviceStreamLoops()
        startAuthStreamLoops()
    }

    /// Cancels the background loops. Symmetry for `start()`; tests and hosts
    /// tearing the store down call this.
    public func stop() {
        runtime.started = false
        for task in runtime.streamTasks {
            task.cancel()
        }
        runtime.streamTasks.removeAll()
    }

    // MARK: - Onboarding / session (useOnboarding.ts)

    /// The persisted onboarding-completed flag: `omi.onboarding.setupRevision`
    /// == "1" (upstream `OmiAuthModule` / `omiNative.web` storage — a native
    /// key outside the 17-entry JS whitelist; `exploreProgress` stays a pure
    /// CSV of explore-check ids).
    func onboardingCompletedFromPreferences() -> Bool {
        preferences.onboardingSetupCompleted
    }

    func saveOnboardingCompleted() async {
        if let settings = services.settings {
            _ = await settings.setPreference(
                desktopPreferenceKeys.onboardingSetupRevision,
                PreferenceValue.string("1"))
        }
        preferences.onboardingSetupCompleted = true
    }

    /// The session probe. nil → Bool transition of `onboardingRequired`;
    /// a host without an authenticator can never establish a real cloud
    /// session and stays on Welcome — never a faked ready shell.
    func probeOnboarding() async {
        guard let auth = services.auth else {
            setOnboardingRequired(true)
            return
        }
        let completed = onboardingCompletedFromPreferences()
        runtime.completedOnboarding = completed
        // The `Authenticating` protocol carries no session probe; the
        // `SessionProbeCapable` capability does (OmiAuthSession implements
        // the real cloud check). Hosts binding a custom authenticator
        // without it get the optimistic default (sign-in itself still
        // gates everything).
        let hasSession: Bool
        if let probe = auth as? SessionProbeCapable {
            hasSession = await probe.hasCloudSession()
        } else {
            hasSession = true
        }
        authErrorCopy = nil
        setupRequired = hasSession && !completed
        setOnboardingRequired(!completed)
        returningUser = completed && !hasSession
        applySessionGate()
    }

    /// Every sign-in path — first-run Welcome, Settings, Connectors, Home
    /// recovery — is the same native auth session. Successful sign-in resumes
    /// unfinished setup; only explicit setup completion enables the product.
    public func startSignIn() async {
        guard let auth = services.auth else { return }
        let operation = runtime.authOperation + 1
        runtime.authOperation = operation
        authErrorCopy = nil
        signInErrorCopy = nil
        signingIn = true
        syncAuthState()
        // The previous handoff's code is dead the moment a new sign-in
        // starts; a fresh one arrives through the desktopHandoffs stream.
        desktopHandoff = nil
        defer {
            if operation == runtime.authOperation {
                signingIn = false
                desktopHandoff = nil
                syncAuthState()
            }
        }
        do {
            let signedIn = try await auth.signIn()
            guard operation == runtime.authOperation else { return }
            if signedIn {
                let completed = onboardingCompletedFromPreferences()
                runtime.completedOnboarding = completed
                setupRequired = !completed
                setOnboardingRequired(!completed)
                returningUser = false
                if completed {
                    await refreshReads(initial: false)
                    applySessionGate()
                }
            } else {
                authErrorCopy = "Sign in was not completed. Try again."
                signInErrorCopy = authErrorCopy
            }
        } catch {
            guard operation == runtime.authOperation else { return }
            authErrorCopy = "Sign in was not completed. Try again."
            signInErrorCopy = authErrorCopy
        }
    }

    public func cancelSignIn() async {
        runtime.authOperation += 1
        signingIn = false
        syncAuthState()
        authErrorCopy = nil
        signInErrorCopy = nil
        desktopHandoff = nil
        await services.auth?.cancelSignIn()
    }

    /// Explicit setup completion (port of `completeSetup`). Only this flips
    /// `setupRequired` off and enables the product shell.
    public func completeOnboarding() async {
        guard setupRequired, !completingSetup else { return }
        let operation = runtime.authOperation + 1
        runtime.authOperation = operation
        completingSetup = true
        authErrorCopy = nil
        defer {
            if operation == runtime.authOperation {
                completingSetup = false
            }
        }
        if let probe = services.auth as? SessionProbeCapable {
            if !(await probe.hasCloudSession()) {
                setupRequired = false
                setOnboardingRequired(true)
                return
            }
        }
        guard operation == runtime.authOperation else { return }
        // The save is a local preference write (no-throw); the TS catch copy
        // guarded the native onboarding marker, which the host owns here.
        await saveOnboardingCompleted()
        guard operation == runtime.authOperation else { return }
        runtime.completedOnboarding = true
        setupRequired = false
        setOnboardingRequired(false)
        returningUser = false
        await refreshReads(initial: false)
        applySessionGate()
    }

    public func signOut() async {
        guard let auth = services.auth else { return }
        runtime.authOperation += 1
        signingIn = false
        completingSetup = false
        authErrorCopy = nil
        signInErrorCopy = nil
        let signedOut: Bool
        do {
            signedOut = try await auth.signOut()
        } catch {
            return
        }
        guard signedOut else { return }
        // After the credential store is cleared: a user who finished setup
        // before is returning (Welcome-back card), not first-run.
        let completed = runtime.completedOnboarding ?? onboardingCompletedFromPreferences()
        runtime.completedOnboarding = completed
        setupRequired = false
        setOnboardingRequired(!completed)
        returningUser = completed
        // No reads refresh here: a signed-out Mac must not fire cloud reads.
        resetReads()
        applySessionGate()
    }

    /// A ready session can die mid-run. Chat/read 401s and the native
    /// session-invalidated signal funnel here; the gate falls back to the
    /// same Welcome as sign-out instead of keeping signed-in chrome up.
    func revalidateSession() async {
        runtime.authOperation += 1
        completingSetup = false
        signingIn = false
        setupRequired = false
        let completed = runtime.completedOnboarding ?? onboardingCompletedFromPreferences()
        setOnboardingRequired(!completed)
        returningUser = completed
        resetReads()
        applySessionGate()
    }

    /// Gate transition: bumps the chat session epoch, drops or (re)loads the
    /// transcript. Mirrors the chat-history effect in AppOrchestrator.tsx.
    func applySessionGate() {
        syncAuthState()
        bumpChatEpoch()
        if !sessionReady {
            resetChatSession()
        } else {
            runtime.streamTasks.append(Task { [weak self] in
                await self?.refreshChatHistory()
            })
            // The TS reads effect re-runs when the session gate opens — the
            // surfaces may already be mounted (the gate opened after their
            // onAppear), so the store owns this refresh too.
            runtime.streamTasks.append(Task { [weak self] in
                await self?.refreshReads(initial: false)
            })
        }
    }

    /// Derives the presentation gate from the probe + in-flight sign-in
    /// (the session phases of DesktopApp.tsx / MobileAppSurface.tsx). While
    /// the probe is unresolved the shell keeps the signed-out gate up — it
    /// never claims a ready session it has not proven.
    func syncAuthState() {
        if signingIn {
            authState = .signingIn
        } else if returningUser {
            authState = .signedOut
        } else if onboardingRequired == true {
            authState = .onboarding
        } else if onboardingRequired == false {
            authState = .signedIn
        } else {
            authState = .signedOut
        }
    }

    func bumpChatEpoch() {
        runtime.chatSessionEpoch += 1
        runtime.chatSessionEpochMirror.set(runtime.chatSessionEpoch)
    }

    func setOnboardingRequired(_ value: Bool?) {
        onboardingRequired = value
        syncPostSetupCue()
    }

    func syncPostSetupCue() {
        let cue = runtime.cueTracker.update(
            onboardingRequired: onboardingRequired, readsPhase: readsPhase)
        postSetupHomeCue = cue
    }

    private func probeRewindAvailability(_ rewind: RewindCaptureControlling) async {
        let permission = await rewind.permissionStatus()
        rewindCaptureState.available = permission == .granted
    }

    // MARK: - Preferences

    func loadPreferencesTask() async {
        guard let settings = services.settings else { return }
        preferences = await settings.loadPreferences()
        preferencesLoaded = true
    }

    public func setPreference(_ key: String, _ value: PreferenceValue) async {
        guard let settings = services.settings else { return }
        preferences = await settings.setPreference(key, value)
        preferencesLoaded = true
        // Rewind capture rides the `screenAnalysisEnabled` preference: the
        // desktop capture toggle writes it, the host capture engine runs
        // while it is on (useRewindCapture semantics — permission copy on a
        // failed start, stop-unconfirmed copy on a failed stop).
        if key == desktopPreferenceKeys.screenCapture,
            let rewind = services.rewindCapture,
            case PreferenceValue.bool(let enabled) = value
        {
            await setRewindCaptureRunning(enabled, rewind: rewind)
        }
    }

    /// Starts/stops the host capture engine and mirrors the outcome into
    /// `rewindCaptureState` (the `available/capturing/busy/error` state of
    /// `useRewindCapture.ts`).
    private func setRewindCaptureRunning(
        _ running: Bool, rewind: RewindCaptureControlling
    ) async {
        guard !rewindCaptureState.busy else { return }
        rewindCaptureState.busy = true
        defer { rewindCaptureState.busy = false }
        if running {
            let permission = await rewind.permissionStatus()
            if let copy = rewindCapturePermissionCopy(permission) {
                rewindCaptureState.errorCopy = copy
                rewindCaptureState.capturing = false
                return
            }
            do {
                try await rewind.start()
                rewindCaptureState.errorCopy = nil
                rewindCaptureState.capturing = true
            } catch {
                rewindCaptureState.errorCopy = rewindCaptureStoppedCopy
                rewindCaptureState.capturing = false
            }
        } else {
            do {
                try await rewind.stop()
                rewindCaptureState.capturing = false
            } catch {
                rewindCaptureState.errorCopy = rewindCaptureStopUnconfirmedCopy
            }
        }
    }

    @discardableResult
    public func requestPermission(_ kind: PermissionKind) async -> PermissionState {
        guard let settings = services.settings else { return .unknown }
        let state = await settings.requestPermission(kind)
        // A newly granted Screen Recording permission requires relaunch per
        // the desktop spec; the host owns that surface. Refresh the snapshot
        // so permission-derived toggles read truthfully either way.
        preferences = await settings.loadPreferences()
        preferencesLoaded = true
        return state
    }

    // MARK: - Cloud settings + connectors

    public func refreshConnectors() async {
        guard let cloud = services.cloud else { return }
        cloudLoading = true
        defer { cloudLoading = false }
        do {
            connectors = try await cloud.loadConnectors()
            connectorsErrorCopy = nil
            accountSettings = await cloud.loadAccountSettings()
        } catch {
            connectors = nil
            connectorsErrorCopy = desktopReadErrorCopy(error)
        }
    }

    public func enableConnector(appId: String) async {
        await setConnectorEnabled(appId: appId, enabled: true)
    }

    public func disableConnector(appId: String) async {
        await setConnectorEnabled(appId: appId, enabled: false)
    }

    private func setConnectorEnabled(appId: String, enabled: Bool) async {
        guard let cloud = services.cloud else { return }
        guard runtime.pendingConnectorId == nil else { return }
        runtime.pendingConnectorId = appId
        defer { runtime.pendingConnectorId = nil }
        do {
            if enabled {
                try await cloud.enableCloudApp(appId: appId)
            } else {
                try await cloud.disableCloudApp(appId: appId)
            }
            await refreshConnectors()
        } catch {
            connectorsErrorCopy = desktopReadErrorCopy(error)
        }
    }

    public func setStoreRecordingPermission(_ value: Bool) async {
        guard let cloud = services.cloud else { return }
        cloudLoading = true
        defer { cloudLoading = false }
        do {
            try await cloud.setStoreRecordingPermission(value)
            accountSettings?.storeRecordingPermission = value
            accountSettings?.storeRecordingError = nil
        } catch {
            accountSettings?.storeRecordingError = desktopReadErrorCopy(error)
        }
    }

    public func setPrivateCloudSync(_ value: Bool) async {
        guard let cloud = services.cloud else { return }
        cloudLoading = true
        defer { cloudLoading = false }
        do {
            try await cloud.setPrivateCloudSync(value)
            accountSettings?.privateCloudSync = value
            accountSettings?.privateCloudSyncError = nil
        } catch {
            accountSettings?.privateCloudSyncError = desktopReadErrorCopy(error)
        }
    }

    public func optInTrainingData() async {
        guard let cloud = services.cloud else { return }
        cloudLoading = true
        defer { cloudLoading = false }
        do {
            try await cloud.optInTrainingData()
            accountSettings?.trainingOptedIn = true
            accountSettings?.trainingError = nil
        } catch {
            accountSettings?.trainingError = desktopReadErrorCopy(error)
        }
    }

    // MARK: - Routing

    public func navigate(_ destination: AppRoute) {
        route = destination
        mobileRoute = MobileRoute(destination)
        if destination == .home {
            homeChatOpen = false
        }
    }

    public func navigate(mobileRoute destination: MobileRoute) {
        homeChatOpen = false
        mobileRoute = destination
        route = destination.appRoute
    }
}
