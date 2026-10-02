import Foundation

// Port of `react-native/src/recordingJournalClient.ts` — encrypted capture
// journal restore/append/flush semantics. The journal entry language is a
// JSON array per entry: ["p", base64Packet], ["a", ackCount], ["s"].

public let recordingJournalMaxBytes = 8_388_608
public let recordingJournalMaxPackets = 65_536

public enum RecordingJournalClientError: Error, Sendable, Equatable {
    case journalUnavailable
    case invalidPacket
    case emptyPacket
    case invalidIdentity
    case exceedsLimit
    case invalidEntry
    case invalidOrder
    case invalidAck
    case invalidAcknowledge
    case invalidCaptureTimestamp
    case invalidNativeAcknowledgement
}

public enum RecordingJournalReplayError: Error, Sendable, Equatable {
    case storageUnavailable
    case invalidStorageAcknowledgement
    case missingSessionAcknowledgement
    case changedJournalIdentity
}

/// `decodeJournalPacket` — bounded base64 with an empty-packet refusal.
public func decodeJournalPacket(_ value: String) throws -> [UInt8] {
    if value.count > Int((Double(recordingJournalMaxBytes) / 3).rounded(.up)) * 4 {
        throw RecordingJournalClientError.invalidPacket
    }
    guard let bytes = Base64Codec.decode(value) else {
        throw RecordingJournalClientError.invalidPacket
    }
    if bytes.isEmpty { throw RecordingJournalClientError.emptyPacket }
    return bytes
}

public struct RestoredRecording: Sendable, Equatable {
    public var journal: RecordingJournalRecord
    public var pending: [[UInt8]]
    public var totalBytes: Int
    public var acknowledged: Int
}

/// Port of `restoreRecording`: validate the journaled identity and replay the
/// packet/acknowledgement/stop ordering into a resumable recording.
public func restoreRecording(
    _ journal: RecordingJournalRecord
) throws -> RestoredRecording {
    guard
        isOptionalCaptureTimestamp(journal.capturedAtMs),
        isCaptureUUID(journal.captureId),
        journal.handle == journal.captureId,
        journal.sessionId == nil || isCaptureUUID(journal.sessionId!),
        !journal.deviceId.isEmpty, journal.deviceId.count <= 256,
        journal.codec >= 0, journal.codec <= 255
    else {
        throw RecordingJournalClientError.invalidIdentity
    }
    var packets = [[UInt8]]()
    var totalBytes = 0
    var acknowledged = 0
    var stopped = false
    for entry in journal.entries {
        guard let record = JSON.parseOrNull(entry), record.arrayValue != nil else {
            throw RecordingJournalClientError.invalidEntry
        }
        let items = record.arrayValue!
        if items.count == 2, items[0].stringValue == "p",
            let packetText = items[1].stringValue, !stopped
        {
            let bytes = try decodeJournalPacket(packetText)
            totalBytes += bytes.count
            if totalBytes > recordingJournalMaxBytes
                || packets.count >= recordingJournalMaxPackets
            {
                throw RecordingJournalClientError.exceedsLimit
            }
            packets.append(bytes)
        } else if items.count == 2, items[0].stringValue == "a",
            let ack = items[1].safeIntegerValue, ack >= acknowledged,
            ack <= packets.count, journal.sessionId != nil
        {
            acknowledged = Int(ack)
        } else if items.count == 1, items[0].stringValue == "s", !stopped {
            stopped = true
        } else {
            throw RecordingJournalClientError.invalidOrder
        }
    }
    return RestoredRecording(
        journal: journal,
        pending: Array(packets[acknowledged...]),
        totalBytes: totalBytes,
        acknowledged: acknowledged
    )
}

// NOTE: the capability probe `hasRecordingJournal(_:)` lives in
// Transport.swift; this file only implements the journal semantics.

/// Port of `createRecordingJournal` — validate the requested identity, then
/// require the native acknowledgement to match exactly.
public func createRecordingJournal(
    _ transport: BackendTransport, input: RecordingJournalInput
) async throws -> RecordingJournalRecord {
    guard let journalStoring = transport as? RecordingJournalStoring else {
        throw RecordingJournalClientError.journalUnavailable
    }
    guard isOptionalCaptureTimestamp(input.capturedAtMs) else {
        throw RecordingJournalClientError.invalidCaptureTimestamp
    }
    guard isCaptureUUID(input.captureId) else {
        throw RecordingJournalClientError.invalidIdentity
    }
    let journal = try await journalStoring.createRecordingJournal(input)
    try restoreRecording(journal)
    if journal.handle != input.captureId
        || journal.captureId != input.captureId
        || journal.capturedAtMs != input.capturedAtMs
        || journal.deviceId != input.deviceId
        || journal.deviceName != input.deviceName
        || journal.codec != input.codec
        || !journal.entries.isEmpty
        || journal.sessionId != nil
    {
        throw RecordingJournalClientError.invalidNativeAcknowledgement
    }
    return journal
}

/// Port of `recordingJournalBackend` — a constrained `BackendTransport` view
/// over one journal handle. `generationEvents`/`cancelGenerationEvents` fall
/// through to the underlying transport, matching the TS wrapper.
public struct RecordingJournalTransport: BackendTransport {
    let backend: BackendTransport
    let storing: RecordingJournalStoring
    let handle: String

    public func request(_ request: BackendRequest) async throws -> BackendResponse {
        try await storing.requestRecordingJournal(handle: handle, request: request)
    }

    public func generationEvents(
        generationId: String, lastEventId: String?,
        onFrame: @escaping @Sendable (String) -> Void
    ) async throws -> BackendResponse {
        try await backend.generationEvents(
            generationId: generationId, lastEventId: lastEventId, onFrame: onFrame)
    }

    public func cancelGenerationEvents(generationId: String) async {
        await backend.cancelGenerationEvents(generationId: generationId)
    }

    public func createWriteId() async throws -> String {
        try await backend.createWriteId()
    }

    public func createRecordingId() async throws -> String {
        try await backend.createRecordingId()
    }

    public func apiContract() async -> APIContract? { await backend.apiContract() }
    public func softwarePlane() async -> SoftwarePlane? { await backend.softwarePlane() }
    @discardableResult
    public func setSoftwarePlane(_ plane: SoftwarePlane) async -> SoftwarePlane? {
        await backend.setSoftwarePlane(plane)
    }
    public func stampedBackendOrigin() async -> String? {
        await backend.stampedBackendOrigin()
    }
}

public func recordingJournalBackend(
    _ transport: BackendTransport, handle: String
) throws -> BackendTransport {
    guard let storing = transport as? RecordingJournalStoring else {
        throw RecordingJournalClientError.journalUnavailable
    }
    return RecordingJournalTransport(backend: transport, storing: storing, handle: handle)
}

/// Drains one owner-scoped durable journal. The storage implementation must
/// persist each append and any acknowledged session identity before returning.
/// Failed requests leave the journal and its latest server acknowledgement in
/// place so a later call can safely replay only the unacknowledged suffix.
public func drainRecordingJournal(
    _ transport: BackendTransport, handle: String
) async throws -> DeviceSessionRecord? {
    guard let storing = transport as? RecordingJournalStoring else {
        throw RecordingJournalReplayError.storageUnavailable
    }
    var journal = try await storing.readRecordingJournal(handle: handle)
    var restored = try restoreRecording(journal)
    guard restored.totalBytes > 0 else {
        await storing.removeRecordingJournal(handle: handle)
        return nil
    }

    if !journalHasStopMarker(journal) {
        journal = try await appendDurableJournalEntry(
            JSON.serialize(JSONValue.array([JSONValue.string("s")])),
            to: journal, using: storing)
        restored = try restoreRecording(journal)
    }

    let journalTransport = try recordingJournalBackend(transport, handle: handle)
    let sessionId: String
    if let existingSessionId = journal.sessionId {
        sessionId = existingSessionId
    } else {
        let session = try await openDeviceSession(
            journalTransport,
            capturedAtMs: journal.capturedAtMs,
            captureId: journal.captureId,
            deviceId: journal.deviceId,
            deviceName: journal.deviceName,
            codec: journal.codec)
        let acknowledged = try await storing.readRecordingJournal(handle: handle)
        guard acknowledged.sessionId == session.id else {
            throw RecordingJournalReplayError.missingSessionAcknowledgement
        }
        guard sameJournalIdentity(journal, acknowledged) else {
            throw RecordingJournalReplayError.changedJournalIdentity
        }
        journal = acknowledged
        restored = try restoreRecording(journal)
        sessionId = session.id
    }

    while !restored.pending.isEmpty {
        var batch = [[UInt8]]()
        var batchBytes = 0
        for packet in restored.pending {
            guard !packet.isEmpty, packet.count <= deviceSessionMaxBatchBytes else {
                throw DeviceSessionClientError.invalidAudioBatch
            }
            if !batch.isEmpty
                && (batch.count >= deviceSessionMaxBatchPackets
                    || batchBytes + packet.count > deviceSessionMaxBatchBytes)
            {
                break
            }
            batch.append(packet)
            batchBytes += packet.count
        }
        guard !batch.isEmpty else { throw DeviceSessionClientError.invalidAudioBatch }

        let firstUnacknowledged = restored.acknowledged
        _ = try await appendDeviceSessionAudio(
            journalTransport, sessionId: sessionId, packets: batch,
            chunkIndex: firstUnacknowledged)
        let newAcknowledged = firstUnacknowledged + batch.count
        let ackEntry = JSON.serialize(
            JSONValue.array([
                JSONValue.string("a"),
                JSONValue.integer(Int64(newAcknowledged)),
            ]))
        journal = try await appendDurableJournalEntry(
            ackEntry, to: journal, using: storing)
        guard journal.sessionId == sessionId else {
            throw RecordingJournalReplayError.missingSessionAcknowledgement
        }
        restored = try restoreRecording(journal)
        guard restored.acknowledged == newAcknowledged else {
            throw RecordingJournalReplayError.invalidStorageAcknowledgement
        }
    }

    let completed = try await completeDeviceSession(
        journalTransport, sessionId: sessionId)
    await storing.removeRecordingJournal(handle: handle)
    return completed
}

private func journalHasStopMarker(_ journal: RecordingJournalRecord) -> Bool {
    journal.entries.contains { entry in
        guard let value = JSON.parseOrNull(entry), let items = value.arrayValue else {
            return false
        }
        return items.count == 1 && items[0].stringValue == "s"
    }
}

private func appendDurableJournalEntry(
    _ entry: String,
    to journal: RecordingJournalRecord,
    using storing: RecordingJournalStoring
) async throws -> RecordingJournalRecord {
    let expectedAppend = journal.entries.count + 1
    let acknowledged = try await storing.appendRecordingJournal(
        handle: journal.handle, entry: entry, expectedEntryCount: expectedAppend)
    guard acknowledged == expectedAppend else {
        throw RecordingJournalReplayError.invalidStorageAcknowledgement
    }
    let updated = try await storing.readRecordingJournal(handle: journal.handle)
    guard sameJournalIdentity(journal, updated),
        updated.entries.count == expectedAppend,
        updated.entries.last == entry
    else {
        throw RecordingJournalReplayError.changedJournalIdentity
    }
    return updated
}

private func sameJournalIdentity(
    _ lhs: RecordingJournalRecord, _ rhs: RecordingJournalRecord
) -> Bool {
    lhs.handle == rhs.handle && lhs.captureId == rhs.captureId
        && lhs.capturedAtMs == rhs.capturedAtMs && lhs.deviceId == rhs.deviceId
        && lhs.deviceName == rhs.deviceName && lhs.codec == rhs.codec
}
