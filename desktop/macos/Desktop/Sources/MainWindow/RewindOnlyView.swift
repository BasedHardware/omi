import OmiSupport
import OmiTheme
import SwiftUI

/// Rewind-only view for when the app is launched with --mode=rewind
/// Shows just the Rewind page without the sidebar, with a settings button overlay
struct RewindOnlyView: View {
  @StateObject private var appState = AppState()
  @ObservedObject private var authState = AuthState.shared

  var body: some View {
    Group {
      if authState.isRestoringAuth {
        VStack(spacing: OmiSpacing.lg) {
          if let iconURL = Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png"),
            let nsImage = NSImage(contentsOf: iconURL)
          {
            Image(nsImage: nsImage)
              .resizable()
              .scaledToFit()
              .frame(width: 64, height: 64)
          }
          ProgressView()
            .scaleEffect(0.8)
            .tint(.white.opacity(0.6))
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      } else if authState.sessionPhase == .recoveryRequired {
        SessionRecoveryView()
          .onAppear {
            log("RewindOnlyView: Showing recoverable auth state")
          }
      } else if !authState.isSignedIn {
        // Not signed in - show sign in view
        SignInView(authState: authState)
          .onAppear {
            log("RewindOnlyView: Showing SignInView (not signed in)")
          }
      } else {
        // Signed in - show Rewind page with settings overlay
        rewindContent
          .onAppear {
            log("RewindOnlyView: Showing Rewind content (signed in)")
            // Start screen monitoring automatically in rewind mode
            startMonitoringIfNeeded()
          }
      }
    }
    .background(OmiColors.backgroundPrimary)
    .frame(minWidth: 800, minHeight: 500)
    .preferredColorScheme(.dark)
    .tint(OmiColors.accent)
    .onAppear {
      log("RewindOnlyView: View appeared - isSignedIn=\(authState.isSignedIn)")
      // Force dark appearance on the window
      DispatchQueue.main.async {
        for window in NSApp.windows {
          if window.title.contains("Rewind") || window.title.lowercased().hasPrefix("omi") {
            window.appearance = NSAppearance(named: .darkAqua)
          }
        }
      }
    }
  }

  // MARK: - Rewind Content

  private var rewindContent: some View {
    ZStack(alignment: .topTrailing) {
      // Main Rewind page (full width, no sidebar)
      RewindPage()

      // Settings button overlay in top-right corner
      settingsButton
        .padding(OmiSpacing.lg)
    }
  }

  // MARK: - Settings Button

  private var settingsButton: some View {
    Menu {
      Button {
        openRewindSettings()
      } label: {
        Label("Rewind Settings", systemImage: "slider.horizontal.3")
      }

      Divider()

      Button {
        openFullApp()
      } label: {
        Label("Open Full omi App", systemImage: "square.grid.2x2")
      }

      Divider()

      Button {
        NSApplication.shared.terminate(nil)
      } label: {
        Label("Quit", systemImage: "xmark.circle")
      }
    } label: {
      Image(systemName: "gearshape.fill")
        .scaledFont(size: OmiType.body)
        .foregroundColor(.white.opacity(0.7))
        .padding(OmiSpacing.sm)
        .background(Color.black.opacity(0.5))
        .clipShape(Circle())
    }
    .menuStyle(.borderlessButton)
    .menuIndicator(.hidden)
    .fixedSize()
    .help("Settings")
  }

  // MARK: - Actions

  private func startMonitoringIfNeeded() {
    let settings = AssistantSettings.shared
    if settings.screenAnalysisEnabled {
      ProactiveAssistantsPlugin.shared.startMonitoring { success, error in
        if success {
          log("RewindOnlyView: Screen analysis started automatically")
        } else {
          log("RewindOnlyView: Screen analysis failed to start: \(error ?? "unknown")")
        }
      }
    }
  }

  private func openRewindSettings() {
    // Open settings window focused on Rewind section
    RewindSettingsWindow.show()
  }

  private func openFullApp() {
    // Launch the full app (without --mode=rewind)
    let appPath = Bundle.main.bundlePath
    let task = Process()
    task.launchPath = "/usr/bin/open"
    task.arguments = ["-n", appPath]  // -n opens a new instance
    try? task.run()
  }
}

// MARK: - Rewind Settings Window

/// Standalone settings window for Rewind-only mode
@MainActor class RewindSettingsWindow {
  static var window: NSWindow?

  static func show() {
    // If window exists, just bring it to front
    if let existingWindow = window, existingWindow.isVisible {
      existingWindow.makeKeyAndOrderFront(nil)
      NSApp.activate()
      return
    }

    // Create settings content - using SettingsContentView with Rewind section
    let settingsView = RewindSettingsView()
      .withFontScaling()
      .frame(minWidth: 500, minHeight: 400)
      .background(OmiColors.backgroundPrimary)
      .preferredColorScheme(.dark)

    let hostingController = NSHostingController(rootView: settingsView)

    let newWindow = NSWindow(contentViewController: hostingController)
    newWindow.title = "Rewind Settings"
    newWindow.setContentSize(NSSize(width: 600, height: 500))
    newWindow.styleMask = [.titled, .closable, .resizable, .miniaturizable]
    newWindow.minSize = NSSize(width: 500, height: 400)
    newWindow.center()
    newWindow.appearance = NSAppearance(named: .darkAqua)
    newWindow.isReleasedWhenClosed = false
    newWindow.makeKeyAndOrderFront(nil)

    NSApp.activate()

    self.window = newWindow
  }
}

// MARK: - Rewind Settings View

/// Settings view specifically for Rewind configuration
struct RewindSettingsView: View {
  @AppStorage("screenAnalysisEnabled") private var screenAnalysisEnabled = true
  @AppStorage("rewindRetentionDays") private var retentionDays = 7
  @AppStorage("rewindCaptureInterval") private var captureInterval = 1.0

  @State private var excludedApps: [String] = []

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: OmiSpacing.xxl) {
        // Header
        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          Text("Rewind Settings")
            .scaledFont(size: 24, weight: .bold)
            .foregroundColor(.white)

          Text("Configure screen capture and storage")
            .scaledFont(size: OmiType.body)
            .foregroundColor(.white.opacity(0.6))
        }

        Divider()
          .background(Color.white.opacity(0.2))

        // Screen Capture Toggle
        settingsRow(
          title: "Screen Capture",
          subtitle: "Capture screenshots for Rewind timeline"
        ) {
          Toggle("", isOn: $screenAnalysisEnabled)
            .toggleStyle(OmiToggleStyle())
        }

        // Retention Period
        settingsRow(
          title: "Keep Screenshots For",
          subtitle: "Older screenshots will be automatically deleted"
        ) {
          SettingsMenuPicker(selection: $retentionDays) {
            Text("1 day").tag(1)
            Text("3 days").tag(3)
            Text("7 days").tag(7)
            Text("14 days").tag(14)
            Text("30 days").tag(30)
          }
        }

        // Storage Info
        storageInfoSection

        Divider()
          .background(Color.white.opacity(0.2))

        // Permissions Section
        permissionsSection

        Spacer()
      }
      .padding(OmiSpacing.xxl)
    }
    .background(OmiColors.backgroundPrimary)
  }

  private func settingsRow<Content: View>(
    title: String,
    subtitle: String,
    @ViewBuilder content: () -> Content
  ) -> some View {
    HStack(alignment: .center, spacing: OmiSpacing.lg) {
      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        Text(title)
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(.white)

        Text(subtitle)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(.white.opacity(0.5))
      }

      Spacer()

      content()
    }
    .padding(.vertical, OmiSpacing.sm)
  }

  private var storageInfoSection: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      Text("Storage")
        .scaledFont(size: OmiType.body, weight: .semibold)
        .foregroundColor(.white.opacity(0.8))

      HStack {
        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          Text("Screenshots stored locally")
            .scaledFont(size: OmiType.body)
            .foregroundColor(.white.opacity(0.7))

          Text("~/Library/Application Support/Omi/users/\(UserDefaults.standard.string(forKey: "auth_userId") ?? "")/")
            .scaledFont(size: OmiType.caption, design: .monospaced)
            .foregroundColor(.white.opacity(0.4))
        }

        Spacer()

        Button("Show in Finder") {
          let url = DesktopLocalProfile.applicationSupportURL()
          NSWorkspace.shared.selectFile(nil, inFileViewerRootedAtPath: url.path)
        }
        .buttonStyle(.plain)
        .foregroundColor(OmiColors.accent)
        .scaledFont(size: OmiType.caption, weight: .medium)
      }
    }
    .padding(OmiSpacing.lg)
    .background(Color.white.opacity(0.05))
    .cornerRadius(OmiChrome.smallControlRadius)
  }

  private var permissionsSection: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      Text("Permissions")
        .scaledFont(size: OmiType.body, weight: .semibold)
        .foregroundColor(.white.opacity(0.8))

      Button {
        ScreenCaptureService.requestScreenRecordingAccessAndOpenSettings()
      } label: {
        HStack {
          Image(systemName: "rectangle.on.rectangle")
            .scaledFont(size: OmiType.subheading)
            .foregroundColor(OmiColors.accent)

          VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
            Text("Screen Recording")
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundColor(.white)

            Text("Required for Rewind to capture your screen")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(.white.opacity(0.5))
          }

          Spacer()

          Text("Open Settings")
            .scaledFont(size: OmiType.caption, weight: .medium)
            .foregroundColor(OmiColors.accent)
        }
        .padding(OmiSpacing.md)
        .background(Color.white.opacity(0.05))
        .cornerRadius(OmiChrome.elementRadius)
      }
      .buttonStyle(.plain)
    }
  }
}

#if canImport(PreviewsMacros)
  #Preview {
    RewindOnlyView()
      .frame(width: 1000, height: 700)
  }
#endif
