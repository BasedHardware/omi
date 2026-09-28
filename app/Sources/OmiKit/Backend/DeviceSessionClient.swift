import Foundation

// Port of `react-native/src/deviceSessionClient.ts` and
// `recordingTranscriptContract.ts` — capture device-session open/append/
// complete/transcribe over the native transport.

public struct RecordingTranscript: Sendable, Equatable {
    public var sessionId: String
    /// "queued" | "running" | "completed" | "failed"
    public var state: String
    public var text: String?
    public var errorCode: String?
    public var discardedLeadingPackets: Int64
}

public struct DeviceSessionBackendError: Error, Sendable, Equatable {
    public let status: Int
    public let backendCode: String

    public init(status: Int, backendCode: String) {
        self.status = status
        self.backendCode = backendCode
    }
}

public enum DeviceSessionClientError: Error, Sendable, Equatable {
    case emptyResponse
    case nonObjectResponse
    case nonObjectSession
    case inventedTranscript
    case incompleteResponse
    case invalidRecordingIdentity
    case unacknowledgedIdentity
    case unacknowledgedAudio
    case unacknowledgedCompletion
    case invalidAudioBatch
    case batchOverRequestLimit
    case unacknowledgedTranscription
}

public func isOptionalCaptureTimestamp(_ value: Int64?) -> Bool {
    guard let value else { return true }
    return value >= 0 && value <= 8_640_000_000_000_000
}

/// `^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`
public func isCaptureUUID(_ value: String) -> Bool {
    let bytes = Array(value.utf8)
    guard bytes.count == 36 else { return false }
    func hex(_ byte: UInt8) -> Bool {
        (byte >= UInt8(ascii: "0") && byte <= UInt8(ascii: "9"))
            || (byte >= UInt8(ascii: "a") && byte <= UInt8(ascii: "f"))
    }
    for (index, byte) in bytes.enumerated() {
        switch index {
        case 8, 13, 18, 23:
            if byte != UInt8(ascii: "-") { return false }
        case 14:
            if byte != UInt8(ascii: "4") { return false }
        case 19:
            if !(byte == UInt8(ascii: "8") || byte == UInt8(ascii: "9")
                || byte == UInt8(ascii: "a") || byte == UInt8(ascii: "b"))
            { return false }
        default:
            if !hex(byte) { return false }
        }
    }
    return true
}

func parseObjectBody(_ body: String?) throws -> JSONValue {
    guard let body else { throw DeviceSessionClientError.emptyResponse }
    guard let parsed = JSON.parseOrNull(body), parsed.isRecord else {
        throw DeviceSessionClientError.nonObjectResponse
    }
    return parsed
}

func parseSessionValue(_ value: JSONValue?) throws -> DeviceSessionRecord {
    guard let item = value, item.isRecord else {
        throw DeviceSessionClientError.nonObjectSession
    }
    // A session must never invent a transcript.
    if item["transcript"]?.stringValue != nil {
        throw DeviceSessionClientError.inventedTranscript
    }
    let capturedAtMs = item["capturedAtMs"]?.safeIntegerValue
    guard
        isOptionalCaptureTimestamp(capturedAtMs),
        let id = item["id"]?.stringValue,
        let deviceId = item["deviceId"]?.stringValue,
        isNullValue(item["deviceName"]) || item["deviceName"]?.stringValue != nil,
        let codec = item["codec"]?.safeIntegerValue, codec >= 0, codec <= 255,
        let stateRaw = item["state"]?.stringValue,
        stateRaw == "open" || stateRaw == "complete" || stateRaw == "failed",
        let byteCount = item["byteCount"]?.safeIntegerValue, byteCount >= 0,
        let chunkCount = item["chunkCount"]?.safeIntegerValue, chunkCount >= 0,
        let startedAt = item["startedAt"]?.safeIntegerValue, startedAt >= 0,
        isNullValue(item["endedAt"])
            || (item["endedAt"]?.safeIntegerValue != nil
                && item["endedAt"]!.safeIntegerValue! >= 0)
    else {
        throw DeviceSessionClientError.incompleteResponse
    }
    return DeviceSessionRecord(
        capturedAtMs: capturedAtMs, id: id, deviceId: deviceId,
        deviceName: item["deviceName"]?.stringValue, codec: Int(codec),
        state: DeviceSessionState(rawValue: stateRaw) ?? .open,
        byteCount: Int(byteCount), chunkCount: Int(chunkCount),
        startedAt: startedAt,
        endedAt: item["endedAt"]?.safeIntegerValue
    )
}

func rejectIfUnusable(_ response: BackendResponse) throws {
    if response.status >= 200 && response.status < 300 { return }
    var backendCode = "unknown"
    if let body = response.body, let parsed = JSON.parseOrNull(body), parsed.isRecord,
        let error = parsed["error"], error.isRecord, let code = error["code"]?.stringValue
    {
        backendCode = code
    }
    throw DeviceSessionBackendError(status: response.status, backendCode: backendCode)
}

public func openDeviceSession(
    _ transport: BackendTransport,
    capturedAtMs: Int64?,
    captureId: String,
    deviceId: String,
    deviceName: String?,
    codec: Int
) async throws -> DeviceSessionRecord {
    guard isOptionalCaptureTimestamp(capturedAtMs), isCaptureUUID(captureId) else {
        throw DeviceSessionClientError.invalidRecordingIdentity
    }
    var members = [(String, JSONValue)]()
    if let capturedAtMs { members.append(("capturedAtMs", JSONValue.integer(capturedAtMs))) }
    members.append(("captureId", JSONValue.string(captureId)))
    members.append(("deviceId", JSONValue.string(deviceId)))
    if let deviceName { members.append(("deviceName", JSONValue.string(deviceName))) }
    members.append(("codec", JSONValue.integer(Int64(codec))))
    let response = try await transport.request(
        BackendRequest(
            id: "device-session-open-\(captureId)", method: .POST,
            path: "/v1/device-sessions", body: JSON.serialize(JSONValue.object(members))))
    try rejectIfUnusable(response)
    let session = try parseSessionValue(try parseObjectBody(response.body)["session"])
    if session.capturedAtMs != capturedAtMs || session.deviceId != deviceId
        || session.codec != codec || session.deviceName != deviceName
        || session.state == .failed
    {
        throw DeviceSessionClientError.unacknowledgedIdentity
    }
    return session
}

public func appendDeviceSessionAudio(
    _ transport: BackendTransport,
    sessionId: String,
    packets: [[UInt8]],
    chunkIndex: Int
) async throws -> DeviceSessionRecord {
    let byteCount = packets.reduce(0) { $0 + $1.count }
    if chunkIndex < 0 || packets.count < 1 || packets.count > 128
        || chunkIndex + packets.count > 65536 || byteCount > 1_048_576
        || packets.contains(where: { $0.isEmpty })
    {
        throw DeviceSessionClientError.invalidAudioBatch
    }
    let chunks = packets.enumerated().map { (offset, bytes) -> JSONValue in
        JSONValue.object([
            ("chunkIndex", JSONValue.integer(Int64(chunkIndex + offset))),
            ("bytesBase64", JSONValue.string(Base64Codec.encode(bytes))),
        ])
    }
    let body = JSON.serialize(JSONValue.object([("chunks", JSONValue.array(chunks))]))
    if body.count > 2_097_152 {
        throw DeviceSessionClientError.batchOverRequestLimit
    }
    let response = try await transport.request(
        BackendRequest(
            id: "device-session-audio-\(sessionId)-\(chunkIndex)-\(packets.count)",
            method: .POST, path: "/v1/device-sessions/\(sessionId)/audio",
            body: body))
    try rejectIfUnusable(response)
    let session = try parseSessionValue(try parseObjectBody(response.body)["session"])
    if session.id != sessionId || session.chunkCount < chunkIndex + packets.count
        || session.byteCount < byteCount || session.state == .failed
    {
        throw DeviceSessionClientError.unacknowledgedAudio
    }
    return session
}

public func completeDeviceSession(
    _ transport: BackendTransport, sessionId: String
) async throws -> DeviceSessionRecord {
    let response = try await transport.request(
        BackendRequest(
            id: "device-session-complete-\(sessionId)", method: .POST,
            path: "/v1/device-sessions/\(sessionId)/complete"))
    try rejectIfUnusable(response)
    let session = try parseSessionValue(try parseObjectBody(response.body)["session"])
    if session.id != sessionId || session.state != .complete {
        throw DeviceSessionClientError.unacknowledgedCompletion
    }
    return session
}

public func isTransientDeviceSessionError(_ error: Error) -> Bool {
    if let backendError = error as? DeviceSessionBackendError {
        return [0, 408, 429, 500, 502, 503, 504].contains(backendError.status)
    }
    // `TypeError` / `OMI_HTTP_TRANSPORT` in the TS client — a request that
    // could not be carried.
    return (error as? TransportFailure) == .transportFailed
}

public func transcribeDeviceSession(
    _ transport: BackendTransport, sessionId: String
) async throws -> RecordingTranscript {
    let response = try await transport.request(
        BackendRequest(
            id: "device-session-transcribe-\(sessionId)", method: .POST,
            path: "/v1/device-sessions/\(encodeQueryComponent(sessionId))/transcribe"))
    try rejectIfUnusable(response)
    let transcript: RecordingTranscript?
    if response.status == 200 || response.status == 202 {
        transcript = parseRecordingTranscript(response.body, sessionId: sessionId)
    } else {
        transcript = nil
    }
    guard let transcript else {
        throw DeviceSessionClientError.unacknowledgedTranscription
    }
    return transcript
}

/// Port of `parseRecordingTranscript`.
public func parseRecordingTranscript(
    _ body: String?, sessionId: String
) -> RecordingTranscript? {
    guard let body, body.count <= 3_000_000, let envelope = JSON.parseOrNull(body),
        envelope.isRecord, let value = envelope["transcription"], value.isRecord
    else { return nil }
    let state = value["state"]?.stringValue
    guard value["sessionId"]?.stringValue == sessionId,
        state == "queued" || state == "running" || state == "completed"
            || state == "failed",
        isNullValue(value["text"]) || value["text"]?.stringValue != nil,
        !(state == "completed" && value["text"]?.stringValue == nil),
        value["segments"]?.arrayValue != nil,
        isNullValue(value["language"]) || value["language"]?.stringValue != nil,
        isNullValue(value["errorCode"]) || value["errorCode"]?.stringValue != nil,
        let updatedAt = value["updatedAt"]?.safeIntegerValue, updatedAt >= 0,
        let discarded = value["discardedLeadingPackets"]?.safeIntegerValue,
        discarded >= 0
    else { return nil }
    return RecordingTranscript(
        sessionId: sessionId, state: state ?? "failed",
        text: value["text"]?.stringValue,
        errorCode: value["errorCode"]?.stringValue,
        discardedLeadingPackets: discarded
    )
}
