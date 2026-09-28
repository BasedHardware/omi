import Foundation

// Port of `react-native/src/taskMutationClient.ts` — task write identity,
// ambiguous-write retry semantics, and response classification. The
// canonical path mints the write id ONCE at prepare time and replays the
// exact envelope body; the Old plane reconciles an uncertain PATCH with a
// read-only GET.

public struct TaskPatch: Sendable, Equatable {
    public var completed: Bool?
    public var description: String?

    public init(completed: Bool? = nil, description: String? = nil) {
        self.completed = completed
        self.description = description
    }

    var isEmpty: Bool { completed == nil && description == nil }
    var keys: [String] {
        var keys = [String]()
        if completed != nil { keys.append("completed") }
        if description != nil { keys.append("description") }
        return keys
    }
}

/// A prepared, replayable task patch. Canonical patches carry the minted
/// write id; Old-plane patches remember whether a send was already attempted
/// so the next send is a read-only reconcile (`attemptedOmiPatches`).
public final class PreparedTaskPatch: @unchecked Sendable {
    public let apiContract: APIContract?
    public let recordId: String
    public let writeId: String?
    public let body: String
    var attemptedOmiPatch = false
    private let lock = NSLock()

    init(
        apiContract: APIContract?, recordId: String, writeId: String?, body: String
    ) {
        self.apiContract = apiContract
        self.recordId = recordId
        self.writeId = writeId
        self.body = body
    }

    var isOmiAttempted: Bool {
        lock.lock()
        defer { lock.unlock() }
        return attemptedOmiPatch
    }

    func markOmiAttempted() {
        lock.lock()
        attemptedOmiPatch = true
        lock.unlock()
    }
}

public enum TaskPatchResult: Sendable {
    case ok(revision: String?)
    case failed(failure: WriteFailure, controlUnavailable: Bool)

    public var okValue: String?? {
        if case .ok(let revision) = self { return .some(revision) }
        return nil
    }
}

public enum TaskMutationError: Error, Sendable, Equatable {
    case invalidEdit
    case missingRevisionIdentity
    case identityInvalid
    case writeIdentityUnavailable
    case backendChanged
}

func nowMilliseconds() -> Int64 {
    Int64(Date().timeIntervalSince1970 * 1000)
}

public func prepareTaskPatch(
    _ transport: BackendTransport,
    recordId: String,
    apiContract: APIContract? = nil,
    baseRevision: String?,
    accountEpoch: Int64?,
    patch: TaskPatch
) async throws -> PreparedTaskPatch {
    let keys = patch.keys
    if apiContract == .omi {
        let descriptionValid =
            patch.description == nil
            || !trimWhitespace(patch.description ?? "").isEmpty
        if recordId.isEmpty || recordId.count > 256 || keys.isEmpty
            || !descriptionValid
        {
            throw TaskMutationError.invalidEdit
        }
        guard await transport.apiContract() == .omi else {
            throw TaskMutationError.backendChanged
        }
        return PreparedTaskPatch(
            apiContract: .omi, recordId: recordId, writeId: nil,
            body: JSON.serialize(
                JSONValue.object(
                    (patch.completed.map { [("completed", JSONValue.bool($0))] } ?? [])
                        + (patch.description.map { [("description", JSONValue.string($0))] } ?? [])
                ))
        )
    }
    let revisionPattern = baseRevision.map { isRevision($0) } ?? false
    if accountEpoch == nil || baseRevision == nil || !revisionPattern
        || keys.isEmpty
    {
        throw TaskMutationError.missingRevisionIdentity
    }
    guard let epoch = accountEpoch, epoch >= 0 else {
        throw TaskMutationError.missingRevisionIdentity
    }
    let updatedAt = nowMilliseconds()
    let writeId = try await transport.createWriteId()
    let patchValue = canonicalPatchJSON(patch, updatedAt: updatedAt)
    let built = buildWriteOpEnvelope(
        domain: "tasks", writeId: writeId,
        op: .patch(
            recordId: recordId, patch: patchValue, baseRevision: baseRevision),
        accountEpoch: epoch
    )
    guard let built = built.okValue, isTrustedWriteOpEnvelope(built.envelope.json)
    else {
        throw TaskMutationError.identityInvalid
    }
    return PreparedTaskPatch(
        apiContract: nil, recordId: recordId, writeId: writeId,
        body: JSON.serialize(built.envelope.json)
    )
}

/// The canonical patch: every field set gets `updatedAt`, and a `completed`
/// edit pins `completedAt` to the same instant (null when reopening).
private func canonicalPatchJSON(_ patch: TaskPatch, updatedAt: Int64) -> JSONValue {
    var members = [(String, JSONValue)]()
    if let completed = patch.completed { members.append(("completed", JSONValue.bool(completed))) }
    if let description = patch.description {
        members.append(("description", JSONValue.string(description)))
    }
    members.append(("updatedAt", JSONValue.integer(updatedAt)))
    if patch.completed != nil {
        members.append(
            (
                "completedAt",
                patch.completed! ? JSONValue.integer(updatedAt) : .null
            ))
    }
    return JSONValue.object(members)
}

func taskConflict() -> TaskPatchResult {
    .failed(
        failure: .permanent(
            reason: .conflict, detail: "Review the current task before another edit"),
        controlUnavailable: false)
}

func backendChanged(_ error: Error) -> Bool {
    error is BackendChangedError
}

public func sendTaskPatch(
    _ transport: BackendTransport, _ prepared: PreparedTaskPatch
) async -> TaskPatchResult {
    if prepared.apiContract == .omi {
        return await sendOmiTaskPatch(transport, prepared)
    }
    let retryable = { (detail: String) -> TaskPatchResult in
        .failed(failure: .retryable(unclassified: true, detail: detail), controlUnavailable: false)
    }
    let response: BackendResponse
    do {
        response = try await transport.request(
            BackendRequest(
                id: "task-write-\(prepared.writeId ?? "")",
                expectedApiContract: .canonical, method: .POST,
                path: "/v1/tasks/ops", body: prepared.body))
    } catch {
        if backendChanged(error) { return taskConflict() }
        return retryable("Task edit could not be confirmed by the transport")
    }
    let json = JSON.parseOrNull(response.body ?? "null")
    if response.status == 200 {
        guard let accepted = isTrustedWriteAccepted(json), accepted.revision != nil else {
            return retryable("Task edit acknowledgement could not be verified")
        }
        return .ok(revision: accepted.revision)
    }
    let classified = ClassifiedResponse(
        status: response.status, body: response.body,
        retryAfterSeconds: response.retryAfterSeconds)
    guard let failure = classifyWriteOpsResponse(classified, "Task edit") else {
        return retryable("Task edit response could not be classified")
    }
    return .failed(
        failure: failure, controlUnavailable: isControlUnavailable(classified))
}

func sendOmiTaskPatch(
    _ transport: BackendTransport, _ prepared: PreparedTaskPatch
) async -> TaskPatchResult {
    let unknown = { () -> TaskPatchResult in
        .failed(
            failure: .retryable(
                unclassified: true,
                detail: "Task edit is unconfirmed; check the saved task before any further edit"),
            controlUnavailable: false)
    }
    do {
        guard await transport.apiContract() == .omi else { return taskConflict() }
        let reconcile = prepared.isOmiAttempted
        prepared.markOmiAttempted()
        let encodedRecordId = encodeQueryComponent(prepared.recordId)
        let request = BackendRequest(
            id: "omi-task-\(prepared.recordId)", expectedApiContract: .omi,
            method: reconcile ? .GET : .PATCH,
            path: "/v1/action-items/\(encodedRecordId)",
            body: reconcile ? nil : prepared.body)
        let response = try await transport.request(request)
        if response.status == 401 {
            return .failed(
                failure: .authInvalid(detail: "Sign in before editing tasks"),
                controlUnavailable: false)
        }
        if response.status == 429 {
            let seconds = response.retryAfterSeconds
            let retryAfterMs =
                (seconds != nil && seconds! >= 0) ? seconds! * 1000 : 1000
            return .failed(
                failure: .rateLimited(
                    retryAfterMilliseconds: retryAfterMs,
                    detail: "Wait before checking the saved task"),
                controlUnavailable: false)
        }
        if [400, 403, 404, 409, 422].contains(response.status) {
            let reason: WriteFailure.PermanentReason =
                response.status == 409
                ? .conflict
                : response.status == 404 ? .gone : .validation
            return .failed(
                failure: .permanent(
                    reason: reason,
                    detail: "The service did not accept this task edit"),
                controlUnavailable: false)
        }
        if response.status != 200 { return unknown() }
        guard let item = JSON.parseOrNull(response.body ?? "null"), item.isRecord,
            let patch = JSON.parseOrNull(prepared.body), patch.isRecord
        else { return unknown() }
        guard
            item["id"]?.stringValue == prepared.recordId,
            item["completed"]?.boolValue != nil,
            item["description"]?.stringValue != nil
        else { return unknown() }
        for (key, desired) in patch.objectValue ?? [] {
            let actual: JSONValue? = item[key]
            let matches: Bool
            switch desired {
            case JSONValue.bool(let value): matches = actual?.boolValue == value
            case JSONValue.string(let value): matches = actual?.stringValue == value
            case JSONValue.number(let value): matches = actual?.numberValue == value
            case .null: matches = (actual?.isNull ?? true)
            default: matches = false
            }
            if !matches {
                return reconcile ? taskConflict() : unknown()
            }
        }
        return .ok(revision: nil)
    } catch {
        return backendChanged(error) ? taskConflict() : unknown()
    }
}
