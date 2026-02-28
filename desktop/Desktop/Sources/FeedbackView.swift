import SwiftUI
import Sentry

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

        NSApp.activate(ignoringOtherApps: true)
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

                Text("App logs will be included automatically. Optionally describe what went wrong.")
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

        // Submit to Sentry with log file attachment (skip in dev builds)
        if !AnalyticsManager.isDevBuild {
            let sentryMessage = message.isEmpty ? "User Report (logs only)" : "User Report: \(message)"

            // Capture event with log file attached via scope
            let eventId = SentrySDK.capture(message: sentryMessage) { scope in
                let isDev = Bundle.main.bundleIdentifier?.hasSuffix("-dev") == true
                let logPath = isDev ? "/tmp/omi-dev.log" : "/tmp/omi.log"
                let logFilename = isDev ? "omi-dev.log" : "omi.log"
                if FileManager.default.fileExists(atPath: logPath) {
                    let attachment = Attachment(path: logPath, filename: logFilename, contentType: "text/plain")
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

            log("User report submitted to Sentry (logs attached, message: \(message.isEmpty ? "none" : "yes"))")
        } else {
            log("User report (dev build - not sent to Sentry). Message: \(message.isEmpty ? "none" : message)")
        }

        // Show success
        withAnimation {
            showSuccess = true
            isSubmitting = false
        }
    }
}
