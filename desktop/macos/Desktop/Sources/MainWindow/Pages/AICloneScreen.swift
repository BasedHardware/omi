import AppKit
import Foundation
import SwiftUI
import OmiTheme

/// One pending on-behalf reply drafted by the AI clone, awaiting the user's review.
struct CloneReviewItem: Identifiable {
    let id = UUID()
    let lineIndex: Int
    let rawLine: String
    let chatId: String
    let contactName: String
    let network: String
    let incoming: String
    let draft: String
    let alternatives: [String]
    let action: String
    let actionReason: String
    let confidence: Double
    let safetyNotes: [String]
}

/// Reads/writes the local review queue that `backend/scripts/beeper_clone_bridge.py`
/// appends to (~/.omi/clone_review_queue.jsonl), and sends approved replies back
/// through the Beeper CLI. Everything stays on-device.
@MainActor
final class CloneReviewStore: ObservableObject {
    @Published var items: [CloneReviewItem] = []
    @Published var statusMessage: String?

    static let queueURL: URL = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent(".omi/clone_review_queue.jsonl")

    private func fileLines() -> [String] {
        guard let content = try? String(contentsOf: Self.queueURL, encoding: .utf8) else { return [] }
        return content.split(separator: "\n", omittingEmptySubsequences: true).map(String.init)
    }

    func reload() {
        var result: [CloneReviewItem] = []
        for (index, line) in fileLines().enumerated() {
            guard let data = line.data(using: .utf8),
                let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            else { continue }
            let reply = obj["reply"] as? [String: Any] ?? [:]
            result.append(
                CloneReviewItem(
                    lineIndex: index,
                    rawLine: line,
                    chatId: obj["chat_id"] as? String ?? "",
                    contactName: reply["contact_name"] as? String ?? (obj["contact_name"] as? String ?? "Contact"),
                    network: reply["network"] as? String ?? (obj["network"] as? String ?? ""),
                    incoming: obj["incoming"] as? String ?? "",
                    draft: reply["draft"] as? String ?? "",
                    alternatives: reply["alternatives"] as? [String] ?? [],
                    action: reply["action"] as? String ?? "review",
                    actionReason: reply["action_reason"] as? String ?? "",
                    confidence: reply["confidence"] as? Double ?? 0,
                    safetyNotes: reply["safety_notes"] as? [String] ?? []
                ))
        }
        items = result
    }

    func discard(_ item: CloneReviewItem) {
        // Remove by line content, not by the stored index: the bridge may have
        // appended new drafts since this item was loaded, so an index would be stale
        // and could drop the wrong draft. Re-reading keeps those concurrent appends.
        var lines = fileLines()
        if let idx = lines.firstIndex(of: item.rawLine) {
            lines.remove(at: idx)
        } else if item.lineIndex < lines.count {
            lines.remove(at: item.lineIndex)
        }
        let joined = lines.isEmpty ? "" : lines.joined(separator: "\n") + "\n"
        try? joined.write(to: Self.queueURL, atomically: true, encoding: .utf8)
        reload()
    }

    func send(_ item: CloneReviewItem, text: String) {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        process.arguments = ["beeper", "send", "text", "--to", item.chatId, "--message", trimmed]
        do {
            try process.run()
            process.waitUntilExit()
            if process.terminationStatus == 0 {
                statusMessage = "Sent to \(item.contactName)."
                discard(item)
            } else {
                statusMessage = "Beeper send failed (exit \(process.terminationStatus)). Is Beeper Desktop running?"
            }
        } catch {
            statusMessage = "Could not run the Beeper CLI. Install it from developers.beeper.com."
        }
    }
}

/// The desktop AI Clone screen: a review inbox of replies the clone drafted for
/// your chat apps (via Beeper), plus your persona voice editor.
struct AICloneScreen: View {
    enum CloneMode: String, CaseIterable, Identifiable {
        case inbox
        case test
        var id: String { rawValue }
        var title: String {
            switch self {
            case .inbox: return "Drafts inbox"
            case .test: return "Test your clone"
            }
        }
    }

    @StateObject private var store = CloneReviewStore()
    @State private var showingPersona = false
    @State private var edited: [UUID: String] = [:]
    @State private var mode: CloneMode = .inbox
    @State private var copiedBridgeCommand = false

    private let bridgeCommand = "python backend/scripts/beeper_clone_bridge.py"

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            modePicker
            Divider()
            switch mode {
            case .inbox:
                inboxContent
            case .test:
                CloneTestView()
            }
        }
        .onAppear { store.reload() }
        .sheet(isPresented: $showingPersona) {
            PersonaPage(onDismiss: { showingPersona = false })
                .frame(minWidth: 540, minHeight: 620)
        }
    }

    private var modePicker: some View {
        Picker("", selection: $mode) {
            ForEach(CloneMode.allCases) { option in
                Text(option.title).tag(option)
            }
        }
        .pickerStyle(.segmented)
        .labelsHidden()
        .padding(.horizontal)
        .padding(.bottom, 10)
    }

    @ViewBuilder
    private var inboxContent: some View {
        if let status = store.statusMessage {
            Text(status)
                .font(.callout)
                .foregroundStyle(OmiColors.textTertiary)
                .padding(.horizontal)
                .padding(.top, 8)
        }
        if store.items.isEmpty {
            emptyState
        } else {
            ScrollView {
                LazyVStack(spacing: 14) {
                    ForEach(store.items) { item in
                        draftCard(item)
                    }
                }
                .padding()
            }
        }
    }

    private var header: some View {
        HStack(alignment: .center) {
            VStack(alignment: .leading, spacing: 2) {
                Text("AI Clone")
                    .font(.title2).bold()
                Text("Review replies your clone drafted for WhatsApp, Telegram, iMessage and more.")
                    .font(.callout)
                    .foregroundStyle(OmiColors.textTertiary)
            }
            Spacer()
            Button {
                showingPersona = true
            } label: {
                Label("Set up my voice", systemImage: "person.crop.circle.badge.checkmark")
            }
            .buttonStyle(.bordered)
            Button {
                store.reload()
            } label: {
                Label("Refresh", systemImage: "arrow.clockwise")
            }
            .buttonStyle(.bordered)
        }
        .padding()
    }

    private var emptyState: some View {
        ScrollView {
            VStack(spacing: 16) {
                VStack(spacing: 8) {
                    Image(systemName: "tray")
                        .font(.system(size: 36))
                        .foregroundStyle(OmiColors.textTertiary)
                    Text("No replies waiting for review")
                        .font(.headline)
                    Text(
                        "Connect your chats with Beeper and run the clone bridge; incoming messages appear here with a suggested reply in your voice, ready to send with one tap."
                    )
                    .font(.callout)
                    .foregroundStyle(OmiColors.textTertiary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 460)
                }
                .padding(.top, 24)

                beeperConnectCard
            }
            .frame(maxWidth: .infinity)
            .padding()
        }
    }

    /// Actionable "connect your chats" card: Beeper unifies WhatsApp, Telegram,
    /// iMessage, and more behind one local API, so the clone reads and replies
    /// across every network with no per-app integration.
    private var beeperConnectCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Connect your chats", systemImage: "link")
                .font(.headline)
            connectStep(
                number: 1,
                title: "Install Beeper Desktop",
                detail: "One inbox for WhatsApp, Telegram, iMessage, Signal, and more.")
            connectStep(
                number: 2,
                title: "Enable the local API",
                detail: "In Beeper: Settings, Desktop API. The clone talks to it on your machine only.")
            connectStep(
                number: 3,
                title: "Run the clone bridge",
                detail: "Drafts land here for review; nothing sends without your tap.")

            HStack(spacing: 8) {
                Text(bridgeCommand)
                    .font(.system(.caption, design: .monospaced))
                    .textSelection(.enabled)
                    .padding(6)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(OmiColors.backgroundTertiary, in: RoundedRectangle(cornerRadius: 6))
                Button {
                    copyBridgeCommand()
                } label: {
                    Label(
                        copiedBridgeCommand ? "Copied" : "Copy",
                        systemImage: copiedBridgeCommand ? "checkmark" : "doc.on.doc")
                }
                .buttonStyle(.bordered)
            }

            HStack(spacing: 8) {
                Button {
                    if let url = URL(string: "https://www.beeper.com/download") {
                        NSWorkspace.shared.open(url)
                    }
                } label: {
                    Label("Get Beeper Desktop", systemImage: "arrow.down.circle")
                }
                .buttonStyle(.borderedProminent)
                .tint(.primary)
                Button {
                    if let url = URL(string: "https://developers.beeper.com") {
                        NSWorkspace.shared.open(url)
                    }
                } label: {
                    Label("API docs", systemImage: "book")
                }
                .buttonStyle(.bordered)
            }
        }
        .padding()
        .frame(maxWidth: 560)
        .background(OmiColors.backgroundRaised, in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(OmiColors.border))
    }

    private func connectStep(number: Int, title: String, detail: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Text("\(number)")
                .font(.caption).bold()
                .foregroundStyle(OmiColors.textSecondary)
                .frame(width: 20, height: 20)
                .background(OmiColors.backgroundTertiary, in: Circle())
            VStack(alignment: .leading, spacing: 1) {
                Text(title).font(.callout).bold()
                Text(detail).font(.caption).foregroundStyle(OmiColors.textTertiary)
            }
            Spacer()
        }
    }

    private func copyBridgeCommand() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(bridgeCommand, forType: .string)
        copiedBridgeCommand = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            copiedBridgeCommand = false
        }
    }

    private func draftCard(_ item: CloneReviewItem) -> some View {
        let binding = Binding<String>(
            get: { edited[item.id] ?? item.draft },
            set: { edited[item.id] = $0 }
        )
        return VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(item.contactName).font(.headline)
                if !item.network.isEmpty {
                    Text(item.network)
                        .font(.caption)
                        .foregroundStyle(OmiColors.textTertiary)
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(OmiColors.border, in: Capsule())
                }
                if item.action == "hold" {
                    Label("Held: review carefully", systemImage: "hand.raised.fill")
                        .font(.caption)
                        .foregroundStyle(OmiColors.textSecondary)
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(OmiColors.border, in: Capsule())
                }
                Spacer()
                Text("confidence \(Int(item.confidence * 100))%")
                    .font(.caption)
                    .foregroundStyle(OmiColors.textTertiary)
            }

            Text(item.incoming)
                .font(.callout)
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(OmiColors.backgroundTertiary, in: RoundedRectangle(cornerRadius: 8))

            Text("Suggested reply (edit before sending):")
                .font(.caption)
                .foregroundStyle(OmiColors.textTertiary)
            TextEditor(text: binding)
                .font(.body)
                .frame(minHeight: 60)
                .padding(6)
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(OmiColors.border))

            if !item.actionReason.isEmpty {
                Label(item.actionReason, systemImage: "shield.lefthalf.filled")
                    .font(.caption)
                    .foregroundStyle(OmiColors.textTertiary)
            }
            ForEach(item.safetyNotes, id: \.self) { note in
                Label(note, systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(OmiColors.textTertiary)
            }

            HStack {
                Spacer()
                Button(role: .cancel) {
                    edited[item.id] = nil
                    store.discard(item)
                } label: {
                    Label("Ignore", systemImage: "xmark")
                }
                .buttonStyle(.bordered)
                Button {
                    store.send(item, text: edited[item.id] ?? item.draft)
                    edited[item.id] = nil
                } label: {
                    Label("Send", systemImage: "paperplane.fill")
                }
                .buttonStyle(.borderedProminent)
                .tint(.primary)
            }
        }
        .padding()
        .background(OmiColors.backgroundRaised, in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(OmiColors.border))
    }
}
