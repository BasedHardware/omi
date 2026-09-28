import Foundation

// Port of the ratified write wire codecs:
//   - `packages/contracts/ratified/src/write/ops.ts` (grammar, refusals,
//     availability signal, accepted shape)
//   - `packages/kernel/src/http-status.ts` (`classifyStatus`)
//   - `packages/adapters-platform/src/write-ops.ts` (envelope building and
//     response classification)

// MARK: - WriteFailure taxonomy (packages/contracts/src/errors.ts)

/// The write/transport error taxonomy. Exactly one kind per failure;
/// `retryable(unclassified: true)` is the taxonomy gap, never a guess.
public enum WriteFailure: Sendable, Equatable {
    case retryable(unclassified: Bool, detail: String)
    case rateLimited(retryAfterMilliseconds: Int, detail: String)
    case authInvalid(detail: String)
    case permanent(reason: PermanentReason, detail: String)

    public enum PermanentReason: String, Sendable, Equatable {
        case validation
        case oversize
        case conflict
        case entitlement
        case gone
        case staleEpoch = "stale_epoch"
    }

    public var kind: String {
        switch self {
        case .retryable: return "retryable"
        case .rateLimited: return "rate-limited"
        case .authInvalid: return "auth-invalid"
        case .permanent: return "permanent"
        }
    }

    public var detail: String {
        switch self {
        case .retryable(_, let detail), .rateLimited(_, let detail),
            .authInvalid(let detail), .permanent(_, let detail):
            return detail
        }
    }

    public var permanentReason: PermanentReason? {
        if case .permanent(let reason, _) = self { return reason }
        return nil
    }
}

/// An HTTP response as the status classifiers see it.
public struct ClassifiedResponse: Sendable {
    public var status: Int
    public var body: String?
    public var retryAfterSeconds: Int?

    public init(status: Int, body: String?, retryAfterSeconds: Int? = nil) {
        self.status = status
        self.body = body
        self.retryAfterSeconds = retryAfterSeconds
    }

    public var retryAfterMilliseconds: Int? {
        retryAfterSeconds.map { $0 * 1000 }
    }
}

// MARK: - classifyStatus (kernel)

/// The one place an HTTP status becomes taxonomy.
public func classifyStatus(_ response: ClassifiedResponse, _ detail: String) -> WriteFailure {
    let status = response.status
    if status == 401 || status == 403 { return .authInvalid(detail: detail) }
    if status == 429 {
        return .rateLimited(retryAfterMilliseconds: response.retryAfterMilliseconds ?? 30_000, detail: detail)
    }
    if status == 404 || status == 410 { return .permanent(reason: .gone, detail: detail) }
    if status == 409 { return .permanent(reason: .conflict, detail: detail) }
    if status == 402 { return .permanent(reason: .entitlement, detail: detail) }
    if status == 413 { return .permanent(reason: .oversize, detail: detail) }
    if status == 400 || status == 422 { return .permanent(reason: .validation, detail: detail) }
    if status >= 500 || status == 408 { return .retryable(unclassified: false, detail: detail) }
    return .retryable(unclassified: true, detail: "unmapped status \(status): \(detail)")
}

// MARK: - Write id and envelope grammar (ratified write/ops.ts)

public let WRITE_ID_ENTROPY_BYTES = 32
public let MAX_WRITE_ENVELOPE_JSON_CODE_UNITS = 1_000_000

/// The wire grammar: 64 lowercase hex characters.
public func parseWriteId(_ raw: String) -> String? {
    let bytes = Array(raw.utf8)
    guard bytes.count == 64 else { return nil }
    for byte in bytes {
        let isHex =
            (byte >= UInt8(ascii: "0") && byte <= UInt8(ascii: "9"))
            || (byte >= UInt8(ascii: "a") && byte <= UInt8(ascii: "f"))
        guard isHex else { return nil }
    }
    return raw
}

/// Hex-encode 32 caller-supplied random bytes into a write id; nil on a
/// wrong-length input (the caller owns the entropy).
public func mintWriteId(_ entropy: [UInt8]) -> String? {
    guard entropy.count == WRITE_ID_ENTROPY_BYTES else { return nil }
    let hexBytes = Array("0123456789abcdef".utf8)
    var output = [UInt8]()
    output.reserveCapacity(64)
    for byte in entropy {
        output.append(hexBytes[Int(byte >> 4)])
        output.append(hexBytes[Int(byte & 0x0F)])
    }
    return String(decoding: output, as: UTF8.self)
}

/// Domains that accept client writes. Memories is read-only by ratified
/// design; an envelope naming it must be refused as validation.
public let WRITABLE_DOMAINS = ["tasks"]

public func isWritableDomain(_ value: String) -> Bool {
    WRITABLE_DOMAINS.contains(value)
}

/// B4: the one route shape, built never hand-spelled.
public func writeOpsPath(_ domain: String) -> String {
    "/v1/\(domain)/ops"
}

/// Write operation over ordered JSON values.
public enum WriteOp: Sendable, Equatable {
    case create(recordId: String, content: JSONValue)
    case patch(recordId: String, patch: JSONValue, baseRevision: String?)
    case delete(recordId: String, baseRevision: String?)
}

public struct WriteOpEnvelope: Sendable, Equatable {
    public var writeId: String
    public var accountEpoch: Int64
    public var domain: String
    public var op: WriteOp

    public init(writeId: String, accountEpoch: Int64, domain: String, op: WriteOp) {
        self.writeId = writeId
        self.accountEpoch = accountEpoch
        self.domain = domain
        self.op = op
    }

    public var json: JSONValue {
        JSONValue.object([
            ("write_id", JSONValue.string(writeId)),
            ("account_epoch", JSONValue.integer(accountEpoch)),
            ("domain", JSONValue.string(domain)),
            ("op", WriteOps.opJSON(op)),
        ])
    }
}

enum WriteOps {
    static func opJSON(_ op: WriteOp) -> JSONValue {
        switch op {
        case .create(let recordId, let content):
            return JSONValue.object([
                ("op", JSONValue.string("create")),
                ("record_id", JSONValue.string(recordId)),
                ("content", content),
            ])
        case .patch(let recordId, let patch, let baseRevision):
            var members: [(String, JSONValue)] = [
                ("op", JSONValue.string("patch")),
                ("record_id", JSONValue.string(recordId)),
                ("patch", patch),
            ]
            if let baseRevision {
                members.append(("base_revision", JSONValue.string(baseRevision)))
            }
            return JSONValue.object(members)
        case .delete(let recordId, let baseRevision):
            var members: [(String, JSONValue)] = [
                ("op", JSONValue.string("delete")),
                ("record_id", JSONValue.string(recordId)),
            ]
            if let baseRevision {
                members.append(("base_revision", JSONValue.string(baseRevision)))
            }
            return JSONValue.object(members)
        }
    }
}

let RECORD_ID_MAX_LENGTH = 256
let REVISION_LENGTH = 64

func isRecordId(_ value: String) -> Bool {
    let bytes = Array(value.utf8)
    guard !bytes.isEmpty, bytes.count <= RECORD_ID_MAX_LENGTH else { return false }
    // [\x21-\x7e] — printable ASCII without space.
    return bytes.allSatisfy { $0 >= 0x21 && $0 <= 0x7E }
}

func isRevision(_ value: String) -> Bool {
    guard value.count == REVISION_LENGTH else { return false }
    for scalar in value.unicodeScalars {
        let ok =
            (scalar.value >= 0x30 && scalar.value <= 0x39)
            || (scalar.value >= 0x61 && scalar.value <= 0x66)
        if !ok { return false }
    }
    return true
}

/// Strict predicate over already-parsed trusted JSON (write/ops.ts
/// `isWriteOp` + `isTrustedWriteOpEnvelope`).
public func isTrustedWriteOpEnvelope(_ value: JSONValue?) -> Bool {
    guard let envelope = value, case .object(let members)? = value, members.count == 4
    else { return false }
    guard let writeId = envelope["write_id"]?.stringValue,
        parseWriteId(writeId) != nil,
        let epoch = envelope["account_epoch"]?.safeIntegerValue, epoch >= 0,
        let domain = envelope["domain"]?.stringValue, isWritableDomain(domain),
        envelope["op"]?.isRecord == true
    else { return false }
    return isWriteOp(envelope["op"]!)
}

private func isWriteOp(_ op: JSONValue) -> Bool {
    guard let kind = op["op"]?.stringValue else { return false }
    guard let recordId = op["record_id"]?.stringValue, isRecordId(recordId) else { return false }
    let base = op["base_revision"]
    let baseOk =
        base == nil
        || (base?.stringValue != nil && isRevision(base!.stringValue!))
    switch kind {
    case "create":
        // A create carries no precondition.
        return op.objectValue!.count == 3 && op["content"]?.isRecord == true
    case "patch":
        let shapeOk = op.objectValue!.count == 3 || op.objectValue!.count == 4
        return baseOk && op["patch"]?.isRecord == true && shapeOk
    case "delete":
        return baseOk && (op.objectValue!.count == 2 || op.objectValue!.count == 3)
    default:
        return false
    }
}

// MARK: - buildWriteOpEnvelope (adapters-platform write-ops.ts)

public enum EnvelopeBuildFailure: Sendable, Equatable {
    case noJournaledWriteId
    case unwritableDomain(String)
    case malformedWriteId
}

public enum EnvelopeBuild: Sendable {
    case ok(path: String, envelope: WriteOpEnvelope)
    case failure(EnvelopeBuildFailure)

    public var okValue: (path: String, envelope: WriteOpEnvelope)? {
        if case .ok(let path, let envelope) = self { return (path, envelope) }
        return nil
    }
}

/// B1: an op with no journaled write id CANNOT be sent — there is no correct
/// convenience here, only refusal, because a send-time mint or a derived id
/// would defeat the server dedupe registry on replay.
public func buildWriteOpEnvelope(
    domain: String, writeId: String?, op: WriteOp, accountEpoch: Int64
) -> EnvelopeBuild {
    guard let writeId else { return .failure(.noJournaledWriteId) }
    guard parseWriteId(writeId) != nil else { return .failure(.malformedWriteId) }
    guard isWritableDomain(domain) else { return .failure(.unwritableDomain(domain)) }
    return .ok(
        path: writeOpsPath(domain),
        envelope: WriteOpEnvelope(
            writeId: writeId, accountEpoch: accountEpoch, domain: domain, op: op)
    )
}

// MARK: - Refusal outcomes and availability signal

public enum WriteRefusalOutcome: String, Sendable, Equatable {
    case authentication
    case authorization
    case entitlement
    case staleEpoch = "stale_epoch"
}

/// The fixed refusal bodies, as literal strings: byte-identical per class.
public let WRITE_REFUSALS: [(WriteRefusalOutcome, Int, String)] = [
    (
        .authentication, 401,
        "{\"error\":\"unauthorized\",\"refusal_outcome\":\"authentication\"}"
    ),
    (
        .authorization, 403,
        "{\"error\":\"forbidden\",\"refusal_outcome\":\"authorization\"}"
    ),
    (
        .entitlement, 403,
        "{\"error\":\"forbidden\",\"refusal_outcome\":\"entitlement\"}"
    ),
    (
        .staleEpoch, 409,
        "{\"error\":\"stale_epoch\",\"refusal_outcome\":\"stale_epoch\"}"
    ),
]

public let CONTROL_UNAVAILABLE_RETRY_AFTER_SECONDS = 60
let CONTROL_UNAVAILABLE_BODY =
    "{\"error\":\"maintenance\",\"refusal_outcome\":\"control_unavailable\"}"

/// Read the refusal class off a response body without trusting the status.
public func readWriteRefusalOutcome(_ status: Int, _ body: String) -> WriteRefusalOutcome? {
    for (outcome, refusalStatus, refusalBody) in WRITE_REFUSALS
    where refusalStatus == status && refusalBody == body {
        return outcome
    }
    return nil
}

/// The fifth value — an availability signal, deliberately NOT a refusal
/// outcome: refresh control state, then drain the op wherever authority lives.
public func readWriteAvailabilitySignal(_ status: Int, _ body: String) -> Bool {
    status == 503 && body == CONTROL_UNAVAILABLE_BODY
}

// MARK: - Write accepted shape

public struct WriteAccepted: Sendable, Equatable {
    public var recordId: String
    public var revision: String?
    public var idempotent: Bool
}

public func isTrustedWriteAccepted(_ value: JSONValue?) -> WriteAccepted? {
    guard let value, case .object(let members) = value, members.count == 2,
        let applied = value["applied"], applied.isRecord,
        applied.objectValue?.count == 2,
        let idempotent = value["idempotent"]?.boolValue
    else { return nil }
    guard let recordId = applied["record_id"]?.stringValue, isRecordId(recordId) else {
        return nil
    }
    let revisionJSON = applied["revision"]
    let revision: String?
    if revisionJSON?.isNull == true {
        revision = nil
    } else if let text = revisionJSON?.stringValue, isRevision(text) {
        revision = text
    } else {
        return nil
    }
    return WriteAccepted(recordId: recordId, revision: revision, idempotent: idempotent)
}

// MARK: - classifyWriteOpsResponse / isControlUnavailable

/// Turn a write-ops response into the client taxonomy. `detail` is
/// diagnostic text for the dead-letter surface and never carries a
/// server-supplied string.
public func classifyWriteOpsResponse(
    _ response: ClassifiedResponse, _ detail: String
) -> WriteFailure? {
    if response.status == 200 { return nil }
    let body = response.body
    let outcome: WriteRefusalOutcome?
    if let body {
        outcome = readWriteRefusalOutcome(response.status, body)
    } else {
        outcome = nil
    }
    switch outcome {
    case .authentication, .authorization:
        // The outbox PAUSES, never drops; re-auth then replays under the same
        // journaled write_id.
        return .authInvalid(detail: detail)
    case .entitlement:
        return .permanent(reason: .entitlement, detail: detail)
    case .staleEpoch:
        // B2. Never `conflict`. Never `gone`.
        return .permanent(reason: .staleEpoch, detail: detail)
    case nil:
        break
    }
    // Not a refusal class. `write_id_reuse` is a 409 that means the adapter
    // laundered two different ops through one key — a client defect.
    if let body, response.status == 409, body == "{\"error\":\"write_id_reuse\"}" {
        return .permanent(reason: .validation, detail: detail)
    }
    // `control_unavailable` is backpressure; 503 classifies retryable either
    // way, but the signal must stay separately readable.
    return classifyStatus(response, detail)
}

/// Did the server say it cannot decide about this account right now?
public func isControlUnavailable(_ response: ClassifiedResponse) -> Bool {
    guard let body = response.body else { return false }
    return readWriteAvailabilitySignal(response.status, body)
}
