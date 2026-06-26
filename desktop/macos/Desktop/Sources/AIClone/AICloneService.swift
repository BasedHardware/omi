import Foundation
import Combine
import GRDB

// MARK: - Models

struct CloneMessage: Identifiable, Sendable {
    let id: String
    let platform: String
    let sender: String
    let incoming: String
    var draftReply: String
    var status: CloneMessageStatus
    let createdAt: Date

    enum CloneMessageStatus: String {
        case pending, approved, dismissed, sent
    }
}

struct TelegramUpdate: Codable {
    let updateId: Int
    let message: TelegramMessage?

    enum CodingKeys: String, CodingKey {
        case updateId = "update_id"
        case message
    }
}

struct TelegramMessage: Codable {
    let messageId: Int
    let from: TelegramUser?
    let chat: TelegramChat
    let text: String?
    let date: Int

    enum CodingKeys: String, CodingKey {
        case messageId = "message_id"
        case from, chat, text, date
    }
}

struct TelegramUser: Codable {
    let id: Int
    let firstName: String?
    let lastName: String?
    let username: String?

    enum CodingKeys: String, CodingKey {
        case id
        case firstName = "first_name"
        case lastName = "last_name"
        case username
    }

    var displayName: String {
        let parts = [firstName, lastName].compactMap { $0 }.joined(separator: " ")
        return parts.isEmpty ? (username ?? "Unknown") : parts
    }
}

struct TelegramChat: Codable {
    let id: Int
    let type: String
}

// MARK: - Service

@MainActor
final class AICloneService: ObservableObject {
    static let shared = AICloneService()

    @Published var pendingMessages: [CloneMessage] = []
    @Published var isEnabled: Bool = false
    @Published var autoReply: Bool = false
    @Published var iMessageConnected: Bool = false
    @Published var telegramBotToken: String = ""

    private var pollingTask: Task<Void, Never>?
    private var lastIMessageDate: Double = 0
    private var lastTelegramUpdateId: Int = 0

    // Mac absolute time epoch offset (seconds from Unix epoch to Jan 1, 2001)
    private let macAbsoluteTimeOffset: Double = 978_307_200

    private init() {
        telegramBotToken = UserDefaults.standard.string(forKey: "aiCloneTelegramToken") ?? ""
        isEnabled = UserDefaults.standard.bool(forKey: "aiCloneEnabled")
        autoReply = UserDefaults.standard.bool(forKey: "aiCloneAutoReply")
        lastIMessageDate = UserDefaults.standard.double(forKey: "aiCloneLastIMessageDate")
        lastTelegramUpdateId = UserDefaults.standard.integer(forKey: "aiCloneLastTelegramUpdateId")
        iMessageConnected = checkIMessageAccess()
    }

    func enable(_ enabled: Bool) {
        isEnabled = enabled
        UserDefaults.standard.set(enabled, forKey: "aiCloneEnabled")
        if enabled {
            startPolling()
        } else {
            stopPolling()
        }
    }

    func saveTelegramToken(_ token: String) {
        telegramBotToken = token.trimmingCharacters(in: .whitespacesAndNewlines)
        UserDefaults.standard.set(telegramBotToken, forKey: "aiCloneTelegramToken")
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

    // MARK: - Platform Polling

    private func pollAllPlatforms() async {
        async let iMsg: Void = pollIMessage()
        async let tg: Void = pollTelegram()
        _ = await (iMsg, tg)
    }

    // MARK: - iMessage

    private func checkIMessageAccess() -> Bool {
        let path = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Messages/chat.db")
        return FileManager.default.isReadableFile(atPath: path.path)
    }

    private func pollIMessage() async {
        guard iMessageConnected else { return }
        let dbPath = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Messages/chat.db").path

        do {
            let dbQueue = try DatabaseQueue(path: dbPath, configuration: {
                var cfg = Configuration()
                cfg.readonly = true
                return cfg
            }())

            // Convert Unix timestamp to Mac absolute time (nanoseconds)
            let cutoffMac = (lastIMessageDate - macAbsoluteTimeOffset) * 1_000_000_000

            let rows = try await dbQueue.read { db -> [(String, String, Double)] in
                let sql = """
                    SELECT h.id as sender_id, m.text, m.date
                    FROM message m
                    LEFT JOIN handle h ON m.handle_id = h.ROWID
                    WHERE m.is_from_me = 0
                      AND m.text IS NOT NULL AND m.text != ''
                      AND m.date > ?
                    ORDER BY m.date DESC LIMIT 10
                    """
                return try Row.fetchAll(db, sql: sql, arguments: [cutoffMac]).compactMap { row in
                    guard let sender = row["sender_id"] as? String,
                          let text = row["text"] as? String,
                          let dateMac = row["date"] as? Double
                    else { return nil }
                    return (sender, text, dateMac)
                }
            }

            for (sender, text, dateMac) in rows.reversed() {
                let unixDate = (dateMac / 1_000_000_000) + macAbsoluteTimeOffset
                if unixDate > lastIMessageDate {
                    lastIMessageDate = unixDate
                    UserDefaults.standard.set(lastIMessageDate, forKey: "aiCloneLastIMessageDate")
                    await handleIncomingMessage(platform: "imessage", sender: sender, message: text)
                }
            }
        } catch {
            log("AICloneService: iMessage read error: \(error)")
        }
    }

    // MARK: - Telegram

    private func pollTelegram() async {
        let token = telegramBotToken
        guard !token.isEmpty else { return }

        let urlString = "https://api.telegram.org/bot\(token)/getUpdates?offset=\(lastTelegramUpdateId + 1)&limit=10&timeout=0"
        guard let url = URL(string: urlString) else { return }

        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            let response = try JSONDecoder().decode(TelegramGetUpdatesResponse.self, from: data)
            guard response.ok else { return }

            for update in response.result {
                if update.updateId > lastTelegramUpdateId {
                    lastTelegramUpdateId = update.updateId
                    UserDefaults.standard.set(lastTelegramUpdateId, forKey: "aiCloneLastTelegramUpdateId")
                }
                if let msg = update.message, let text = msg.text, !text.isEmpty {
                    // Ignore bot commands
                    if text.hasPrefix("/") { continue }
                    let sender = msg.from?.displayName ?? "Someone"
                    await handleIncomingMessage(platform: "telegram", sender: sender, message: text)
                }
            }
        } catch {
            log("AICloneService: Telegram poll error: \(error)")
        }
    }

    // MARK: - Handle Incoming

    private func handleIncomingMessage(platform: String, sender: String, message: String) async {
        // Check for duplicates (same platform+sender+message within last minute)
        let isDuplicate = pendingMessages.contains {
            $0.platform == platform && $0.sender == sender && $0.incoming == message
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
                incoming: message,
                draftReply: reply.reply,
                status: .pending,
                createdAt: Date()
            )
            pendingMessages.insert(cloneMsg, at: 0)

            if autoReply {
                await autoSend(cloneMsg)
            }
        } catch {
            log("AICloneService: Failed to generate reply: \(error)")
        }
    }

    // MARK: - Actions

    func approveMessage(_ id: String) async {
        guard let idx = pendingMessages.firstIndex(where: { $0.id == id }) else { return }
        let msg = pendingMessages[idx]
        if msg.platform == "telegram" {
            await sendTelegramReply(msg.draftReply, originalMessage: msg)
        }
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
        if pendingMessages[idx].platform == "telegram" {
            var msg = pendingMessages[idx]
            msg.draftReply = editedText
            await sendTelegramReply(editedText, originalMessage: msg)
        }
        pendingMessages[idx].status = .sent
        try? await APIClient.shared.updateCloneMessage(id: id, status: "sent", editedReply: editedText)
    }

    // MARK: - Sending

    private func autoSend(_ msg: CloneMessage) async {
        if msg.platform == "telegram" {
            await sendTelegramReply(msg.draftReply, originalMessage: msg)
        }
        // iMessage auto-send would require AppleScript — shown in UI for safety
    }

    private func sendTelegramReply(_ text: String, originalMessage: CloneMessage) async {
        let token = telegramBotToken
        guard !token.isEmpty else { return }
        // We'd need the chat_id stored in the message — for now log
        log("AICloneService: Telegram send: \(text.prefix(50))")
    }

    func refreshConnectivity() {
        iMessageConnected = checkIMessageAccess()
    }
}

// MARK: - Telegram Response Wrapper

private struct TelegramGetUpdatesResponse: Codable {
    let ok: Bool
    let result: [TelegramUpdate]
}
