import SwiftUI

/// Full detail view for a single conversation
struct ConversationDetailView: View {
    let conversation: ServerConversation
    let onBack: () -> Void
    var folders: [Folder] = []
    var onMoveToFolder: ((String, String?) async -> Void)?
    var onDelete: (() -> Void)?
    var onTitleUpdated: ((String) -> Void)?

    // People (speaker naming)
    var people: [Person] = []
    var onFetchPeople: (() async -> Void)?
    var onCreatePerson: ((String) async -> Person?)?
    var onAssignSpeaker: ((String, [Int], String?, Bool) async -> Bool)?

    @StateObject private var appProvider = AppProvider()
    @State private var showAppSelector = false
    @State private var isReprocessing = false
    @State private var selectedAppForReprocess: OmiApp?

    // Transcript drawer state (replaces tab system)
    @State private var showTranscriptDrawer = false

    // Entry animation
    @State private var hasAppeared = false

    // Full conversation loaded from API (with transcript segments)
    @State private var loadedConversation: ServerConversation?
    @State private var isLoadingConversation = false

    // Action states
    @State private var showDeleteConfirmation = false
    @State private var showEditDialog = false
    @State private var editedTitle = ""
    @State private var isUpdatingTitle = false
    @State private var isCopyingLink = false
    @State private var isDeleting = false

    // Speaker naming state
    @State private var showNameSpeakerSheet = false
    @State private var selectedSegmentForNaming: TranscriptSegment? = nil

    /// The conversation to display - use loaded version if available, otherwise use prop
    private var displayConversation: ServerConversation {
        loadedConversation ?? conversation
    }

    /// The date to display (prefer startedAt, fall back to createdAt)
    private var displayDate: Date {
        displayConversation.startedAt ?? displayConversation.createdAt
    }

    // Static date formatters — creating DateFormatter is expensive, avoid per-render allocation
    private static let dayDateFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "EEEE, MMM d, yyyy"
        return f
    }()
    private static let timeOnlyFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "h:mm a"
        return f
    }()
    private static let shortDateFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "MMM d, yyyy"
        return f
    }()

    /// Format date for display
    private var formattedDate: String {
        Self.dayDateFormatter.string(from: displayDate)
    }

    /// Format time for display
    private var formattedTime: String {
        Self.timeOnlyFormatter.string(from: displayDate)
    }

    /// Format time range for header subtitle (e.g., "Jan 15, 2025 from 2:30 PM to 3:15 PM")
    private var formattedTimeRange: String {
        let dateStr = Self.shortDateFormatter.string(from: displayDate)
        let startStr = Self.timeOnlyFormatter.string(from: displayDate)

        if let finishedAt = displayConversation.finishedAt {
            let endStr = Self.timeOnlyFormatter.string(from: finishedAt)
            return "\(dateStr) from \(startStr) to \(endStr)"
        }
        return "\(dateStr) at \(startStr)"
    }

    var body: some View {
        HStack(spacing: 0) {
            // Main content (always visible)
            VStack(alignment: .leading, spacing: 0) {
                headerView

                ScrollView {
                    // Card container wrapping summary content
                    VStack(alignment: .leading, spacing: 0) {
                        // Card header bar
                        HStack(spacing: 8) {
                            Image(systemName: "doc.text")
                                .scaledFont(size: 12)
                                .foregroundColor(OmiColors.textTertiary)
                            Text("Conversation Details")
                                .scaledFont(size: 13, weight: .medium)
                                .foregroundColor(OmiColors.textSecondary)
                            Spacer()
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 10)
                        .background(OmiColors.backgroundTertiary.opacity(0.4))

                        VStack(alignment: .leading, spacing: 24) {
                            summaryContent
                        }
                        .padding(24)
                    }
                    .background(
                        RoundedRectangle(cornerRadius: 16)
                            .fill(OmiColors.backgroundSecondary.opacity(0.6))
                    )
                    .clipShape(RoundedRectangle(cornerRadius: 16))
                    .overlay(
                        RoundedRectangle(cornerRadius: 16)
                            .stroke(OmiColors.backgroundTertiary.opacity(0.3), lineWidth: 1)
                    )
                    .shadow(color: Color.black.opacity(0.1), radius: 20, x: 0, y: 8)
                    .padding(24)
                }
            }
            .frame(maxWidth: .infinity)

            // Transcript drawer (slides in from right)
            if showTranscriptDrawer {
                Rectangle()
                    .fill(OmiColors.border)
                    .frame(width: 1)

                transcriptDrawerView
                    .frame(width: 450)
                    .transition(.move(edge: .trailing))
            }
        }
        .opacity(hasAppeared ? 1 : 0)
        .offset(y: hasAppeared ? 0 : 20)
        .onAppear {
            withAnimation(.easeOut(duration: 0.5)) {
                hasAppeared = true
            }
        }
        .task {
            await appProvider.fetchApps()
            await onFetchPeople?()
            AnalyticsManager.shared.conversationDetailOpened(conversationId: conversation.id)

            // Load segments from local database if not already present
            // Segments are stored locally but not loaded with the list view for performance
            if conversation.transcriptSegments.isEmpty {
                isLoadingConversation = true
                do {
                    // First try local database (faster, works offline)
                    if let session = try await TranscriptionStorage.shared.getSessionByBackendId(conversation.id) {
                        let segmentRecords = try await TranscriptionStorage.shared.getSegments(sessionId: session.id!)
                        if !segmentRecords.isEmpty {
                            // Convert local records to TranscriptSegments and update conversation
                            let segments = segmentRecords.map { $0.toTranscriptSegment() }
                            var updatedConversation = conversation
                            updatedConversation.transcriptSegments = segments
                            loadedConversation = updatedConversation
                            log("ConversationDetail: Loaded \(segments.count) segments from local database")
                        } else {
                            // No local segments, fetch from API
                            let fullConversation = try await APIClient.shared.getConversation(id: conversation.id)
                            loadedConversation = fullConversation
                            log("ConversationDetail: Loaded \(fullConversation.transcriptSegments.count) segments from API")
                        }
                    } else {
                        // No local session found, fetch from API
                        let fullConversation = try await APIClient.shared.getConversation(id: conversation.id)
                        loadedConversation = fullConversation
                        log("ConversationDetail: Loaded \(fullConversation.transcriptSegments.count) segments from API (no local session)")
                    }
                } catch {
                    logError("ConversationDetail: Failed to load conversation segments", error: error)
                }
                isLoadingConversation = false
            }
        }
        .dismissableSheet(isPresented: $showAppSelector) {
            AppSelectorSheet(
                apps: appProvider.apps.filter { $0.capabilities.contains("memories") },
                isLoading: isReprocessing,
                onSelect: { app in
                    selectedAppForReprocess = app
                    Task {
                        await reprocessWithApp(app)
                    }
                },
                onDismiss: { showAppSelector = false }
            )
            .frame(width: 400, height: 500)
        }
        .dismissableSheet(isPresented: $showNameSpeakerSheet) {
            if let segment = selectedSegmentForNaming {
                NameSpeakerSheet(
                    segment: segment,
                    allSegments: displayConversation.transcriptSegments,
                    people: people,
                    onSave: { personId, isUser, segmentIds in
                        Task {
                            let success = await onAssignSpeaker?(conversation.id, segmentIds, personId, isUser) ?? false
                            if success {
                                // Update local segments with the new personId/isUser
                                var updated = displayConversation
                                for idx in segmentIds where idx < updated.transcriptSegments.count {
                                    let old = updated.transcriptSegments[idx]
                                    updated.transcriptSegments[idx] = TranscriptSegment(
                                        id: old.id,
                                        text: old.text,
                                        speaker: old.speaker,
                                        isUser: isUser ? true : old.isUser,
                                        personId: personId ?? old.personId,
                                        start: old.start,
                                        end: old.end
                                    )
                                }
                                loadedConversation = updated
                            }
                            showNameSpeakerSheet = false
                            selectedSegmentForNaming = nil
                        }
                    },
                    onCreatePerson: { name in
                        await onCreatePerson?(name)
                    },
                    onDismiss: {
                        showNameSpeakerSheet = false
                        selectedSegmentForNaming = nil
                    }
                )
            }
        }
    }

    // MARK: - Header

    private var headerView: some View {
        HStack(spacing: 12) {
            // Back button
            Button(action: onBack) {
                HStack(spacing: 6) {
                    Image(systemName: "chevron.left")
                        .scaledFont(size: 14, weight: .medium)
                    Text("Back")
                        .scaledFont(size: 14, weight: .medium)
                }
                .foregroundColor(OmiColors.purplePrimary)
            }
            .buttonStyle(.plain)

            // Emoji
            Text(displayConversation.structured.emoji.isEmpty ? "\u{1F4AC}" : displayConversation.structured.emoji)
                .scaledFont(size: 28)

            // Title + timestamp subtitle
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 8) {
                    Text(displayConversation.title)
                        .scaledFont(size: 18, weight: .semibold)
                        .foregroundColor(OmiColors.textPrimary)
                        .lineLimit(1)

                    // Edit title button (inline with title)
                    Button(action: {
                        editedTitle = displayConversation.title
                        showEditDialog = true
                    }) {
                        Image(systemName: "pencil")
                            .scaledFont(size: 14)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                    .buttonStyle(.plain)
                    .help("Edit title")
                }

                Text(formattedTimeRange)
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textTertiary)
            }

            Spacer()

            // Status badge
            if displayConversation.status != .completed {
                statusBadge
            }

            // View Transcript pill button
            viewTranscriptButton

            // Inline action buttons
            inlineActionButtons
        }
        .padding(.horizontal, 24)
        .padding(.vertical, 16)
        .background(OmiColors.backgroundTertiary.opacity(0.5))
        .alert("Edit Conversation Title", isPresented: $showEditDialog) {
            TextField("Title", text: $editedTitle)
            Button("Cancel", role: .cancel) { }
            Button("Save") {
                Task { await updateTitle() }
            }
            .disabled(editedTitle.isEmpty || isUpdatingTitle)
        } message: {
            Text("Enter a new title for this conversation")
        }
        .alert("Delete Conversation", isPresented: $showDeleteConfirmation) {
            Button("Cancel", role: .cancel) { }
            Button("Delete", role: .destructive) {
                Task { await deleteConversation() }
            }
        } message: {
            Text("Are you sure you want to delete this conversation? This action cannot be undone.")
        }
    }

    // MARK: - View Transcript Button

    private var viewTranscriptButton: some View {
        Button(action: {
            withAnimation(.easeInOut(duration: 0.25)) {
                showTranscriptDrawer.toggle()
            }
        }) {
            HStack(spacing: 6) {
                Image(systemName: "text.quote")
                    .scaledFont(size: 12)
                Text(showTranscriptDrawer ? "Hide Transcript" : "View Transcript")
                    .scaledFont(size: 12, weight: .medium)
            }
            .foregroundColor(showTranscriptDrawer ? .white : OmiColors.textSecondary)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(
                Capsule()
                    .fill(showTranscriptDrawer ? OmiColors.purplePrimary : OmiColors.backgroundTertiary)
            )
        }
        .buttonStyle(.plain)
    }

    // MARK: - Inline Action Buttons

    private var inlineActionButtons: some View {
        HStack(spacing: 8) {
            // Copy link button
            Button(action: { Task { await copyLink() } }) {
                Image(systemName: isCopyingLink ? "arrow.triangle.2.circlepath" : "link")
                    .scaledFont(size: 14)
                    .foregroundColor(OmiColors.textSecondary)
                    .frame(width: 28, height: 28)
                    .background(
                        Circle()
                            .fill(OmiColors.backgroundTertiary)
                    )
            }
            .buttonStyle(.plain)
            .disabled(isCopyingLink)
            .help("Copy link")

            // Copy transcript button
            Button(action: copyTranscript) {
                Image(systemName: "doc.on.doc")
                    .scaledFont(size: 14)
                    .foregroundColor(OmiColors.textSecondary)
                    .frame(width: 28, height: 28)
                    .background(
                        Circle()
                            .fill(OmiColors.backgroundTertiary)
                    )
            }
            .buttonStyle(.plain)
            .help("Copy transcript")

            // Move to folder button (menu)
            if !folders.isEmpty {
                Menu {
                    if displayConversation.folderId != nil {
                        Button(action: {
                            Task { await onMoveToFolder?(conversation.id, nil) }
                        }) {
                            Label("Remove from Folder", systemImage: "folder.badge.minus")
                        }
                        Divider()
                    }

                    ForEach(folders) { folder in
                        Button(action: {
                            Task { await onMoveToFolder?(conversation.id, folder.id) }
                        }) {
                            HStack {
                                Text(folder.name)
                                if displayConversation.folderId == folder.id {
                                    Image(systemName: "checkmark")
                                }
                            }
                        }
                        .disabled(displayConversation.folderId == folder.id)
                    }
                } label: {
                    Image(systemName: displayConversation.folderId != nil ? "folder.fill" : "folder")
                        .scaledFont(size: 14)
                        .foregroundColor(displayConversation.folderId != nil ? OmiColors.purplePrimary : OmiColors.textSecondary)
                        .frame(width: 28, height: 28)
                        .background(
                            Circle()
                                .fill(OmiColors.backgroundTertiary)
                        )
                }
                .menuStyle(.borderlessButton)
                .frame(width: 28)
                .help("Move to folder")
            }

            // Delete button
            Button(action: { showDeleteConfirmation = true }) {
                Image(systemName: "trash")
                    .scaledFont(size: 14)
                    .foregroundColor(OmiColors.error)
                    .frame(width: 28, height: 28)
                    .background(
                        Circle()
                            .fill(OmiColors.backgroundTertiary)
                    )
            }
            .buttonStyle(.plain)
            .help("Delete conversation")
        }
    }

    // MARK: - Actions

    private func copyTranscript() {
        let peopleDict = Dictionary(uniqueKeysWithValues: people.map { ($0.id, $0) })
        let transcript: String = displayConversation.transcriptSegments.map { segment -> String in
            let speakerName: String
            if segment.isUser {
                speakerName = "You"
            } else if let personId = segment.personId, let person = peopleDict[personId] {
                speakerName = person.name
            } else {
                speakerName = "Speaker \(segment.speaker ?? "Unknown")"
            }
            return "[\(speakerName)]: \(segment.text)"
        }.joined(separator: "\n\n")

        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(transcript, forType: .string)
    }

    private func copyLink() async {
        isCopyingLink = true
        defer { isCopyingLink = false }

        do {
            let shareableUrl = try await APIClient.shared.getConversationShareLink(id: conversation.id)
            await MainActor.run {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(shareableUrl, forType: .string)
            }
        } catch {
            logError("Failed to get share link", error: error)
        }
    }

    private func updateTitle() async {
        guard !editedTitle.isEmpty else { return }
        isUpdatingTitle = true
        defer { isUpdatingTitle = false }

        do {
            try await APIClient.shared.updateConversationTitle(id: conversation.id, title: editedTitle)
            onTitleUpdated?(editedTitle)
        } catch {
            logError("Failed to update title", error: error)
        }
    }

    private func deleteConversation() async {
        isDeleting = true
        defer { isDeleting = false }

        do {
            try await APIClient.shared.deleteConversation(id: conversation.id)
            await MainActor.run {
                onDelete?()
                onBack()
            }
        } catch {
            logError("Failed to delete conversation", error: error)
        }
    }

    private var statusBadge: some View {
        Text(displayConversation.status.rawValue.replacingOccurrences(of: "_", with: " ").capitalized)
            .scaledFont(size: 11, weight: .medium)
            .foregroundColor(statusColor)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(
                Capsule()
                    .fill(statusColor.opacity(0.2))
            )
    }

    private var statusColor: Color {
        switch displayConversation.status {
        case .completed:
            return OmiColors.success
        case .processing, .merging:
            return OmiColors.info
        case .inProgress:
            return OmiColors.warning
        case .failed:
            return OmiColors.error
        }
    }

    // MARK: - Summary Content (always visible, no tabs)

    @ViewBuilder
    private var summaryContent: some View {
        // Overview section
        if !displayConversation.overview.isEmpty {
            overviewSection
        }

        // Metadata chips
        metadataSection

        // App Results section
        if !displayConversation.appsResults.isEmpty {
            appResultsSection
        }

        // Suggested apps section
        suggestedAppsSection

        // Action items section
        if !displayConversation.structured.actionItems.isEmpty {
            actionItemsSection
        }
    }

    // MARK: - Transcript Drawer

    @ViewBuilder
    private var transcriptDrawerView: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Drawer header
            HStack(spacing: 10) {
                Image(systemName: "text.quote")
                    .scaledFont(size: 14)
                    .foregroundColor(OmiColors.textSecondary)

                Text("Transcript")
                    .scaledFont(size: 15, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                // Segment count badge
                Text("\(displayConversation.transcriptSegments.count)")
                    .scaledFont(size: 11, weight: .medium)
                    .foregroundColor(OmiColors.purplePrimary)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 2)
                    .background(
                        Capsule()
                            .fill(OmiColors.purplePrimary.opacity(0.15))
                    )

                Spacer()

                // Copy button
                Button(action: copyTranscript) {
                    Image(systemName: "doc.on.doc")
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textSecondary)
                        .frame(width: 28, height: 28)
                        .background(
                            Circle()
                                .fill(OmiColors.backgroundTertiary)
                        )
                }
                .buttonStyle(.plain)
                .help("Copy transcript")

                // Close button
                Button(action: {
                    withAnimation(.easeInOut(duration: 0.25)) {
                        showTranscriptDrawer = false
                    }
                }) {
                    Image(systemName: "xmark")
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textSecondary)
                        .frame(width: 28, height: 28)
                        .background(
                            Circle()
                                .fill(OmiColors.backgroundTertiary)
                        )
                }
                .buttonStyle(.plain)
                .help("Close transcript")
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 14)
            .background(OmiColors.backgroundTertiary.opacity(0.5))

            // Drawer content
            if displayConversation.transcriptSegments.isEmpty && !isLoadingConversation {
                // Empty state
                VStack(spacing: 12) {
                    Image(systemName: "text.quote")
                        .scaledFont(size: 40)
                        .foregroundColor(OmiColors.textTertiary.opacity(0.5))

                    Text("No transcript available")
                        .scaledFont(size: 14)
                        .foregroundColor(OmiColors.textTertiary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if isLoadingConversation {
                // Loading state
                VStack(spacing: 12) {
                    ProgressView()
                        .scaleEffect(0.8)

                    Text("Loading transcript...")
                        .scaledFont(size: 14)
                        .foregroundColor(OmiColors.textTertiary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                // LazyVStack is a DIRECT child of ScrollView so it gets bounded proposed height
                // and only materializes visible children.
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 12) {
                        transcriptBubblesContent
                    }
                    .padding(16)
                }
            }
        }
        .background(OmiColors.backgroundPrimary)
    }

    // MARK: - Transcript Bubbles (shared)

    /// Flat content intended to be placed inside a parent LazyVStack.
    /// Do NOT wrap this in another LazyVStack or VStack — it emits ForEach items directly.
    @ViewBuilder
    private var transcriptBubblesContent: some View {
        let peopleDict = Dictionary(uniqueKeysWithValues: people.map { ($0.id, $0) })
        ForEach(displayConversation.transcriptSegments) { segment in
            SpeakerBubbleView(
                segment: segment,
                isUser: segment.isUser,
                personName: segment.personId.flatMap { peopleDict[$0]?.name },
                onSpeakerTapped: segment.isUser ? nil : {
                    selectedSegmentForNaming = segment
                    showNameSpeakerSheet = true
                }
            )
            .padding(.horizontal, 16)
        }
    }

    // MARK: - Overview Section

    private var overviewSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "star.fill")
                    .scaledFont(size: 13)
                    .foregroundColor(Color(red: 0.95, green: 0.75, blue: 0.15))

                Text("Summary")
                    .scaledFont(size: 14, weight: .semibold)
                    .foregroundColor(OmiColors.textSecondary)
            }

            SelectableMarkdown(text: displayConversation.overview, sender: .ai)
                .textSelection(.enabled)
                .environment(\.colorScheme, .dark)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    // MARK: - Metadata Section

    private var metadataSection: some View {
        HStack(spacing: 12) {
            // Source chip (device indicator)
            sourceChip

            // Duration chip
            metadataChip(icon: "hourglass", text: displayConversation.formattedDuration)

            // Category chip
            if !displayConversation.structured.category.isEmpty && displayConversation.structured.category != "other" {
                metadataChip(icon: "tag", text: displayConversation.structured.category.capitalized)
            }

            Spacer()
        }
    }

    private var sourceChip: some View {
        metadataChip(icon: "dot.radiowaves.left.and.right", text: sourceLabel)
    }

    private var sourceLabel: String {
        switch displayConversation.source {
        case .desktop: return "Desktop"
        case .omi: return "Omi"
        case .phone: return "Phone"
        case .appleWatch: return "Apple Watch"
        case .workflow: return "Workflow"
        case .screenpipe: return "Screenpipe"
        case .friend, .friendCom: return "Friend"
        case .openglass: return "OpenGlass"
        case .frame: return "Frame"
        case .bee: return "Bee"
        case .limitless: return "Limitless"
        case .plaud: return "Plaud"
        default: return "Unknown"
        }
    }

    private func metadataChip(icon: String, text: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
                .scaledFont(size: 11)
                .foregroundColor(OmiColors.textTertiary)

            Text(text)
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textSecondary)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(
            Capsule()
                .fill(OmiColors.backgroundTertiary)
        )
    }

    // MARK: - App Results Section

    private var appResultsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("App Insights")
                    .scaledFont(size: 14, weight: .semibold)
                    .foregroundColor(OmiColors.textSecondary)

                Spacer()

                Button(action: { showAppSelector = true }) {
                    HStack(spacing: 4) {
                        Image(systemName: "arrow.triangle.2.circlepath")
                            .scaledFont(size: 11)
                        Text("Reprocess")
                            .scaledFont(size: 12)
                    }
                    .foregroundColor(OmiColors.purplePrimary)
                }
                .buttonStyle(.plain)
                .disabled(isReprocessing)
            }

            ForEach(displayConversation.appsResults) { result in
                AppResultCard(
                    result: result,
                    app: appProvider.apps.first { $0.id == result.appId }
                )
            }
        }
    }

    // MARK: - Suggested Apps Section

    private var suggestedAppsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Try with Apps")
                    .scaledFont(size: 14, weight: .semibold)
                    .foregroundColor(OmiColors.textSecondary)

                Spacer()
            }

            let memoryApps = appProvider.apps.filter {
                $0.capabilities.contains("memories") &&
                !displayConversation.appsResults.contains(where: { $0.appId == $0.id })
            }.prefix(4)

            if memoryApps.isEmpty && !appProvider.isLoading {
                Text("Enable apps with memory capability to get additional insights")
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textTertiary)
                    .padding()
                    .frame(maxWidth: .infinity)
                    .background(
                        RoundedRectangle(cornerRadius: 8)
                            .fill(OmiColors.backgroundSecondary)
                    )
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 12) {
                        ForEach(Array(memoryApps)) { app in
                            SuggestedAppCard(
                                app: app,
                                isLoading: selectedAppForReprocess?.id == app.id && isReprocessing,
                                onTap: {
                                    selectedAppForReprocess = app
                                    Task {
                                        await reprocessWithApp(app)
                                    }
                                }
                            )
                        }
                    }
                }
            }
        }
    }

    // MARK: - Reprocess

    private func reprocessWithApp(_ app: OmiApp) async {
        isReprocessing = true
        defer {
            isReprocessing = false
            selectedAppForReprocess = nil
            showAppSelector = false
        }

        // Track reprocess
        AnalyticsManager.shared.conversationReprocessed(conversationId: conversation.id, appId: app.id)

        do {
            try await APIClient.shared.reprocessConversation(
                conversationId: conversation.id,
                appId: app.id
            )
        } catch {
            logError("Failed to reprocess conversation", error: error)
        }
    }

    // MARK: - Action Items Section

    private var actionItemsSection: some View {
        let activeItems = displayConversation.structured.actionItems.filter { !$0.deleted }
        return VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: "checklist")
                    .scaledFont(size: 14)
                    .foregroundColor(OmiColors.textSecondary)

                Text("Action Items")
                    .scaledFont(size: 16, weight: .semibold)
                    .foregroundColor(OmiColors.textSecondary)

                // Count badge
                Text("\(activeItems.count)")
                    .scaledFont(size: 11, weight: .medium)
                    .foregroundColor(OmiColors.purplePrimary)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 2)
                    .background(
                        Capsule()
                            .fill(OmiColors.purplePrimary.opacity(0.15))
                    )

                Spacer()
            }

            VStack(alignment: .leading, spacing: 8) {
                ForEach(activeItems) { item in
                    HStack(alignment: .top, spacing: 10) {
                        Image(systemName: item.completed ? "checkmark.circle.fill" : "circle")
                            .scaledFont(size: 16)
                            .foregroundColor(item.completed ? OmiColors.success : OmiColors.textTertiary)

                        Text(item.description)
                            .scaledFont(size: 14)
                            .foregroundColor(item.completed ? OmiColors.textTertiary : OmiColors.textPrimary)
                            .textSelection(.enabled)
                            .strikethrough(item.completed, color: OmiColors.textTertiary)
                    }
                    .padding(12)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(
                        RoundedRectangle(cornerRadius: 12)
                            .fill(OmiColors.backgroundTertiary)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 12)
                            .stroke(OmiColors.backgroundTertiary.opacity(0.3), lineWidth: 1)
                    )
                }
            }
        }
    }
}

#Preview {
    ConversationDetailView(
        conversation: ServerConversation.preview,
        onBack: { }
    )
    .frame(width: 600, height: 800)
    .background(OmiColors.backgroundPrimary)
}

// Preview helper
extension ServerConversation {
    static var preview: ServerConversation {
        // This would need to be implemented with a proper initializer
        // For now, previews won't work without mock data
        fatalError("Preview not implemented")
    }
}

// MARK: - App Result Card

struct AppResultCard: View {
    let result: AppResponse
    let app: OmiApp?

    @State private var isExpanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            // Header
            HStack(spacing: 10) {
                if let app = app {
                    AsyncImage(url: URL(string: app.image)) { phase in
                        switch phase {
                        case .success(let image):
                            image
                                .resizable()
                                .aspectRatio(contentMode: .fill)
                        default:
                            RoundedRectangle(cornerRadius: 8)
                                .fill(OmiColors.backgroundTertiary)
                        }
                    }
                    .frame(width: 32, height: 32)
                    .clipShape(RoundedRectangle(cornerRadius: 8))

                    VStack(alignment: .leading, spacing: 2) {
                        Text(app.name)
                            .scaledFont(size: 13, weight: .medium)
                            .foregroundColor(OmiColors.textPrimary)

                        Text(app.author)
                            .scaledFont(size: 11)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                } else {
                    Image(systemName: "app.fill")
                        .scaledFont(size: 16)
                        .foregroundColor(OmiColors.textTertiary)
                        .frame(width: 32, height: 32)
                        .background(OmiColors.backgroundTertiary)
                        .clipShape(RoundedRectangle(cornerRadius: 8))

                    Text("App")
                        .scaledFont(size: 13, weight: .medium)
                        .foregroundColor(OmiColors.textPrimary)
                }

                Spacer()

                Button(action: { withAnimation { isExpanded.toggle() } }) {
                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .scaledFont(size: 12)
                        .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
            }

            // Content
            if isExpanded || result.content.count < 200 {
                Text(result.content)
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textSecondary)
                    .textSelection(.enabled)
                    .lineSpacing(4)
            } else {
                Text(result.content.prefix(200) + "...")
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textSecondary)
                    .textSelection(.enabled)
                    .lineSpacing(4)
            }

            // "Generated by" footer
            if let app = app {
                HStack(spacing: 6) {
                    AsyncImage(url: URL(string: app.image)) { phase in
                        switch phase {
                        case .success(let image):
                            image
                                .resizable()
                                .aspectRatio(contentMode: .fill)
                        default:
                            RoundedRectangle(cornerRadius: 4)
                                .fill(OmiColors.backgroundTertiary)
                        }
                    }
                    .frame(width: 16, height: 16)
                    .clipShape(RoundedRectangle(cornerRadius: 4))

                    Text("Generated by \(app.name)")
                        .scaledFont(size: 11)
                        .foregroundColor(OmiColors.textTertiary)
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(
                    Capsule()
                        .fill(OmiColors.backgroundTertiary.opacity(0.6))
                )
            }
        }
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(OmiColors.backgroundSecondary)
        )
    }
}

// MARK: - Suggested App Card

struct SuggestedAppCard: View {
    let app: OmiApp
    let isLoading: Bool
    let onTap: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: onTap) {
            VStack(spacing: 8) {
                ZStack {
                    AsyncImage(url: URL(string: app.image)) { phase in
                        switch phase {
                        case .success(let image):
                            image
                                .resizable()
                                .aspectRatio(contentMode: .fill)
                        default:
                            RoundedRectangle(cornerRadius: 12)
                                .fill(OmiColors.backgroundTertiary)
                        }
                    }
                    .frame(width: 56, height: 56)
                    .clipShape(RoundedRectangle(cornerRadius: 12))

                    if isLoading {
                        RoundedRectangle(cornerRadius: 12)
                            .fill(Color.black.opacity(0.5))
                            .frame(width: 56, height: 56)

                        ProgressView()
                            .scaleEffect(0.7)
                            .tint(.white)
                    }
                }

                Text(app.name)
                    .scaledFont(size: 11, weight: .medium)
                    .foregroundColor(OmiColors.textPrimary)
                    .lineLimit(1)
            }
            .frame(width: 80)
            .padding(.vertical, 10)
            .padding(.horizontal, 8)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(isHovering ? OmiColors.backgroundTertiary : OmiColors.backgroundSecondary)
            )
        }
        .buttonStyle(.plain)
        .disabled(isLoading)
        .onHover { isHovering = $0 }
    }
}

// MARK: - App Selector Sheet

struct AppSelectorSheet: View {
    let apps: [OmiApp]
    let isLoading: Bool
    let onSelect: (OmiApp) -> Void
    let onDismiss: () -> Void

    @State private var selectedAppId: String?

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Select App")
                    .scaledFont(size: 16, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                Button(action: onDismiss) {
                    Image(systemName: "xmark.circle.fill")
                        .scaledFont(size: 20)
                        .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
            }
            .padding()

            Divider()
                .background(OmiColors.backgroundTertiary)

            // Apps list
            if apps.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "square.grid.2x2")
                        .scaledFont(size: 40)
                        .foregroundColor(OmiColors.textTertiary)

                    Text("No Apps Available")
                        .scaledFont(size: 14, weight: .medium)
                        .foregroundColor(OmiColors.textSecondary)

                    Text("Enable apps with memory capability to reprocess conversations")
                        .scaledFont(size: 12)
                        .foregroundColor(OmiColors.textTertiary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding()
            } else {
                ScrollView {
                    LazyVStack(spacing: 2) {
                        ForEach(apps) { app in
                            AppSelectorRow(
                                app: app,
                                isSelected: selectedAppId == app.id,
                                isLoading: isLoading && selectedAppId == app.id
                            ) {
                                selectedAppId = app.id
                                onSelect(app)
                            }
                        }
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 8)
                }
            }
        }
        .frame(width: 320, height: 400)
        .background(OmiColors.backgroundPrimary)
    }
}

struct AppSelectorRow: View {
    let app: OmiApp
    let isSelected: Bool
    let isLoading: Bool
    let onSelect: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: onSelect) {
            HStack(spacing: 12) {
                AsyncImage(url: URL(string: app.image)) { phase in
                    switch phase {
                    case .success(let image):
                        image
                            .resizable()
                            .aspectRatio(contentMode: .fill)
                    default:
                        RoundedRectangle(cornerRadius: 10)
                            .fill(OmiColors.backgroundTertiary)
                    }
                }
                .frame(width: 44, height: 44)
                .clipShape(RoundedRectangle(cornerRadius: 10))

                VStack(alignment: .leading, spacing: 2) {
                    Text(app.name)
                        .scaledFont(size: 13, weight: .medium)
                        .foregroundColor(OmiColors.textPrimary)

                    Text(app.author)
                        .scaledFont(size: 11)
                        .foregroundColor(OmiColors.textTertiary)
                }

                Spacer()

                if isLoading {
                    ProgressView()
                        .scaleEffect(0.7)
                } else if isSelected {
                    Image(systemName: "checkmark.circle.fill")
                        .scaledFont(size: 18)
                        .foregroundColor(OmiColors.purplePrimary)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(isSelected || isHovering ? OmiColors.backgroundTertiary : Color.clear)
            )
        }
        .buttonStyle(.plain)
        .disabled(isLoading)
        .onHover { isHovering = $0 }
    }
}
