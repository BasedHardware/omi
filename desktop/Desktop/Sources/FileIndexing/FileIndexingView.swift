import SwiftUI
import SceneKit

/// Standalone file indexing view: loading → brainMap.
/// Works in two contexts:
/// 1. Embedded in OnboardingView step 4 (new users)
/// 2. Shown as a dismissable overlay on app launch in DesktopHomeView (existing users)
struct FileIndexingView: View {
    enum Phase { case loading, brainMap }

    @State private var phase: Phase = .loading
    @State private var scanningFolder: String = ""
    @State private var totalFilesScanned: Int = 0
    @State private var progress: Double = 0.0
    @State private var statusText: String = "Scanning your files..."
    @State private var showInfoPopover: Bool = false
    @State private var chatMessages: [String] = []
    @State private var pipelineStarted = false

    @StateObject private var graphViewModel = MemoryGraphViewModel()

    @ObservedObject var chatProvider: ChatProvider

    /// Tells the parent when brainMap phase is active (for full-bleed layout)
    var isBrainMapPhase: Binding<Bool>? = nil

    /// Called when user completes (with file count) or skips (with 0)
    var onComplete: (Int) -> Void

    var body: some View {
        VStack(spacing: 0) {
            switch phase {
            case .loading:
                loadingView
            case .brainMap:
                brainMapView
            }
        }
        .onAppear {
            if !pipelineStarted {
                pipelineStarted = true
                startLoadingPipeline()
            }
        }
    }

    // MARK: - Loading Phase

    private var loadingView: some View {
        VStack(spacing: 0) {
            Spacer()

            // Animation
            OnboardingLoadingAnimation(progress: progress)
                .padding(.bottom, 20)

            // Title
            Text("Let me access files to learn about you")
                .scaledFont(size: 16, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)
                .multilineTextAlignment(.center)
                .padding(.bottom, 6)

            // Subtitle
            Text("All data is secure and belongs to you. Open-source verified.")
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textTertiary)
                .multilineTextAlignment(.center)

            // Progress bar
            VStack(spacing: 6) {
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        RoundedRectangle(cornerRadius: 3)
                            .fill(OmiColors.backgroundTertiary)
                            .frame(height: 6)

                        RoundedRectangle(cornerRadius: 3)
                            .fill(
                                LinearGradient(
                                    colors: [OmiColors.purplePrimary, OmiColors.purpleSecondary],
                                    startPoint: .leading,
                                    endPoint: .trailing
                                )
                            )
                            .frame(width: max(0, geo.size.width * progress), height: 6)
                            .animation(.easeOut(duration: 0.3), value: progress)
                    }
                }
                .frame(height: 6)

                Text("\(Int(progress * 100))%")
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textTertiary)
                    .monospacedDigit()
            }
            .padding(.horizontal, 40)
            .padding(.top, 20)

            // Skip
            Button(action: skip) {
                Text("Skip")
                    .scaledFont(size: 13)
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
            .padding(.top, 16)

            Spacer()
        }
    }

    // MARK: - Info Popover

    private var infoPopoverContent: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Behind the scenes")
                    .scaledFont(size: 13, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)
                Spacer()
            }

            if !scanningFolder.isEmpty {
                HStack(spacing: 6) {
                    Image(systemName: "folder")
                        .scaledFont(size: 10)
                        .foregroundColor(OmiColors.purplePrimary)
                    Text("Scanning ~/\(scanningFolder)")
                        .scaledFont(size: 11)
                        .foregroundColor(OmiColors.textSecondary)
                }
            }

            if totalFilesScanned > 0 {
                Text("\(totalFilesScanned.formatted()) files indexed")
                    .scaledFont(size: 11)
                    .foregroundColor(OmiColors.textTertiary)
            }

            // Live chat messages from the AI exploration
            let aiMessages = chatProvider.messages.filter { $0.sender == .ai }
            if !aiMessages.isEmpty {
                Divider()

                ScrollView {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(Array(aiMessages.enumerated()), id: \.offset) { _, msg in
                            Text(msg.text)
                                .scaledFont(size: 11)
                                .foregroundColor(OmiColors.textSecondary)
                                .lineSpacing(3)
                                .textSelection(.enabled)
                        }
                    }
                }
                .frame(maxHeight: 300)
            }
        }
        .padding(14)
        .frame(width: 340)
    }

    // MARK: - Brain Map Phase

    private var brainMapView: some View {
        ZStack {
            if graphViewModel.isEmpty {
                // Empty fallback
                VStack(spacing: 12) {
                    Image(systemName: "brain")
                        .scaledFont(size: 40)
                        .foregroundColor(.white.opacity(0.15))
                    Text("Your knowledge graph will grow as Omi learns more about you")
                        .scaledFont(size: 13)
                        .foregroundColor(.white.opacity(0.4))
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 40)
                }
            } else {
                // 3D graph — SceneKit renders its own black background
                MemoryGraphSceneView(viewModel: graphViewModel)
            }

            // Floating title + continue button
            VStack {
                Text("Here's what I know about you")
                    .font(.system(size: 22, weight: .bold))
                    .foregroundColor(.white)
                    .shadow(color: .black.opacity(0.7), radius: 12, x: 0, y: 2)
                    .shadow(color: .black.opacity(0.4), radius: 24, x: 0, y: 4)
                    .padding(.top, 40)

                Spacer()

                Button(action: { onComplete(totalFilesScanned) }) {
                    Text("Continue")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(.white)
                        .frame(maxWidth: 220)
                        .padding(.vertical, 12)
                        .background(OmiColors.purplePrimary)
                        .cornerRadius(12)
                        .shadow(color: OmiColors.purplePrimary.opacity(0.4), radius: 16, x: 0, y: 4)
                }
                .buttonStyle(.plain)
                .padding(.bottom, 40)
            }
        }
    }

    // MARK: - Pipeline

    private func startLoadingPipeline() {
        totalFilesScanned = 0
        progress = 0.0

        // Set flag immediately so DesktopHomeView won't spawn a duplicate sheet
        // when onboarding completes mid-pipeline
        UserDefaults.standard.set(true, forKey: "hasCompletedFileIndexing")

        Task {
            // Stage 1: File Scanning (0% → 60%)
            await runFileScanning()

            // Stage 2: AI Exploration (60% → 90%)
            await runAIExploration()

            // Stage 3: Knowledge Graph Build (90% → 100%)
            await runKnowledgeGraphBuild()

            // Transition to brain map
            await MainActor.run {
                withAnimation(.easeInOut(duration: 0.5)) {
                    phase = .brainMap
                    isBrainMapPhase?.wrappedValue = true
                }
            }
        }
    }

    /// Stage 1: Scan folders, progress 0% → 60%
    private func runFileScanning() async {
        await MainActor.run {
            statusText = "Scanning your files..."
        }

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
        let existingFolders = folders.filter { fm.fileExists(atPath: $0.1.path) }
        let folderCount = existingFolders.count + 1 // +1 for Applications
        var completedFolders = 0

        for (name, url) in existingFolders {
            await MainActor.run {
                scanningFolder = name
            }
            let count = await FileIndexerService.shared.scanFolders([url])
            completedFolders += 1
            await MainActor.run {
                totalFilesScanned += count
                progress = Double(completedFolders) / Double(folderCount) * 0.6
            }
        }

        // Also index installed app names from /Applications
        let appCount = await scanApplicationNames()
        await MainActor.run {
            totalFilesScanned += appCount
            progress = 0.6
            scanningFolder = ""
        }
    }

    /// Stage 2: AI exploration chat in background, progress 60% → 90%
    private func runAIExploration() async {
        await MainActor.run {
            statusText = "Analyzing your files..."
        }

        // Start progress animation (ease-out curve over ~30s)
        let progressTask = Task {
            let startTime = Date()
            let duration: Double = 30.0
            while !Task.isCancelled {
                let elapsed = Date().timeIntervalSince(startTime)
                let t = min(elapsed / duration, 1.0)
                // Ease-out: fast at start, slow at end
                let eased = 1.0 - pow(1.0 - t, 3.0)
                let newProgress = 0.6 + eased * 0.3 // 60% → 90%
                await MainActor.run {
                    progress = min(newProgress, 0.89) // Cap at 89% until AI finishes
                }
                try? await Task.sleep(nanoseconds: 200_000_000) // 200ms
            }
        }

        // Run AI exploration in background — don't wait for it to complete
        Task { await startExplorationChat() }

        // Just wait a fixed time for the exploration to make progress, then move on
        try? await Task.sleep(nanoseconds: 45_000_000_000) // 45s
        log("FileIndexingView: AI exploration timeout reached, moving to knowledge graph build")

        // Cancel progress animation and jump to 90%
        progressTask.cancel()
        await MainActor.run {
            progress = 0.9
        }
    }

    /// Stage 3: Load knowledge graph (or build from scratch if none exists), progress 90% → 100%
    private func runKnowledgeGraphBuild() async {
        await MainActor.run {
            statusText = "Loading your knowledge graph..."
            progress = 0.92
        }

        // First, try loading the existing graph (user may already have one from mobile)
        await graphViewModel.loadGraph()
        log("FileIndexingView: Existing graph check — isEmpty=\(graphViewModel.isEmpty)")

        if !graphViewModel.isEmpty {
            // User already has a graph (e.g. from mobile app) — use it directly
            log("FileIndexingView: Using existing knowledge graph")
            await MainActor.run {
                progress = 1.0
                statusText = "Done!"
            }
            try? await Task.sleep(nanoseconds: 500_000_000)
            return
        }

        // No existing graph — build from scratch
        await MainActor.run {
            statusText = "Building your knowledge graph..."
            progress = 0.95
        }

        // Fire-and-forget the rebuild with a short timeout — the endpoint can hang
        Task {
            do {
                _ = try await withThrowingTaskGroup(of: Void.self) { group in
                    group.addTask {
                        _ = try await APIClient.shared.rebuildKnowledgeGraph()
                    }
                    group.addTask {
                        try await Task.sleep(nanoseconds: 10_000_000_000) // 10s timeout
                        throw CancellationError()
                    }
                    try await group.next()
                    group.cancelAll()
                }
                log("FileIndexingView: Knowledge graph rebuild completed")
            } catch {
                log("FileIndexingView: Knowledge graph rebuild timed out or failed: \(error.localizedDescription)")
            }
        }

        // Poll until graph has data
        let maxAttempts = 15 // 15 × 3s = 45s max
        for attempt in 1...maxAttempts {
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            await graphViewModel.loadGraph()

            if !graphViewModel.isEmpty {
                log("FileIndexingView: Graph ready after \(attempt) polls")
                break
            }
            log("FileIndexingView: Graph poll \(attempt)/\(maxAttempts), still empty")
        }

        await MainActor.run {
            progress = 1.0
            statusText = "Done!"
        }

        // Brief pause to show 100%
        try? await Task.sleep(nanoseconds: 500_000_000)
    }

    // MARK: - Helpers

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

        // Track chat messages for info popover
        await MainActor.run {
            chatMessages = chatProvider.messages
                .filter { $0.sender == .ai }
                .map { String($0.text.prefix(200)) }
        }

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
