import OmiTheme
import SwiftUI
import UniformTypeIdentifiers

/// Stable report title for user feedback. Shared by the real `submitFeedback()`
/// path and the non-prod dry-run bridge action so the dry-run can never drift
/// from the title the real submit logs (SET-02).
func feedbackReportTitle(for _: String) -> String {
  "User Report"
}

/// Filename of the JSON diagnostics attachment produced by a feedback report.
/// Shared so the dry-run reports the same attachment name the real submit uses.
let feedbackDiagnosticsAttachmentFilename = "desktop_diagnostics.json"

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
    newWindow.styleMask = [.titled, .closable, .fullSizeContentView]
    // Transparent, light-pinned, and shadowed by its own frame. Without the pin an `NSTextField`
    // inside this sheet resolves `labelColor` against the machine's appearance and renders near-white
    // type on the near-white panel.
    WindowGlass.wear(newWindow, as: .titled)
    newWindow.setContentSize(NSSize(width: 400, height: 340))
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
  @State private var savedReportPath: String?

  init(userEmail: String?, onDismiss: @escaping () -> Void) {
    self.userEmail = userEmail
    self.onDismiss = onDismiss
    // Pre-fill email from auth
    _email = State(initialValue: userEmail ?? "")
    // Pre-fill name from AuthService
    _name = State(initialValue: AuthService.shared.displayName)
  }

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      if showSuccess {
        // Success state
        VStack(spacing: OmiSpacing.md) {
          Image(systemName: "checkmark.circle.fill")
            .scaledFont(size: 48)
            .foregroundColor(Ink.listeningGreen)

          Text(savedReportPath == nil ? "Report not saved" : "Report saved on this Mac")
            .inkStyle(.firstTitle, color: Ink.primary)

          if let savedReportPath {
            Text(
              "Nothing was sent over the network. The report (your note plus redacted diagnostics) is saved at:\n\(savedReportPath)"
            )
            .inkStyle(.prose, color: Ink.secondary)
            .textSelection(.enabled)
          } else {
            Text("The report could not be written to disk. Try \"Save Diagnostics…\" instead.")
              .inkStyle(.prose, color: Ink.secondary)
          }

          Button("Close") {
            onDismiss()
          }
          .keyboardShortcut(.defaultAction)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      } else {
        // Form state
        Text("Report an Issue")
          .inkStyle(.rowCopy, color: Ink.primary)

        Text(
          "Redacted diagnostics will be included automatically. Notes, name, and email stay on this device for privacy; save a diagnostics file to share them manually."
        )
        .inkStyle(.statusLabel, color: Ink.secondary)

        TextEditor(text: $feedbackText)
          .font(.body)
          .frame(minHeight: 100)
          .border(Ink.hairline, width: 1)

        HStack {
          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Name (optional)")
              .inkStyle(.statusLabel, color: Ink.secondary)
            TextField("Your name", text: $name)
              .textFieldStyle(.roundedBorder)
          }

          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Email")
              .inkStyle(.statusLabel, color: Ink.secondary)
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
    .padding(OmiSpacing.xl)
    // Clear of the traffic lights, which `.fullSizeContentView` puts over the content.
    .padding(.top, OmiSpacing.lg)
    .frame(width: 400, height: 340)
    // The sheet paints no ground of its own; the glass owns it, full bleed because the window frame
    // already carries the corner and the shadow.
    .inkGlassPanel(cornerRadius: 0, shadow: nil)
  }

  /// Write the report (note + redacted diagnostics bundle) under
  /// `Application Support/<bundle>/Feedback Reports/` so the user keeps a
  /// durable, shareable copy on their own machine. Best-effort: returns nil
  /// when the write fails.
  @discardableResult
  private static func persistLocalReport(
    title: String,
    note: String,
    name: String,
    email: String
  ) -> URL? {
    let fileManager = FileManager.default
    let applicationSupport =
      fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
      ?? fileManager.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support")
    let bundleID = Bundle.main.bundleIdentifier ?? "com.omi.desktop"
    let reportsDir =
      applicationSupport
      .appendingPathComponent(bundleID, isDirectory: true)
      .appendingPathComponent("Feedback Reports", isDirectory: true)
    let formatter = DateFormatter()
    formatter.dateFormat = "yyyyMMdd-HHmmss"
    let stamp = formatter.string(from: Date())
    let target = reportsDir.appendingPathComponent("report-\(stamp).txt")

    do {
      try fileManager.createDirectory(at: reportsDir, withIntermediateDirectories: true)
      var text = "title: \(title)\n"
      text += "created_at: \(ISO8601DateFormatter().string(from: Date()))\n"
      if !name.isEmpty { text += "name: \(name)\n" }
      if !email.isEmpty { text += "email: \(email)\n" }
      text += "\n\(note)\n"
      if let diagnosticsURL = DesktopDiagnosticsManager.shared.writeIncidentDiagnosticsAttachment(
        area: "other",
        failureClass: "user_report",
        phase: "other")
      {
        defer { try? fileManager.removeItem(at: diagnosticsURL) }
        if let diagnosticsData = try? Data(contentsOf: diagnosticsURL),
          let diagnosticsText = String(data: diagnosticsData, encoding: .utf8)
        {
          text += "\n--- redacted diagnostics (desktop_diagnostics.json) ---\n"
          text += diagnosticsText
          text += "\n"
        }
      }
      try text.data(using: .utf8)?.write(to: target, options: .atomic)
      return target
    } catch {
      logError("Failed to persist local feedback report", error: error)
      return nil
    }
  }

  private func submitFeedback() {
    isSubmitting = true

    let message = feedbackText.trimmingCharacters(in: .whitespacesAndNewlines)

    // Track feedback submitted
    AnalyticsManager.shared.feedbackSubmitted(feedbackLength: message.count)

    // With crash reporting removed, a report is retained locally on this
    // machine only: the note plus the bounded, redacted diagnostics bundle.
    // Nothing is transmitted anywhere; support shares the file manually.
    let reportTitle = feedbackReportTitle(for: message)
    let savedReportURL = Self.persistLocalReport(
      title: reportTitle,
      note: message,
      name: name,
      email: email)
    if let savedReportURL {
      log("User report saved locally: \(savedReportURL.path)")
    } else {
      logError("User report could not be saved locally")
    }

    // Show success
    OmiMotion.withGated {
      savedReportPath = savedReportURL?.path
      showSuccess = true
      isSubmitting = false
    }
  }

  /// Save a redacted diagnostics bundle to a user-chosen location and reveal it
  /// in Finder. Fully offline — no network — so users on named/dev
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
