import Foundation
import OmiCore
import OmiNetwork

/// What the phone-call endpoints received, and how they answer.
public final class FakePhoneCalls: @unchecked Sendable {
    let lock = NSLock()
    public var numbers: [VerifiedPhoneNumber] = []
    /// `startPhoneVerification` answers with this, or throws `verifyError`.
    public var verification = PhoneVerification(phoneNumber: "", validationCode: "123456", status: "pending")
    public var verifyError: APIError?
    /// One answer per poll, in order; `true` also stores the number. Empty: not verified yet.
    public var checkAnswers: [Bool] = []
    public var deleteError: APIError?
    public var tokenError: APIError?
    public var socketError: APIError?
    public var quota: PhoneCallQuota?
    public var history: [Conversation] = []
    /// Every socket opened, in order; the newest is `socket`.
    public fileprivate(set) var sockets: [FakePhoneCallChannel] = []
    public fileprivate(set) var socketRequests: [SocketRequest] = []
    public fileprivate(set) var verifyRequests: [String] = []
    public fileprivate(set) var checkRequests: [String] = []
    public fileprivate(set) var deleted: [String] = []
    public fileprivate(set) var tokenRequests = 0

    public struct SocketRequest: Sendable {
        public let uid: String
        public let callID: String
        public let language: String
    }

    init() {}

    public var socket: FakePhoneCallChannel? {
        lock.withLock { sockets.last }
    }

    func record(_ update: (FakePhoneCalls) throws -> Void) rethrows {
        try lock.withLock { try update(self) }
    }
}

public extension FakeAPIClient {
    func verifiedPhoneNumbers() async throws -> [VerifiedPhoneNumber] {
        if let failure = lock.withLock({ _error }) { throw failure }
        return phoneCalls.lock.withLock { phoneCalls.numbers }
    }

    func startPhoneVerification(phoneNumber: String) async throws -> PhoneVerification {
        try phoneCalls.record { calls in
            calls.verifyRequests.append(phoneNumber)
            if let error = calls.verifyError { throw error }
        }
        let answer = phoneCalls.lock.withLock { phoneCalls.verification }
        return PhoneVerification(phoneNumber: phoneNumber, validationCode: answer.validationCode, status: answer.status)
    }

    func checkPhoneVerification(phoneNumber: String) async throws -> Bool {
        phoneCalls.record { calls in
            calls.checkRequests.append(phoneNumber)
            guard !calls.checkAnswers.isEmpty, calls.checkAnswers.removeFirst() else { return }
            calls.numbers.append(VerifiedPhoneNumber(
                id: "n\(calls.numbers.count + 1)", phoneNumber: phoneNumber, verifiedAt: Fixtures.now, isPrimary: calls.numbers.isEmpty
            ))
        }
        return phoneCalls.lock.withLock { phoneCalls.numbers.contains { $0.phoneNumber == phoneNumber } }
    }

    func deletePhoneNumber(id: String) async throws {
        try phoneCalls.record { calls in
            if let error = calls.deleteError { throw error }
            calls.deleted.append(id)
            calls.numbers.removeAll { $0.id == id }
        }
    }

    func phoneCallToken() async throws -> PhoneCallToken {
        try phoneCalls.record { calls in
            calls.tokenRequests += 1
            if let error = calls.tokenError { throw error }
        }
        return PhoneCallToken(accessToken: "twilio-token", ttl: 3600, identity: "uid-1")
    }

    func phoneCallQuota() async throws -> PhoneCallQuota? {
        phoneCalls.lock.withLock { phoneCalls.quota }
    }

    func phoneCallConversations(limit: Int, offset: Int) async throws -> [Conversation] {
        phoneCalls.lock.withLock { Array(phoneCalls.history.dropFirst(offset).prefix(limit)) }
    }

    func openPhoneCallSocket(uid: String, callID: String, language: String) async throws -> any PhoneCallTranscriptChannel {
        let socket = FakePhoneCallChannel()
        try phoneCalls.record { calls in
            if let error = calls.socketError { throw error }
            calls.sockets.append(socket)
            calls.socketRequests.append(FakePhoneCalls.SocketRequest(uid: uid, callID: callID, language: language))
        }
        return socket
    }
}

/// Records the frames a call sends; tests push server messages through `emit`.
public final class FakePhoneCallChannel: PhoneCallTranscriptChannel, @unchecked Sendable {
    public let events: AsyncStream<PhoneCallSocketEvent>
    private let continuation: AsyncStream<PhoneCallSocketEvent>.Continuation
    private let lock = NSLock()
    private var _frames: [Data] = []
    private var _closed = false

    public init() {
        (events, continuation) = AsyncStream.makeStream(of: PhoneCallSocketEvent.self)
    }

    public var frames: [Data] {
        lock.withLock { _frames }
    }

    public var isClosed: Bool {
        lock.withLock { _closed }
    }

    public func emit(_ event: PhoneCallSocketEvent) {
        continuation.yield(event)
    }

    /// The server dropped the socket.
    public func drop() {
        continuation.yield(.closed("dropped"))
        continuation.finish()
    }

    public func send(frame: Data) {
        lock.withLock { _frames.append(frame) }
    }

    public func close() {
        lock.withLock { _closed = true }
        continuation.finish()
    }
}
