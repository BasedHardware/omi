import Foundation
import Combine

// MARK: - Models

struct CloneMessage: Identifiable, Sendable {
    let id: String
    let platform: String
    let sender: String
    let chatIdentifier: String  // phone/email for iMessage, chat_id string for Telegram
    let incoming: String
    var draftReply: String
    var status: CloneMessageStatus
    let createdAt: Date

    enum CloneMessageStatus: String {
        case pending, approved, dismissed, sent
    }
}

// MARK: - Service

@MainActor
final class AICloneService: ObservableObject {
    static let shared = AICloneService()

    @Published var isEnabled: Bool = false

    // iMessage
    @Published var iMessageConnected: Bool = false
    @Published var iMessageActive: Bool = false

    // Telegram — Bot API state
    @Published var telegramConnected: Bool = false
    @Published var telegramBotUsername: String = ""
    @Published var telegramConnecting: Bool = false
    @Published var telegramError: String = ""
    @Published var telegramActive: Bool = false

    // WhatsApp — Cloud API bot state
    @Published var whatsAppConfigured: Bool = false
    @Published var whatsAppBotPhone: String = ""
    @Published var whatsAppActive: Bool = false

    private var pollingTask: Task<Void, Never>?
    private var lastIMessageDate: Double = 0

    private init() {
        isEnabled = UserDefaults.standard.bool(forKey: "aiCloneEnabled")
        lastIMessageDate = UserDefaults.standard.double(forKey: "aiCloneLastIMessageDate")
        iMessageConnected = checkIMessagePermission()
        // Migration: key absent means this is a first-run after the per-platform toggle was added.
        // Default to active if AI Clone was already enabled and iMessage was connected.
        if UserDefaults.standard.object(forKey: "aiCloneIMessageActive") == nil {
            iMessageActive = isEnabled && iMessageConnected
            UserDefaults.standard.set(iMessageActive, forKey: "aiCloneIMessageActive")
        } else {
            iMessageActive = UserDefaults.standard.bool(forKey: "aiCloneIMessageActive")
        }
        telegramConnected = UserDefaults.standard.bool(forKey: "aiCloneTelegramConnected")
        telegramBotUsername = UserDefaults.standard.string(forKey: "aiCloneTelegramBotUsername") ?? ""
        telegramActive = UserDefaults.standard.bool(forKey: "aiCloneTelegramActive")
        whatsAppConfigured = UserDefaults.standard.bool(forKey: "aiCloneWhatsAppConfigured")
        whatsAppBotPhone = UserDefaults.standard.string(forKey: "aiCloneWhatsAppBotPhone") ?? ""
        whatsAppActive = UserDefaults.standard.bool(forKey: "aiCloneWhatsAppActive")
        if isEnabled { startPolling() }
    }

    func setActive(platform: String, active: Bool) {
        applyActive(platform: platform, active: active)
        Task {
            do {
                try await APIClient.shared.setPlatformActive(platform: platform, active: active)
            } catch {
                // Revert optimistic update — backend rejected the change.
                applyActive(platform: platform, active: !active)
                log("AICloneService: failed to sync \(platform) active=\(active): \(error)")
            }
        }
    }

    private func applyActive(platform: String, active: Bool) {
        switch platform {
        case "imessage":
            iMessageActive = active
            UserDefaults.standard.set(active, forKey: "aiCloneIMessageActive")
        case "telegram":
            telegramActive = active
            UserDefaults.standard.set(active, forKey: "aiCloneTelegramActive")
        case "whatsapp":
            whatsAppActive = active
            UserDefaults.standard.set(active, forKey: "aiCloneWhatsAppActive")
        default:
            break
        }
    }

    func configureWhatsApp(botPhone: String) {
        whatsAppBotPhone = botPhone
        whatsAppConfigured = !botPhone.isEmpty
        UserDefaults.standard.set(whatsAppConfigured, forKey: "aiCloneWhatsAppConfigured")
        UserDefaults.standard.set(botPhone, forKey: "aiCloneWhatsAppBotPhone")
    }

    func enable(_ enabled: Bool) {
        isEnabled = enabled
        UserDefaults.standard.set(enabled, forKey: "aiCloneEnabled")
        Task { try? await APIClient.shared.updateCloneSettings(enabled: enabled, autoReply: true) }
        if enabled { startPolling() } else { stopPolling() }
    }

    func startPolling() {
        pollingTask?.cancel()
        pollingTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.pollIMessage()
                try? await Task.sleep(for: .seconds(15))
            }
        }
    }

    func stopPolling() {
        pollingTask?.cancel()
        pollingTask = nil
    }

    // MARK: - iMessage (AppleScript)

    private func checkIMessagePermission() -> Bool {
        return FileManager.default.fileExists(atPath: "/System/Applications/Messages.app")
    }

    private func pollIMessage() async {
        guard iMessageActive else { return }
        let cutoffInterval = max(lastIMessageDate, Date().timeIntervalSince1970 - 900)
        let script = """
        tell application "Messages"
            set resultStr to ""
            set cutoffDate to (current date) - \(Int(Date().timeIntervalSince1970 - cutoffInterval))
            repeat with aChat in every chat
                try
                    set partList to participants of aChat
                    if (count of partList) is 1 then
                        set theBuddy to item 1 of partList
                        set buddyHandle to handle of theBuddy
                        set buddyName to name of theBuddy
                        repeat with aMsg in (messages of aChat)
                            if direction of aMsg is incoming and date of aMsg > cutoffDate then
                                set msgContent to content of aMsg
                                if msgContent is not "" then
                                    set resultStr to resultStr & buddyHandle & "|||" & buddyName & "|||" & msgContent & "|||" & ((date of aMsg) as string) & "~~~"
                                end if
                            end if
                        end repeat
                    end if
                end try
            end repeat
            return resultStr
        end tell
        """

        guard let raw = await runOsascript(script), !raw.isEmpty else { return }

        let entries = raw.components(separatedBy: "~~~").filter { !$0.isEmpty }
        for entry in entries.reversed() {
            let parts = entry.components(separatedBy: "|||")
            guard parts.count >= 4 else { continue }
            let handle = parts[0].trimmingCharacters(in: .whitespacesAndNewlines)
            let name = parts[1].trimmingCharacters(in: .whitespacesAndNewlines)
            // Rejoin middle parts in case the message itself contained "|||"
            let text = parts[2..<(parts.count - 1)].joined(separator: "|||")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            let dateStr = parts[parts.count - 1].trimmingCharacters(in: .whitespacesAndNewlines)

            let msgDate = parseAppleScriptDate(dateStr) ?? Date()
            if msgDate.timeIntervalSince1970 > lastIMessageDate {
                lastIMessageDate = msgDate.timeIntervalSince1970
                UserDefaults.standard.set(lastIMessageDate, forKey: "aiCloneLastIMessageDate")
            }
            await handleIMessage(sender: name.isEmpty ? handle : name, handle: handle, message: text)
        }
    }

    private func parseAppleScriptDate(_ str: String) -> Date? {
        let formatters = [
            "EEEE, MMMM d, yyyy 'at' h:mm:ss a",
            "EEEE, d MMMM yyyy 'at' HH:mm:ss",
            "EEEE, MMMM d, yyyy 'at' HH:mm:ss",
        ]
        for fmt in formatters {
            let f = DateFormatter()
            f.dateFormat = fmt
            f.locale = Locale.current
            if let d = f.date(from: str) { return d }
        }
        return nil
    }

    // MARK: - Telegram (Bot API)

    func telegramConnect(botToken: String) async {
        telegramConnecting = true
        telegramError = ""
        do {
            let result = try await APIClient.shared.telegramConnect(botToken: botToken)
            telegramConnected = true
            telegramBotUsername = result.botUsername
            UserDefaults.standard.set(true, forKey: "aiCloneTelegramConnected")
            UserDefaults.standard.set(result.botUsername, forKey: "aiCloneTelegramBotUsername")
        } catch {
            telegramError = "Invalid bot token. Create one at @BotFather and try again."
        }
        telegramConnecting = false
    }

    func telegramDisconnect() async {
        try? await APIClient.shared.telegramDisconnect()
        telegramConnected = false
        telegramBotUsername = ""
        telegramActive = false
        UserDefaults.standard.set(false, forKey: "aiCloneTelegramConnected")
        UserDefaults.standard.removeObject(forKey: "aiCloneTelegramBotUsername")
        UserDefaults.standard.set(false, forKey: "aiCloneTelegramActive")
    }

    // MARK: - Handle iMessage (auto-reply)

    private func handleIMessage(sender: String, handle: String, message: String) async {
        do {
            let reply = try await APIClient.shared.generateCloneReply(
                platform: "imessage",
                sender: sender,
                message: message
            )
            // Append "— Omi" signature so the recipient knows this is an AI reply
            let signedReply = reply.reply + "\n— Omi"
            await sendViaIMessage(handle: handle, text: signedReply)
            try? await APIClient.shared.updateCloneMessage(id: reply.messageId, status: "sent", editedReply: nil)
        } catch {
            log("AICloneService: Failed to handle iMessage: \(error)")
        }
    }

    // MARK: - Platform Send

    private func sendViaTelegram(chatId: String, text: String) async {
        guard let id = Int(chatId) else { return }
        do {
            try await APIClient.shared.telegramSend(chatId: id, text: text)
        } catch {
            log("AICloneService: Telegram send failed: \(error)")
        }
    }

    private func sendViaWhatsApp(to: String, text: String) async {
        do {
            try await APIClient.shared.whatsappSend(to: to, text: text)
        } catch {
            log("AICloneService: WhatsApp send failed: \(error)")
        }
    }

    private func sendViaIMessage(handle: String, text: String) async {
        let escaped = text
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")
        let escapedHandle = handle
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")

        let script = """
        tell application "Messages"
            send "\(escaped)" to buddy "\(escapedHandle)" of (first service whose service type = iMessage)
        end tell
        """
        let result = await runOsascript(script)
        if result == nil {
            log("AICloneService: iMessage send may have failed for handle=\(handle)")
        }
    }

    // MARK: - osascript helper

    private func runOsascript(_ script: String) async -> String? {
        return await Task.detached(priority: .utility) {
            let proc = Process()
            proc.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
            proc.arguments = ["-e", script]
            let outPipe = Pipe()
            let errPipe = Pipe()
            proc.standardOutput = outPipe
            proc.standardError = errPipe
            do {
                try proc.run()
            } catch {
                return nil
            }
            proc.waitUntilExit()
            let data = outPipe.fileHandleForReading.readDataToEndOfFile()
            let output = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)
            return (output?.isEmpty == false) ? output : nil
        }.value
    }

    // MARK: - Connectivity

    func refreshConnectivity() {
        iMessageConnected = checkIMessagePermission()
    }
}
