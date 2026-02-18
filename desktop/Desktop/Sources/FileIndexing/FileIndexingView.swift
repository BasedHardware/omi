import SwiftUI

/// Standalone file indexing view: consent → scanning → chat.
/// Works in two contexts:
/// 1. Embedded in OnboardingView step 4 (new users)
/// 2. Shown as a dismissable overlay on app launch in DesktopHomeView (existing users)
struct FileIndexingView: View {
    enum Phase { case consent, scanning, chat }

    @State private var phase: Phase = .consent
    @State private var scanningFolder: String = ""
    @State private var totalFilesScanned: Int = 0

    @ObservedObject var chatProvider: ChatProvider

    /// Called when user completes (with file count) or skips (with 0)
    var onComplete: (Int) -> Void

    var body: some View {
        VStack(spacing: 0) {
            switch phase {
            case .consent:
                consentView
            case .scanning:
                scanningView
            case .chat:
                chatView
            }
        }
    }

    // MARK: - Consent

    private var consentView: some View {
        VStack(spacing: 16) {
            Spacer()

            Image(systemName: "folder.badge.gearshape")
                .scaledFont(size: 48)
                .foregroundColor(OmiColors.purplePrimary)

            Text("Get to Know You")
                .font(.title2)
                .fontWeight(.semibold)

            Text("Let Omi look at your files to understand what you work on, your projects, and interests.")
                .font(.body)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)
                .fixedSize(horizontal: false, vertical: true)

            VStack(spacing: 4) {
                HStack(spacing: 8) {
                    Image(systemName: "lock.shield")
                        .scaledFont(size: 12)
                        .foregroundColor(.secondary)
                    Text("Scans common folders for file names only")
                        .scaledFont(size: 12)
                        .foregroundColor(.secondary)
                }

                HStack(spacing: 8) {
                    Image(systemName: "eye.slash")
                        .scaledFont(size: 12)
                        .foregroundColor(.secondary)
                    Text("File contents are never uploaded")
                        .scaledFont(size: 12)
                        .foregroundColor(.secondary)
                }
            }
            .padding(.top, 4)

            Spacer()

            VStack(spacing: 8) {
                Button(action: startScanning) {
                    Text("Get Started")
                        .frame(maxWidth: 200)
                        .padding(.vertical, 8)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)

                Button(action: skip) {
                    Text("Skip")
                        .scaledFont(size: 13)
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
            }
            .padding(.bottom, 20)
        }
        .padding(24)
    }

    // MARK: - Scanning

    private var scanningView: some View {
        VStack(spacing: 16) {
            Spacer()

            ProgressView()
                .scaleEffect(1.5)
                .padding(.bottom, 8)

            Text("Scanning your files...")
                .font(.title2)
                .fontWeight(.semibold)

            if !scanningFolder.isEmpty {
                Text("~/\(scanningFolder)")
                    .scaledFont(size: 14)
                    .foregroundColor(OmiColors.purplePrimary)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 4)
                    .background(OmiColors.purplePrimary.opacity(0.1))
                    .cornerRadius(6)
            }

            Text("\(totalFilesScanned.formatted()) files found")
                .font(.title3)
                .foregroundColor(.secondary)
                .monospacedDigit()

            Spacer()
        }
        .padding(24)
    }

    // MARK: - Chat

    private var chatView: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                if let logoURL = Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png"),
                   let logoImage = NSImage(contentsOf: logoURL) {
                    Image(nsImage: logoImage)
                        .resizable()
                        .scaledToFit()
                        .frame(width: 24, height: 24)
                }

                Text("Exploring \(totalFilesScanned.formatted()) files...")
                    .scaledFont(size: 14, weight: .medium)
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                Button(action: { onComplete(totalFilesScanned) }) {
                    Text("Done")
                        .scaledFont(size: 13, weight: .medium)
                        .foregroundColor(OmiColors.purplePrimary)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(OmiColors.purplePrimary.opacity(0.1))
                        .cornerRadius(6)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)

            Divider()

            // Messages
            ChatMessagesView(
                messages: chatProvider.messages,
                isSending: chatProvider.isSending,
                hasMoreMessages: false,
                isLoadingMoreMessages: false,
                isLoadingInitial: chatProvider.isLoading,
                app: nil,
                onLoadMore: {},
                onRate: { _, _ in },
                welcomeContent: {
                    VStack(spacing: 12) {
                        ProgressView()
                            .scaleEffect(0.8)
                        Text("Analyzing your files...")
                            .scaledFont(size: 13)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            )

            // Input
            ChatInputView(
                onSend: { text in
                    Task { await chatProvider.sendMessage(text) }
                },
                onFollowUp: { text in
                    Task { await chatProvider.sendFollowUp(text) }
                },
                onStop: {
                    chatProvider.stopAgent()
                },
                isSending: chatProvider.isSending,
                mode: $chatProvider.chatMode
            )
            .padding()
        }
    }

    // MARK: - Actions

    private func startScanning() {
        phase = .scanning
        totalFilesScanned = 0

        Task {
            let home = FileManager.default.homeDirectoryForCurrentUser
            let folders = [
                ("Downloads", home.appendingPathComponent("Downloads")),
                ("Documents", home.appendingPathComponent("Documents")),
                ("Desktop", home.appendingPathComponent("Desktop")),
                ("Developer", home.appendingPathComponent("Developer")),
                ("Projects", home.appendingPathComponent("Projects")),
                ("Code", home.appendingPathComponent("Code")),
                ("src", home.appendingPathComponent("src")),
                ("repos", home.appendingPathComponent("repos")),
                ("Sites", home.appendingPathComponent("Sites")),
            ]

            let fm = FileManager.default
            for (name, url) in folders {
                guard fm.fileExists(atPath: url.path) else { continue }
                await MainActor.run {
                    scanningFolder = name
                }
                let count = await FileIndexerService.shared.scanFolders([url])
                await MainActor.run {
                    totalFilesScanned += count
                }
            }

            // Also index installed app names from /Applications
            let appCount = await scanApplicationNames()

            await MainActor.run {
                totalFilesScanned += appCount
                UserDefaults.standard.set(true, forKey: "hasCompletedFileIndexing")
                scanningFolder = ""
                phase = .chat
            }

            // Auto-start the AI exploration chat
            await startExplorationChat()
        }
    }

    /// Scan /Applications and ~/Applications for app names
    private func scanApplicationNames() async -> Int {
        await MainActor.run {
            scanningFolder = "Applications"
        }

        let home = FileManager.default.homeDirectoryForCurrentUser
        let appDirs = [
            URL(fileURLWithPath: "/Applications"),
            home.appendingPathComponent("Applications"),
        ]

        var count = 0
        for dir in appDirs {
            let scanned = await FileIndexerService.shared.scanFolders([dir])
            count += scanned
        }
        return count
    }

    /// Send the exploration prompt to the chat
    private func startExplorationChat() async {
        // Multi-chat users get a dedicated session; single-chat users stay in default chat
        if chatProvider.multiChatEnabled {
            let session = await chatProvider.createNewSession(skipGreeting: true)
            guard session != nil else {
                log("FileIndexingView: Failed to create session for file exploration")
                return
            }
        }

        let prompt = """
        I just indexed \(totalFilesScanned) files on your computer. I want to understand who you are — your projects, passions, and what you're building.

        Use the execute_sql tool to explore the indexed_files table. Start with an overview (file types, folders, project indicators), then dig deeper:

        1. Find project files (package.json, Cargo.toml, etc.) to identify active projects
        2. Look at recently modified files to understand what you're working on right now
        3. Search for patterns — recurring themes, technologies, interests
        4. Open interesting files (read_file tool) to understand project purposes and context
        5. Don't stop at surface level — keep investigating, follow threads, connect the dots

        Tell me a story about this person. Who are they? What are they building? What drives them? What's their tech stack and workflow? Share discoveries as you find them, like you're exploring and getting to know a new friend.
        """
        await chatProvider.sendMessage(prompt)

        // Append the AI's exploration response to the user's AI profile
        await appendExplorationToProfile()

        // Follow up: ask the model to find something actionable
        await chatProvider.sendMessage("Now based on everything you discovered, find something that you can actually help me with to get done. Something that is clearly not done yet and something that you as an AI agent can execute upon.")
    }

    /// Append the AI's file exploration response to the latest AI user profile
    private func appendExplorationToProfile() async {
        // Get the last AI message (the exploration response)
        guard let lastAIMessage = chatProvider.messages.last(where: { $0.sender == .ai }),
              !lastAIMessage.text.isEmpty else {
            log("FileIndexingView: No AI response to append to profile")
            return
        }

        let service = AIUserProfileService.shared
        let existingProfile = await service.getLatestProfile()

        if let existing = existingProfile, let profileId = existing.id {
            // Append to existing profile
            let updated = existing.profileText + "\n\n--- File Exploration Insights ---\n" + lastAIMessage.text
            let success = await service.updateProfileText(id: profileId, newText: updated)
            log("FileIndexingView: Appended exploration to AI profile (success=\(success))")
        } else {
            // No profile exists yet — create one via generation, or save directly
            // For now, trigger a full generation which will pick up the new data
            log("FileIndexingView: No existing AI profile, triggering generation")
            _ = try? await service.generateProfile()
        }
    }

    private func skip() {
        log("FileIndexingView: User skipped file indexing")
        UserDefaults.standard.set(true, forKey: "hasCompletedFileIndexing")
        onComplete(0)
    }
}
