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

    @Published var pendingMessages: [CloneMessage] = []
    @Published var isEnabled: Bool = false
    @Published var autoReply: Bool = false

    // iMessage
    @Published var iMessageConnected: Bool = false

    // Telegram — personal account (Telethon) state
    @Published var telegramConnected: Bool = false
    @Published var telegramDisplayName: String = ""
    @Published var telegramPhone: String = ""
    @Published var telegramSendingCode: Bool = false
    @Published var telegramVerifying: Bool = false
    @Published var telegramError: String = ""

    // WhatsApp — Cloud API bot state
    @Published var whatsAppConfigured: Bool = false
    @Published var whatsAppBotPhone: String = ""

    private var pollingTask: Task<Void, Never>?
    private var lastIMessageDate: Double = 0
    private var lastTelegramPollTime: Double = 0

    // phone_code_hash from send-code response, needed for verify step
    var telegramPendingHash: String = ""

    private init() {
        isEnabled = UserDefaults.standard.bool(forKey: "aiCloneEnabled")
        autoReply = UserDefaults.standard.bool(forKey: "aiCloneAutoReply")
        lastIMessageDate = UserDefaults.standard.double(forKey: "aiCloneLastIMessageDate")
        lastTelegramPollTime = UserDefaults.standard.double(forKey: "aiCloneLastTelegramPoll")
        telegramConnected = UserDefaults.standard.bool(forKey: "aiCloneTelegramConnected")
        telegramDisplayName = UserDefaults.standard.string(forKey: "aiCloneTelegramName") ?? ""
        telegramPhone = UserDefaults.standard.string(forKey: "aiCloneTelegramPhone") ?? ""
        iMessageConnected = checkIMessagePermission()
        whatsAppConfigured = UserDefaults.standard.bool(forKey: "aiCloneWhatsAppConfigured")
        whatsAppBotPhone = UserDefaults.standard.string(forKey: "aiCloneWhatsAppBotPhone") ?? ""
        // Resume polling if AI Clone was enabled before the app was quit.
        if isEnabled { startPolling() }
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
        Task { try? await APIClient.shared.updateCloneSettings(enabled: enabled, autoReply: autoReply) }
        if enabled { startPolling() } else { stopPolling() }
    }

    func setAutoReply(_ value: Bool) {
        autoReply = value
        UserDefaults.standard.set(value, forKey: "aiCloneAutoReply")
        Task { try? await APIClient.shared.updateCloneSettings(enabled: isEnabled, autoReply: value) }
    }

    func startPolling() {
        pollingTask?.cancel()
        pollingTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.pollAllPlatforms()
                try? await Task.sleep(for: .seconds(15))
            }
        }
    }

    func stopPolling() {
        pollingTask?.cancel()
        pollingTask = nil
    }

    // MARK: - Polling

    private func pollAllPlatforms() async {
        async let iMsg: Void = pollIMessage()
        async let tg: Void = pollTelegram()
        _ = await (iMsg, tg)
    }

    // MARK: - iMessage (AppleScript)

    private func checkIMessagePermission() -> Bool {
        // Full disk access check — if the app can query Messages.app via AppleScript, it'll work.
        // We just verify Messages.app exists.
        return FileManager.default.fileExists(atPath: "/System/Applications/Messages.app")
    }

    private func pollIMessage() async {
        // Use AppleScript to read recent incoming messages from Messages.app.
        // The app has com.apple.security.automation.apple-events = true, so this works without sandbox.
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
            await handleIncoming(platform: "imessage", sender: name.isEmpty ? handle : name, chatId: handle, message: text)
        }
    }

    private func parseAppleScriptDate(_ str: String) -> Date? {
        // AppleScript date strings vary by locale; try a few formatters
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

    // MARK: - Telegram (personal account via backend Telethon)

    private func pollTelegram() async {
        guard telegramConnected else { return }
        let since = lastTelegramPollTime
        guard let result = try? await APIClient.shared.telegramPollMessages(since: since) else { return }
        for msg in result.messages {
            if msg.timestamp > lastTelegramPollTime {
                lastTelegramPollTime = msg.timestamp
                UserDefaults.standard.set(lastTelegramPollTime, forKey: "aiCloneLastTelegramPoll")
            }
            await handleIncoming(
                platform: "telegram",
                sender: msg.sender,
                chatId: String(msg.chatId),
                message: msg.message
            )
        }
    }

    // MARK: - Telegram Auth

    func telegramSendCode(phone: String) async {
        telegramSendingCode = true
        telegramError = ""
        do {
            let hash = try await APIClient.shared.telegramSendCode(phone: phone)
            telegramPendingHash = hash
        } catch {
            telegramError = "Failed to send code. Check your phone number and try again."
        }
        telegramSendingCode = false
    }

    func telegramVerify(phone: String, code: String) async {
        telegramVerifying = true
        telegramError = ""
        do {
            let info = try await APIClient.shared.telegramVerify(
                phone: phone,
                code: code,
                phoneCodeHash: telegramPendingHash
            )
            telegramConnected = true
            telegramDisplayName = info.displayName
            telegramPhone = phone
            telegramPendingHash = ""
            UserDefaults.standard.set(true, forKey: "aiCloneTelegramConnected")
            UserDefaults.standard.set(info.displayName, forKey: "aiCloneTelegramName")
            UserDefaults.standard.set(phone, forKey: "aiCloneTelegramPhone")
        } catch {
            telegramError = "Wrong code. Please try again."
        }
        telegramVerifying = false
    }

    func telegramDisconnect() async {
        try? await APIClient.shared.telegramDisconnect()
        telegramConnected = false
        telegramDisplayName = ""
        telegramPhone = ""
        telegramPendingHash = ""
        UserDefaults.standard.set(false, forKey: "aiCloneTelegramConnected")
        UserDefaults.standard.removeObject(forKey: "aiCloneTelegramName")
        UserDefaults.standard.removeObject(forKey: "aiCloneTelegramPhone")
    }

    // MARK: - Handle Incoming

    private func handleIncoming(platform: String, sender: String, chatId: String, message: String) async {
        // Only deduplicate against messages still awaiting action (status == .pending).
        // Allowing the same text from the same chat after it has been sent/dismissed lets
        // legitimate repeated short messages (e.g. "ok", "thanks") through.
        let isDuplicate = pendingMessages.contains {
            $0.status == .pending && $0.platform == platform && $0.chatIdentifier == chatId && $0.incoming == message
        }
        guard !isDuplicate else { return }

        do {
            let reply = try await APIClient.shared.generateCloneReply(
                platform: platform,
                sender: sender,
                message: message
            )
            let cloneMsg = CloneMessage(
                id: reply.messageId,
                platform: platform,
                sender: sender,
                chatIdentifier: chatId,
                incoming: message,
                draftReply: reply.reply,
                status: .pending,
                createdAt: Date()
            )
            pendingMessages.insert(cloneMsg, at: 0)

            if autoReply {
                await performSend(cloneMsg)
            }
        } catch {
            log("AICloneService: Failed to generate reply: \(error)")
        }
    }

    // MARK: - Actions

    func approveMessage(_ id: String) async {
        guard let idx = pendingMessages.firstIndex(where: { $0.id == id }) else { return }
        let msg = pendingMessages[idx]
        await performSend(msg)
        pendingMessages[idx].status = .sent
        try? await APIClient.shared.updateCloneMessage(id: id, status: "sent", editedReply: nil)
    }

    func dismissMessage(_ id: String) async {
        guard let idx = pendingMessages.firstIndex(where: { $0.id == id }) else { return }
        pendingMessages[idx].status = .dismissed
        try? await APIClient.shared.updateCloneMessage(id: id, status: "dismissed", editedReply: nil)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            self.pendingMessages.removeAll { $0.id == id }
        }
    }

    func editAndSend(_ id: String, editedText: String) async {
        guard let idx = pendingMessages.firstIndex(where: { $0.id == id }) else { return }
        pendingMessages[idx].draftReply = editedText
        var edited = pendingMessages[idx]
        edited = CloneMessage(
            id: edited.id,
            platform: edited.platform,
            sender: edited.sender,
            chatIdentifier: edited.chatIdentifier,
            incoming: edited.incoming,
            draftReply: editedText,
            status: edited.status,
            createdAt: edited.createdAt
        )
        await performSend(edited)
        pendingMessages[idx].status = .sent
        try? await APIClient.shared.updateCloneMessage(id: id, status: "sent", editedReply: editedText)
    }

    // MARK: - Platform Send

    private func performSend(_ msg: CloneMessage) async {
        switch msg.platform {
        case "telegram":
            await sendViaTelegram(chatId: msg.chatIdentifier, text: msg.draftReply)
        case "imessage":
            await sendViaIMessage(handle: msg.chatIdentifier, text: msg.draftReply)
        case "whatsapp":
            await sendViaWhatsApp(to: msg.chatIdentifier, text: msg.draftReply)
        default:
            break
        }
    }

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
        // Escape text for AppleScript string literal
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
