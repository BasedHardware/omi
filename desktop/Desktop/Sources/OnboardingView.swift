import SwiftUI
import AppKit
import AVKit

struct OnboardingView: View {
    @ObservedObject var appState: AppState
    var onComplete: (() -> Void)? = nil
    @AppStorage("onboardingStep") private var currentStep = 0
    @Environment(\.dismiss) private var dismiss

    // Timer to periodically check permission status when on permissions step
    let permissionCheckTimer = Timer.publish(every: 1.0, on: .main, in: .common).autoconnect()

    let steps = ["Video", "Name", "Language", "Permissions", "Done"]

    // State for name input
    @State private var nameInput: String = ""
    @State private var nameError: String = ""
    @FocusState private var isNameFieldFocused: Bool

    // State for language selection
    @State private var selectedLanguage: String = "en"
    @State private var autoDetectEnabled: Bool = false

    // Track whether we've initialized bluetooth on the permissions step
    @State private var hasInitializedBluetoothForPermissions = false

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
            if currentStep == 3 {
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
            if granted && currentStep == 3 {
                log("Notification permission granted on permissions step, bringing to front")
                bringToFront()
            }
        }
        .onChange(of: appState.hasScreenRecordingPermission) { _, granted in
            if granted && currentStep == 3 {
                log("Screen recording permission granted on permissions step, bringing to front")
                bringToFront()
                // Silently trigger system audio permission (piggybacks on screen recording)
                if appState.isSystemAudioSupported && !appState.hasSystemAudioPermission {
                    appState.triggerSystemAudioPermission()
                }
            }
        }
        .onChange(of: appState.hasMicrophonePermission) { _, granted in
            if granted && currentStep == 3 {
                log("Microphone permission granted on permissions step, bringing to front")
                bringToFront()
            }
        }
        .onChange(of: appState.hasAccessibilityPermission) { _, granted in
            if granted && currentStep == 3 {
                log("Accessibility permission granted on permissions step, bringing to front")
                bringToFront()
            }
        }
        .onChange(of: appState.hasAutomationPermission) { _, granted in
            if granted && currentStep == 3 {
                log("Automation permission granted on permissions step, bringing to front")
                bringToFront()
            }
        }
        .onChange(of: appState.hasBluetoothPermission) { _, granted in
            if granted && currentStep == 3 {
                log("Bluetooth permission granted on permissions step, bringing to front")
                bringToFront()
            }
        }
        .onChange(of: currentStep) { _, newStep in
            // Initialize Bluetooth when reaching permissions step
            if newStep == 3 && !hasInitializedBluetoothForPermissions {
                log("Reached Permissions step, initializing Bluetooth manager")
                appState.initializeBluetoothIfNeeded()
                hasInitializedBluetoothForPermissions = true
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
        case 3: return true // Permissions step - always allow continuing (Skip exists)
        case 4: return true // Done step
        default: return true
        }
    }

    private var allPermissionsGranted: Bool {
        appState.hasScreenRecordingPermission
            && appState.hasMicrophonePermission
            && appState.hasNotificationPermission
            && appState.hasAccessibilityPermission
            && appState.hasAutomationPermission
            && (appState.hasBluetoothPermission || isBluetoothUnsupported || isBluetoothPermissionDenied)
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
                        // Progress indicators + Skip button row
                        ZStack {
                            HStack(spacing: 12) {
                                ForEach(0..<steps.count, id: \.self) { index in
                                    progressIndicator(for: index)
                                }
                            }

                            // Skip button in top-right corner (only on Permissions step)
                            if currentStep == 3 {
                                HStack {
                                    Spacer()
                                    Button(action: {
                                        AnalyticsManager.shared.onboardingStepCompleted(step: 3, stepName: "Permissions")
                                        currentStep = 4
                                    }) {
                                        Text("Skip")
                                            .font(.system(size: 13))
                                            .foregroundColor(.secondary)
                                    }
                                    .buttonStyle(.plain)
                                }
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
                    .frame(width: currentStep == 3 ? 480 : 420)
                    .frame(height: currentStep == 3 ? 520 : 420)
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
                .font(.system(size: 12))
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
        case 3: return allPermissionsGranted // Permissions step
        case 4: return true // Done - always "granted"
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
            permissionsStepView
        case 4:
            VStack(spacing: 16) {
                Image(systemName: "checkmark.circle")
                    .font(.system(size: 48))
                    .foregroundColor(OmiColors.purplePrimary)

                Text("You're All Set!")
                    .font(.title)
                    .fontWeight(.semibold)

                Text("Just use Omi in the background for 2 days and you'll start getting useful feedback after!")
                    .font(.title3)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
                    .fixedSize(horizontal: false, vertical: true)
            }
        default:
            EmptyView()
        }
    }

    // MARK: - Name Step View

    private var nameStepView: some View {
        VStack(spacing: 16) {
            Image(systemName: "person.circle")
                .font(.system(size: 48))
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
                .font(.system(size: 48))
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
        }
    }

    // MARK: - Consolidated Permissions Step View

    private var permissionsStepView: some View {
        VStack(spacing: 16) {
            Text("Permissions")
                .font(.title2)
                .fontWeight(.semibold)

            Text("Omi needs a few permissions to work properly.")
                .font(.body)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 24)

            ScrollView {
                VStack(spacing: 10) {
                    VStack(spacing: 4) {
                        permissionRow(
                            number: 1,
                            icon: "record.circle",
                            name: "Screen Recording",
                            isGranted: appState.hasScreenRecordingPermission,
                            action: {
                                AnalyticsManager.shared.permissionRequested(permission: "screen_recording")
                                appState.triggerScreenRecordingPermission()
                            }
                        )
                        VStack(spacing: 2) {
                            Text("Used for Rewind — your personal screen history.")
                                .font(.system(size: 11, weight: .medium))
                                .foregroundColor(.secondary)
                            Text("All data stays on your device. Nothing is uploaded to the cloud.")
                                .font(.system(size: 11))
                                .foregroundColor(.secondary)
                        }
                        .padding(.horizontal, 16)
                        .padding(.bottom, 4)
                    }
                    permissionRow(
                        number: 2,
                        icon: "mic",
                        name: "Microphone",
                        isGranted: appState.hasMicrophonePermission,
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
                        action: {
                            AnalyticsManager.shared.permissionRequested(permission: "automation")
                            appState.triggerAutomationPermission()
                        }
                    )
                    permissionRow(
                        number: 6,
                        icon: "antenna.radiowaves.left.and.right",
                        name: "Bluetooth",
                        isGranted: appState.hasBluetoothPermission || isBluetoothUnsupported || isBluetoothPermissionDenied,
                        action: {
                            AnalyticsManager.shared.permissionRequested(permission: "bluetooth")
                            appState.initializeBluetoothIfNeeded()
                            appState.triggerBluetoothPermission()
                        }
                    )
                }
                .padding(.horizontal, 24)
            }
            .frame(maxHeight: 260)
        }
    }

    @ViewBuilder
    private func permissionRow(number: Int, icon: String, name: String, isGranted: Bool, action: @escaping () -> Void) -> some View {
        HStack(spacing: 12) {
            Text("\(number).")
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(.secondary)
                .frame(width: 20, alignment: .trailing)

            Image(systemName: icon)
                .font(.system(size: 14))
                .foregroundColor(isGranted ? .green : OmiColors.purplePrimary)
                .frame(width: 20)

            Text(name)
                .font(.system(size: 14, weight: .medium))

            Spacer()

            if isGranted {
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 16))
                    .foregroundColor(.green)
            } else {
                Button(action: action) {
                    Text("Grant Access")
                        .font(.system(size: 12, weight: .medium))
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
                .fill(isGranted ? Color.green.opacity(0.08) : OmiColors.backgroundPrimary.opacity(0.5))
        )
    }

    private var isBluetoothPermissionDenied: Bool {
        appState.isBluetoothPermissionDenied()
    }

    private var isBluetoothUnsupported: Bool {
        appState.isBluetoothUnsupported()
    }

    @ViewBuilder
    private var buttonSection: some View {
        HStack(spacing: 16) {
            // Back button (not shown on first step or name step)
            if currentStep > 0 && currentStep != 1 {
                Button(action: { currentStep -= 1 }) {
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
        .padding(.horizontal, 40)
        .padding(.bottom, 20)
    }

    private var mainButtonTitle: String {
        switch currentStep {
        case 0: return "Continue"
        case 1: return "Continue"
        case 2: return "Continue"
        case 3: return "Continue"
        case 4: return "Start Using Omi"
        default: return "Continue"
        }
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
            // Permissions step - advance to Done
            AnalyticsManager.shared.onboardingStepCompleted(step: 3, stepName: "Permissions")
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
            if appState.hasBluetoothPermission {
                AnalyticsManager.shared.permissionGranted(permission: "bluetooth")
            }
            // Trigger proactive monitoring if screen recording is granted
            if appState.hasScreenRecordingPermission {
                ProactiveAssistantsPlugin.shared.startMonitoring { _, _ in }
            }
            currentStep += 1
        case 4:
            log("OnboardingView: Step 4 - Completing onboarding")
            AnalyticsManager.shared.onboardingStepCompleted(step: 4, stepName: "Done")
            AnalyticsManager.shared.onboardingCompleted()
            appState.hasCompletedOnboarding = true
            // Enable launch at login by default for new users
            if LaunchAtLoginManager.shared.setEnabled(true) {
                AnalyticsManager.shared.launchAtLoginChanged(enabled: true, source: "onboarding")
            }
            ProactiveAssistantsPlugin.shared.startMonitoring { _, _ in }
            appState.startTranscription()
            // Only call completion handler if provided (for sheet presentations)
            // Don't dismiss - DesktopHomeView will automatically transition to mainContent
            if let onComplete = onComplete {
                log("OnboardingView: Calling onComplete handler")
                onComplete()
            } else {
                log("OnboardingView: Onboarding complete, DesktopHomeView will show mainContent")
            }
        default:
            break
        }
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
