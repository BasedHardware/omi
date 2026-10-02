import XCTest

@testable import OmiKit

final class RecordingJournalClientTests: XCTestCase {
    func testRecordingJournalTransportDelegatesForeignHandleToScopedStore() async throws {
        let vault = JournalPartitionVault()
        let accountA = OwnerScopedJournalTransport(owner: "account-a", vault: vault)
        let input = RecordingJournalInput(
            capturedAtMs: 1_000, deviceId: "omi-1", deviceName: "NotePin", codec: 1)
        let journal = try await createRecordingJournal(accountA, input: input)

        let accountB = OwnerScopedJournalTransport(owner: "account-b", vault: vault)
        let visibleToB = try await accountB.listRecordingJournals()
        XCTAssertTrue(visibleToB.isEmpty)

        do {
            _ = try await accountB.readRecordingJournal(handle: journal.handle)
            XCTFail("A different owner must not read the journal")
        } catch {
            XCTAssertEqual(error as? JournalPartitionError, .foreignHandle)
        }

        let accountATransport = try recordingJournalBackend(accountA, handle: journal.handle)
        let allowed = try await accountATransport.request(
            BackendRequest(method: .POST, path: "/v1/device-sessions"))
        XCTAssertEqual(allowed.status, 200)

        let accountBTransport = try recordingJournalBackend(accountB, handle: journal.handle)
        do {
            _ = try await accountBTransport.request(
                BackendRequest(method: .POST, path: "/v1/device-sessions"))
            XCTFail("The journal transport must preserve its current store's owner scope")
        } catch {
            XCTAssertEqual(error as? JournalPartitionError, .foreignHandle)
        }

        await accountB.removeRecordingJournal(handle: journal.handle)
        let retainedForA = try await accountA.readRecordingJournal(handle: journal.handle)
        XCTAssertEqual(retainedForA, journal)
    }
}

// This in-memory store models the documented owner-scoped capability. The
// test exercises OmiKit's transport wrapper against that protocol boundary;
// it does not claim a production host persistence implementation exists.
private enum JournalPartitionError: Error, Sendable, Equatable {
    case missingHandle
    case foreignHandle
}

private actor JournalPartitionVault {
    private var ownerByHandle: [String: String] = [:]
    private var records: [String: RecordingJournalRecord] = [:]

    func create(
        owner: String, input: RecordingJournalInput, captureId: String
    ) -> RecordingJournalRecord {
        let record = RecordingJournalRecord(
            capturedAtMs: input.capturedAtMs, handle: captureId, captureId: captureId,
            deviceId: input.deviceId, deviceName: input.deviceName, codec: input.codec,
            sessionId: nil, entries: [])
        ownerByHandle[record.handle] = owner
        records[record.handle] = record
        return record
    }

    func list(owner: String) -> [RecordingJournalRecord] {
        records.values.filter { ownerByHandle[$0.handle] == owner }
            .sorted { $0.handle < $1.handle }
    }

    func read(owner: String, handle: String) throws -> RecordingJournalRecord {
        guard let record = records[handle], let actualOwner = ownerByHandle[handle] else {
            throw JournalPartitionError.missingHandle
        }
        guard actualOwner == owner else { throw JournalPartitionError.foreignHandle }
        return record
    }

    func append(owner: String, handle: String, entry: String) throws -> Int {
        var record = try read(owner: owner, handle: handle)
        record.entries.append(entry)
        records[handle] = record
        return record.entries.count
    }

    func request(
        owner: String, handle: String, request: BackendRequest
    ) throws -> BackendResponse {
        _ = try read(owner: owner, handle: handle)
        return BackendResponse(id: request.id, status: 200, body: nil)
    }

    func remove(owner: String, handle: String) {
        guard ownerByHandle[handle] == owner else { return }
        ownerByHandle.removeValue(forKey: handle)
        records.removeValue(forKey: handle)
    }
}

private actor OwnerScopedJournalTransport: BackendTransport, RecordingJournalStoring {
    private let owner: String
    private let vault: JournalPartitionVault

    init(owner: String, vault: JournalPartitionVault) {
        self.owner = owner
        self.vault = vault
    }

    func request(_ request: BackendRequest) async throws -> BackendResponse {
        BackendResponse(id: request.id, status: 200, body: nil)
    }

    func generationEvents(
        generationId: String, lastEventId: String?,
        onFrame: @escaping @Sendable (String) -> Void
    ) async throws -> BackendResponse {
        _ = lastEventId
        _ = onFrame
        return BackendResponse(id: generationId, status: 200, body: nil)
    }

    func cancelGenerationEvents(generationId: String) async { _ = generationId }
    func createWriteId() async throws -> String { "write-id" }
    func createRecordingId() async throws -> String { Self.captureID }
    func apiContract() async -> APIContract? { .canonical }
    func softwarePlane() async -> SoftwarePlane? { .new }
    func setSoftwarePlane(_ plane: SoftwarePlane) async -> SoftwarePlane? { plane }
    func stampedBackendOrigin() async -> String? { nil }

    func createRecordingJournal(
        _ input: RecordingJournalInput
    ) async throws -> RecordingJournalRecord {
        await vault.create(owner: owner, input: input, captureId: Self.captureID)
    }

    func listRecordingJournals() async throws -> [RecordingJournalRecord] {
        await vault.list(owner: owner)
    }

    func readRecordingJournal(handle: String) async throws -> RecordingJournalRecord {
        try await vault.read(owner: owner, handle: handle)
    }

    func appendRecordingJournal(handle: String, entry: String) async throws -> Int {
        try await vault.append(owner: owner, handle: handle, entry: entry)
    }

    func requestRecordingJournal(
        handle: String, request: BackendRequest
    ) async throws -> BackendResponse {
        try await vault.request(owner: owner, handle: handle, request: request)
    }

    func removeRecordingJournal(handle: String) async {
        await vault.remove(owner: owner, handle: handle)
    }

    private static let captureID = "123e4567-e89b-42d3-a456-426614174000"
}
