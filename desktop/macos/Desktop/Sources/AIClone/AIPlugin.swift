import Foundation

/// Metadata for each AI Clone plugin supported by the desktop app.
///
/// Each plugin is a self-hosted FastAPI service that the user runs (or that
/// the Omi desktop launcher deploys). The desktop app talks to the same shape
/// of REST API across all plugins — only the credential fields and the
/// setup/toggle request bodies differ.
enum AIPlugin: String, CaseIterable, Identifiable {
    case telegram = "telegram"
    case whatsapp = "whatsapp"

    var id: String { rawValue }

    /// Display name shown in the UI.
    var displayName: String {
        switch self {
        case .telegram: return "Telegram"
        case .whatsapp: return "WhatsApp"
        }
    }

    /// SF Symbol used for the plugin card icon.
    var systemImage: String {
        switch self {
        case .telegram: return "paperplane.fill"
        case .whatsapp: return "message.fill"
        }
    }

    /// Short tagline shown on the plugin card.
    var tagline: String {
        switch self {
        case .telegram: return "Reply on your behalf via your Telegram bot."
        case .whatsapp: return "Reply on your behalf via WhatsApp Business Cloud API."
        }
    }

    /// List of credential fields the user must enter to connect this plugin.
    /// Order matches the order shown in the connect form.
    var credentialFields: [AICredentialField] {
        switch self {
        case .telegram:
            return [
                AICredentialField(
                    key: "bot_token",
                    label: "Bot Token",
                    placeholder: "From @BotFather",
                    isSecure: true
                )
            ]
        case .whatsapp:
            return [
                AICredentialField(
                    key: "access_token",
                    label: "Access Token",
                    placeholder: "Permanent system user token",
                    isSecure: true
                ),
                AICredentialField(
                    key: "phone_number_id",
                    label: "Phone Number ID",
                    placeholder: "From Meta WhatsApp dashboard",
                    isSecure: false
                ),
                AICredentialField(
                    key: "verify_token",
                    label: "Verify Token",
                    placeholder: "The token you entered in Meta webhook config",
                    isSecure: true
                )
            ]
        }
    }

    /// Returns the JSON request body for `POST /setup`, given the user's
    /// entered credentials plus the auto-populated identity fields.
    func setupRequestBody(
        credentials: [String: String],
        omiUid: String,
        personaId: String,
        omiDevApiKey: String,
        publicBaseUrl: String
    ) -> [String: Any] {
        var body: [String: Any] = [
            "omi_uid": omiUid,
            "persona_id": personaId,
            "omi_dev_api_key": omiDevApiKey,
            "public_base_url": publicBaseUrl,
        ]
        for (key, value) in credentials {
            body[key] = value
        }
        return body
    }

    /// Returns the JSON request body for `POST /toggle`.
    /// The `enabled` parameter controls the target state — callers must
    /// pass the desired value, not assume "true". (P2 fix: previously
    /// hardcoded true, preventing disable operations.)
    func toggleRequestBody(chatId: String, enabled: Bool) -> [String: Any] {
        switch self {
        case .telegram:
            return ["chat_id": chatId, "enabled": enabled]
        case .whatsapp:
            return ["phone": chatId, "enabled": enabled]
        }
    }

    /// The credential that doubles as the auth secret for `/toggle`.
    /// Telegram: bot_token. WhatsApp: access_token.
    var toggleAuthCredentialKey: String {
        switch self {
        case .telegram: return "bot_token"
        case .whatsapp: return "access_token"
        }
    }
}

/// One input field on the plugin connect form.
struct AICredentialField: Identifiable {
    let key: String
    let label: String
    let placeholder: String
    let isSecure: Bool

    var id: String { key }
}