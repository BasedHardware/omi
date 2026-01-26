import SwiftUI

/// Tab selection for settings
enum SettingsTab: String, CaseIterable {
    case focus = "Focus"
    case tasks = "Tasks"
}

/// SwiftUI view for Proactive Assistants settings
struct SettingsView: View {
    @State private var selectedTab: SettingsTab = .focus

    // Master monitoring state
    @State private var isMonitoring: Bool
    @State private var isToggling: Bool = false
    @State private var permissionError: String?

    // Focus Assistant states
    @State private var focusEnabled: Bool
    @State private var cooldownInterval: Int
    @State private var glowOverlayEnabled: Bool
    @State private var analysisDelay: Int

    // Task Assistant states
    @State private var taskEnabled: Bool
    @State private var extractionInterval: Double
    @State private var minConfidence: Double

    // Glow preview state
    @State private var isPreviewRunning: Bool = false

    private let cooldownOptions = [1, 2, 5, 10, 15, 30, 60]
    private let analysisDelayOptions = [0, 60, 300] // seconds: instant, 1 min, 5 min
    private let extractionIntervalOptions: [Double] = [10.0, 600.0, 3600.0] // 10s, 10min, 1hr

    var onClose: (() -> Void)?

    init(onClose: (() -> Void)? = nil) {
        self.onClose = onClose
        let settings = AssistantSettings.shared

        // Master monitoring state - initialize from actual plugin state
        _isMonitoring = State(initialValue: ProactiveAssistantsPlugin.shared?.isMonitoring ?? false)

        // Focus settings
        _focusEnabled = State(initialValue: FocusAssistantSettings.shared.isEnabled)
        _cooldownInterval = State(initialValue: settings.cooldownInterval)
        _glowOverlayEnabled = State(initialValue: settings.glowOverlayEnabled)
        _analysisDelay = State(initialValue: settings.analysisDelay)

        // Task settings
        _taskEnabled = State(initialValue: TaskAssistantSettings.shared.isEnabled)
        _extractionInterval = State(initialValue: TaskAssistantSettings.shared.extractionInterval)
        _minConfidence = State(initialValue: TaskAssistantSettings.shared.minConfidence)
    }

    var body: some View {
        VStack(spacing: 0) {
            // Master Monitoring Toggle
            masterMonitoringSection
                .padding(.horizontal, 20)
                .padding(.top, 16)
                .padding(.bottom, 12)

            Divider()
                .background(Color.primary.opacity(0.1))

            // Tab bar
            HStack(spacing: 0) {
                ForEach(SettingsTab.allCases, id: \.self) { tab in
                    tabButton(for: tab)
                }
            }
            .padding(.horizontal, 20)
            .padding(.top, 12)
            .padding(.bottom, 8)

            Divider()
                .background(Color.primary.opacity(0.1))

            // Tab content
            VStack(spacing: 20) {
                switch selectedTab {
                case .focus:
                    focusTabContent
                case .tasks:
                    tasksTabContent
                }
            }
            .padding(20)
        }
        .frame(width: 420)
        .fixedSize(horizontal: false, vertical: true)
        .background(Color(nsColor: .windowBackgroundColor))
        .onReceive(NotificationCenter.default.publisher(for: .assistantSettingsDidChange)) { _ in
            // Update state when settings change externally
            focusEnabled = FocusAssistantSettings.shared.isEnabled
            taskEnabled = TaskAssistantSettings.shared.isEnabled
        }
        .onReceive(NotificationCenter.default.publisher(for: .assistantMonitoringStateDidChange)) { _ in
            // Update monitoring state when it changes externally
            isMonitoring = ProactiveAssistantsPlugin.shared?.isMonitoring ?? false
        }
        .onChange(of: isShowingPreview) { _ in
            resizeWindowToFit()
        }
        .onChange(of: selectedTab) { _ in
            resizeWindowToFit()
        }
        .animation(.easeInOut(duration: 0.3), value: isShowingPreview)
        .animation(.easeInOut(duration: 0.2), value: selectedTab)
    }

    // MARK: - Master Monitoring Section

    private var masterMonitoringSection: some View {
        HStack(alignment: .center, spacing: 12) {
            // Status indicator
            Circle()
                .fill(isMonitoring ? Color(red: 0.16, green: 0.79, blue: 0.26) : Color.secondary.opacity(0.3))
                .frame(width: 10, height: 10)
                .shadow(color: isMonitoring ? Color(red: 0.16, green: 0.79, blue: 0.26).opacity(0.5) : .clear, radius: 4)

            VStack(alignment: .leading, spacing: 2) {
                Text("Proactive Monitoring")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundColor(.primary)

                Text(permissionError ?? (isMonitoring ? "Analyzing your screen" : "Monitoring is paused"))
                    .font(.system(size: 12))
                    .foregroundColor(permissionError != nil ? .orange : .secondary)
            }

            Spacer()

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
    }

    // MARK: - Monitoring Control

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

    // MARK: - Tab Button

    private func tabButton(for tab: SettingsTab) -> some View {
        VStack(spacing: 6) {
            HStack(spacing: 6) {
                Image(systemName: tab == .focus ? "eye.fill" : "checklist")
                    .font(.system(size: 14))
                Text(tab.rawValue)
                    .font(.system(size: 14, weight: .medium))
            }
            .foregroundColor(selectedTab == tab ? .accentColor : .secondary)
            .padding(.horizontal, 16)
            .padding(.vertical, 8)

            // Underline indicator
            Rectangle()
                .fill(selectedTab == tab ? Color.accentColor : Color.clear)
                .frame(height: 2)
        }
        .contentShape(Rectangle())
        .onTapGesture {
            withAnimation(.easeInOut(duration: 0.2)) {
                selectedTab = tab
            }
        }
    }


    // MARK: - Focus Tab Content

    private var focusTabContent: some View {
        VStack(spacing: 20) {
            // Focus Assistant Toggle
            settingRow(
                title: "Focus Assistant",
                subtitle: "Detect distractions and help you stay focused",
                icon: "eye.fill"
            ) {
                Toggle("", isOn: $focusEnabled)
                    .toggleStyle(.switch)
                    .labelsHidden()
                    .onChange(of: focusEnabled) { newValue in
                        FocusAssistantSettings.shared.isEnabled = newValue
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
                subtitle: "Show colored border when focus changes",
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
                subtitle: "Customize AI instructions for focus analysis",
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
    }

    // MARK: - Tasks Tab Content

    private var tasksTabContent: some View {
        VStack(spacing: 20) {
            // Task Assistant Toggle
            settingRow(
                title: "Task Assistant",
                subtitle: "Extract tasks and action items from your screen",
                icon: "checklist"
            ) {
                Toggle("", isOn: $taskEnabled)
                    .toggleStyle(.switch)
                    .labelsHidden()
                    .onChange(of: taskEnabled) { newValue in
                        TaskAssistantSettings.shared.isEnabled = newValue
                    }
            }

            Divider()
                .background(Color.primary.opacity(0.1))

            // Extraction Interval
            settingRow(
                title: "Extraction Interval",
                subtitle: "How often to scan for new tasks",
                icon: "clock"
            ) {
                Picker("", selection: $extractionInterval) {
                    ForEach(extractionIntervalOptions, id: \.self) { seconds in
                        Text(formatExtractionInterval(seconds)).tag(seconds)
                    }
                }
                .pickerStyle(.menu)
                .frame(width: 120)
                .onChange(of: extractionInterval) { newValue in
                    TaskAssistantSettings.shared.extractionInterval = newValue
                }
            }

            Divider()
                .background(Color.primary.opacity(0.1))

            // Minimum Confidence
            VStack(alignment: .leading, spacing: 12) {
                HStack(alignment: .center, spacing: 12) {
                    Image(systemName: "gauge.with.dots.needle.67percent")
                        .font(.system(size: 16))
                        .foregroundColor(.accentColor)
                        .frame(width: 24, height: 24)

                    VStack(alignment: .leading, spacing: 2) {
                        Text("Minimum Confidence")
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(.primary)

                        Text("Only show tasks above this confidence level")
                            .font(.system(size: 12))
                            .foregroundColor(.secondary)
                    }

                    Spacer()

                    Text("\(Int(minConfidence * 100))%")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundColor(.secondary)
                        .frame(width: 40, alignment: .trailing)
                }

                Slider(value: $minConfidence, in: 0.3...0.9, step: 0.1)
                    .onChange(of: minConfidence) { newValue in
                        TaskAssistantSettings.shared.minConfidence = newValue
                    }
            }

            Divider()
                .background(Color.primary.opacity(0.1))

            // Task Analysis Prompt - opens in separate window
            settingRow(
                title: "Task Extraction Prompt",
                subtitle: "Customize AI instructions for task extraction",
                icon: "text.alignleft"
            ) {
                Button(action: {
                    TaskPromptEditorWindow.show()
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
        isShowingPreview = true

        // Show the demo window and get its frame
        let demoWindow = GlowDemoWindow.show()
        let windowFrame = demoWindow.frame

        // Phase 1: Show focused (green) glow after a small delay
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
            withAnimation {
                previewPhase = .focused
            }
            // Show glow around the demo window
            OverlayService.shared.showGlow(around: windowFrame, colorMode: .focused, isPreview: true)
        }

        // Phase 2: Show distracted (red) glow
        DispatchQueue.main.asyncAfter(deadline: .now() + 3.3) {
            withAnimation {
                previewPhase = .distracted
            }
            // Show glow around the demo window
            OverlayService.shared.showGlow(around: windowFrame, colorMode: .distracted, isPreview: true)
        }

        // End preview and close demo window
        DispatchQueue.main.asyncAfter(deadline: .now() + 7.0) {
            withAnimation {
                previewPhase = .none
                isShowingPreview = false
            }
            GlowDemoWindow.close()
        }
    }

    // MARK: - Helper Views

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

    // MARK: - Formatters

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

    private func formatExtractionInterval(_ seconds: Double) -> String {
        if seconds < 60 {
            return "\(Int(seconds)) seconds"
        } else if seconds < 3600 {
            let minutes = Int(seconds / 60)
            return minutes == 1 ? "1 minute" : "\(minutes) minutes"
        } else {
            let hours = Int(seconds / 3600)
            return hours == 1 ? "1 hour" : "\(hours) hours"
        }
    }

    private func resizeWindowToFit() {
        guard let window = NSApp.windows.first(where: { $0.title == "Proactive Assistant Settings" }),
              let hostingView = window.contentView as? NSHostingView<SettingsView> else {
            return
        }

        // Get the ideal size from the hosting view
        let fittingSize = hostingView.fittingSize
        let newHeight = fittingSize.height

        var frame = window.frame
        let heightDiff = newHeight - frame.height

        // Adjust origin to keep top of window in place (macOS coordinates have origin at bottom-left)
        frame.origin.y -= heightDiff
        frame.size.height = newHeight

        NSAnimationContext.runAnimationGroup { context in
            context.duration = 0.25
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
