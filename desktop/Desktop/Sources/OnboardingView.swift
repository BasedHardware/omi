import SwiftUI
import AppKit
import AVKit

struct OnboardingView: View {
    @ObservedObject var appState: AppState
    @ObservedObject var chatProvider: ChatProvider
    var onComplete: (() -> Void)? = nil
    @AppStorage("onboardingStep") private var currentStep = 0
    @Environment(\.dismiss) private var dismiss

    // Timer to periodically check permission status when on permissions step
    let permissionCheckTimer = Timer.publish(every: 1.0, on: .main, in: .common).autoconnect()

    let steps = ["Video", "Name", "Language", "Get to Know You", "Permissions", "Explore"]

    // State for name input
    @State private var nameInput: String = ""
    @State private var nameError: String = ""
    @FocusState private var isNameFieldFocused: Bool

    // State for language selection
    @State private var selectedLanguage: String = "en"
    @State private var autoDetectEnabled: Bool = false

    // State for file indexing (now step 3 consent, background scan, step 5 chat reveal)
    @State private var fileIndexingDone = false
    @State private var fileIndexingSkipped = false
    @State private var backgroundScanTask: Task<Void, Never>?
    @State private var totalFilesScanned: Int = 0
    @State private var scanningInProgress: Bool = false


    // Privacy sheet
    @State private var showPrivacySheet = false

    var body: some View {
        ZStack {
            // Full dark background
            OmiColors.backgroundPrimary
                .ignoresSafeArea()

            Group {
                if appState.hasCompletedOnboarding {
                    // Onboarding complete - this view will be replaced by DesktopHomeView's mainContent
                    // Don't call dismiss() here as it can close the window unexpectedly
                    Color.clear
                        .onAppear {
                            log("OnboardingView: hasCompletedOnboarding=true, starting monitoring")
                            if !ProactiveAssistantsPlugin.shared.isMonitoring {
                                ProactiveAssistantsPlugin.shared.startMonitoring { _, _ in }
                            }
                            // Only call completion handler if provided (for sheet presentations)
                            // Don't dismiss - DesktopHomeView will automatically show mainContent
                            if let onComplete = onComplete {
                                log("OnboardingView: Calling onComplete handler")
                                onComplete()
                            } else {
                                log("OnboardingView: No onComplete handler, view will transition via DesktopHomeView")
                            }
                        }
                } else {
                    onboardingContent
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .onReceive(permissionCheckTimer) { _ in
            // Poll all permissions when on the permissions step
            if currentStep == 4 {
                appState.checkNotificationPermission()
                appState.checkScreenRecordingPermission()
                appState.checkMicrophonePermission()
                appState.checkAccessibilityPermission()
                appState.checkAutomationPermission()
                appState.checkBluetoothPermission()
                appState.checkSystemAudioPermission()
            }
        }
        // Bring app to front when any permission is granted while on the permissions step
        .onChange(of: appState.hasNotificationPermission) { _, granted in
            if granted && currentStep == 4 {
                log("Notification permission granted on permissions step, bringing to front")
                bringToFront()
            }
        }
        .onChange(of: appState.hasScreenRecordingPermission) { _, granted in
            if granted && currentStep == 4 {
                log("Screen recording permission granted on permissions step, bringing to front")
                bringToFront()
                // Silently trigger system audio permission (piggybacks on screen recording)
                if appState.isSystemAudioSupported && !appState.hasSystemAudioPermission {
                    appState.triggerSystemAudioPermission()
                }
            }
        }
        .onChange(of: appState.hasMicrophonePermission) { _, granted in
            if granted && currentStep == 4 {
                log("Microphone permission granted on permissions step, bringing to front")
                bringToFront()
            }
        }
        .onChange(of: appState.hasAccessibilityPermission) { _, granted in
            if granted && currentStep == 4 {
                log("Accessibility permission granted on permissions step, bringing to front")
                bringToFront()
            }
        }
        .onChange(of: appState.hasAutomationPermission) { _, granted in
            if granted && currentStep == 4 {
                log("Automation permission granted on permissions step, bringing to front")
                bringToFront()
            }
        }
        .onAppear {
            // Handle relaunch case: if app restarts on step 4 (e.g., after Screen Recording quit & reopen),
            // immediately check all permissions.
            // onChange(of: currentStep) won't fire since the value didn't change.
            if currentStep == 4 {
                log("OnboardingView onAppear: on permissions step, checking all permissions immediately")
                appState.checkAllPermissions()
            }

            // Handle relaunch case: if app restarts on step 4 or 5, the background scan task is lost.
            // Re-launch it if scanning hasn't completed yet, or restore file count if it has.
            if (currentStep == 4 || currentStep == 5) && backgroundScanTask == nil && !fileIndexingSkipped {
                let alreadyCompleted = UserDefaults.standard.bool(forKey: "hasCompletedFileIndexing")
                if alreadyCompleted {
                    // Scan finished before restart — restore file count from DB
                    log("OnboardingView onAppear: file indexing already completed, restoring count")
                    Task {
                        let count = await FileIndexerService.shared.getIndexedFileCount()
                        await MainActor.run {
                            totalFilesScanned = count
                        }
                        // If chat is empty, re-start the exploration chat
                        if chatProvider.messages.isEmpty {
                            log("OnboardingView onAppear: chat empty after restart, re-starting exploration")
                            await startExplorationChat()
                        }
                    }
                } else {
                    // Scan was interrupted — re-launch the full pipeline
                    log("OnboardingView onAppear: scan interrupted by restart, re-launching background indexing")
                    startBackgroundFileIndexing()
                }
            }
        }
    }

    private func bringToFront() {
        log("bringToFront() called, scheduling activation in 0.3s")
        log("Current app is active: \(NSApp.isActive ? "YES" : "NO")")

        // Small delay to let window ordering settle after System Preferences closes
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
            log("Executing activation after delay")

            // Use NSApp.activate which works even when app is not active
            NSApp.activate(ignoringOtherApps: true)
            log("Called NSApp.activate(ignoringOtherApps: true)")

            // Bring the main window to front
            var foundWindow = false
            for window in NSApp.windows {
                if window.title == "Omi" {
                    foundWindow = true
                    log("Found 'Omi' window, making key and ordering front")
                    window.makeKeyAndOrderFront(nil)
                    window.orderFrontRegardless()
                }
            }
            if !foundWindow {
                log("WARNING - Could not find 'Omi' window!")
            }

            log("After activation - app is active: \(NSApp.isActive ? "YES" : "NO")")
        }
    }

    /// Check if current step's permission is granted
    private var currentPermissionGranted: Bool {
        switch currentStep {
        case 0: return true // Video step - always valid
        case 1: return !nameInput.trimmingCharacters(in: .whitespaces).isEmpty // Name step - valid if name entered
        case 2: return true // Language step - always valid (has default)
        case 3: return true // File indexing consent - always valid (has buttons)
        case 4: return requiredPermissionsGranted // Permissions step
        case 5: return fileIndexingDone // Chat reveal step
        default: return true
        }
    }

    private var allPermissionsGranted: Bool {
        appState.hasScreenRecordingPermission
            && appState.hasMicrophonePermission
            && appState.hasNotificationPermission
            && appState.hasAccessibilityPermission
            && appState.hasAutomationPermission
    }

    private var requiredPermissionsGranted: Bool {
        appState.hasScreenRecordingPermission
            && appState.hasMicrophonePermission
            && appState.hasNotificationPermission
            && appState.hasAccessibilityPermission
            && appState.hasAutomationPermission
    }

    /// Index of the first ungranted permission (determines which GIF/guide to show)
    private var activePermissionIndex: Int {
        if !appState.hasScreenRecordingPermission { return 0 }
        if !appState.hasMicrophonePermission { return 1 }
        if !appState.hasNotificationPermission { return 2 }
        if !appState.hasAccessibilityPermission { return 3 }
        if !appState.hasAutomationPermission { return 4 }
        return -1 // All granted
    }

    private var activePermissionGifName: String? {
        switch activePermissionIndex {
        case 0: return "permissions"
        case 2: return "enable_notifications"
        case 3: return "accessibility_permission"
        default: return nil
        }
    }

    private var activePermissionGuideText: String {
        switch activePermissionIndex {
        case 0: return "Click 'Grant Access', then toggle ON Screen Recording for Omi in System Settings and click 'Quit & Reopen'."
        case 1: return "Click 'Grant Access' and allow Omi to use your microphone for live transcription."
        case 2: return "Click 'Grant Access' and allow notifications so Omi can keep you updated."
        case 3: return "Click 'Grant Access', then find Omi in System Settings and toggle the Accessibility switch ON."
        case 4:
            if appState.automationPermissionError != 0 {
                return "Having trouble? Open System Settings → Privacy & Security → Automation, find Omi and toggle it ON. If Omi isn't listed, try quitting and reopening the app."
            }
            return "Click 'Grant Access', then find Omi in the Automation list and toggle the switch ON."
        default: return "All permissions granted! Click Continue to finish setup."
        }
    }

    private var activePermissionIcon: String {
        switch activePermissionIndex {
        case 0: return "record.circle"
        case 1: return "mic"
        case 2: return "bell"
        case 3: return "hand.raised"
        case 4: return "gearshape.2"
        default: return "checkmark.circle"
        }
    }

    private var activePermissionName: String {
        switch activePermissionIndex {
        case 0: return "Screen Recording"
        case 1: return "Microphone"
        case 2: return "Notifications"
        case 3: return "Accessibility"
        case 4: return "Automation"
        default: return ""
        }
    }

    private var onboardingContent: some View {
        Group {
            if currentStep == 0 {
                // Full-window video with overlaid controls, capped at native resolution
                ZStack {
                    OnboardingVideoView()
                        .aspectRatio(16.0 / 9.0, contentMode: .fit)
                        .frame(maxWidth: 960)

                    // Overlay progress indicators and button
                    VStack {
                        // Progress indicators at top
                        HStack(spacing: 12) {
                            ForEach(0..<steps.count, id: \.self) { index in
                                progressIndicator(for: index)
                            }
                        }
                        .padding(.top, 20)
                        .padding(.horizontal, 20)

                        Spacer()

                        // Continue button at bottom
                        Button(action: handleMainAction) {
                            Text("Continue")
                                .frame(maxWidth: 200)
                                .padding(.vertical, 8)
                        }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.large)
                        .padding(.bottom, 24)
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                // Standard card layout for all other steps
                VStack(spacing: 24) {
                    Spacer()

                    VStack(spacing: 24) {
                        // Progress indicators
                        HStack(spacing: 12) {
                            ForEach(0..<steps.count, id: \.self) { index in
                                progressIndicator(for: index)
                            }
                        }
                        .padding(.top, 20)
                        .padding(.horizontal, 20)

                        Spacer()
                            .frame(height: 20)

                        stepContent

                        Spacer()
                            .frame(height: 20)

                        buttonSection
                    }
                    .frame(width: currentStep == 4 ? 720 : (currentStep == 5 ? 600 : 420))
                    .frame(height: currentStep == 4 ? 560 : (currentStep == 5 ? 650 : 420))
                    .background(
                        RoundedRectangle(cornerRadius: 16)
                            .fill(OmiColors.backgroundSecondary)
                            .overlay(
                                RoundedRectangle(cornerRadius: 16)
                                    .stroke(OmiColors.backgroundTertiary.opacity(0.5), lineWidth: 1)
                            )
                    )

                    Spacer()
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
    }

    @ViewBuilder
    private func progressIndicator(for index: Int) -> some View {
        let isGranted = permissionGranted(for: index)

        if index < currentStep || (index == currentStep && isGranted) {
            // Completed or granted - show checkmark
            Image(systemName: "checkmark.circle.fill")
                .foregroundColor(.white)
                .scaledFont(size: 12)
        } else if index == currentStep {
            // Current step, not yet granted - filled circle
            Circle()
                .fill(OmiColors.purplePrimary)
                .frame(width: 10, height: 10)
        } else {
            // Future step - empty circle
            Circle()
                .stroke(Color.gray.opacity(0.3), lineWidth: 1.5)
                .frame(width: 10, height: 10)
        }
    }

    private func permissionGranted(for step: Int) -> Bool {
        switch step {
        case 0: return true // Video - always "granted"
        case 1: return !nameInput.trimmingCharacters(in: .whitespaces).isEmpty // Name step
        case 2: return true // Language step - always "granted" (has default)
        case 3: return true // File indexing consent - always "granted"
        case 4: return allPermissionsGranted // Permissions step
        case 5: return fileIndexingDone // Chat reveal step
        default: return false
        }
    }

    @ViewBuilder
    private var stepContent: some View {
        switch currentStep {
        case 0:
            EmptyView() // Video step uses full-window layout, not stepContent
        case 1:
            nameStepView
        case 2:
            languageStepView
        case 3:
            fileIndexingConsentView
        case 4:
            permissionsStepView
        case 5:
            onboardingChatRevealView
        default:
            EmptyView()
        }
    }

    // MARK: - Name Step View

    private var nameStepView: some View {
        VStack(spacing: 16) {
            Image(systemName: "person.circle")
                .scaledFont(size: 48)
                .foregroundColor(OmiColors.purplePrimary)

            Text("What's your name?")
                .font(.title2)
                .fontWeight(.semibold)

            Text("Tell us how you'd like to be addressed.")
                .font(.body)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)

            VStack(alignment: .leading, spacing: 8) {
                TextField("Enter your name", text: $nameInput)
                    .textFieldStyle(.roundedBorder)
                    .font(.body)
                    .focused($isNameFieldFocused)
                    .onSubmit {
                        if isNameValid {
                            handleMainAction()
                        }
                    }

                if !nameError.isEmpty {
                    HStack(spacing: 4) {
                        Image(systemName: "exclamationmark.circle")
                            .font(.caption)
                        Text(nameError)
                            .font(.caption)
                    }
                    .foregroundColor(.red)
                }

                if !nameInput.isEmpty {
                    Text("\(nameInput.count) characters")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .frame(maxWidth: .infinity, alignment: .trailing)
                }
            }
            .frame(width: 280)
            .padding(.top, 8)
        }
        .onAppear {
            // Pre-fill from Firebase if available
            if nameInput.isEmpty {
                let existingName = AuthService.shared.displayName
                if !existingName.isEmpty {
                    nameInput = existingName
                }
            }
            // Focus the text field
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                isNameFieldFocused = true
            }
        }
    }

    private var isNameValid: Bool {
        let trimmed = nameInput.trimmingCharacters(in: .whitespaces)
        return trimmed.count >= 2
    }

    // MARK: - Language Step View

    private var languageStepView: some View {
        VStack(spacing: 16) {
            Image(systemName: "globe")
                .scaledFont(size: 48)
                .foregroundColor(OmiColors.purplePrimary)

            Text("Language")
                .font(.title2)
                .fontWeight(.semibold)

            Text("Choose the language you speak.")
                .font(.body)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)

            Picker("", selection: $selectedLanguage) {
                ForEach(AssistantSettings.supportedLanguages, id: \.code) { language in
                    Text(language.name).tag(language.code)
                }
            }
            .pickerStyle(.menu)
            .frame(width: 220)
            .padding(.top, 8)
        }
        .onAppear {
            selectedLanguage = AssistantSettings.shared.transcriptionLanguage
            autoDetectEnabled = false
            // Fetch language from Firestore (source of truth) for returning users
            Task {
                if let response = try? await APIClient.shared.getUserLanguage(),
                   !response.language.isEmpty {
                    await MainActor.run {
                        selectedLanguage = response.language
                        AssistantSettings.shared.transcriptionLanguage = response.language
                    }
                }
            }
        }
    }

    // MARK: - File Indexing Consent View (Step 3)

    private var fileIndexingConsentView: some View {
        VStack(spacing: 16) {
            Spacer()

            Image(systemName: "folder.badge.gearshape")
                .scaledFont(size: 48)
                .foregroundColor(OmiColors.purplePrimary)

            Text("Get to Know You")
                .font(.title2)
                .fontWeight(.semibold)

            Text("Let Omi look at your files to understand what you work on, your projects, and interests.")
                .font(.body)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)
                .fixedSize(horizontal: false, vertical: true)

            VStack(spacing: 4) {
                HStack(spacing: 8) {
                    Image(systemName: "lock.shield")
                        .scaledFont(size: 12)
                        .foregroundColor(.secondary)
                    Text("Scans common folders for file names only")
                        .scaledFont(size: 12)
                        .foregroundColor(.secondary)
                }

                HStack(spacing: 8) {
                    Image(systemName: "eye.slash")
                        .scaledFont(size: 12)
                        .foregroundColor(.secondary)
                    Text("File contents are never uploaded")
                        .scaledFont(size: 12)
                        .foregroundColor(.secondary)
                }
            }
            .padding(.top, 4)

            Spacer()
        }
    }

    // MARK: - Chat Reveal View (Step 5)

    private var onboardingChatRevealView: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                if let logoURL = Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png"),
                   let logoImage = NSImage(contentsOf: logoURL) {
                    Image(nsImage: logoImage)
                        .resizable()
                        .scaledToFit()
                        .frame(width: 24, height: 24)
                }

                if scanningInProgress {
                    Text("Scanning your files...")
                        .scaledFont(size: 14, weight: .medium)
                        .foregroundColor(OmiColors.textPrimary)
                } else {
                    Text("Exploring \(totalFilesScanned.formatted()) files...")
                        .scaledFont(size: 14, weight: .medium)
                        .foregroundColor(OmiColors.textPrimary)
                }

                Spacer()

                Button(action: { handleFileIndexingComplete(fileCount: totalFilesScanned) }) {
                    Text("Done")
                        .scaledFont(size: 13, weight: .medium)
                        .foregroundColor(OmiColors.purplePrimary)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(OmiColors.purplePrimary.opacity(0.1))
                        .cornerRadius(6)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)

            Divider()

            // Messages
            ChatMessagesView(
                messages: chatProvider.messages,
                isSending: chatProvider.isSending,
                hasMoreMessages: false,
                isLoadingMoreMessages: false,
                isLoadingInitial: chatProvider.isLoading,
                app: nil,
                onLoadMore: {},
                onRate: { _, _ in },
                welcomeContent: {
                    VStack(spacing: 12) {
                        ProgressView()
                            .scaleEffect(0.8)
                        Text("Analyzing your files...")
                            .scaledFont(size: 13)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            )

            // Input
            ChatInputView(
                onSend: { text in
                    Task { await chatProvider.sendMessage(text) }
                },
                onFollowUp: { text in
                    Task { await chatProvider.sendFollowUp(text) }
                },
                onStop: {
                    chatProvider.stopAgent()
                },
                isSending: chatProvider.isSending,
                isStopping: chatProvider.isStopping,
                mode: $chatProvider.chatMode,
                inputText: $chatProvider.draftText
            )
            .padding()
        }
    }

    // MARK: - File Indexing Completion

    private func handleFileIndexingComplete(fileCount: Int) {
        fileIndexingDone = true

        if fileCount > 0 {
            log("OnboardingView: File indexing completed with \(fileCount) files")
            AnalyticsManager.shared.onboardingStepCompleted(step: 5, stepName: "FileIndexing")
        } else {
            log("OnboardingView: File indexing skipped")
            AnalyticsManager.shared.onboardingStepCompleted(step: 5, stepName: "FileIndexing_Skipped")
        }

        // Cancel background scan task if still running
        backgroundScanTask?.cancel()
        backgroundScanTask = nil

        AnalyticsManager.shared.onboardingCompleted()
        appState.hasCompletedOnboarding = true
        // Start cloud agent VM pipeline
        Task {
            await AgentVMService.shared.startPipeline()
        }
        if LaunchAtLoginManager.shared.setEnabled(true) {
            AnalyticsManager.shared.launchAtLoginChanged(enabled: true, source: "onboarding")
        }
        ProactiveAssistantsPlugin.shared.startMonitoring { _, _ in }
        appState.startTranscription()

        // Create a welcome task for the new user
        Task {
            await TasksStore.shared.createTask(
                description: "Run Omi for two days to start receiving helpful advice",
                dueAt: Date(),
                priority: "low"
            )
        }

        // Send a welcome notification
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
            NotificationService.shared.sendNotification(
                title: "You're all set!",
                message: "Just go back to your work and run me in the background. I'll start sending you useful advice during your day."
            )
        }

        if let onComplete = onComplete {
            onComplete()
        }
    }

    // MARK: - Consolidated Permissions Step View

    private var permissionsStepView: some View {
        VStack(spacing: 12) {
            Text("Permissions")
                .font(.title2)
                .fontWeight(.semibold)

            Text("Omi needs a few permissions to work properly.")
                .font(.body)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)

            HStack(spacing: 16) {
                // Left side: permission rows
                VStack(spacing: 8) {
                    permissionRow(
                        number: 1,
                        icon: "record.circle",
                        name: "Screen Recording",
                        isGranted: appState.hasScreenRecordingPermission,
                        isActive: activePermissionIndex == 0,
                        action: {
                            AnalyticsManager.shared.permissionRequested(permission: "screen_recording")
                            appState.triggerScreenRecordingPermission()
                        }
                    )
                    permissionRow(
                        number: 2,
                        icon: "mic",
                        name: "Microphone",
                        isGranted: appState.hasMicrophonePermission,
                        isActive: activePermissionIndex == 1,
                        action: {
                            AnalyticsManager.shared.permissionRequested(permission: "microphone")
                            appState.requestMicrophonePermission()
                        }
                    )
                    permissionRow(
                        number: 3,
                        icon: "bell",
                        name: "Notifications",
                        isGranted: appState.hasNotificationPermission,
                        isActive: activePermissionIndex == 2,
                        action: {
                            AnalyticsManager.shared.permissionRequested(permission: "notifications")
                            appState.requestNotificationPermission()
                        }
                    )
                    permissionRow(
                        number: 4,
                        icon: "hand.raised",
                        name: "Accessibility",
                        isGranted: appState.hasAccessibilityPermission,
                        isActive: activePermissionIndex == 3,
                        action: {
                            AnalyticsManager.shared.permissionRequested(permission: "accessibility")
                            appState.triggerAccessibilityPermission()
                        }
                    )
                    permissionRow(
                        number: 5,
                        icon: "gearshape.2",
                        name: "Automation",
                        isGranted: appState.hasAutomationPermission,
                        isActive: activePermissionIndex == 4,
                        action: {
                            AnalyticsManager.shared.permissionRequested(permission: "automation")
                            appState.triggerAutomationPermission()
                        }
                    )
                    // Privacy link
                    Button(action: { showPrivacySheet = true }) {
                        HStack(spacing: 6) {
                            Image(systemName: "shield.lefthalf.filled")
                                .scaledFont(size: 11)
                            Text("Data & Privacy")
                                .scaledFont(size: 12)
                        }
                        .foregroundColor(OmiColors.textTertiary)
                    }
                    .buttonStyle(.plain)
                    .padding(.top, 4)
                }
                .frame(maxWidth: .infinity)

                // Right side: GIF / guide for active permission
                permissionGuidePanel
                    .frame(maxWidth: .infinity)
            }
            .padding(.horizontal, 16)
        }
        .sheet(isPresented: $showPrivacySheet) {
            OnboardingPrivacySheet(isPresented: $showPrivacySheet)
        }
    }

    private var permissionGuidePanel: some View {
        VStack(spacing: 12) {
            if let gifName = activePermissionGifName {
                AnimatedGIFView(gifName: gifName)
                    .id(gifName)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if activePermissionIndex >= 0 {
                Spacer()
                Image(systemName: activePermissionIcon)
                    .scaledFont(size: 40)
                    .foregroundColor(OmiColors.purplePrimary)
                Text(activePermissionName)
                    .font(.headline)
                    .fontWeight(.semibold)
                Text(activePermissionGuideText)
                    .scaledFont(size: 13)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 16)
                Spacer()
            } else {
                Spacer()
                Image(systemName: "checkmark.circle.fill")
                    .scaledFont(size: 48)
                    .foregroundColor(.green)
                Text("All Set!")
                    .font(.headline)
                Text("All permissions granted. Click Continue.")
                    .scaledFont(size: 13)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                Spacer()
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(OmiColors.backgroundPrimary.opacity(0.5))
        )
    }

    @ViewBuilder
    private func permissionRow(number: Int, icon: String, name: String, isGranted: Bool, isActive: Bool, action: @escaping () -> Void) -> some View {
        HStack(spacing: 12) {
            Text("\(number).")
                .scaledFont(size: 14, weight: .medium)
                .foregroundColor(.secondary)
                .frame(width: 20, alignment: .trailing)

            Image(systemName: icon)
                .scaledFont(size: 14)
                .foregroundColor(isGranted ? .green : OmiColors.purplePrimary)
                .frame(width: 20)

            Text(name)
                .scaledFont(size: 14, weight: .medium)

            Spacer()

            if isGranted {
                Image(systemName: "checkmark.circle.fill")
                    .scaledFont(size: 16)
                    .foregroundColor(.green)
            } else {
                Button(action: action) {
                    Text("Grant Access")
                        .scaledFont(size: 12, weight: .medium)
                        .foregroundColor(.white)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 5)
                        .background(
                            RoundedRectangle(cornerRadius: 6)
                                .fill(OmiColors.purplePrimary)
                        )
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 12)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(isGranted ? Color.green.opacity(0.08) : (isActive ? OmiColors.purplePrimary.opacity(0.08) : OmiColors.backgroundPrimary.opacity(0.5)))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(isActive && !isGranted ? OmiColors.purplePrimary.opacity(0.4) : Color.clear, lineWidth: 1.5)
        )
    }

    @ViewBuilder
    private var buttonSection: some View {
        VStack(spacing: 8) {
            // Step 5 (chat reveal) has its own Done button in the header
            if currentStep == 5 {
                EmptyView()
            } else if currentStep == 3 {
                // File indexing consent: custom Get Started + Skip buttons
                VStack(spacing: 8) {
                    Button(action: handleMainAction) {
                        Text("Get Started")
                            .frame(maxWidth: 200)
                            .padding(.vertical, 8)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)

                    Button(action: handleSkipFileIndexing) {
                        Text("Skip")
                            .scaledFont(size: 13)
                            .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                }
            } else {
                HStack(spacing: 16) {
                    // Back button (not shown on first step, name step, or permissions step if scan started)
                    if currentStep > 0 && currentStep != 1 && !(currentStep == 4 && scanningInProgress) {
                        Button(action: {
                            currentStep -= 1
                        }) {
                            Text("Back")
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 8)
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.large)
                    }

                    // Main action / Continue button
                    Button(action: handleMainAction) {
                        Text(mainButtonTitle)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 8)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                }
            }

            if currentStep == 4 && !requiredPermissionsGranted {
                Text("You can grant permissions later in Settings")
                    .scaledFont(size: 12)
                    .foregroundColor(.secondary)
            }
        }
        .padding(.horizontal, 40)
        .padding(.bottom, 20)
    }

    private var mainButtonTitle: String {
        return "Continue"
    }

    private func handleMainAction() {
        switch currentStep {
        case 0:
            AnalyticsManager.shared.onboardingStepCompleted(step: 0, stepName: "Video")
            currentStep += 1
        case 1:
            // Name step - validate and save
            let trimmedName = nameInput.trimmingCharacters(in: .whitespaces)
            if trimmedName.count < 2 {
                nameError = "Please enter at least 2 characters"
                return
            }
            nameError = ""
            // Save the name
            Task {
                await AuthService.shared.updateGivenName(trimmedName)
            }
            AnalyticsManager.shared.onboardingStepCompleted(step: 1, stepName: "Name")
            currentStep += 1
        case 2:
            // Language step - save settings (single language mode)
            AssistantSettings.shared.transcriptionLanguage = selectedLanguage
            AssistantSettings.shared.transcriptionAutoDetect = false
            // Also update backend
            Task {
                _ = try? await APIClient.shared.updateUserLanguage(selectedLanguage)
                _ = try? await APIClient.shared.updateTranscriptionPreferences(
                    singleLanguageMode: true,
                    vocabulary: nil
                )
            }
            AnalyticsManager.shared.onboardingStepCompleted(step: 2, stepName: "Language")
            AnalyticsManager.shared.languageChanged(language: selectedLanguage)
            currentStep += 1
        case 3:
            // File indexing consent - start background scan and advance to permissions
            AnalyticsManager.shared.onboardingStepCompleted(step: 3, stepName: "FileIndexingConsent")
            startBackgroundFileIndexing()
            currentStep += 1
        case 4:
            // Permissions step - advance to chat reveal (or complete if file indexing was skipped)
            AnalyticsManager.shared.onboardingStepCompleted(step: 4, stepName: "Permissions")
            // Log granted permissions
            if appState.hasScreenRecordingPermission {
                AnalyticsManager.shared.permissionGranted(permission: "screen_recording")
            }
            if appState.hasMicrophonePermission {
                AnalyticsManager.shared.permissionGranted(permission: "microphone")
            }
            if appState.hasNotificationPermission {
                AnalyticsManager.shared.permissionGranted(permission: "notifications")
            }
            if appState.hasAccessibilityPermission {
                AnalyticsManager.shared.permissionGranted(permission: "accessibility")
            }
            if appState.hasAutomationPermission {
                AnalyticsManager.shared.permissionGranted(permission: "automation")
            }
            // Log skipped permissions
            if !appState.hasScreenRecordingPermission {
                AnalyticsManager.shared.permissionSkipped(permission: "screen_recording")
            }
            if !appState.hasMicrophonePermission {
                AnalyticsManager.shared.permissionSkipped(permission: "microphone")
            }
            if !appState.hasNotificationPermission {
                AnalyticsManager.shared.permissionSkipped(permission: "notifications")
            }
            if !appState.hasAccessibilityPermission {
                AnalyticsManager.shared.permissionSkipped(permission: "accessibility")
            }
            if !appState.hasAutomationPermission {
                AnalyticsManager.shared.permissionSkipped(permission: "automation")
            }
            // Trigger proactive monitoring if screen recording is granted
            if appState.hasScreenRecordingPermission {
                ProactiveAssistantsPlugin.shared.startMonitoring { _, _ in }
            }
            // If file indexing was skipped, complete onboarding directly
            if fileIndexingSkipped {
                handleFileIndexingComplete(fileCount: 0)
            } else {
                currentStep += 1
            }
        case 5:
            break // Chat reveal view has its own Done button
        default:
            break
        }
    }

    // MARK: - Background File Indexing

    private func startBackgroundFileIndexing() {
        scanningInProgress = true
        backgroundScanTask = Task {
            await performBackgroundScan()

            guard !Task.isCancelled else { return }

            await MainActor.run {
                scanningInProgress = false
            }

            // Auto-start the AI exploration chat
            await startExplorationChat()
        }
    }

    private func performBackgroundScan() async {
        let home = FileManager.default.homeDirectoryForCurrentUser
        let folders = [
            ("Downloads", home.appendingPathComponent("Downloads")),
            ("Documents", home.appendingPathComponent("Documents")),
            ("Desktop", home.appendingPathComponent("Desktop")),
            ("Developer", home.appendingPathComponent("Developer")),
            ("Projects", home.appendingPathComponent("Projects")),
            ("Code", home.appendingPathComponent("Code")),
            ("src", home.appendingPathComponent("src")),
            ("repos", home.appendingPathComponent("repos")),
            ("Sites", home.appendingPathComponent("Sites")),
        ]

        let fm = FileManager.default
        for (name, url) in folders {
            guard !Task.isCancelled else { return }
            guard fm.fileExists(atPath: url.path) else { continue }
            log("FileIndexer: Scanning \(name)")
            let count = await FileIndexerService.shared.scanFolders([url])
            await MainActor.run {
                totalFilesScanned += count
            }
        }

        // Also index installed app names from /Applications
        guard !Task.isCancelled else { return }
        let appDirs = [
            URL(fileURLWithPath: "/Applications"),
            home.appendingPathComponent("Applications"),
        ]
        for dir in appDirs {
            guard !Task.isCancelled else { return }
            let scanned = await FileIndexerService.shared.scanFolders([dir])
            await MainActor.run {
                totalFilesScanned += scanned
            }
        }

        await MainActor.run {
            UserDefaults.standard.set(true, forKey: "hasCompletedFileIndexing")
        }
    }

    private func startExplorationChat() async {
        // Multi-chat users get a dedicated session; single-chat users stay in default chat
        if chatProvider.multiChatEnabled {
            let session = await chatProvider.createNewSession(skipGreeting: true)
            guard session != nil else {
                log("OnboardingView: Failed to create session for file exploration")
                return
            }
        }

        let prompt = """
        I just indexed \(totalFilesScanned) files on your computer. I want to understand who you are — your projects, passions, and what you're building.

        Use the execute_sql tool to explore the indexed_files table. Start with an overview (file types, folders, project indicators), then dig deeper:

        1. Find project files (package.json, Cargo.toml, etc.) to identify active projects
        2. Look at recently modified files to understand what you're working on right now
        3. Search for patterns — recurring themes, technologies, interests
        4. Open interesting files (read_file tool) to understand project purposes and context
        5. Don't stop at surface level — keep investigating, follow threads, connect the dots

        Tell me a story about this person. Who are they? What are they building? What drives them? What's their tech stack and workflow? Share discoveries as you find them, like you're exploring and getting to know a new friend.
        """
        await chatProvider.sendMessage(prompt)

        // Append the AI's exploration response to the user's AI profile
        await appendExplorationToProfile()

        // Follow up: ask the model to find something actionable
        await chatProvider.sendMessage("Now based on everything you discovered, find something that you can actually help me with to get done. Something that is clearly not done yet and something that you as an AI agent can execute upon.")
    }

    private func appendExplorationToProfile() async {
        // Get the last AI message (the exploration response)
        guard let lastAIMessage = chatProvider.messages.last(where: { $0.sender == .ai }),
              !lastAIMessage.text.isEmpty else {
            log("OnboardingView: No AI response to append to profile")
            return
        }

        let explorationText = lastAIMessage.text
        let service = AIUserProfileService.shared

        // Retry up to 3 times for transient SQLite/network failures
        for attempt in 1...3 {
            let existingProfile = await service.getLatestProfile()

            if let existing = existingProfile, let profileId = existing.id {
                // Append to existing profile
                let updated = existing.profileText + "\n\n--- File Exploration Insights ---\n" + explorationText
                let success = await service.updateProfileText(id: profileId, newText: updated)
                log("OnboardingView: Appended exploration to AI profile (success=\(success), attempt=\(attempt))")
                if success { return }
            } else {
                // No profile exists yet — save exploration text directly as a new profile
                let success = await service.saveExplorationAsProfile(text: "--- File Exploration Insights ---\n" + explorationText)
                log("OnboardingView: Saved exploration as new AI profile (success=\(success), attempt=\(attempt))")
                if success { return }
            }

            // Wait before retrying (2s, 4s)
            if attempt < 3 {
                log("OnboardingView: Retrying profile save (attempt \(attempt) failed)")
                try? await Task.sleep(nanoseconds: UInt64(attempt) * 2_000_000_000)
            }
        }
        log("OnboardingView: Failed to save exploration to AI profile after 3 attempts")
    }

    private func handleSkipFileIndexing() {
        log("OnboardingView: User skipped file indexing")
        fileIndexingSkipped = true
        UserDefaults.standard.set(true, forKey: "hasCompletedFileIndexing")
        AnalyticsManager.shared.onboardingStepCompleted(step: 3, stepName: "FileIndexingConsent_Skipped")
        currentStep += 1 // Advance to permissions step
    }
}

// MARK: - Onboarding Video View

struct OnboardingVideoView: NSViewRepresentable {
    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    func makeNSView(context: Context) -> AVPlayerView {
        let playerView = AVPlayerView()
        if let url = Bundle.resourceBundle.url(forResource: "omi-demo", withExtension: "mp4") {
            let player = AVPlayer(url: url)
            playerView.player = player
            playerView.controlsStyle = .inline
            playerView.showsFullScreenToggleButton = false
            player.play()

            NotificationCenter.default.addObserver(
                context.coordinator,
                selector: #selector(Coordinator.playerDidFinishPlaying(_:)),
                name: .AVPlayerItemDidPlayToEndTime,
                object: player.currentItem
            )
            context.coordinator.player = player
        }
        return playerView
    }

    func updateNSView(_ nsView: AVPlayerView, context: Context) {}

    class Coordinator: NSObject {
        var player: AVPlayer?

        @objc func playerDidFinishPlaying(_ notification: Notification) {
            player?.seek(to: .zero)
            player?.play()
        }
    }
}

// MARK: - Animated GIF View

struct AnimatedGIFView: NSViewRepresentable {
    let gifName: String

    func makeNSView(context: Context) -> NSImageView {
        let imageView = NSImageView()
        imageView.imageScaling = .scaleProportionallyDown
        imageView.animates = true
        imageView.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        imageView.setContentCompressionResistancePriority(.defaultLow, for: .vertical)

        if let url = Bundle.resourceBundle.url(forResource: gifName, withExtension: "gif"),
           let image = NSImage(contentsOf: url) {
            imageView.image = image
        }

        return imageView
    }

    func updateNSView(_ nsView: NSImageView, context: Context) {
        nsView.animates = true
    }
}

// MARK: - Onboarding Privacy Sheet

struct OnboardingPrivacySheet: View {
    @Binding var isPresented: Bool

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Image(systemName: "shield.lefthalf.filled")
                    .scaledFont(size: 16)
                    .foregroundColor(OmiColors.purplePrimary)

                Text("Data & Privacy")
                    .scaledFont(size: 16, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                Button(action: { isPresented = false }) {
                    Image(systemName: "xmark.circle.fill")
                        .scaledFont(size: 18)
                        .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
            }
            .padding(20)

            Divider()

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    // Encryption
                    privacyCard {
                        VStack(alignment: .leading, spacing: 10) {
                            Label("Encryption", systemImage: "lock.shield")
                                .scaledFont(size: 13, weight: .semibold)
                                .foregroundColor(OmiColors.textPrimary)

                            HStack(spacing: 8) {
                                Image(systemName: "checkmark.circle.fill")
                                    .scaledFont(size: 11)
                                    .foregroundColor(.green)
                                Text("Server-side encryption")
                                    .scaledFont(size: 12)
                                    .foregroundColor(OmiColors.textSecondary)
                                Text("Active")
                                    .scaledFont(size: 10, weight: .semibold)
                                    .foregroundColor(.green)
                                    .padding(.horizontal, 5)
                                    .padding(.vertical, 1)
                                    .background(Color.green.opacity(0.15))
                                    .cornerRadius(3)
                            }

                            HStack(spacing: 8) {
                                Image(systemName: "lock.fill")
                                    .scaledFont(size: 11)
                                    .foregroundColor(OmiColors.textTertiary)
                                Text("End-to-end encryption")
                                    .scaledFont(size: 12)
                                    .foregroundColor(OmiColors.textTertiary)
                                Text("Coming Soon")
                                    .scaledFont(size: 10, weight: .semibold)
                                    .foregroundColor(OmiColors.textTertiary)
                                    .padding(.horizontal, 5)
                                    .padding(.vertical, 1)
                                    .background(OmiColors.backgroundQuaternary.opacity(0.5))
                                    .cornerRadius(3)
                            }

                            Text("Your data is encrypted and stored securely with Google Cloud infrastructure.")
                                .scaledFont(size: 11)
                                .foregroundColor(OmiColors.textTertiary)
                                .padding(.top, 2)
                        }
                    }

                    // What We Track
                    privacyCard {
                        VStack(alignment: .leading, spacing: 8) {
                            Label("What We Track", systemImage: "list.bullet")
                                .scaledFont(size: 13, weight: .semibold)
                                .foregroundColor(OmiColors.textPrimary)

                            VStack(alignment: .leading, spacing: 4) {
                                sheetTrackingItem("Onboarding steps completed")
                                sheetTrackingItem("Settings changes")
                                sheetTrackingItem("App installations and usage")
                                sheetTrackingItem("Device connection status")
                                sheetTrackingItem("Transcript processing events")
                                sheetTrackingItem("Conversation creation and updates")
                                sheetTrackingItem("Memory extraction events")
                                sheetTrackingItem("Chat interactions")
                                sheetTrackingItem("Speech profile creation")
                                sheetTrackingItem("Focus session events")
                                sheetTrackingItem("App open/close events")
                            }
                        }
                    }

                    // Privacy Guarantees
                    privacyCard {
                        VStack(alignment: .leading, spacing: 8) {
                            Label("Privacy Guarantees", systemImage: "hand.raised.fill")
                                .scaledFont(size: 13, weight: .semibold)
                                .foregroundColor(OmiColors.textPrimary)

                            VStack(alignment: .leading, spacing: 5) {
                                sheetBullet("Anonymous tracking with randomly generated IDs")
                                sheetBullet("No personal info stored in analytics")
                                sheetBullet("Data is never sold or shared with third parties")
                                sheetBullet("Opt out of tracking at any time")
                            }
                        }
                    }
                }
                .padding(20)
            }
        }
        .frame(width: 400, height: 480)
        .background(OmiColors.backgroundSecondary)
    }

    private func privacyCard<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        content()
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(OmiColors.backgroundTertiary.opacity(0.5))
                    .overlay(
                        RoundedRectangle(cornerRadius: 10)
                            .stroke(OmiColors.backgroundQuaternary.opacity(0.3), lineWidth: 1)
                    )
            )
    }

    private func sheetTrackingItem(_ text: String) -> some View {
        HStack(spacing: 6) {
            Circle()
                .fill(OmiColors.textTertiary.opacity(0.5))
                .frame(width: 3, height: 3)
            Text(text)
                .scaledFont(size: 11)
                .foregroundColor(OmiColors.textTertiary)
        }
    }

    private func sheetBullet(_ text: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: "checkmark")
                .scaledFont(size: 8, weight: .bold)
                .foregroundColor(.green)
            Text(text)
                .scaledFont(size: 11)
                .foregroundColor(OmiColors.textSecondary)
        }
    }
}
