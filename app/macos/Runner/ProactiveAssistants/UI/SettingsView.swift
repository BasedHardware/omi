import SwiftUI

/// Preview phase for glow demonstration
enum GlowPreviewPhase {
    case none
    case focused
    case distracted
}

/// SwiftUI view for Proactive Assistants settings
struct SettingsView: View {
    @State private var isMonitoring: Bool
    @State private var isToggling: Bool = false
    @State private var permissionError: String?
    @State private var cooldownInterval: Int
    @State private var glowOverlayEnabled: Bool
    @State private var analysisDelay: Int

    // Glow preview states
    @State private var previewPhase: GlowPreviewPhase = .none
    @State private var isShowingPreview: Bool = false

    private let cooldownOptions = [1, 2, 5, 10, 15, 30, 60]
    private let analysisDelayOptions = [0, 60, 300] // seconds: instant, 1 min, 5 min

    var onClose: (() -> Void)?

    init(onClose: (() -> Void)? = nil) {
        self.onClose = onClose
        let settings = AssistantSettings.shared
        // Initialize from actual monitoring state, not just the preference
        _isMonitoring = State(initialValue: ProactiveAssistantsPlugin.shared?.isMonitoring ?? false)
        _cooldownInterval = State(initialValue: settings.cooldownInterval)
        _glowOverlayEnabled = State(initialValue: settings.glowOverlayEnabled)
        _analysisDelay = State(initialValue: settings.analysisDelay)
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                // Focus Monitoring Toggle
                settingRow(
                    title: "Proactive Assistants",
                    subtitle: permissionError ?? "Enable AI-powered focus tracking and task extraction",
                    subtitleColor: permissionError != nil ? .orange : .secondary,
                    icon: "eye.fill"
                ) {
                    if isToggling {
                        ProgressView()
                            .scaleEffect(0.7)
                            .frame(width: 51, height: 31)
                    } else {
                        Toggle("", isOn: $isMonitoring)
                            .toggleStyle(.switch)
                            .labelsHidden()
                            .onChange(of: isMonitoring) { newValue in
                                toggleMonitoring(enabled: newValue)
                            }
                    }
                }

                Divider()
                    .background(Color.primary.opacity(0.1))

                // Analysis Delay
                settingRow(
                    title: "Analysis Delay",
                    subtitle: "Wait before analyzing after switching apps",
                    icon: "clock.arrow.circlepath"
                ) {
                    Picker("", selection: $analysisDelay) {
                        ForEach(analysisDelayOptions, id: \.self) { seconds in
                            Text(formatAnalysisDelay(seconds)).tag(seconds)
                        }
                    }
                    .pickerStyle(.menu)
                    .frame(width: 120)
                    .onChange(of: analysisDelay) { newValue in
                        AssistantSettings.shared.analysisDelay = newValue
                    }
                }

                Divider()
                    .background(Color.primary.opacity(0.1))

                // Cooldown Interval
                settingRow(
                    title: "Notification Cooldown",
                    subtitle: "Minimum time between distraction alerts",
                    icon: "timer"
                ) {
                    Picker("", selection: $cooldownInterval) {
                        ForEach(cooldownOptions, id: \.self) { minutes in
                            Text(formatMinutes(minutes)).tag(minutes)
                        }
                    }
                    .pickerStyle(.menu)
                    .frame(width: 120)
                    .onChange(of: cooldownInterval) { newValue in
                        AssistantSettings.shared.cooldownInterval = newValue
                    }
                }

                Divider()
                    .background(Color.primary.opacity(0.1))

                // Glow Overlay Toggle
                settingRow(
                    title: "Visual Glow Effect",
                    subtitle: "Show colored border around windows when focus changes",
                    icon: "sparkles"
                ) {
                    Toggle("", isOn: $glowOverlayEnabled)
                        .toggleStyle(.switch)
                        .labelsHidden()
                        .disabled(isShowingPreview)
                        .onChange(of: glowOverlayEnabled) { newValue in
                            AssistantSettings.shared.glowOverlayEnabled = newValue
                            if newValue {
                                startGlowPreview()
                            }
                        }
                }

                // Glow Preview Section (only shown when preview is active)
                if isShowingPreview {
                    glowPreviewSection
                        .transition(.opacity.combined(with: .scale(scale: 0.95)))
                }

                Divider()
                    .background(Color.primary.opacity(0.1))

                // Analysis Prompt - opens in separate window
                settingRow(
                    title: "Focus Analysis Prompt",
                    subtitle: "Customize the AI instructions for focus analysis",
                    icon: "text.alignleft"
                ) {
                    Button(action: {
                        PromptEditorWindow.show()
                    }) {
                        HStack(spacing: 4) {
                            Text("Edit")
                                .font(.system(size: 12))
                            Image(systemName: "arrow.up.right.square")
                                .font(.system(size: 11))
                        }
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                }
            }
            .padding(20)
        }
        .frame(width: 400, height: isShowingPreview ? 620 : 480)
        .background(Color(nsColor: .windowBackgroundColor))
        .onReceive(NotificationCenter.default.publisher(for: .assistantMonitoringStateDidChange)) { _ in
            // Update state when monitoring changes externally
            isMonitoring = ProactiveAssistantsPlugin.shared?.isMonitoring ?? false
        }
        .onChange(of: isShowingPreview) { showingPreview in
            // Resize window when preview section appears/disappears
            resizeSettingsWindow(expanded: showingPreview)
        }
        .animation(.easeInOut(duration: 0.3), value: isShowingPreview)
    }

    // MARK: - Glow Preview Section

    private var glowPreviewSection: some View {
        VStack(spacing: 16) {
            // Preview header
            HStack {
                Image(systemName: "wand.and.stars")
                    .font(.system(size: 14))
                    .foregroundColor(.accentColor)
                Text("Preview")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(.secondary)
                Spacer()
            }

            // Preview content
            HStack(spacing: 20) {
                // Focused state
                glowStatePreview(
                    title: "Focused",
                    description: "You're on track",
                    color: Color(red: 0.16, green: 0.79, blue: 0.26), // #28CA42
                    isActive: previewPhase == .focused
                )

                // Arrow between states
                Image(systemName: "arrow.right")
                    .font(.system(size: 16, weight: .medium))
                    .foregroundColor(.secondary.opacity(0.5))

                // Distracted state
                glowStatePreview(
                    title: "Distracted",
                    description: "Time to refocus",
                    color: Color(red: 0.95, green: 0.3, blue: 0.3), // Red
                    isActive: previewPhase == .distracted
                )
            }
            .padding(.vertical, 8)

            // Progress indicator
            HStack(spacing: 8) {
                if previewPhase != .none {
                    ProgressView()
                        .scaleEffect(0.6)
                    Text(previewPhase == .focused ? "Showing focused glow..." : "Showing distracted glow...")
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                } else {
                    Text("Toggle on to see preview")
                        .font(.system(size: 12))
                        .foregroundColor(.secondary.opacity(0.6))
                }
            }
            .frame(height: 20)
        }
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color.primary.opacity(0.05))
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .strokeBorder(Color.primary.opacity(0.1), lineWidth: 1)
                )
        )
    }

    private func glowStatePreview(title: String, description: String, color: Color, isActive: Bool) -> some View {
        VStack(spacing: 8) {
            // Glow indicator circle
            ZStack {
                // Outer glow
                Circle()
                    .fill(color.opacity(isActive ? 0.3 : 0.1))
                    .frame(width: 50, height: 50)
                    .blur(radius: isActive ? 8 : 0)

                // Inner circle
                Circle()
                    .fill(color.opacity(isActive ? 1.0 : 0.3))
                    .frame(width: 30, height: 30)

                // Pulse animation
                if isActive {
                    Circle()
                        .stroke(color.opacity(0.5), lineWidth: 2)
                        .frame(width: 40, height: 40)
                        .scaleEffect(isActive ? 1.3 : 1.0)
                        .opacity(isActive ? 0 : 1)
                        .animation(
                            Animation.easeOut(duration: 1.0).repeatForever(autoreverses: false),
                            value: isActive
                        )
                }
            }
            .frame(width: 60, height: 60)

            // Labels
            Text(title)
                .font(.system(size: 13, weight: isActive ? .semibold : .regular))
                .foregroundColor(isActive ? .primary : .secondary)

            Text(description)
                .font(.system(size: 11))
                .foregroundColor(.secondary.opacity(0.8))
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 8)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(isActive ? color.opacity(0.1) : Color.clear)
        )
        .animation(.easeInOut(duration: 0.3), value: isActive)
    }

    // MARK: - Glow Preview Logic

    private func startGlowPreview() {
        // Get the settings window frame ONCE before starting
        // This ensures both glows appear around the same position
        guard let settingsWindow = NSApp.windows.first(where: { $0.title == "Proactive Assistant Settings" }) else {
            log("Could not find settings window for glow preview")
            return
        }

        let windowFrame = settingsWindow.frame
        isShowingPreview = true

        // Phase 1: Show focused (green) glow after a small delay
        // Green glow auto-dismisses after 3.5s, so we show it at T+0.3s
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
            withAnimation {
                previewPhase = .focused
            }
            // Use the captured frame and mark as preview to bypass settings check
            OverlayService.shared.showGlow(around: windowFrame, colorMode: .focused, isPreview: true)
        }

        // Phase 2: Show distracted (red) glow
        // Show at T+3.0s - BEFORE green's 3.5s auto-dismiss to avoid race condition
        // (green started at 0.3s, so 0.3 + 3.0 = 3.3s, before 0.3 + 3.5 = 3.8s auto-dismiss)
        DispatchQueue.main.asyncAfter(deadline: .now() + 3.3) {
            withAnimation {
                previewPhase = .distracted
            }
            // Use the same captured frame
            OverlayService.shared.showGlow(around: windowFrame, colorMode: .distracted, isPreview: true)
        }

        // End preview at T+6.8s (3.3s + 3.5s auto-dismiss time)
        DispatchQueue.main.asyncAfter(deadline: .now() + 7.0) {
            withAnimation {
                previewPhase = .none
                isShowingPreview = false
            }
        }
    }

    private func toggleMonitoring(enabled: Bool) {
        guard let plugin = ProactiveAssistantsPlugin.shared else {
            permissionError = "Plugin not available"
            isMonitoring = false
            return
        }

        // Check permission first
        if enabled && !plugin.hasScreenRecordingPermission {
            permissionError = "Screen recording permission required"
            isMonitoring = false
            // Open system preferences
            ScreenCaptureService.openScreenRecordingPreferences()
            return
        }

        permissionError = nil
        isToggling = true

        if enabled {
            plugin.startMonitoringFromNative { success, error in
                DispatchQueue.main.async {
                    isToggling = false
                    if !success {
                        permissionError = error ?? "Failed to start monitoring"
                        isMonitoring = false
                    }
                }
            }
        } else {
            plugin.stopMonitoringFromNative()
            isToggling = false
        }
    }

    private func settingRow<Content: View>(
        title: String,
        subtitle: String,
        subtitleColor: Color = .secondary,
        icon: String,
        @ViewBuilder control: () -> Content
    ) -> some View {
        HStack(alignment: .center, spacing: 12) {
            Image(systemName: icon)
                .font(.system(size: 16))
                .foregroundColor(.accentColor)
                .frame(width: 24, height: 24)

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(.primary)

                Text(subtitle)
                    .font(.system(size: 12))
                    .foregroundColor(subtitleColor)
                    .lineLimit(2)
            }

            Spacer()

            control()
        }
    }

    private func formatMinutes(_ minutes: Int) -> String {
        if minutes == 1 {
            return "1 minute"
        } else if minutes < 60 {
            return "\(minutes) minutes"
        } else {
            return "1 hour"
        }
    }

    private func formatAnalysisDelay(_ seconds: Int) -> String {
        if seconds == 0 {
            return "Instant"
        } else if seconds < 60 {
            return "\(seconds) seconds"
        } else if seconds == 60 {
            return "1 minute"
        } else {
            return "\(seconds / 60) minutes"
        }
    }

    private func resizeSettingsWindow(expanded: Bool) {
        guard let window = NSApp.windows.first(where: { $0.title == "Proactive Assistant Settings" }) else {
            return
        }

        let newHeight: CGFloat = expanded ? 620 : 480
        var frame = window.frame
        let heightDiff = newHeight - frame.height

        // Adjust origin to keep top of window in place (macOS coordinates have origin at bottom-left)
        frame.origin.y -= heightDiff
        frame.size.height = newHeight

        NSAnimationContext.runAnimationGroup { context in
            context.duration = 0.3
            context.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
            window.animator().setFrame(frame, display: true)
        }
    }
}

// MARK: - Backward Compatibility Alias

typealias FocusSettingsView = SettingsView

#Preview {
    SettingsView()
}
