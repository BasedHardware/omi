import SwiftUI
import AppKit
import AVKit

struct OnboardingView: View {
    @ObservedObject var appState: AppState
    var onComplete: (() -> Void)? = nil
    @AppStorage("onboardingStep") private var currentStep = 0
    @Environment(\.dismiss) private var dismiss

    // Track which permissions user has attempted to grant (to start polling)
    // Persisted so polling resumes after app restart
    @AppStorage("hasTriggeredNotification") private var hasTriggeredNotification = false
    @AppStorage("hasTriggeredAutomation") private var hasTriggeredAutomation = false
    @AppStorage("hasTriggeredScreenRecording") private var hasTriggeredScreenRecording = false
    @AppStorage("hasTriggeredMicrophone") private var hasTriggeredMicrophone = false
    @AppStorage("hasTriggeredSystemAudio") private var hasTriggeredSystemAudio = false
    @AppStorage("hasTriggeredAccessibility") private var hasTriggeredAccessibility = false
    @AppStorage("hasTriggeredBluetooth") private var hasTriggeredBluetooth = false

    // Timer to periodically check permission status (only for triggered permissions)
    let permissionCheckTimer = Timer.publish(every: 1.0, on: .main, in: .common).autoconnect()

    let steps = ["Video", "Name", "Language", "Notifications", "Automation", "Screen Recording", "Microphone", "System Audio", "Accessibility", "Bluetooth", "Done"]

    // State for name input
    @State private var nameInput: String = ""
    @State private var nameError: String = ""
    @FocusState private var isNameFieldFocused: Bool

    // State for language selection
    @State private var selectedLanguage: String = "en"
    @State private var autoDetectEnabled: Bool = false

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
            // Only poll for permissions that user has triggered
            if hasTriggeredNotification {
                appState.checkNotificationPermission()
            }
            if hasTriggeredAutomation {
                appState.checkAutomationPermission()
            }
            if hasTriggeredScreenRecording {
                appState.checkScreenRecordingPermission()
            }
            if hasTriggeredMicrophone {
                appState.checkMicrophonePermission()
            }
            if hasTriggeredSystemAudio {
                appState.checkSystemAudioPermission()
            }
            if hasTriggeredAccessibility {
                appState.checkAccessibilityPermission()
            }
            if hasTriggeredBluetooth {
                appState.checkBluetoothPermission()
            }
        }
        // Bring app to front when the CURRENT step's permission is granted
        // Only bring to front if we're on the step that requires this permission
        .onChange(of: appState.hasNotificationPermission) { _, granted in
            if granted && currentStep == 3 {
                log("Notification permission granted (current step), bringing to front")
                bringToFront()
            } else if granted {
                log("Notification permission granted (not current step \(currentStep), skipping bringToFront)")
            }
        }
        .onChange(of: appState.hasAutomationPermission) { _, granted in
            if granted && currentStep == 4 {
                log("Automation permission granted (current step), bringing to front")
                bringToFront()
            } else if granted {
                log("Automation permission granted (not current step \(currentStep), skipping bringToFront)")
            }
        }
        .onChange(of: appState.hasScreenRecordingPermission) { _, granted in
            if granted && currentStep == 5 {
                log("Screen recording permission granted (current step), bringing to front")
                bringToFront()
            } else if granted {
                log("Screen recording permission granted (not current step \(currentStep), skipping bringToFront)")
            }
        }
        .onChange(of: appState.hasMicrophonePermission) { _, granted in
            if granted && currentStep == 6 {
                log("Microphone permission granted (current step), bringing to front")
                bringToFront()
            } else if granted {
                log("Microphone permission granted (not current step \(currentStep), skipping bringToFront)")
            }
        }
        .onChange(of: appState.hasSystemAudioPermission) { _, granted in
            if granted && currentStep == 7 {
                log("System audio permission granted (current step), bringing to front")
                bringToFront()
            } else if granted {
                log("System audio permission granted (not current step \(currentStep), skipping bringToFront)")
            }
        }
        .onChange(of: appState.hasAccessibilityPermission) { _, granted in
            if granted && currentStep == 8 {
                log("Accessibility permission granted (current step), bringing to front")
                bringToFront()
            } else if granted {
                log("Accessibility permission granted (not current step \(currentStep), skipping bringToFront)")
            }
        }
        .onChange(of: appState.hasBluetoothPermission) { _, granted in
            if granted && currentStep == 9 {
                log("Bluetooth permission granted (current step), bringing to front")
                bringToFront()
            } else if granted {
                log("Bluetooth permission granted (not current step \(currentStep), skipping bringToFront)")
            }
        }
        .onChange(of: currentStep) { _, newStep in
            // Initialize Bluetooth when reaching step 9 so the state is shown correctly
            if newStep == 9 {
                log("Reached Bluetooth step, initializing Bluetooth manager")
                appState.initializeBluetoothIfNeeded()
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
        case 3: return appState.hasNotificationPermission
        case 4: return appState.hasAutomationPermission
        case 5: return appState.hasScreenRecordingPermission
        case 6: return appState.hasMicrophonePermission
        case 7: return !appState.isSystemAudioSupported || appState.hasSystemAudioPermission // Skip if not supported
        case 8: return appState.hasAccessibilityPermission
        case 9: return appState.hasBluetoothPermission || isBluetoothUnsupported || isBluetoothPermissionDenied
        default: return true
        }
    }

    private var onboardingContent: some View {
        Group {
            if currentStep == 0 {
                // Full-window video with overlaid controls
                ZStack {
                    OnboardingVideoView()
                        .ignoresSafeArea()

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
                        HStack(spacing: 12) {
                            ForEach(0..<steps.count, id: \.self) { index in
                                progressIndicator(for: index)
                            }
                        }
                        .padding(.top, 20)

                        Spacer()
                            .frame(height: 20)

                        stepContent

                        Spacer()
                            .frame(height: 20)

                        buttonSection
                    }
                    .frame(width: (currentStep == 3 && !appState.hasNotificationPermission) || (currentStep == 5 && !appState.hasScreenRecordingPermission) ? 500 : 420)
                    .frame(height: (currentStep == 3 && !appState.hasNotificationPermission) || (currentStep == 5 && !appState.hasScreenRecordingPermission) ? 520 : 420)
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
        case 3: return appState.hasNotificationPermission
        case 4: return appState.hasAutomationPermission
        case 5: return appState.hasScreenRecordingPermission
        case 6: return appState.hasMicrophonePermission
        case 7: return !appState.isSystemAudioSupported || appState.hasSystemAudioPermission // System Audio
        case 8: return appState.hasAccessibilityPermission // Accessibility
        case 9: return appState.hasBluetoothPermission || isBluetoothUnsupported || isBluetoothPermissionDenied // Bluetooth (allow skip if unsupported/denied)
        case 10: return true // Done - always "granted"
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
            notificationStepView
        case 4:
            stepView(
                icon: appState.hasAutomationPermission ? "checkmark.circle.fill" : "gearshape.2",
                iconColor: appState.hasAutomationPermission ? .white : OmiColors.purplePrimary,
                title: "Automation",
                description: appState.hasAutomationPermission
                    ? "Automation permission granted! Omi can now detect which app you're using."
                    : "Omi needs Automation permission to detect which app you're using.\n\nClick below to grant permission, then return to this window."
            )
        case 5:
            screenRecordingStepView
        case 6:
            microphoneStepView
        case 7:
            systemAudioStepView
        case 8:
            accessibilityStepView
        case 9:
            bluetoothStepView
        case 10:
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

    private func stepView(icon: String, iconColor: Color = OmiColors.purplePrimary, title: String, description: String) -> some View {
        VStack(spacing: 16) {
            Image(systemName: icon)
                .font(.system(size: 48))
                .foregroundColor(iconColor)

            Text(title)
                .font(.title2)
                .fontWeight(.semibold)

            Text(description)
                .font(.body)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)
                .fixedSize(horizontal: false, vertical: true)
        }
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
        case 0:
            return "Continue"
        case 1:
            return "Continue"  // Name step
        case 2:
            return "Continue"  // Language step
        case 3:
            return appState.hasNotificationPermission ? "Continue" : "Enable Notifications"
        case 4:
            return appState.hasAutomationPermission ? "Continue" : "Grant Automation Access"
        case 5:
            return appState.hasScreenRecordingPermission ? "Continue" : "Grant Screen Recording"
        case 6:
            return appState.hasMicrophonePermission ? "Continue" : "Enable Microphone"
        case 7:
            return systemAudioButtonTitle
        case 8:
            return appState.hasAccessibilityPermission ? "Continue" : "Grant Accessibility"
        case 9:
            if appState.hasBluetoothPermission {
                return "Continue"
            } else if isBluetoothUnsupported || isBluetoothPermissionDenied {
                return "Skip"
            } else {
                return "Grant Bluetooth Access"
            }
        case 10:
            return "Start Using Omi"
        default:
            return "Continue"
        }
    }

    private var systemAudioButtonTitle: String {
        if !appState.isSystemAudioSupported {
            return "Continue"  // Not supported on this macOS version
        }
        return appState.hasSystemAudioPermission ? "Continue" : "Enable System Audio"
    }

    // MARK: - Microphone Step View

    @State private var micResetInProgress = false
    @State private var micResetButtonText = "Reset & Restart"

    private var isMicrophonePermissionDenied: Bool {
        appState.isMicrophonePermissionDenied()
    }

    private var microphoneStepView: some View {
        VStack(spacing: 16) {
            if appState.hasMicrophonePermission {
                // Granted state
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 48))
                    .foregroundColor(.white)

                Text("Microphone")
                    .font(.title2)
                    .fontWeight(.semibold)

                Text("Microphone access granted! Omi can now transcribe your conversations.")
                    .font(.body)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)

            } else if isMicrophonePermissionDenied {
                // Denied state - show reset options
                // Note: Grant Access button is NOT shown here because macOS won't show the permission
                // dialog again after the user denied it. They must reset the permission first.
                Image(systemName: "mic.slash.fill")
                    .font(.system(size: 48))
                    .foregroundColor(.red)

                Text("Microphone Permission Denied")
                    .font(.title2)
                    .fontWeight(.semibold)

                Text("Permission was previously denied. Reset it to try again:")
                    .font(.body)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)

                VStack(spacing: 8) {
                    // Option 1: Quick Reset
                    Button(action: micTryDirectReset) {
                        HStack(spacing: 8) {
                            if micResetInProgress {
                                ProgressView()
                                    .scaleEffect(0.7)
                                    .frame(width: 14, height: 14)
                            } else {
                                Image(systemName: "arrow.clockwise")
                                    .font(.system(size: 14))
                            }
                            Text(micResetButtonText)
                                .font(.system(size: 13, weight: .medium))
                        }
                        .foregroundColor(.primary)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                        .frame(width: 260)
                        .background(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(Color.secondary.opacity(0.5), lineWidth: 1)
                        )
                    }
                    .buttonStyle(.plain)
                    .disabled(micResetInProgress)

                    // Option 2: Terminal
                    Button(action: micTryTerminalReset) {
                        HStack(spacing: 8) {
                            Image(systemName: "terminal")
                                .font(.system(size: 14))
                            Text("Reset via Terminal")
                                .font(.system(size: 13, weight: .medium))
                        }
                        .foregroundColor(.primary)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                        .frame(width: 260)
                        .background(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(Color.secondary.opacity(0.5), lineWidth: 1)
                        )
                    }
                    .buttonStyle(.plain)

                    // Option 3: Manual
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Option 3: Manual")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(.secondary)

                        // Step 1
                        HStack(alignment: .top, spacing: 6) {
                            Text("1.")
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(.secondary)
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Open System Settings")
                                    .font(.system(size: 12))
                                    .foregroundColor(.secondary)
                                Button(action: micOpenSystemSettings) {
                                    HStack(spacing: 6) {
                                        Image(systemName: "gear")
                                            .font(.system(size: 12))
                                        Text("Open Settings")
                                            .font(.system(size: 12, weight: .medium))
                                    }
                                    .foregroundColor(.primary)
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 6)
                                    .background(
                                        RoundedRectangle(cornerRadius: 6)
                                            .stroke(Color.secondary.opacity(0.5), lineWidth: 1)
                                    )
                                }
                                .buttonStyle(.plain)
                            }
                        }

                        // Step 2
                        HStack(alignment: .top, spacing: 6) {
                            Text("2.")
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(.secondary)
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Find \"Omi\" and toggle it ON")
                                    .font(.system(size: 12))
                                    .foregroundColor(.secondary)

                                // Screenshot
                                if let image = NSImage(contentsOfFile: Bundle.resourceBundle.path(forResource: "microphone-settings", ofType: "png") ?? "") {
                                    Image(nsImage: image)
                                        .resizable()
                                        .scaledToFit()
                                        .frame(maxWidth: 220)
                                        .cornerRadius(6)
                                        .overlay(
                                            RoundedRectangle(cornerRadius: 6)
                                                .stroke(Color.secondary.opacity(0.3), lineWidth: 1)
                                        )
                                }
                            }
                        }
                    }
                    .frame(width: 260, alignment: .leading)
                }

            } else {
                // Not determined state - normal flow
                Image(systemName: "mic")
                    .font(.system(size: 48))
                    .foregroundColor(OmiColors.purplePrimary)

                Text("Microphone")
                    .font(.title2)
                    .fontWeight(.semibold)

                Text("Omi needs microphone access to transcribe your conversations and provide context-aware assistance.")
                    .font(.body)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
            }
        }
    }

    private func micTryDirectReset() {
        micResetInProgress = true
        micResetButtonText = "Resetting & Restarting..."

        DispatchQueue.global(qos: .userInitiated).async {
            // Reset and restart the app - macOS requires restart to show permission dialog again
            let success = appState.resetMicrophonePermissionDirect(shouldRestart: true)

            if !success {
                DispatchQueue.main.async {
                    micResetButtonText = "Failed - Try Terminal"
                    DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
                        micResetInProgress = false
                        micResetButtonText = "Reset & Restart"
                    }
                }
            }
            // If success, app will restart automatically
        }
    }

    private func micTryTerminalReset() {
        // Reset via terminal and restart - macOS requires restart to show permission dialog again
        appState.resetMicrophonePermissionViaTerminal(shouldRestart: true)
    }

    private func micOpenSystemSettings() {
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone") {
            NSWorkspace.shared.open(url)
        }
        // User will manually grant permission in System Settings
        // No automatic restart needed - they can grant it directly there
    }

    // MARK: - Notification Step with Tutorial GIF

    private var notificationStepView: some View {
        VStack(spacing: 12) {
            if appState.hasNotificationPermission {
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 48))
                    .foregroundColor(.white)

                Text("Notifications")
                    .font(.title2)
                    .fontWeight(.semibold)

                Text("Notifications are enabled! You'll receive focus alerts from Omi.")
                    .font(.body)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
            } else {
                Text("Notifications")
                    .font(.title2)
                    .fontWeight(.semibold)

                Text("Omi sends you gentle notifications when it detects you're getting distracted from your work.")
                    .font(.body)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)

                // Animated GIF tutorial
                AnimatedGIFView(gifName: "enable_notifications")
                    .frame(maxWidth: 440, maxHeight: 350)
                    .cornerRadius(8)
                    .shadow(color: .black.opacity(0.2), radius: 4, x: 0, y: 2)
            }
        }
    }

    // MARK: - Screen Recording Step with Tutorial GIF

    private var screenRecordingStepView: some View {
        VStack(spacing: 12) {
            if appState.hasScreenRecordingPermission {
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 48))
                    .foregroundColor(.white)

                Text("Screen Recording")
                    .font(.title2)
                    .fontWeight(.semibold)

                Text("Screen Recording permission granted! Omi can now analyze your focus.")
                    .font(.body)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
            } else {
                Text("Screen Recording")
                    .font(.title2)
                    .fontWeight(.semibold)

                Text("Follow these steps to grant permission:")
                    .font(.body)
                    .foregroundColor(.secondary)

                // Animated GIF tutorial
                AnimatedGIFView(gifName: "permissions")
                    .frame(maxWidth: 440, maxHeight: 350)
                    .cornerRadius(8)
                    .shadow(color: .black.opacity(0.2), radius: 4, x: 0, y: 2)
            }
        }
    }

    // MARK: - System Audio Step View

    private var systemAudioStepView: some View {
        VStack(spacing: 16) {
            if !appState.isSystemAudioSupported {
                // macOS version doesn't support system audio capture
                Image(systemName: "speaker.slash")
                    .font(.system(size: 48))
                    .foregroundColor(.secondary)

                Text("System Audio")
                    .font(.title2)
                    .fontWeight(.semibold)

                Text("System audio capture requires macOS 14.4 or later.\n\nYou can still use Omi with microphone-only transcription.")
                    .font(.body)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
            } else if appState.hasSystemAudioPermission {
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 48))
                    .foregroundColor(.white)

                Text("System Audio")
                    .font(.title2)
                    .fontWeight(.semibold)

                Text("System audio capture is ready! Omi can now capture audio from your meetings and media.")
                    .font(.body)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
            } else {
                Image(systemName: "speaker.wave.2")
                    .font(.system(size: 48))
                    .foregroundColor(OmiColors.purplePrimary)

                Text("System Audio")
                    .font(.title2)
                    .fontWeight(.semibold)

                Text("Omi can capture system audio to transcribe meetings, videos, and other media playing on your Mac.\n\nThis uses the same Screen Recording permission you already granted.")
                    .font(.body)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    // MARK: - Accessibility Step View

    @State private var accessibilityResetInProgress = false
    @State private var accessibilityResetButtonText = "Reset & Restart"

    private var isAccessibilityPermissionDenied: Bool {
        appState.isAccessibilityPermissionDenied()
    }

    private var accessibilityStepView: some View {
        VStack(spacing: 16) {
            if appState.hasAccessibilityPermission {
                // Granted state
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 48))
                    .foregroundColor(.white)

                Text("Accessibility")
                    .font(.title2)
                    .fontWeight(.semibold)

                Text("Accessibility permission granted! Omi can now provide click-through sidebar functionality.")
                    .font(.body)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)

            } else if isAccessibilityPermissionDenied {
                // Denied state - show reset options
                Image(systemName: "hand.raised.slash.fill")
                    .font(.system(size: 48))
                    .foregroundColor(.red)

                Text("Accessibility Permission Denied")
                    .font(.title2)
                    .fontWeight(.semibold)

                Text("Permission was previously denied. Reset it to try again:")
                    .font(.body)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)

                VStack(spacing: 8) {
                    // Option 1: Quick Reset
                    Button(action: accessibilityTryDirectReset) {
                        HStack(spacing: 8) {
                            if accessibilityResetInProgress {
                                ProgressView()
                                    .scaleEffect(0.7)
                                    .frame(width: 14, height: 14)
                            } else {
                                Image(systemName: "arrow.clockwise")
                                    .font(.system(size: 14))
                            }
                            Text(accessibilityResetButtonText)
                                .font(.system(size: 13, weight: .medium))
                        }
                        .foregroundColor(.primary)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                        .frame(width: 260)
                        .background(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(Color.secondary.opacity(0.5), lineWidth: 1)
                        )
                    }
                    .buttonStyle(.plain)
                    .disabled(accessibilityResetInProgress)

                    // Option 2: Manual
                    Button(action: accessibilityOpenSystemSettings) {
                        HStack(spacing: 8) {
                            Image(systemName: "gear")
                                .font(.system(size: 14))
                            Text("Open System Settings")
                                .font(.system(size: 13, weight: .medium))
                        }
                        .foregroundColor(.primary)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                        .frame(width: 260)
                        .background(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(Color.secondary.opacity(0.5), lineWidth: 1)
                        )
                    }
                    .buttonStyle(.plain)
                }

            } else {
                // Not determined state - normal flow
                Image(systemName: "hand.raised")
                    .font(.system(size: 48))
                    .foregroundColor(OmiColors.purplePrimary)

                Text("Accessibility")
                    .font(.title2)
                    .fontWeight(.semibold)

                Text("Omi needs Accessibility permission to provide seamless click-through behavior on the sidebar.\n\nThis allows you to interact with the sidebar without needing to click twice when switching apps.")
                    .font(.body)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func accessibilityTryDirectReset() {
        accessibilityResetInProgress = true
        accessibilityResetButtonText = "Resetting & Restarting..."

        DispatchQueue.global(qos: .userInitiated).async {
            let success = appState.resetAccessibilityPermissionDirect(shouldRestart: true)

            if !success {
                DispatchQueue.main.async {
                    accessibilityResetButtonText = "Failed - Try Settings"
                    DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
                        accessibilityResetInProgress = false
                        accessibilityResetButtonText = "Reset & Restart"
                    }
                }
            }
            // If success, app will restart automatically
        }
    }

    private func accessibilityOpenSystemSettings() {
        appState.openAccessibilityPreferences()
    }

    // MARK: - Bluetooth Step View

    private var isBluetoothPermissionDenied: Bool {
        appState.isBluetoothPermissionDenied()
    }

    private var isBluetoothUnsupported: Bool {
        appState.isBluetoothUnsupported()
    }

    private var bluetoothStepView: some View {
        VStack(spacing: 16) {
            if appState.hasBluetoothPermission {
                // Granted state
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 48))
                    .foregroundColor(.white)

                Text("Bluetooth")
                    .font(.title2)
                    .fontWeight(.semibold)

                Text("Bluetooth access granted! Omi can now connect to your wearable device.")
                    .font(.body)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)

            } else if isBluetoothPermissionDenied {
                // Denied state - show manual settings option
                Image(systemName: "antenna.radiowaves.left.and.right.slash")
                    .font(.system(size: 48))
                    .foregroundColor(.red)

                Text("Bluetooth Permission Denied")
                    .font(.title2)
                    .fontWeight(.semibold)

                Text("Permission was previously denied. Please enable Bluetooth access in System Settings:")
                    .font(.body)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)

                Button(action: bluetoothOpenSystemSettings) {
                    HStack(spacing: 8) {
                        Image(systemName: "gear")
                            .font(.system(size: 14))
                        Text("Open System Settings")
                            .font(.system(size: 13, weight: .medium))
                    }
                    .foregroundColor(.primary)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                    .frame(width: 260)
                    .background(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(Color.secondary.opacity(0.5), lineWidth: 1)
                    )
                }
                .buttonStyle(.plain)

            } else if isBluetoothUnsupported {
                // Unsupported state - allow skip with explanation
                Image(systemName: "exclamationmark.triangle")
                    .font(.system(size: 48))
                    .foregroundColor(.orange)

                Text("Bluetooth Unavailable")
                    .font(.title2)
                    .fontWeight(.semibold)

                Text("Bluetooth appears unavailable on this Mac. This can happen on newer macOS versions. You can skip this step and Omi will work without wearable device support.")
                    .font(.body)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
                    .fixedSize(horizontal: false, vertical: true)

                Text("You can try enabling Bluetooth in System Settings if you have an Omi wearable.")
                    .font(.caption)
                    .foregroundColor(.secondary.opacity(0.8))
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)

                Button(action: bluetoothOpenSystemSettings) {
                    HStack(spacing: 8) {
                        Image(systemName: "gear")
                            .font(.system(size: 14))
                        Text("Open System Settings")
                            .font(.system(size: 13, weight: .medium))
                    }
                    .foregroundColor(.primary)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                    .frame(width: 260)
                    .background(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(Color.secondary.opacity(0.5), lineWidth: 1)
                    )
                }
                .buttonStyle(.plain)

            } else {
                // Not determined state - normal flow
                Image(systemName: "antenna.radiowaves.left.and.right")
                    .font(.system(size: 48))
                    .foregroundColor(OmiColors.purplePrimary)

                Text("Bluetooth")
                    .font(.title2)
                    .fontWeight(.semibold)

                Text("Omi needs Bluetooth access to connect to your Omi wearable device for audio capture and transcription.")
                    .font(.body)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func bluetoothOpenSystemSettings() {
        appState.openBluetoothPreferences()
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
            if appState.hasNotificationPermission {
                // Permission already granted - advance
                AnalyticsManager.shared.onboardingStepCompleted(step: 3, stepName: "Notifications")
                AnalyticsManager.shared.permissionGranted(permission: "notifications")
                currentStep += 1
            } else {
                AnalyticsManager.shared.permissionRequested(permission: "notifications")
                hasTriggeredNotification = true
                appState.requestNotificationPermission()
            }
        case 4:
            if appState.hasAutomationPermission {
                AnalyticsManager.shared.onboardingStepCompleted(step: 4, stepName: "Automation")
                AnalyticsManager.shared.permissionGranted(permission: "automation")
                currentStep += 1
            } else {
                AnalyticsManager.shared.permissionRequested(permission: "automation")
                hasTriggeredAutomation = true
                appState.triggerAutomationPermission()
            }
        case 5:
            if appState.hasScreenRecordingPermission {
                AnalyticsManager.shared.onboardingStepCompleted(step: 5, stepName: "Screen Recording")
                AnalyticsManager.shared.permissionGranted(permission: "screen_recording")
                // Trigger proactive monitoring to surface any additional ScreenCaptureKit permission dialogs
                // (e.g., "allow app to bypass standard screen recording" on macOS Sequoia)
                ProactiveAssistantsPlugin.shared.startMonitoring { _, _ in }
                currentStep += 1
            } else {
                AnalyticsManager.shared.permissionRequested(permission: "screen_recording")
                hasTriggeredScreenRecording = true
                appState.triggerScreenRecordingPermission()
            }
        case 6:
            if appState.hasMicrophonePermission {
                AnalyticsManager.shared.onboardingStepCompleted(step: 6, stepName: "Microphone")
                AnalyticsManager.shared.permissionGranted(permission: "microphone")
                currentStep += 1
            } else {
                // Request permission - UI will update based on denied/not determined state
                AnalyticsManager.shared.permissionRequested(permission: "microphone")
                hasTriggeredMicrophone = true
                appState.requestMicrophonePermission()
            }
        case 7:
            // System Audio step
            if !appState.isSystemAudioSupported {
                // Not supported on this macOS version - just continue
                AnalyticsManager.shared.onboardingStepCompleted(step: 7, stepName: "System Audio")
                currentStep += 1
            } else if appState.hasSystemAudioPermission {
                AnalyticsManager.shared.onboardingStepCompleted(step: 7, stepName: "System Audio")
                AnalyticsManager.shared.permissionGranted(permission: "system_audio")
                currentStep += 1
            } else {
                AnalyticsManager.shared.permissionRequested(permission: "system_audio")
                hasTriggeredSystemAudio = true
                appState.triggerSystemAudioPermission()
            }
        case 8:
            // Accessibility step
            if appState.hasAccessibilityPermission {
                AnalyticsManager.shared.onboardingStepCompleted(step: 8, stepName: "Accessibility")
                AnalyticsManager.shared.permissionGranted(permission: "accessibility")
                currentStep += 1
            } else {
                AnalyticsManager.shared.permissionRequested(permission: "accessibility")
                hasTriggeredAccessibility = true
                appState.triggerAccessibilityPermission()
            }
        case 9:
            // Bluetooth step
            // Initialize Bluetooth if not already done
            appState.initializeBluetoothIfNeeded()

            if appState.hasBluetoothPermission {
                AnalyticsManager.shared.onboardingStepCompleted(step: 9, stepName: "Bluetooth")
                AnalyticsManager.shared.permissionGranted(permission: "bluetooth", extraProperties: [
                    "bluetooth_state": BluetoothManager.shared.bluetoothStateDescription,
                    "bluetooth_state_raw": BluetoothManager.shared.bluetoothState.rawValue
                ])
                currentStep += 1
            } else if isBluetoothUnsupported || isBluetoothPermissionDenied {
                // Allow skipping when Bluetooth is unsupported or denied
                AnalyticsManager.shared.onboardingStepCompleted(step: 9, stepName: "Bluetooth")
                AnalyticsManager.shared.permissionSkipped(permission: "bluetooth", extraProperties: [
                    "bluetooth_state": BluetoothManager.shared.bluetoothStateDescription,
                    "bluetooth_state_raw": BluetoothManager.shared.bluetoothState.rawValue,
                    "reason": isBluetoothUnsupported ? "unsupported" : "denied"
                ])
                currentStep += 1
            } else {
                AnalyticsManager.shared.permissionRequested(permission: "bluetooth", extraProperties: [
                    "bluetooth_state": BluetoothManager.shared.bluetoothStateDescription,
                    "bluetooth_state_raw": BluetoothManager.shared.bluetoothState.rawValue
                ])
                hasTriggeredBluetooth = true
                appState.triggerBluetoothPermission()
            }
        case 10:
            log("OnboardingView: Step 10 - Completing onboarding")
            AnalyticsManager.shared.onboardingStepCompleted(step: 10, stepName: "Done")
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

