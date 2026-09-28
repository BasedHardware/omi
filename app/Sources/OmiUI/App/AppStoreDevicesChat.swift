import Foundation
import OmiKit

// AppStore orchestration, continued: chat (AppOrchestrator.tsx send / older
// pages / stop), task mutations (useTaskMutations.ts), and the device layer
// (useNativeDevices.ts scan/connect + capture plumbing).

extension AppStore {
    // MARK: - Chat transcript

    /// Drops the previous session's transcript, cursors, and bookkeeping so
    /// nothing leaks across accounts (port of `resetChatSession`).
    func resetChatSession() {
        chatErrorCopy = nil
        composerText = ""
        chatMessages = []
        olderChatCursor = nil
        hasOlderChat = false
        chatBusy = false
        chatHistoryLoading = false
        chatHistorySettled = false
        chatGeneration = .idle
        activeGenerationId = nil
        runtime.sendInFlight = false
        runtime.activeOmiRequestId = nil
    }

    /// Port of the chat-history effect: load the newest canonical history for
    /// the live session, merging into whatever is already on screen.
    func refreshChatHistory() async {
        bumpChatEpoch()
        guard sessionReady else {
            resetChatSession()
            return
        }
        guard let chat = services.chat else {
            chatHistorySettled = true
            return
        }
        let session = runtime.chatSessionEpoch
        chatHistoryLoading = true
        defer {
            if session == runtime.chatSessionEpoch {
                chatHistoryLoading = false
            }
        }
        do {
            let page = try await chat.loadNewestChatHistory()
            guard session == runtime.chatSessionEpoch else { return }
            chatMessages = reconcileCanonicalChatHistory(chatMessages, page.messages)
            olderChatCursor = page.olderCursor
            hasOlderChat = page.hasOlder
            chatErrorCopy = nil
            chatHistorySettled = true
        } catch {
            guard session == runtime.chatSessionEpoch, onboardingRequired == false
            else { return }
            chatErrorCopy = chatHistoryErrorCopy(error)
            chatHistorySettled = true
            // A 401/unconfigured history load can mean the cloud session
            // died; re-probe it instead of keeping a ready shell up.
            if chatSessionLost(error) {
                await revalidateSession()
            }
        }
    }

    /// Port of `send()` — optimistic local + pending rows, streaming assistant
    /// text, then the canonical settle. Session epochs and the synchronous
    /// request-started fence keep a retired send from writing into the next
    /// session's transcript.
    public func sendChat(_ text: String) async {
        let trimmed = text.trimmingCharacters(
            in: CharacterSet.whitespacesAndNewlines)
        guard let chat = services.chat else { return }
        guard sessionReady, !trimmed.isEmpty, !chatBusy, !runtime.sendInFlight
        else { return }
        runtime.sendInFlight = true
        let session = runtime.chatSessionEpoch
        let epochMirror = runtime.chatSessionEpochMirror
        runtime.chatMutationSeq += 1
        let admitted = LockedBox(false)
        let requestStarted = LockedBox(false)
        let omiRequest = LockedBox<String?>(nil)
        chatBusy = true
        chatErrorCopy = nil
        let now = appNowMilliseconds()
        let local = createLocalChatMessage(trimmed, now: now)
        let pending = createPendingAssistantMessage(local)
        let pendingId = pending.id
        chatMessages.append(contentsOf: [local, pending])
        // The omnibar path always sends the shared draft (TS implicit send),
        // which clears it.
        composerText = ""
        defer {
            runtime.sendInFlight = false
            if runtime.chatSessionEpoch == session {
                activeGenerationId = nil
                runtime.activeOmiRequestId = nil
                chatBusy = false
                chatGeneration = .idle
            }
        }
        do {
            let result = try await chat.sendChatMessage(
                trimmed, now: now,
                onGenerationStarted: { [weak self] generationId in
                    marshalToMainActor { [weak self] in
                        guard let self, self.runtime.chatSessionEpoch == session
                        else { return }
                        admitted.set(true)
                        self.activeGenerationId = generationId
                        if let index = self.chatMessages.firstIndex(where: {
                            $0.id == pendingId
                        }) {
                            self.chatMessages[index].generationId = generationId
                        }
                    }
                },
                localMessage: local,
                onRequestStarted: { requestId in
                    // Synchronous gate on the calling thread: a gate
                    // transition must refuse the request before it starts.
                    guard epochMirror.get() == session else { return false }
                    requestStarted.set(true)
                    omiRequest.set(requestId)
                    return true
                },
                onAssistantText: { [weak self] visible in
                    guard epochMirror.get() == session else { return }
                    let started = requestStarted.get()
                    let request = omiRequest.get()
                    if started, request != local.id { return }
                    marshalToMainActor { [weak self] in
                        guard let self else { return }
                        if let index = self.chatMessages.firstIndex(where: {
                            $0.id == pendingId
                        }) {
                            self.chatMessages[index].text = visible
                        }
                        self.chatGeneration = .streaming(visible)
                    }
                })
            // A gate transition retired the session this send belonged to:
            // its canonical messages belong to the previous account.
            let started = requestStarted.get()
            let request = omiRequest.get()
            guard runtime.chatSessionEpoch == session,
                !started || request == local.id
            else { return }
            chatMessages = settleChatTranscript(
                current: chatMessages, echoId: local.id, pendingId: pendingId,
                human: result.human, assistant: result.assistant)
            chatGeneration = .idle
        } catch {
            let started = requestStarted.get()
            let request = omiRequest.get()
            let didStart = admitted.get() || started
            guard runtime.chatSessionEpoch == session,
                !started || request == local.id
            else { return }
            if !admitted.get() && !started {
                chatMessages.removeAll { $0.id == local.id || $0.id == pendingId }
                if composerText.isEmpty { composerText = trimmed }
            } else {
                if let index = chatMessages.firstIndex(where: { $0.id == pendingId }),
                    chatMessages[index].generationOutcome == nil
                {
                    chatMessages[index].generationOutcome = .cancelled
                }
            }
            chatErrorCopy =
                didStart
                ? (isCancellation(error)
                    ? "Response stopped locally. It may still complete on the server."
                    : "Response interrupted. It may still complete.")
                : OmiKit.chatErrorCopy(error)
            if chatSessionLost(error) {
                await revalidateSession()
            }
        }
    }

    /// Port of `stopGeneration`.
    public func cancelChatGeneration() async {
        guard services.chat != nil else { return }
        let generationId = activeGenerationId
        let requestId = runtime.activeOmiRequestId
        guard generationId != nil || requestId != nil else { return }
        let session = runtime.chatSessionEpoch
        if let requestId {
            guard let streaming = services.transport as? OmiChatStreaming else {
                chatErrorCopy = "Could not stop the response."
                return
            }
            await streaming.cancelOmiChat(requestId: requestId)
            guard runtime.chatSessionEpoch == session,
                runtime.activeOmiRequestId == requestId
            else { return }
            runtime.activeOmiRequestId = nil
            chatBusy = false
            let pendingId = pendingAssistantId(requestId)
            if let index = chatMessages.firstIndex(where: { $0.id == pendingId }),
                chatMessages[index].generationOutcome == nil
            {
                chatMessages[index].generationOutcome = .cancelled
            }
            chatErrorCopy =
                "Response stopped locally. It may still complete on the server."
        } else if let generationId, let chat = services.chat {
            do {
                try await chat.cancelChatGeneration(generationId)
            } catch {
                if runtime.chatSessionEpoch == session {
                    chatErrorCopy = "Could not stop the response."
                }
            }
        }
    }

    /// Port of `loadOlderMessages` — cursor pagination plus the 410
    /// refresh-history recovery, both fenced by the session epoch and the
    /// send mutation counter.
    public func loadOlderChatHistory() async {
        guard let chat = services.chat, let cursor = olderChatCursor,
            !loadingOlderChat, sessionReady
        else { return }
        let session = runtime.chatSessionEpoch
        let mutation = runtime.chatMutationSeq
        loadingOlderChat = true
        chatErrorCopy = nil
        defer {
            if session == runtime.chatSessionEpoch {
                loadingOlderChat = false
            }
        }
        do {
            let page = try await chat.loadOlderChatHistory(olderCursor: cursor)
            guard session == runtime.chatSessionEpoch else { return }
            chatMessages = mergeOlderChatHistory(chatMessages, page.messages)
            olderChatCursor = page.olderCursor
            hasOlderChat = page.hasOlder
        } catch {
            guard session == runtime.chatSessionEpoch else { return }
            if let backendError = error as? ChatBackendError,
                backendError.status == 410,
                backendError.action == "refresh_history",
                runtime.chatMutationSeq == mutation
            {
                do {
                    let page = try await chat.loadNewestChatHistory()
                    guard session == runtime.chatSessionEpoch,
                        runtime.chatMutationSeq == mutation
                    else { return }
                    chatMessages = reconcileCanonicalChatHistory(
                        chatMessages.filter { $0.localOnly == true },
                        page.messages)
                    olderChatCursor = page.olderCursor
                    hasOlderChat = page.hasOlder
                    return
                } catch {
                    if chatSessionLost(error) {
                        await revalidateSession()
                    }
                }
            }
            if session == runtime.chatSessionEpoch {
                chatErrorCopy = "Older messages could not be loaded."
                if chatSessionLost(error) {
                    await revalidateSession()
                }
            }
        }
    }

    // MARK: - Task mutations (useTaskMutations.ts)

    var taskWritesAvailable: Bool {
        guard sessionReady, services.tasks != nil,
            let read = tasksRead
        else { return false }
        return read.apiContract == .omi || read.accountEpoch != nil
    }

    func resetTaskMutation() {
        runtime.taskGeneration += 1
        runtime.pendingTaskPatch = nil
        runtime.taskMutationActive = false
        runtime.taskAcknowledged = false
        runtime.taskRetryAfterMs = 0
        busyTaskId = nil
        taskMutationErrorCopy = nil
        canRetryTaskMutation = false
    }

    public func toggleTask(_ task: TaskProjection) async {
        await changeTask(task.id, TaskPatch(completed: !task.completed))
    }

    public func renameTask(_ task: TaskProjection, title: String) async {
        await changeTask(task.id, TaskPatch(description: title))
    }

    /// Adds a task through the ratified canonical write-op create. The TS
    /// client shipped no task-create path; this uses the same envelope
    /// grammar and response classification as the patch path.
    public func addTask(title: String) async {
        let trimmed = title.trimmingCharacters(
            in: CharacterSet.whitespacesAndNewlines)
        guard !trimmed.isEmpty, sessionReady, !runtime.taskMutationActive,
            runtime.pendingTaskPatch == nil, let transport = services.transport
        else { return }
        guard let read = tasksRead, read.apiContract != .omi,
            let epoch = read.accountEpoch
        else {
            taskMutationErrorCopy = "Refresh this task before editing."
            return
        }
        let generation = runtime.taskGeneration + 1
        runtime.taskGeneration = generation
        runtime.taskMutationActive = true
        busyTaskId = "new"
        taskMutationErrorCopy = nil
        defer {
            if generation == runtime.taskGeneration {
                runtime.taskMutationActive = false
                busyTaskId = nil
            }
        }
        do {
            let writeId = try await transport.createWriteId()
            let recordId = UUID().uuidString.lowercased()
            let now = appNowMilliseconds()
            let built = buildWriteOpEnvelope(
                domain: "tasks", writeId: writeId,
                op: .create(
                    recordId: recordId,
                    content: JSONValue.object([
                        ("completed", JSONValue.bool(false)),
                        ("description", JSONValue.string(trimmed)),
                        ("createdAt", JSONValue.integer(now)),
                        ("updatedAt", JSONValue.integer(now)),
                    ])),
                accountEpoch: epoch)
            guard let envelope = built.okValue,
                isTrustedWriteOpEnvelope(envelope.envelope.json)
            else {
                taskMutationErrorCopy =
                    "The change could not be prepared. Your edit has not been sent."
                return
            }
            let response = try await transport.request(
                BackendRequest(
                    id: "task-create-\(writeId)",
                    expectedApiContract: .canonical, method: .POST,
                    path: envelope.path,
                    body: JSON.serialize(envelope.envelope.json)))
            if response.status == 200 {
                _ = await refreshTasks()
                return
            }
            let classified = ClassifiedResponse(
                status: response.status, body: response.body,
                retryAfterSeconds: response.retryAfterSeconds)
            let failure = classifyWriteOpsResponse(classified, "Task add")
                ?? classifyStatus(classified, "Task add")
            await applyTaskFailure(
                failure, controlUnavailable: isControlUnavailable(classified),
                epoch: generation)
        } catch {
            if generation == runtime.taskGeneration {
                taskMutationErrorCopy =
                    "The change could not be prepared. Your edit has not been sent."
            }
        }
    }

    private func changeTask(_ id: String, _ patch: TaskPatch) async {
        guard taskWritesAvailable, !runtime.taskMutationActive,
            runtime.pendingTaskPatch == nil, let read = tasksRead
        else { return }
        guard let task = read.items.first(where: { $0.id == id }) else { return }
        if read.apiContract != .omi
            && (task.revision == nil || read.accountEpoch == nil)
        {
            taskMutationErrorCopy = "Refresh this task before editing."
            return
        }
        let generation = runtime.taskGeneration + 1
        runtime.taskGeneration = generation
        runtime.taskMutationActive = true
        busyTaskId = id
        taskMutationErrorCopy = nil
        defer {
            if generation == runtime.taskGeneration {
                runtime.taskMutationActive = false
            }
        }
        do {
            let prepared = try await services.tasks!.prepareTaskPatch(
                recordId: id, apiContract: read.apiContract,
                baseRevision: task.revision, accountEpoch: read.accountEpoch,
                patch: patch)
            guard generation == runtime.taskGeneration else { return }
            runtime.pendingTaskPatch = prepared
            await submitTaskMutation(prepared, epoch: generation)
        } catch {
            if generation == runtime.taskGeneration {
                taskMutationErrorCopy =
                    "The change could not be prepared. Your edit has not been sent."
                busyTaskId = nil
            }
        }
    }

    private func submitTaskMutation(
        _ prepared: PreparedTaskPatch, epoch: Int
    ) async {
        guard let tasksService = services.tasks, epoch == runtime.taskGeneration
        else { return }
        canRetryTaskMutation = false
        taskMutationErrorCopy = nil
        if !runtime.taskAcknowledged {
            let result = await tasksService.sendTaskPatch(prepared)
            guard epoch == runtime.taskGeneration else { return }
            if case .failed(let failure, let controlUnavailable) = result {
                await applyTaskFailure(
                    failure, controlUnavailable: controlUnavailable, epoch: epoch)
                return
            }
            runtime.taskAcknowledged = true
        }
        let refreshed = await refreshTasks()
        guard epoch == runtime.taskGeneration else { return }
        if refreshed == nil
            || refreshed!.page.completenessStatus != .complete
        {
            taskMutationErrorCopy =
                "Saved, but the latest tasks could not be loaded. Retry to refresh."
            canRetryTaskMutation = true
        } else {
            resetTaskMutation()
        }
    }

    private func applyTaskFailure(
        _ failure: WriteFailure, controlUnavailable: Bool, epoch: Int
    ) async {
        guard epoch == runtime.taskGeneration else { return }
        switch failure {
        case .authInvalid:
            taskMutationErrorCopy = "Sign in again before changing tasks."
            await revalidateSession()
        case .permanent(let reason, _):
            let isConflict = reason == WriteFailure.PermanentReason.conflict
            taskMutationErrorCopy =
                isConflict
                ? "This task changed elsewhere. Review the latest task before editing again."
                : "This change was not accepted. Your edit remains here to copy or dismiss."
            if isConflict
                || reason == WriteFailure.PermanentReason.staleEpoch
            {
                _ = await refreshTasks()
            }
        case .rateLimited(let retryAfterMilliseconds, _):
            runtime.taskRetryAfterMs =
                appNowMilliseconds() + Int64(retryAfterMilliseconds)
            taskMutationErrorCopy =
                controlUnavailable
                ? "Task editing is temporarily unavailable. Retry when the service is ready."
                : "The change could not be confirmed. Retry to check the same change."
            canRetryTaskMutation = true
        case .retryable:
            runtime.taskRetryAfterMs = 0
            taskMutationErrorCopy =
                controlUnavailable
                ? "Task editing is temporarily unavailable. Retry when the service is ready."
                : "The change could not be confirmed. Retry to check the same change."
            canRetryTaskMutation = true
        }
    }

    /// Replays the last prepared patch verbatim (port of `retry`).
    public func retryTaskMutation() async {
        guard sessionReady, !runtime.taskMutationActive, canRetryTaskMutation,
            let pending = runtime.pendingTaskPatch
        else { return }
        if appNowMilliseconds() < runtime.taskRetryAfterMs {
            taskMutationErrorCopy = "Please wait before retrying this change."
            return
        }
        await submitTaskMutation(pending, epoch: runtime.taskGeneration)
    }

    // MARK: - Devices (useNativeDevices.ts)

    public func startScan() async {
        guard let transport = services.devices, !deviceBusy else { return }
        deviceBusy = true
        deviceScanMessage = nil
        deviceErrorCopy = nil
        scanning = true
        defer {
            scanning = false
            deviceBusy = false
        }
        do {
            // The 8-second discovery window matches `startScan(8)` in
            // useNativeDevices.ts.
            let devices = try await transport.startScan(durationSeconds: 8)
            discoveredDevices = devices.sorted { $0.id < $1.id }
        } catch {
            // Bluetooth permission prompting is a host capability; a failed
            // scan reports the honest failure copy either way.
            deviceScanMessage =
                "Could not scan for your Omi. Check Bluetooth and try again."
        }
    }

    public func stopScan() {
        scanning = false
        guard let transport = services.devices else { return }
        Task { await transport.stopScan() }
    }

    public func connect(_ device: DiscoveredDevice) async {
        guard let transport = services.devices, !deviceBusy,
            connectingDeviceId == nil
        else { return }
        deviceBusy = true
        deviceScanMessage = nil
        deviceErrorCopy = nil
        connectingDeviceId = device.id
        defer {
            connectingDeviceId = nil
            deviceBusy = false
        }
        do {
            let event = try await transport.connect(deviceId: device.id)
            runtime.connectedDeviceId = device.id
            runtime.connectionId = event.connectionId
            connectedDeviceName = device.name
            let info: BleDeviceInfo?
            if let eventInfo = event.info {
                info = eventInfo
            } else {
                info = await transport.deviceInfo(deviceId: device.id)
            }
            connectedDeviceInfo = info
            openCapture(deviceId: device.id, deviceName: device.name)
            captureStage = runtime.captureMachine?.stage ?? .waiting
        } catch {
            deviceScanMessage =
                "Could not connect to your Omi. Keep it nearby and try again."
        }
    }

    public func disconnectDevice() async {
        guard let transport = services.devices, let id = runtime.connectedDeviceId,
            !deviceBusy
        else { return }
        deviceBusy = true
        deviceScanMessage = nil
        defer { deviceBusy = false }
        await transport.disconnect(deviceId: id)
        finishCapture()
        runtime.connectedDeviceId = nil
        runtime.connectionId = nil
        connectedDeviceName = nil
        connectedDeviceInfo = nil
        batteryLevel = nil
        captureStage = .idle
    }

    func startDeviceStreamLoops() {
        guard let transport = services.devices else { return }
        runtime.streamTasks.append(Task { [weak self] in
            let initial = await transport.currentBluetoothState()
            await MainActor.run { self?.bluetoothState = initial }
            for await state in transport.bluetoothStates {
                await MainActor.run { self?.bluetoothState = state }
            }
        })
        runtime.streamTasks.append(Task { [weak self] in
            for await event in transport.connectionEvents {
                await MainActor.run { self?.applyConnectionEvent(event) }
            }
        })
        runtime.streamTasks.append(Task { [weak self] in
            for await packet in transport.audioPackets {
                await MainActor.run { self?.ingestAudioPacket(packet) }
            }
        })
    }

    func startAuthStreamLoops() {
        guard let auth = services.auth else { return }
        runtime.streamTasks.append(Task { [weak self] in
            for await handoff in auth.desktopHandoffs {
                await MainActor.run { self?.desktopHandoff = handoff }
            }
        })
        runtime.streamTasks.append(Task { [weak self] in
            for await _ in auth.sessionInvalidated {
                await MainActor.run { self?.handleSessionInvalidated() }
            }
        })
    }

    func handleSessionInvalidated() {
        guard runtime.started else { return }
        Task { await revalidateSession() }
    }

    func applyConnectionEvent(_ event: DeviceConnectionEvent) {
        switch event.phase {
        case .connecting:
            if runtime.connectedDeviceId == nil
                || runtime.connectedDeviceId == event.deviceId
            {
                connectingDeviceId = event.deviceId
            }
        case .connected:
            guard runtime.connectedDeviceId == nil
                || runtime.connectedDeviceId == event.deviceId
            else { return }
            runtime.connectedDeviceId = event.deviceId
            runtime.connectionId = event.connectionId
            if connectedDeviceName == nil {
                connectedDeviceName = event.info?.model ?? "Omi"
            }
            connectedDeviceInfo = event.info ?? connectedDeviceInfo
            if runtime.captureMachine == nil {
                openCapture(deviceId: event.deviceId, deviceName: connectedDeviceName)
            }
            captureStage = runtime.captureMachine?.stage ?? .waiting
        case .disconnected:
            guard event.deviceId == runtime.connectedDeviceId else { return }
            finishCapture()
            runtime.connectedDeviceId = nil
            runtime.connectionId = nil
            connectedDeviceName = nil
            connectedDeviceInfo = nil
            batteryLevel = nil
            captureStage = .idle
        }
    }

    func ingestAudioPacket(_ packet: DeviceAudioPacket) {
        guard packet.deviceId == runtime.connectedDeviceId,
            let machine = runtime.captureMachine
        else { return }
        if machine.ingest(packet.raw, receivedAtMs: packet.receivedAtMs) != nil,
            captureStage != .active
        {
            captureStage = .active
        }
    }

    /// Opens one capture machine for the connection. Codec negotiation rides
    /// with the platform transport; 0 keeps the shared C++ framing rules
    /// active without claiming a negotiated codec.
    private func openCapture(deviceId: String, deviceName: String?) {
        let machine = CaptureSessionMachine()
        machine.open(
            deviceId: deviceId, deviceName: deviceName, codec: 0,
            nowMs: appNowMilliseconds())
        runtime.captureMachine = machine
    }

    /// Performs the journal handoff. With a journal-capable transport the
    /// batch is stored packet-by-packet; without one the handoff is dropped
    /// honestly rather than faked into storage.
    private func finishCapture() {
        guard let machine = runtime.captureMachine else { return }
        runtime.captureMachine = nil
        guard let handoff = machine.handoff(nowMs: appNowMilliseconds()) else {
            return
        }
        guard let storing = services.transport as? RecordingJournalStoring else {
            return
        }
        runtime.streamTasks.append(Task {
            guard let record = try? await storing.createRecordingJournal(handoff.input)
            else { return }
            for packet in handoff.packets {
                let entry = JSON.serialize(
                    JSONValue.array([
                        JSONValue.string("p"),
                        JSONValue.string(
                            Data(packet.payload).base64EncodedString()),
                    ]))
                _ = try? await storing.appendRecordingJournal(
                    handle: record.handle, entry: entry)
            }
        })
    }
}
