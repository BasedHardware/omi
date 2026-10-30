import Foundation
import OmiCore

/// Supplies the Firebase ID token for `Authorization: Bearer`. Implemented by the app target,
/// so this package never links Firebase.
public protocol AuthTokenProviding: Sendable {
    func idToken(forceRefresh: Bool) async throws -> String
}

public enum APIError: Error, Equatable, Sendable {
    case notSignedIn
    case http(status: Int, body: String)
    case decoding(String)
    case transport(String)
}

/// Everything the stores need from the backend. Stores depend on this protocol, never on
/// `APIClient`, so they test against `FakeAPIClient`.
public protocol APIClientProtocol: PaymentsAPI, ConversationContentAPI {
    func conversations(limit: Int, offset: Int) async throws -> [Conversation]
    func conversationDetail(id: String) async throws -> ConversationDetail
    func actionItems(limit: Int, offset: Int) async throws -> [ActionItem]
    func setActionItem(id: String, completed: Bool) async throws
    func memories(limit: Int, offset: Int) async throws -> [Memory]
    func createActionItem(description: String, dueAt: Date?) async throws -> ActionItem
    /// New text and due date (`nil` clears it); returns the stored task.
    func updateActionItem(id: String, description: String, dueAt: Date?) async throws -> ActionItem
    func deleteActionItem(id: String) async throws
    /// Cancelled, superseded (merged into `supersededBy`) or completed.
    func setActionItemStatus(id: String, status: ActionItem.Status, supersededBy: String?) async throws
    func editMemory(id: String, content: String) async throws
    func deleteMemory(id: String) async throws
    func renameConversation(id: String, title: String) async throws
    func deleteConversation(id: String) async throws
    func dailySummaries(limit: Int) async throws -> [DailySummary]
    func createDailySummary(date: String) async throws -> DailySummary?
    func localDevCustomToken(uid: String) async throws -> String

    // Agent
    func sendMessage(_ text: String, context: ChatContext?, sessionID: String?) -> AsyncThrowingStream<ChatStreamEvent, any Error>
    func createChatSession(title: String) async throws -> String
    func chatHistory(limit: Int, sessionID: String?) async throws -> [ChatMessage]
    func chatSessions() async throws -> [(id: String, title: String)]
    func accountGeneration() async throws -> Int
    func startWork(onTask taskID: String, title: String, generation: Int) async throws -> String
    @discardableResult
    func recordWorkstreamEvent(
        _ ref: WorkstreamRef,
        kind: String,
        summary: String,
        evidence: [[String: String]],
        idempotencyKey: String
    ) async throws -> String
    func recordResultArtifact(
        _ ref: WorkstreamRef,
        messageID: String,
        resultText: String,
        evidenceEventID: String,
        runID: String
    ) async throws
    func updateWorkstream(_ ref: WorkstreamRef, status: Workstream.Status?, summary: String?) async throws
    func workstream(_ workstreamID: String) async throws -> Workstream
    func whatMattersNow() async throws -> [Recommendation]
    func sendRecommendationFeedback(_ recommendation: Recommendation, decision: Recommendation.Decision, generation: Int) async throws
    func workstreamEvents(_ workstreamID: String, afterSequence: Int) async throws -> [Workstream.Event]
    /// An agent run's stream: declares `deviceTools`, typed errors arrive as `.failed(<code>)`.
    func streamAgent(_ text: String, context: ChatContext?, sessionID: String?, deviceTools: [String])
        -> AsyncThrowingStream<ChatStreamEvent, any Error>
    func sendDeviceToolResult(callID: String, result: DeviceToolResult) async throws

    // Account
    func onboardingState() async throws -> OnboardingState
    func updateOnboarding(completed: Bool?, acquisitionSource: String?) async throws
    func primaryLanguage() async throws -> String?
    func setPrimaryLanguage(_ code: String) async throws
    func setTimeZone(_ identifier: String) async throws
    func deleteAccount(reason: String?) async throws
    func availableLanguages() async throws -> [(name: String, code: String)]

    // Settings
    func dailySummary() async throws -> (enabled: Bool, hour: Int)
    func setDailySummary(enabled: Bool, hour: Int) async throws
    func notificationFrequency() async throws -> Int
    func setNotificationFrequency(_ value: Int) async throws
    func storesRecordings() async throws -> Bool
    func setStoresRecordings(_ value: Bool) async throws
    func assistantVoices() async throws -> (voices: [(id: String, name: String)], selected: String?)
    func setAssistantVoice(_ id: String) async throws
    func vocabulary() async throws -> [String]
    func setVocabulary(_ words: [String]) async throws
    func people() async throws -> [Person]
    func addPerson(_ name: String) async throws
    func renamePerson(_ id: String, to name: String) async throws
    func deletePerson(_ id: String) async throws
    func phoneNumbers() async throws -> [PhoneNumber]

    // Capabilities
    func integrationConnected(_ key: String) async throws -> Bool
    func integrationOAuthURL(_ integration: Integration) async throws -> URL
    func disconnectIntegration(_ integration: Integration) async throws
    func connectedTaskApps() async throws -> Set<String>
    func searchApps(query: String, installedOnly: Bool, offset: Int) async throws -> [OmiApp]
    func setApp(_ id: String, enabled: Bool) async throws

    // Capture
    func openListenSocket(uid: String, options: ListenSocket.Options) async throws -> any LiveTranscriptionChannel
    /// Transcription only (`/v2/voice-message/transcribe-stream`): PCM16 in, segments out, nothing saved.
    func openTranscribeStream(language: String) async throws -> any LiveTranscriptionChannel
    func hasSpeechProfile() async throws -> Bool
    /// `POST v3/upload-audio`: a 16 kHz mono WAV of the user speaking becomes their voice profile.
    func uploadSpeechProfile(wav: Data) async throws
    /// `category` is `manual` for memories typed in by hand, `system` for voice-intro answers.
    func createMemory(content: String, category: String) async throws -> Memory
    func finalizeInProgressConversation() async throws -> String?
    /// `POST v1/conversations/{id}/finalize`: finalizes exactly this conversation (a recording the
    /// app left open). 503 when the backend has no durable finalization worker.
    func finalizeConversation(id: String) async throws

    // Notifications
    /// `POST v1/users/fcm-token`: this install's FCM token and IANA time zone.
    func saveNotificationToken(_ token: String, timeZone: String, deviceIDHash: String?) async throws
    // Search and paging
    /// Backend conversation search (titles, overviews, transcripts), newest first.
    func searchConversations(query: String, page: Int, perPage: Int) async throws -> [Conversation]
    /// One page of chat history, oldest first; `offset` counts back from the newest message.
    func chatHistory(limit: Int, offset: Int, sessionID: String?) async throws -> [ChatMessage]
    // Firmware
    /// The newest Omi firmware for this device, or `nil` when it is up to date.
    func latestFirmware(model: String, firmware: String, hardware: String?, manufacturer: String?) async throws -> FirmwareRelease?
    // Offline sync (recordings the Omi kept while the phone was away)
    func uploadOfflineRecording(filename: String, data: Data) async throws -> SyncUpload
    func syncJob(id: String) async throws -> SyncJob?
    // Speakers and people (APIClient+Speakers.swift)
    func peopleWithStats() async throws -> [Person]
    func createPerson(named name: String) async throws -> Person
    func setPersonPinned(_ id: String, pinned: Bool) async throws
    func deleteSpeechSample(personID: String, index: Int) async throws
    func conversations(withPerson personID: String, page: Int, perPage: Int) async throws -> [Conversation]
    func assignSpeaker(conversationID: String, segmentIDs: [String], speakerID: Int?, to target: SpeakerTarget) async throws
        -> ConversationDetail
    func rejectSpeaker(conversationID: String, speakerID: Int, kind: SpeakerRejection, personID: String?, segmentIDs: [String]?)
        async throws -> ConversationDetail
    func reprocessConversation(id: String) async throws -> ConversationDetail
    func voiceMatches(personID: String) async throws -> [VoiceMatch]
    func speakerPrompts() async throws -> [SpeakerPrompt]
    func markSpeakerPromptsShown(_ ids: [String]) async throws
    func dismissSpeakerPrompts() async throws
    func answerSpeakerPrompt(_ prompt: SpeakerPrompt, answer: SpeakerPromptAnswer) async throws
    func speakerClip(conversationID: String, start: Double, end: Double) async throws -> Data
    func voiceProfileSettings() async throws -> VoiceProfileSettings
    func updateVoiceProfileSettings(asksToTag: Bool?, savesOtherVoices: Bool?) async throws -> VoiceProfileSettings
    func ignoredVoices() async throws -> [IgnoredVoice]
    func restoreIgnoredVoice(conversationID: String, speakerID: Int) async throws
    // Device actions (the Omi's button)
    /// `PATCH v1/conversations/{id}/starred`.
    func starConversation(id: String, starred: Bool) async throws
    /// `POST v2/voice-messages`: a spoken question (Omi audio file), the chat answer streamed back.
    func sendVoiceMessage(filename: String, audio: Data) -> AsyncThrowingStream<VoiceMessageEvent, any Error>
    /// `POST v1/mobile/device-diagnostics`: a diagnostics bundle (schema 2 JSON) for support; returns the ticket.
    func uploadDeviceDiagnostics(_ bundle: Data) async throws -> String
    // Chat extras (`APIClient+ChatExtras.swift`)
    /// The chat's send: with uploaded file ids and the device tools this phone declares ("Omi
    /// asks"); typed stream errors arrive as `.failed(<code>)`.
    func sendChatMessage(_ text: String, fileIDs: [String], context: ChatContext?, sessionID: String?, deviceTools: [String])
        -> AsyncThrowingStream<ChatStreamEvent, any Error>
    /// `POST v2/voice-message/transcribe`: the words of an Omi recording, nothing stored (the
    /// question then goes into the pinned main chat like a typed one).
    func transcribeVoiceMessage(filename: String, audio: Data) async throws -> String
    func rateChatMessage(id: String, value: Int, reason: String?) async throws
    func clearChat(sessionID: String) async throws -> ChatMessage?
    func uploadChatFile(filename: String, mimeType: String, data: Data) async throws -> ChatFile
    func synthesizeSpeech(text: String, voiceID: String?) async throws -> Data
    // Conversation actions (APIClient+ConversationActions.swift)
    func conversations(limit: Int, offset: Int, filter: ConversationFilter) async throws -> [Conversation]
    func setConversationStarred(id: String, starred: Bool) async throws
    func setConversationVisibility(id: String, visibility: Conversation.Visibility) async throws
    /// Starts a background merge; returns the backend's warning (e.g. large time gaps).
    func mergeConversations(ids: [String]) async throws -> String?
    func editTranscriptSegment(conversationID: String, segmentID: String, text: String) async throws
    func conversationAudio(id: String) async throws -> ConversationAudio
    func folders() async throws -> [Folder]
    func moveConversation(id: String, toFolder folderID: String?) async throws
    func moveConversations(ids: [String], toFolder folderID: String) async throws
    // Task extras (APIClient+TaskExtras.swift)
    func deleteActionItems(ids: [String]) async throws -> [String]
    func setTaskLayout(_ entries: [TaskLayout]) async throws
    func createIntegrationTask(app: String, title: String, dueAt: Date?) async throws
    func markActionItemExported(id: String, platform: String, appleReminderID: String?) async throws
    func shareActionItems(ids: [String]) async throws -> URL
    func sharedActionItems(token: String) async throws -> SharedTasks
    func acceptSharedActionItems(token: String) async throws -> Int
    func connectTaskIntegration(_ key: String) async throws
    func pendingReminderSync() async throws -> PendingTaskSync
    func syncActionItems(_ updates: [TaskSyncUpdate]) async throws
    // Goals (APIClient+Goals.swift)
    func goals() async throws -> [Goal]
    func createGoal(title: String, current: Double, target: Double) async throws -> Goal
    func updateGoal(id: String, title: String, current: Double, target: Double) async throws -> Goal
    func setGoalProgress(id: String, current: Double) async throws -> Goal
    func deleteGoal(id: String) async throws
    // Memory management (APIClient+MemoryExtras.swift)
    func setMemoryVisibility(id: String, visibility: Memory.Visibility) async throws
    func setMemoryBaseline(id: String, pinned: Bool) async throws
    func reviewMemory(id: String, isRight: Bool) async throws
    func memoryReviewQueue() async throws -> [MemoryConflict]
    func resolveMemoryConflict(id: String, decision: MemoryConflict.Decision) async throws
    func deleteAllMemories() async throws
    func knowledgeGraph() async throws -> KnowledgeGraph
    // Account and data (APIClient+Profile.swift, APIClient+Imports.swift)
    func exportAllData() async throws -> URL
    func usage(period: UsageStats.Period, timeZone: String) async throws -> UsageStats
    func fairUseStatus() async throws -> FairUseStatus
    func cancelSubscription(reason: String?, details: String?) async throws
    func referralURL() async throws -> URL?
    func userProfile() async throws -> UserProfile
    func wrapped(year: Int) async throws -> Wrapped
    func generateWrapped(year: Int) async throws
    func appsWithDataAccess() async throws -> [AppDataAccess]
    func importLimitless(zip: Data, filename: String, language: String) async throws -> ImportJob
    func importJobs() async throws -> [ImportJob]
    func cancelImportJob(id: String) async throws
    func deleteImportJob(id: String) async throws
    // What's new, For you, search filters (APIClient+Discover.swift)
    func changelogs(fromVersion: String?, toVersion: String?, limit: Int) async throws -> [Announcement]
    func pendingAnnouncements(appVersion: String, versionUpgrade: Bool) async throws -> [Announcement]
    func dismissAnnouncement(id: String, buttonTapped: Bool) async throws
    func forYouFeed() async throws -> [ForYouItem]?
    func sendForYouFeedback(itemID: String, _ feedback: ForYouItem.Feedback) async throws
    func searchConversations(query: String, page: Int, perPage: Int, filter: ConversationSearchFilter) async throws -> [Conversation]
    func searchRecaps(query: String) async throws -> [DailySummary]
    // Developer settings (APIClient+Developer.swift)
    func webhookStatus() async throws -> [DeveloperWebhook: Bool]
    func webhookURL(_ hook: DeveloperWebhook) async throws -> String
    func setWebhookURL(_ hook: DeveloperWebhook, url: String) async throws
    func setWebhook(_ hook: DeveloperWebhook, enabled: Bool) async throws
    func developerKeys(_ kind: DeveloperKey.Kind) async throws -> [DeveloperKey]
    func createDeveloperKey(_ kind: DeveloperKey.Kind, name: String, scopes: [String]?) async throws -> DeveloperKey
    func revokeDeveloperKey(_ kind: DeveloperKey.Kind, id: String) async throws
    // App store (APIClient+AppStore.swift)
    func appDetail(id: String, uid: String?) async throws -> AppDetail
    func appCategories() async throws -> [AppCategory]
    func browseApps(_ query: AppQuery, offset: Int) async throws -> (apps: [OmiApp], hasMore: Bool)
    func reviewApp(id: String, score: Int, text: String, updating: Bool) async throws
    func appSubscription(id: String) async throws -> AppSubscription?
    func cancelAppSubscription(id: String) async throws
    // Chat apps (APIClient+ChatApps.swift)
    func chatSessions(appID: String) async throws -> [(id: String, title: String)]
    func createChatSession(title: String, appID: String) async throws -> String
    // Task app settings (APIClient+TaskAppSettings.swift)
    func taskAppOptions(_ level: TaskAppLevel, parent: String?) async throws -> [TaskAppOption]
    func saveTaskAppSelection(_ app: String, selection: [TaskAppLevel: TaskAppOption?]) async throws
    func defaultTaskApp() async throws -> String?
    func setDefaultTaskApp(_ app: String) async throws
    // Transcription preferences (APIClient+Transcription.swift)
    func singleLanguageMode() async throws -> Bool
    func setSingleLanguageMode(_ value: Bool) async throws
    // Phone calls (APIClient+PhoneCalls.swift)
    func verifiedPhoneNumbers() async throws -> [VerifiedPhoneNumber]
    func startPhoneVerification(phoneNumber: String) async throws -> PhoneVerification
    func checkPhoneVerification(phoneNumber: String) async throws -> Bool
    func deletePhoneNumber(id: String) async throws
    func phoneCallToken() async throws -> PhoneCallToken
    func phoneCallQuota() async throws -> PhoneCallQuota?
    func phoneCallConversations(limit: Int, offset: Int) async throws -> [Conversation]
    func openPhoneCallSocket(uid: String, callID: String, language: String) async throws -> any PhoneCallTranscriptChannel
    // Location, Apple Health, naming voices live (APIClient+Location / +Health / +LiveSpeakers.swift)
    func updateUserGeolocation(_ snapshot: GeolocationSnapshot) async throws
    @discardableResult
    func syncAppleHealth(_ summary: HealthSummary) async throws -> Date?
    func markAppleHealthConnected() async throws
    func inProgressConversationID() async throws -> String?
    // Conversation extras (APIClient+ConversationExtras.swift)
    func conversations(limit: Int, offset: Int, query: ConversationQuery) async throws -> [Conversation]
    func reprocessConversation(id: String, appID: String) async throws -> ConversationDetail
    func suggestedSummaryApps(conversationID: String) async throws -> [OmiApp]
    func summaryApps() async throws -> [OmiApp]
    func setPreferredSummaryApp(id: String) async throws
    func generateAppDescription(name: String, prompt: String) async throws -> (description: String, emoji: String)
    func createSummaryApp(_ draft: SummaryTemplateDraft, description: String, icon: Data) async throws -> String
    func calendarEvents(from start: Date, to end: Date) async throws -> [CalendarEventCandidate]
    func linkCalendarEvent(conversationID: String, eventID: String) async throws -> CalendarEventLink
    func unlinkCalendarEvent(conversationID: String) async throws
    func setEventsCreated(conversationID: String, indexes: [Int], created: Bool) async throws
    func testConversationPrompt(conversationID: String, prompt: String) async throws -> String
    func conversationPhoto(conversationID: String, photoID: String) async throws -> Data
    func conversationScreenshots(conversationID: String) async throws -> [ConversationScreenshot]
    func deleteConversationScreenshot(conversationID: String, screenshotID: String) async throws -> [ConversationScreenshot]
    func separateRecording(conversationID: String) async throws
    func precacheConversationAudio(id: String) async throws
}

/// URLSession-backed client. Header contract mirrors the Flutter app's `buildHeaders`
/// (`app/lib/backend/http/shared.dart`).
public struct APIClient: APIClientProtocol {
    let configuration: AppConfiguration
    let tokens: any AuthTokenProviding
    let session: URLSession

    public init(configuration: AppConfiguration, tokens: any AuthTokenProviding, session: URLSession = .shared) {
        self.configuration = configuration
        self.tokens = tokens
        self.session = session
    }

    enum Method: String { case get = "GET", post = "POST", patch = "PATCH", put = "PUT", delete = "DELETE" }

    enum Body {
        case none
        case json(Data)
        case form([String: String])
        /// One file part (`multipart/form-data`), as FastAPI's `UploadFile` expects.
        case file(field: String, filename: String, mimeType: String, data: Data)
    }

    func request(
        _ method: Method,
        _ path: String,
        query: [URLQueryItem] = [],
        body: Body = .none,
        headers: [String: String] = [:],
        authenticated: Bool = true
    ) async throws -> URLRequest {
        var components = URLComponents(url: configuration.apiBaseURL.appending(path: path), resolvingAgainstBaseURL: false)!
        if !query.isEmpty { components.queryItems = query }
        var request = URLRequest(url: components.url!)
        request.httpMethod = method.rawValue
        request.timeoutInterval = 30
        request.setValue("ios", forHTTPHeaderField: "X-App-Platform")
        request.setValue(configuration.appVersion, forHTTPHeaderField: "X-App-Version")
        request.setValue(configuration.appBuild, forHTTPHeaderField: "X-App-Build")
        switch body {
        case .none:
            break
        case let .json(data):
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = data
        case let .form(fields):
            request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
            var form = URLComponents()
            form.queryItems = fields.map { URLQueryItem(name: $0.key, value: $0.value) }
            request.httpBody = form.percentEncodedQuery?.data(using: .utf8)
        case let .file(field, filename, mimeType, data):
            let boundary = "omi-\(UUID().uuidString)"
            request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
            var body = Data()
            body.append(Data("--\(boundary)\r\n".utf8))
            body.append(Data("Content-Disposition: form-data; name=\"\(field)\"; filename=\"\(filename)\"\r\n".utf8))
            body.append(Data("Content-Type: \(mimeType)\r\n\r\n".utf8))
            body.append(data)
            body.append(Data("\r\n--\(boundary)--\r\n".utf8))
            request.httpBody = body
            request.timeoutInterval = 60
        }
        for (name, value) in headers {
            request.setValue(value, forHTTPHeaderField: name)
        }
        if authenticated {
            // Authenticated requests never degrade into anonymous traffic.
            let token = try await tokens.idToken(forceRefresh: false)
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        return request
    }

    func data(
        _ method: Method,
        _ path: String,
        query: [URLQueryItem] = [],
        body: Body = .none,
        headers: [String: String] = [:],
        authenticated: Bool = true
    ) async throws -> Data {
        let request = try await request(method, path, query: query, body: body, headers: headers, authenticated: authenticated)
        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.transport(error.localizedDescription)
        }
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200 ..< 300).contains(status) else {
            throw APIError.http(status: status, body: String(bytes: data.prefix(500), encoding: .utf8) ?? "")
        }
        return data
    }

    func decode<T: Decodable>(_ type: T.Type, from data: Data) throws -> T {
        do {
            return try JSONDecoder().decode(type, from: data)
        } catch {
            throw APIError.decoding(String(describing: error))
        }
    }
}
