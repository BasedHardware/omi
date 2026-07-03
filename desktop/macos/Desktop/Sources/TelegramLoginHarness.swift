import Foundation

/// Headless automation actions for the native Telegram (TDLib) login + send flow,
/// registered on the local automation bridge (non-production bundles only). They let
/// an agent drive the real auth state machine turn-by-turn without touching the UI —
/// mirroring how the Rust POC used a control directory.
///
/// Actions:
///   telegram_login_start                 — create the client, begin/resume auth
///   telegram_login_status                — current auth state ("connecting"/"waitPhone"/…)
///   telegram_login_phone phone=+1…       — submit the phone number
///   telegram_login_code code=12345       — submit the login code
///   telegram_login_password password=…   — submit the 2-step password (2FA accounts)
///   telegram_send chat_id=… text=…       — send a text message (requires ready)
///   telegram_logout                      — log out and tear the client down
enum TelegramLoginHarness {

  @MainActor
  static func register(on registry: DesktopAutomationActionRegistry) {
    registry.register(
      name: "telegram_login_start",
      summary: "Create the Telegram TDLib client and begin (or resume) the auth flow"
    ) { _ in
      await TelegramSendService.shared.start()
      // Give TDLib a beat to emit the first authorization-state update.
      try? await Task.sleep(nanoseconds: 800_000_000)
      return ["state": Self.label(await TelegramSendService.shared.state())]
    }

    registry.register(
      name: "telegram_login_status",
      summary: "Report the current Telegram authorization state"
    ) { _ in
      ["state": Self.label(await TelegramSendService.shared.state())]
    }

    registry.register(
      name: "telegram_login_phone",
      summary: "Submit the phone number to Telegram (international format, e.g. +14155550123)",
      params: ["phone"]
    ) { params in
      guard let phone = params["phone"], !phone.isEmpty else { return ["error": "missing 'phone'"] }
      await TelegramSendService.shared.submitPhone(phone)
      try? await Task.sleep(nanoseconds: 1_500_000_000)
      return ["state": Self.label(await TelegramSendService.shared.state())]
    }

    registry.register(
      name: "telegram_login_code",
      summary: "Submit the Telegram login code",
      params: ["code"]
    ) { params in
      guard let code = params["code"], !code.isEmpty else { return ["error": "missing 'code'"] }
      await TelegramSendService.shared.submitCode(code)
      try? await Task.sleep(nanoseconds: 1_500_000_000)
      return ["state": Self.label(await TelegramSendService.shared.state())]
    }

    registry.register(
      name: "telegram_login_password",
      summary: "Submit the Telegram two-step verification password",
      params: ["password"]
    ) { params in
      guard let password = params["password"], !password.isEmpty else {
        return ["error": "missing 'password'"]
      }
      await TelegramSendService.shared.submitPassword(password)
      try? await Task.sleep(nanoseconds: 1_500_000_000)
      return ["state": Self.label(await TelegramSendService.shared.state())]
    }

    registry.register(
      name: "telegram_me",
      summary: "Return the logged-in Telegram user (id + name) via an authenticated getMe round-trip"
    ) { _ in
      do {
        let me = try await TelegramSendService.shared.me()
        return ["id": String(me.id), "name": me.firstName, "last_name": me.lastName]
      } catch {
        return ["error": error.localizedDescription]
      }
    }

    registry.register(
      name: "telegram_send",
      summary: "Send a text message to a Telegram chat id (requires a ready session)",
      params: ["chat_id", "text"]
    ) { params in
      guard let chatIdString = params["chat_id"], let chatId = Int64(chatIdString) else {
        return ["error": "missing or invalid 'chat_id'"]
      }
      guard let text = params["text"], !text.isEmpty else { return ["error": "missing 'text'"] }
      do {
        try await TelegramSendService.shared.sendMessage(chatId: chatId, text: text)
        return ["sent": "true", "chat_id": chatIdString]
      } catch {
        return ["error": error.localizedDescription]
      }
    }

    registry.register(
      name: "telegram_logout",
      summary: "Log out of Telegram and tear down the TDLib client"
    ) { _ in
      await TelegramSendService.shared.logout()
      return ["state": Self.label(await TelegramSendService.shared.state())]
    }
  }

  private static func label(_ state: TelegramAuthState) -> String {
    switch state {
    case .connecting: return "connecting"
    case .waitPhone: return "waitPhone"
    case .waitCode: return "waitCode"
    case .waitPassword: return "waitPassword"
    case .ready: return "ready"
    case .closed: return "closed"
    case .error(let message): return "error: \(message)"
    }
  }
}
