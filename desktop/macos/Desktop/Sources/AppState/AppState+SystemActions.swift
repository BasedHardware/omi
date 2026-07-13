import AVFoundation
import Combine
import SwiftUI
import UserNotifications

@MainActor
extension AppState {
  func requestMicrophonePermission() {
    // Activate app to ensure permission dialog appears
    NSApp.activate()

    log(
      "Requesting microphone permission, current status: \(AudioCaptureService.authorizationStatus().rawValue)"
    )

    Task {
      let granted = await AudioCaptureService.requestPermission()
      await MainActor.run {
        self.hasMicrophonePermission = granted
        log("Microphone permission request completed, granted: \(granted)")
        if granted {
          log("Microphone permission granted")
          // Only start transcription if onboarding is complete
          // During onboarding, we just update the permission state
          if self.hasCompletedOnboarding {
            self.startTranscription()
          }
        } else {
          log("Microphone permission denied")
          // UI will show the denied state with reset options inline
        }
      }
    }
  }

  /// Check microphone permission status
  func checkMicrophonePermission() {
    hasMicrophonePermission = AudioCaptureService.checkPermission()
  }

  /// Check if microphone permission was explicitly denied
  func isMicrophonePermissionDenied() -> Bool {
    return AudioCaptureService.isPermissionDenied()
  }

  /// Check if screen recording permission is denied (onboarding complete but permission not granted)
  func isScreenRecordingPermissionDenied() -> Bool {
    return hasCompletedOnboarding && !CGPreflightScreenCaptureAccess()
  }

  /// Restart the app by launching a new instance and terminating the current one
  nonisolated func restartApp() {
    if UpdaterViewModel.isUpdateInProgress {
      log("Sparkle update in progress, skipping independent restart (Sparkle will handle relaunch)")
      return
    }

    log("Restarting app...")

    guard let bundleURL = Bundle.main.bundleURL as URL? else {
      log("Failed to get bundle URL for restart")
      return
    }

    // Never relaunch a DMG/translocated path — `open` on the mounted-DMG bundle
    // re-reveals the installer's "Drag to Applications" Finder window. Prefer an
    // installed copy when one exists (AppInstaller normally guarantees this).
    var relaunchURL = bundleURL
    if AppInstaller.isInstallerLocation(bundleURL.path) {
      let installed = AppInstaller.installedURL(forBundleURL: bundleURL)
      if FileManager.default.fileExists(atPath: installed.path) {
        log("Restart: bundle is on an installer mount, relaunching installed copy instead")
        relaunchURL = installed
      }
    }

    // Use a shell script to wait briefly, then relaunch the app
    let task = Process()
    task.executableURL = URL(fileURLWithPath: "/bin/sh")
    task.arguments = [
      "-c",
      Self.relaunchCommand(
        appPath: relaunchURL.path,
        isNonProduction: AppBuild.isNonProduction,
        automationPort: DesktopAutomationLaunchOptions.port),
    ]

    do {
      try task.run()
      log("Restart scheduled, terminating current instance...")

      // Terminate the current app
      DispatchQueue.main.async {
        NSApplication.shared.terminate(nil)
      }
    } catch {
      log("Failed to schedule restart: \(error)")
    }
  }

  /// Builds the `/bin/sh -c` payload that relaunches the app after a short delay.
  ///
  /// On **non-production** builds the automation port is re-passed as an argv
  /// (`--automation-port=`) so the reopened bundle rebinds the SAME port the harness
  /// launched with. A plain `open <bundle>` carries no argv and no env, so on its own
  /// the reopened app would fall back to a launchd-session-inherited
  /// `OMI_AUTOMATION_PORT` (or the default port), and the automation harness, still
  /// polling the pre-quit port, would find nothing after Quit & Reopen (PERM-06). argv
  /// is the highest-precedence port source, so it wins over any inherited env. The
  /// production relaunch stays a plain `open` and is unchanged.
  nonisolated static func relaunchCommand(
    appPath: String,
    isNonProduction: Bool,
    automationPort: UInt16
  ) -> String {
    var openCommand = "open \"\(appPath)\""
    if isNonProduction {
      openCommand += " --args \(DesktopAutomationLaunchOptions.portPrefix)\(automationPort)"
    }
    return "sleep 0.5 && \(openCommand)"
  }

  /// Reset onboarding state for the current app only, then restart.
  /// This clears onboarding state without touching production data or system permissions.
  nonisolated func resetOnboardingAndRestart() {
    log("Resetting onboarding state for current app...")
    let graphAuthorizationSnapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot()

    // Update live @AppStorage-backed state on the main thread *before* clearing
    // UserDefaults. DesktopHomeView handles .resetOnboardingRequested by setting
    // hasCompletedOnboarding = false; dispatch synchronously so that runs first.
    let postResetNotification = {
      NotificationCenter.default.post(name: .resetOnboardingRequested, object: nil)
    }
    if Thread.isMainThread {
      postResetNotification()
    } else {
      DispatchQueue.main.sync(execute: postResetNotification)
    }

    // Clear onboarding-related UserDefaults keys (thread-safe, after live state)
    let onboardingKeys = [
      "hasCompletedOnboarding",
      "onboardingStep",
      "hasSeenRewindIntro",
      "hasTriggeredNotification",
      "hasTriggeredAutomation",
      "hasTriggeredScreenRecording",
      "hasTriggeredMicrophone",
      "hasTriggeredSystemAudio",
      "hasTriggeredAccessibility",
      "hasTriggeredBluetooth",
      "onboardingJustCompleted",
    ]
    for key in onboardingKeys {
      UserDefaults.standard.removeObject(forKey: key)
    }
    UserDefaults.standard.synchronize()
    log("Cleared onboarding UserDefaults keys")

    // Clear onboarding chat persistence and messages
    OnboardingChatPersistence.clear()
    log("Cleared onboarding chat persistence")

    Task { @MainActor [self] in
      // Clear knowledge graph (local + server) so the onboarding chart starts fresh
      if let graphAuthorizationSnapshot {
        let authorization = LocalMutationAuthorization {
          RuntimeOwnerIdentity.isAuthorizationCurrent(graphAuthorizationSnapshot)
        }
        do {
          try await KnowledgeGraphStorage.shared.clearAll(authorization: authorization)
          log("Cleared local knowledge graph storage")
        } catch LocalMutationAuthorizationError.revoked {
          log("Skipped stale-owner local knowledge graph reset")
        } catch {
          logError("Failed to clear local knowledge graph during onboarding reset", error: error)
        }
      } else {
        log("Skipped local knowledge graph reset without an authenticated owner")
      }
      do {
        try await APIClient.shared.deleteKnowledgeGraph()
        log("Cleared server knowledge graph")
      } catch {
        logError("Failed to clear server knowledge graph during onboarding reset", error: error)
      }

      // Clear the default stream through the kernel journal's durable,
      // generation-fenced delete outbox. No UI surface may write or delete
      // backend chat state directly.
      if let chatProvider = ChatProvider.mainInstance {
        if await chatProvider.clearDefaultJournalForOnboardingReset() {
          log("Queued default chat reset through kernel journal")
        } else {
          log("Failed to queue default chat reset through kernel journal")
        }
      } else {
        log("Default chat reset deferred: main chat provider unavailable")
      }

      try? await Task.sleep(nanoseconds: 150_000_000)
      // Keep onboarding reset scoped to the current app instance.
      // It must not mutate production defaults, shared local data, or TCC permissions.
      self.restartApp()
    }
  }

  /// Clean conflicting app bundles from Trash, DerivedData, and DMG staging directories
  nonisolated func cleanConflictingAppBundles() {
    let fileManager = FileManager.default
    let homeDir = fileManager.homeDirectoryForCurrentUser.path

    // Clean Omi apps from Trash (they still pollute Launch Services!)
    let trashPath = "\(homeDir)/.Trash"
    if let contents = try? fileManager.contentsOfDirectory(atPath: trashPath) {
      for item in contents where item.lowercased().contains("omi") {
        let itemPath = "\(trashPath)/\(item)"
        do {
          try fileManager.removeItem(atPath: itemPath)
          log("Cleaned from Trash: \(item)")
        } catch {
          log("Failed to clean from Trash: \(item) - \(error.localizedDescription)")
        }
      }
    }

    // Clean DMG staging directories
    let tmpDir = "/private/tmp"
    if let contents = try? fileManager.contentsOfDirectory(atPath: tmpDir) {
      for item in contents where item.hasPrefix("omi-dmg-staging") || item.hasPrefix("omi-dmg-test")
      {
        let itemPath = "\(tmpDir)/\(item)"
        do {
          try fileManager.removeItem(atPath: itemPath)
          log("Cleaned DMG staging: \(item)")
        } catch {
          log("Failed to clean DMG staging: \(item) - \(error.localizedDescription)")
        }
      }
    }

    // Clean Xcode DerivedData Omi builds
    let derivedDataPath = "\(homeDir)/Library/Developer/Xcode/DerivedData"
    if let contents = try? fileManager.contentsOfDirectory(atPath: derivedDataPath) {
      for item in contents where item.lowercased().contains("omi") {
        let buildProductsPath = "\(derivedDataPath)/\(item)/Build/Products"
        if let buildDirs = try? fileManager.contentsOfDirectory(atPath: buildProductsPath) {
          for buildDir in buildDirs {
            let appPath = "\(buildProductsPath)/\(buildDir)/Omi.app"
            let appPath2 = "\(buildProductsPath)/\(buildDir)/Omi Computer.app"
            let appPath3 = "\(buildProductsPath)/\(buildDir)/omi.app"
            let appPath4 = "\(buildProductsPath)/\(buildDir)/Omi Dev.app"
            for path in [appPath, appPath2, appPath3, appPath4] {
              if fileManager.fileExists(atPath: path) {
                do {
                  try fileManager.removeItem(atPath: path)
                  log("Cleaned DerivedData: \(path)")
                } catch {
                  log("Failed to clean DerivedData: \(path) - \(error.localizedDescription)")
                }
              }
            }
          }
        }
      }
    }
  }

  /// Eject any mounted Omi DMG volumes
  nonisolated func ejectMountedDMGVolumes() {
    let fileManager = FileManager.default
    let volumesPath = "/Volumes"

    guard let contents = try? fileManager.contentsOfDirectory(atPath: volumesPath) else { return }

    for volume in contents where volume.lowercased().contains("omi") || volume.hasPrefix("dmg.") {
      let volumePath = "\(volumesPath)/\(volume)"

      // Try diskutil eject first
      let process = Process()
      process.executableURL = URL(fileURLWithPath: "/usr/sbin/diskutil")
      process.arguments = ["eject", volumePath]
      process.standardOutput = FileHandle.nullDevice
      process.standardError = FileHandle.nullDevice

      do {
        try process.run()
        process.waitUntilExit()
        if process.terminationStatus == 0 {
          log("Ejected volume: \(volume)")
        } else {
          // Try hdiutil detach as fallback
          let detachProcess = Process()
          detachProcess.executableURL = URL(fileURLWithPath: "/usr/bin/hdiutil")
          detachProcess.arguments = ["detach", volumePath]
          detachProcess.standardOutput = FileHandle.nullDevice
          detachProcess.standardError = FileHandle.nullDevice
          try? detachProcess.run()
          detachProcess.waitUntilExit()
        }
      } catch {
        log("Failed to eject volume: \(volume) - \(error.localizedDescription)")
      }
    }
  }

  /// Reset Launch Services database to clear stale app registrations
  nonisolated func resetLaunchServicesDatabase() {
    let lsregisterPath =
      "/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
    SystemCommand.runLogging(
      "Reset Launch Services database",
      executable: lsregisterPath,
      arguments: ["-kill", "-r", "-domain", "local", "-domain", "user"])
  }

  /// Clean user TCC database entries for Omi apps
  nonisolated func cleanUserTCCDatabase() {
    let homeDir = FileManager.default.homeDirectoryForCurrentUser.path
    let tccDbPath = "\(homeDir)/Library/Application Support/com.apple.TCC/TCC.db"

    SystemCommand.runLogging(
      "Clean user TCC database (production bundle)",
      executable: "/usr/bin/sqlite3",
      arguments: [tccDbPath, "DELETE FROM access WHERE client LIKE '%com.omi.computer-macos%';"])

    // Also clean entries for non-production Omi bundles (for example com.omi.desktop-dev, com.omi.1233).
    SystemCommand.runLogging(
      "Clean user TCC database (non-production bundles)",
      executable: "/usr/bin/sqlite3",
      arguments: [
        tccDbPath,
        "DELETE FROM access WHERE client LIKE 'com.omi.%' AND client != 'com.omi.computer-macos';",
      ])
  }

  /// Reset microphone permission using tccutil (Option 1: Direct)
  /// Returns true if the reset command was executed successfully
  /// If shouldRestart is true, the app will restart after reset
  nonisolated func resetMicrophonePermissionDirect(shouldRestart: Bool = false) -> Bool {
    let bundleId = Bundle.main.bundleIdentifier ?? "com.omi.computer-macos"
    log("Resetting microphone permission for \(bundleId) via tccutil...")

    let success = SystemCommand.runLogging(
      "tccutil reset Microphone (\(bundleId))",
      executable: "/usr/bin/tccutil",
      arguments: ["reset", "Microphone", bundleId])

    if success && shouldRestart {
      restartApp()
    }

    return success
  }

  /// Reset microphone permission via Terminal (Option 2: Visible to user)
  /// If shouldRestart is true, the app will restart after the terminal command
  func resetMicrophonePermissionViaTerminal(shouldRestart: Bool = false) {
    let bundleId = Bundle.main.bundleIdentifier ?? "com.omi.computer-macos"
    let appPath = Bundle.main.bundleURL.path
    log("Opening Terminal to reset microphone permission for \(bundleId)...")

    // Build the shell command - escape single quotes in path for shell
    let escapedPath = appPath.replacingOccurrences(of: "'", with: "'\\''")
    let restartCommand = shouldRestart ? " && open '\(escapedPath)'" : ""
    let shellCommand =
      "tccutil reset Microphone \(bundleId) && echo 'Done! Permission reset.'\(restartCommand)"

    // AppleScript to open Terminal and run the command
    let script = "tell application \"Terminal\"\nactivate\ndo script \"\(shellCommand)\"\nend tell"

    var error: NSDictionary?
    if let appleScript = NSAppleScript(source: script) {
      appleScript.executeAndReturnError(&error)
      if let error = error {
        log("AppleScript error: \(error)")
      } else if shouldRestart {
        // Terminate current app after terminal script is running
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
          NSApplication.shared.terminate(nil)
        }
      }
    }
  }

  func recordSystemAudioCaptureOutcome(_ status: SystemAudioPermissionStatus) {
    systemAudioPermissionStatus = status
    hasSystemAudioPermission = status == .granted
  }

  /// Check system audio permission support and keep the last observed tap result fresh.
  ///
  /// Core Audio process taps (macOS 14.4+) do not provide a preflight API. Unlike
  /// Screen Recording, the truthful product state comes from a real tap outcome.
  /// If no tap is currently running, a previously granted outcome is no longer a
  /// fresh assertion, so refreshes return to unknown until the next tap succeeds.
  func checkSystemAudioPermission() {
    guard #available(macOS 14.4, *) else {
      recordSystemAudioCaptureOutcome(.unsupported)
      return
    }

    if let service = systemAudioCaptureService as? SystemAudioCaptureService, service.capturing {
      recordSystemAudioCaptureOutcome(.granted)
    } else if systemAudioPermissionStatus == .granted {
      recordSystemAudioCaptureOutcome(.unknown)
    }
  }

  /// Trigger system audio permission by actually testing capture
  /// This verifies system audio works by briefly starting and stopping capture
  func triggerSystemAudioPermission() {
    guard #available(macOS 14.4, *) else {
      log("System audio not supported on this macOS version")
      recordSystemAudioCaptureOutcome(.unsupported)
      return
    }

    log("System audio: Testing capture...")

    // Create a test capture service
    let testService = SystemAudioCaptureService()

    Task {
      do {
        // Try to start capture - this will fail if permission is not granted
        try await testService.startCapture { _ in
          // We don't need the audio data, just testing if it works
        }

        // If we get here, capture started successfully
        log("System audio: Test capture started successfully")

        // Stop the test capture
        testService.stopCapture()
        log("System audio: Test capture stopped")

        // Mark permission as granted
        recordSystemAudioCaptureOutcome(.granted)
        log("System audio: Permission verified")

      } catch {
        logError("System audio: Test capture failed", error: error)
        recordSystemAudioCaptureOutcome(SystemAudioPermissionStatus.classify(captureError: error))

        // Open System Settings to Screen Recording section
        if let url = URL(
          string: "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture")
        {
          NSWorkspace.shared.open(url)
        }
      }
    }
  }
}

// MARK: - System Event Notification Names

extension Notification.Name {
  /// Posted when the current app instance should fully clear its own onboarding state.
}

// MARK: - Privileged system command runner (BL-022)

/// Structured outcome of a system / privileged shell-out (`tccutil`,
/// `lsregister`, `sqlite3` on `TCC.db`, `xattr`, …).
///
/// These call sites previously used `try? process.run()`, which dropped *both*
/// launch failures and non-zero exits silently — a failed provenance strip broke
/// future Sparkle updates, and a failed `tccutil`/`sqlite3` reset looked
/// identical to success (BL-022). Making the outcome explicit lets callers log it
/// with context and, where a UI surface exists, reflect it — without ever
/// crashing.
enum SystemCommandOutcome: Equatable {
  /// Process ran and exited 0.
  case succeeded
  /// Process could not be started (missing binary, sandbox denial, …).
  case failedToLaunch(String)
  /// Process ran but exited non-zero; carries a bounded, sanitized stderr snippet.
  case exitedNonZero(code: Int32, stderr: String)

  var isSuccess: Bool {
    if case .succeeded = self { return true }
    return false
  }

  /// Short, log-safe one-liner describing the outcome.
  var summary: String {
    switch self {
    case .succeeded:
      return "ok"
    case .failedToLaunch(let detail):
      return "failed to launch\(detail.isEmpty ? "" : " — \(detail)")"
    case .exitedNonZero(let code, let stderr):
      return "exit \(code)\(stderr.isEmpty ? "" : " — \(stderr)")"
    }
  }

  /// Emit a single structured log line. Success is `log`; any failure is
  /// `logError` so it surfaces in error triage instead of vanishing. Use for
  /// commands that are expected to succeed (permission resets, provenance strip);
  /// for best-effort tools whose non-zero exit is benign, log `summary` directly.
  func logResult(_ label: String) {
    switch self {
    case .succeeded:
      log("\(label): ok")
    case .failedToLaunch, .exitedNonZero:
      logError("\(label): \(summary)")
    }
  }
}

/// Runs system/privileged shell-outs and returns a structured outcome instead of
/// throwing or silently swallowing. stderr is captured (bounded + sanitized) so
/// failures are diagnosable; stdout is discarded. Blocking — call off the main
/// thread for slow tools.
enum SystemCommand {
  @discardableResult
  static func run(
    executable: String,
    arguments: [String],
    maxStderrLength: Int = 200
  ) -> SystemCommandOutcome {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: executable)
    process.arguments = arguments
    let stderrPipe = Pipe()
    process.standardOutput = FileHandle.nullDevice
    process.standardError = stderrPipe

    do {
      try process.run()
    } catch {
      return .failedToLaunch(
        sanitizedCommandOutput(error.localizedDescription, maxLength: maxStderrLength))
    }

    // Drain stderr before waitUntilExit so a chatty tool can't deadlock on a full
    // pipe buffer; readDataToEndOfFile returns once the child closes the pipe.
    let stderrData = stderrPipe.fileHandleForReading.readDataToEndOfFile()
    process.waitUntilExit()

    if process.terminationStatus == 0 {
      return .succeeded
    }
    let snippet = sanitizedCommandOutput(
      String(decoding: stderrData, as: UTF8.self), maxLength: maxStderrLength)
    return .exitedNonZero(code: process.terminationStatus, stderr: snippet)
  }

  /// Run a should-succeed command, log its outcome under `label` (failure →
  /// `logError`), and return whether it succeeded so callers can branch.
  @discardableResult
  static func runLogging(_ label: String, executable: String, arguments: [String]) -> Bool {
    let outcome = run(executable: executable, arguments: arguments)
    outcome.logResult(label)
    return outcome.isSuccess
  }
}

/// Collapse captured command output to a single, control-char-free, length-
/// bounded snippet safe to log. The privileged system tools used here don't emit
/// user secrets, so this bounds noise rather than scrubbing PII.
func sanitizedCommandOutput(_ raw: String, maxLength: Int = 200) -> String {
  // Replace every control character (not just \r\n\t) with a space so a tool's
  // stderr can't inject terminal/log escape sequences into our logs or Sentry.
  let collapsed =
    raw.unicodeScalars
    .map { CharacterSet.controlCharacters.contains($0) ? " " : String($0) }
    .joined()
    .trimmingCharacters(in: .whitespacesAndNewlines)
  if collapsed.count <= maxLength { return collapsed }
  return String(collapsed.prefix(maxLength)) + "…"
}
