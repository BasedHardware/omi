import SwiftUI

/// Minimal Telegram login sheet: phone → code → optional 2-step password, driving
/// `TelegramSendService`'s auth state machine through to `authorizationStateReady`.
///
/// The service is the source of truth; this view observes `TelegramLoginModel` and
/// pushes user input back into the actor. It intentionally does NOT own any TDLib
/// state itself.
struct TelegramLoginView: View {
  @ObservedObject private var model = TelegramLoginModel.shared
  @Environment(\.dismiss) private var dismiss

  @State private var phone = ""
  @State private var code = ""
  @State private var password = ""

  var body: some View {
    VStack(alignment: .leading, spacing: 16) {
      Text("Connect Telegram")
        .font(.title2.weight(.semibold))

      switch model.state {
      case .connecting:
        row {
          ProgressView().controlSize(.small)
          Text("Connecting…").foregroundStyle(.secondary)
        }

      case .waitPhone:
        field(
          title: "Phone number",
          prompt: "+1 415 555 0123",
          text: $phone,
          submitLabel: "Send code"
        ) {
          model.isSubmitting = true
          Task { await TelegramSendService.shared.submitPhone(phone) }
        }

      case .waitCode:
        field(
          title: "Login code",
          prompt: "12345",
          text: $code,
          submitLabel: "Verify"
        ) {
          model.isSubmitting = true
          Task { await TelegramSendService.shared.submitCode(code) }
        }

      case .waitPassword:
        secureField(
          title: "Two-step verification password",
          text: $password,
          submitLabel: "Log in"
        ) {
          model.isSubmitting = true
          Task { await TelegramSendService.shared.submitPassword(password) }
        }

      case .ready:
        row {
          Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
          Text("Connected").font(.headline)
        }
        Button("Done") { dismiss() }
          .keyboardShortcut(.defaultAction)

      case .closed:
        Text("Disconnected.").foregroundStyle(.secondary)

      case .error(let message):
        row {
          Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.orange)
          Text(message).foregroundStyle(.secondary)
        }
        Button("Try again") {
          Task { await TelegramSendService.shared.start() }
        }
      }
    }
    .padding(24)
    .frame(width: 380)
    .task { await TelegramSendService.shared.start() }
  }

  // MARK: - Building blocks

  @ViewBuilder
  private func row<Content: View>(@ViewBuilder _ content: () -> Content) -> some View {
    HStack(spacing: 8) { content() }
  }

  @ViewBuilder
  private func field(
    title: String, prompt: String, text: Binding<String>, submitLabel: String,
    action: @escaping () -> Void
  ) -> some View {
    VStack(alignment: .leading, spacing: 8) {
      Text(title).font(.subheadline).foregroundStyle(.secondary)
      TextField(prompt, text: text)
        .textFieldStyle(.roundedBorder)
        .onSubmit(action)
      submitButton(submitLabel, text: text.wrappedValue, action: action)
    }
  }

  @ViewBuilder
  private func secureField(
    title: String, text: Binding<String>, submitLabel: String, action: @escaping () -> Void
  ) -> some View {
    VStack(alignment: .leading, spacing: 8) {
      Text(title).font(.subheadline).foregroundStyle(.secondary)
      SecureField("", text: text)
        .textFieldStyle(.roundedBorder)
        .onSubmit(action)
      submitButton(submitLabel, text: text.wrappedValue, action: action)
    }
  }

  @ViewBuilder
  private func submitButton(_ label: String, text: String, action: @escaping () -> Void)
    -> some View
  {
    Button(action: action) {
      if model.isSubmitting {
        ProgressView().controlSize(.small)
      } else {
        Text(label)
      }
    }
    .keyboardShortcut(.defaultAction)
    .disabled(model.isSubmitting || text.trimmingCharacters(in: .whitespaces).isEmpty)
  }
}
