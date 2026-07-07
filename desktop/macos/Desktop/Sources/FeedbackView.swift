import Sentry
import SwiftUI
import UniformTypeIdentifiers
import OmiTheme

/// Window controller for the feedback dialog
@MainActor
class FeedbackWindow {
  private static var window: NSWindow?

  static func show(userEmail: String?) {
    // Close existing window if any
    window?.close()

    // Track feedback opened
    AnalyticsManager.shared.feedbackOpened()

    let feedbackView = FeedbackView(userEmail: userEmail) {
      window?.close()
      window = nil
    }

    let hostingController = NSHostingController(rootView: feedbackView.withFontScaling())

    let newWindow = NSWindow(contentViewController: hostingController)
    newWindow.title = "Report Issue"
    newWindow.styleMask = [.titled, .closable]
    newWindow.setContentSize(NSSize(width: 400, height: 300))
    newWindow.center()
    newWindow.makeKeyAndOrderFront(nil)
    newWindow.level = .floating

    window = newWindow

    NSApp.activate()
  }
}

/// SwiftUI view for collecting user feedback and sending logs
struct FeedbackView: View {
  let userEmail: String?
  let onDismiss: () -> Void

  @State private var feedbackText: String = ""
  @State private var name: String = ""
  @State private var email: String = ""
  @State private var isSubmitting: Bool = false
  @State private var showSuccess: Bool = false

  init(userEmail: String?, onDismiss: @escaping () -> Void) {
    self.userEmail = userEmail
    self.onDismiss = onDismiss
    // Pre-fill email from auth
    _email = State(initialValue: userEmail ?? "")
    // Pre-fill name from AuthService
    _name = State(initialValue: AuthService.shared.displayName)
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 16) {
      if showSuccess {
        // Success state
        VStack(spacing: 12) {
          Image(systemName: "checkmark.circle.fill")
            .scaledFont(size: 48)
            .foregroundColor(.green)

          Text("Report sent!")
            .font(.headline)

          Text("We'll look into this issue.")
            .foregroundColor(.secondary)

          Button("Close") {
            onDismiss()
          }
          .keyboardShortcut(.defaultAction)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      } else {
        // Form state
        Text("Report an Issue")
          .font(.headline)

        Text(
          "App logs will be included automatically. Optionally describe what went wrong, or save a redacted diagnostics file to share manually."
        )
        .font(.caption)
        .foregroundColor(.secondary)

        TextEditor(text: $feedbackText)
          .font(.body)
          .frame(minHeight: 100)
          .border(Color.gray.opacity(0.3), width: 1)

        HStack {
          VStack(alignment: .leading, spacing: 4) {
            Text("Name (optional)")
              .font(.caption)
              .foregroundColor(.secondary)
            TextField("Your name", text: $name)
              .textFieldStyle(.roundedBorder)
          }

          VStack(alignment: .leading, spacing: 4) {
            Text("Email")
              .font(.caption)
              .foregroundColor(.secondary)
            TextField("your@email.com", text: $email)
              .textFieldStyle(.roundedBorder)
          }
        }

        HStack {
          Button("Cancel") {
            onDismiss()
          }
          .keyboardShortcut(.cancelAction)

          Button("Save Diagnostics…") {
            saveDiagnosticsLocally()
          }
          .help("Save a redacted diagnostics report locally — works offline, nothing is uploaded.")

          Spacer()

          Button("Send Report") {
            submitFeedback()
          }
          .keyboardShortcut(.defaultAction)
          .disabled(isSubmitting)
        }
      }
    }
    .padding(20)
    .frame(width: 400, height: 300)
  }

  private func submitFeedback() {
    isSubmitting = true

    let message = feedbackText.trimmingCharacters(in: .whitespacesAndNewlines)

    // Track feedback submitted
    AnalyticsManager.shared.feedbackSubmitted(feedbackLength: message.count)

    // Submit to Sentry with log file attachment (dev + prod — user explicitly chose to report)
    let sentryMessage = message.isEmpty ? "User Report (logs only)" : "User Report: \(message)"

    // Capture event with log file attached via scope
    let eventId = SentrySDK.capture(message: sentryMessage) { scope in
      let logPath = omiLogFilePath()
      let logFilename = (logPath as NSString).lastPathComponent
      if FileManager.default.fileExists(atPath: logPath) {
        let attachment = Attachment(path: logPath, filename: logFilename, contentType: "text/plain")
        scope.addAttachment(attachment)
      }
      if let diagnosticsURL = DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment() {
        let attachment = Attachment(
          path: diagnosticsURL.path,
          filename: "desktop_diagnostics.json",
          contentType: "application/json")
        scope.addAttachment(attachment)
      }
    }

    // Also send as Sentry feedback if there's a message
    if !message.isEmpty {
      let feedback = SentryFeedback(
        message: message,
        name: name.trimmingCharacters(in: .whitespacesAndNewlines),
        email: email.trimmingCharacters(in: .whitespacesAndNewlines),
        associatedEventId: eventId
      )
      SentrySDK.capture(feedback: feedback)
    }

    log(
      "User report submitted to Sentry (logs attached, message: \(message.isEmpty ? "none" : "yes"))"
    )

    // Show success
    withAnimation {
      showSuccess = true
      isSubmitting = false
    }
  }

  /// Save a redacted diagnostics bundle to a user-chosen location and reveal it
  /// in Finder. Fully offline — no Sentry, no network — so users on named/dev
  /// bundles or without connectivity can still capture a report (BL-023 / SET-03).
  private func saveDiagnosticsLocally() {
    let panel = NSSavePanel()
    panel.title = "Save Diagnostics"
    panel.message = "Save a redacted diagnostics report you can share manually."
    panel.nameFieldStringValue = "omi-diagnostics-\(Self.exportTimestamp()).txt"
    panel.allowedContentTypes = [.plainText]
    panel.canCreateDirectories = true

    guard panel.runModal() == .OK, let url = panel.url else { return }

    // Building the bundle reads the log, serializes snapshots, and writes the
    // file — keep it off the main thread so a large log can't hang the UI. The
    // panel already returned; reveal in Finder back on main.
    DispatchQueue.global(qos: .userInitiated).async {
      let saved = DesktopDiagnosticsManager.shared.writeLocalDiagnosticsBundle(to: url)
      DispatchQueue.main.async {
        if saved {
          NSWorkspace.shared.activateFileViewerSelecting([url])
          log("Saved local diagnostics bundle to a user-chosen location")
        } else {
          log("Failed to save local diagnostics bundle")
        }
      }
    }
  }

  private static func exportTimestamp() -> String {
    let formatter = DateFormatter()
    formatter.dateFormat = "yyyyMMdd-HHmmss"
    return formatter.string(from: Date())
  }
}
