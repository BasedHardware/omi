#if !SKIP && canImport(CryptoKit)
  import CryptoKit
  import Foundation
  import XCTest
  @testable import OmiKit

  /// These tests use synthetic owners and an ephemeral AES-GCM key. They exercise
  /// the file adapter only; they do not verify ownership or exercise host capture.
  final class EncryptedRecordingJournalTransportTests: XCTestCase {
    func testJournalFilesAreEncryptedAndPartitionsAreAccountScoped() async throws {
      let root = try temporaryRoot()
      defer { try? FileManager.default.removeItem(at: root) }
      let vault = SyntheticRecordingJournalVault()
      let files = POSIXAtomicRecordingJournalFiles()
      let ownerA = owner(key: String(repeating: "a", count: 64))
      let providerA = TestRecordingJournalOwnerProvider(ownerA)
      let adapterA = makeAdapter(
        ownerProvider: providerA, backend: TestRecordingJournalBackend(),
        vault: vault, files: files, root: root)

      let journal = try await createJournal(on: adapterA)
      _ = try await adapterA.appendRecordingJournal(
        handle: journal.handle, entry: packetEntry, expectedEntryCount: 1)

      let partitionA = try vault.partitionIdentifier(for: ownerA)
      let journalURL = journalURL(root: root, partition: partitionA, handle: journal.handle)
      let ciphertext = try Data(contentsOf: journalURL)
      XCTAssertNil(ciphertext.range(of: Data("device-1".utf8)))
      XCTAssertNil(ciphertext.range(of: Data("Synthetic Pin".utf8)))
      let fileAttributes = try FileManager.default.attributesOfItem(atPath: journalURL.path)
      XCTAssertEqual((fileAttributes[.posixPermissions] as? NSNumber)?.intValue, 0o600)
      let directoryAttributes = try FileManager.default.attributesOfItem(
        atPath: journalURL.deletingLastPathComponent().path)
      XCTAssertEqual(
        (directoryAttributes[.posixPermissions] as? NSNumber)?.intValue, 0o700)

      let ownerB = owner(key: String(repeating: "b", count: 64))
      let adapterB = makeAdapter(
        ownerProvider: TestRecordingJournalOwnerProvider(ownerB),
        backend: TestRecordingJournalBackend(), vault: vault, files: files, root: root)
      let ownerBJournals = try await adapterB.listRecordingJournals()
      XCTAssertTrue(ownerBJournals.isEmpty)
      let foreignRead = await capturedError {
        try await adapterB.readRecordingJournal(handle: journal.handle)
      }
      XCTAssertEqual(foreignRead as? EncryptedRecordingJournalError, .journalNotFound)
      await adapterB.removeRecordingJournal(handle: journal.handle)
      let remainingForA = try await adapterA.readRecordingJournal(handle: journal.handle)
      XCTAssertEqual(remainingForA.entries, [packetEntry])
    }

    func testJournalFileLimitIsGlobalAcrossOwnerPartitions() async throws {
      let root = try temporaryRoot()
      defer { try? FileManager.default.removeItem(at: root) }
      let vault = SyntheticRecordingJournalVault()
      let files = POSIXAtomicRecordingJournalFiles()
      let adapterA = makeAdapter(
        ownerProvider: TestRecordingJournalOwnerProvider(
          owner(key: String(repeating: "a", count: 64))),
        backend: TestRecordingJournalBackend(), vault: vault, files: files, root: root)
      let adapterB = makeAdapter(
        ownerProvider: TestRecordingJournalOwnerProvider(
          owner(key: String(repeating: "b", count: 64))),
        backend: TestRecordingJournalBackend(), vault: vault, files: files, root: root)

      for _ in 0..<32 {
        let input = journalInput(captureId: UUID().uuidString)
        _ = try await createJournal(on: adapterA, input: input)
      }
      for _ in 0..<32 {
        let input = journalInput(captureId: UUID().uuidString)
        _ = try await createJournal(on: adapterB, input: input)
      }
      let overflow = await capturedError {
        let input = journalInput(captureId: UUID().uuidString)
        _ = try await createJournal(on: adapterB, input: input)
      }

      XCTAssertEqual(overflow as? EncryptedRecordingJournalError, .storageLimitExceeded)
      let journalsA = try await adapterA.listRecordingJournals()
      let journalsB = try await adapterB.listRecordingJournals()
      XCTAssertEqual(journalsA.count, 32)
      XCTAssertEqual(journalsB.count, 32)
    }

    func testConcurrentOwnersCannotPassTheGlobalFileQuotaTogether() async throws {
      let root = try temporaryRoot()
      defer { try? FileManager.default.removeItem(at: root) }
      let vault = SyntheticRecordingJournalVault()
      let providerA = TestRecordingJournalOwnerProvider(
        owner(key: String(repeating: "a", count: 64)))
      let providerB = TestRecordingJournalOwnerProvider(
        owner(key: String(repeating: "b", count: 64)))
      let adapterA = makeAdapter(
        ownerProvider: providerA,
        backend: TestRecordingJournalBackend(), vault: vault,
        files: POSIXAtomicRecordingJournalFiles(), root: root)
      let adapterB = makeAdapter(
        ownerProvider: providerB,
        backend: TestRecordingJournalBackend(), vault: vault,
        files: POSIXAtomicRecordingJournalFiles(), root: root)

      for _ in 0..<32 {
        _ = try await createJournal(
          on: adapterA, input: journalInput(captureId: UUID().uuidString))
      }
      for _ in 0..<31 {
        _ = try await createJournal(
          on: adapterB, input: journalInput(captureId: UUID().uuidString))
      }

      let barrier = RecordingJournalStorageLockBarrier()
      let contenderA = makeAdapter(
        ownerProvider: providerA, backend: TestRecordingJournalBackend(), vault: vault,
        files: BarrierRecordingJournalFiles(barrier: barrier), root: root)
      let contenderB = makeAdapter(
        ownerProvider: providerB, backend: TestRecordingJournalBackend(), vault: vault,
        files: BarrierRecordingJournalFiles(barrier: barrier), root: root)
      barrier.arm()
      let inputA = journalInput(captureId: UUID().uuidString)
      let inputB = journalInput(captureId: UUID().uuidString)
      let successfulCreates = await withTaskGroup(of: Bool.self, returning: Int.self) { group in
        group.addTask {
          do {
            _ = try await contenderA.createRecordingJournal(inputA)
            return true
          } catch {
            return false
          }
        }
        group.addTask {
          do {
            _ = try await contenderB.createRecordingJournal(inputB)
            return true
          } catch {
            return false
          }
        }
        var successCount = 0
        for await succeeded in group {
          if succeeded { successCount += 1 }
        }
        return successCount
      }

      XCTAssertEqual(successfulCreates, 1)
      XCTAssertEqual(barrier.arrivalCount(), 2)
      XCTAssertFalse(barrier.didTimeout())
      let journalsA = try await adapterA.listRecordingJournals()
      let journalsB = try await adapterB.listRecordingJournals()
      XCTAssertEqual(journalsA.count + journalsB.count, 64)
    }

    func testConcurrentAppendAndSessionAckPreserveBothUpdates() async throws {
      let root = try temporaryRoot()
      defer { try? FileManager.default.removeItem(at: root) }
      let vault = SyntheticRecordingJournalVault()
      let provider = TestRecordingJournalOwnerProvider(owner())
      let backend = TestRecordingJournalBackend()
      let seedAdapter = makeAdapter(
        ownerProvider: provider, backend: backend, vault: vault,
        files: POSIXAtomicRecordingJournalFiles(), root: root)
      let journal = try await createJournal(on: seedAdapter)
      _ = try await seedAdapter.appendRecordingJournal(
        handle: journal.handle, entry: packetEntry, expectedEntryCount: 1)

      let barrier = RecordingJournalStorageLockBarrier()
      let appendAdapter = makeAdapter(
        ownerProvider: provider, backend: backend, vault: vault,
        files: BarrierRecordingJournalFiles(barrier: barrier), root: root)
      let sessionAdapter = makeAdapter(
        ownerProvider: provider, backend: backend, vault: vault,
        files: BarrierRecordingJournalFiles(barrier: barrier), root: root)
      let appendedEntry = "[\"p\",\"BAUG\"]"
      let openRequest = BackendRequest(
        id: "concurrent-open", method: .POST, path: "/v1/device-sessions",
        body:
          #"{"captureId":"\#(journal.captureId)","deviceId":"device-1","deviceName":"Synthetic Pin","codec":21,"capturedAtMs":123}"#
      )
      barrier.arm()

      let successes = await withTaskGroup(of: Bool.self, returning: Int.self) { group in
        group.addTask {
          do {
            _ = try await appendAdapter.appendRecordingJournal(
              handle: journal.handle, entry: appendedEntry, expectedEntryCount: 2)
            return true
          } catch {
            return false
          }
        }
        group.addTask {
          do {
            _ = try await sessionAdapter.requestRecordingJournal(
              handle: journal.handle, request: openRequest)
            return true
          } catch {
            return false
          }
        }
        var successCount = 0
        for await succeeded in group {
          if succeeded { successCount += 1 }
        }
        return successCount
      }

      XCTAssertEqual(successes, 2)
      XCTAssertEqual(barrier.arrivalCount(), 2)
      XCTAssertFalse(barrier.didTimeout())
      let saved = try await seedAdapter.readRecordingJournal(handle: journal.handle)
      XCTAssertEqual(saved.entries, [packetEntry, appendedEntry])
      XCTAssertEqual(saved.sessionId, TestRecordingJournalBackend.sessionID)
    }

    func testJournalByteLimitIsGlobalAcrossOwnerPartitions() async throws {
      let root = try temporaryRoot()
      defer { try? FileManager.default.removeItem(at: root) }
      let vault = SyntheticRecordingJournalVault()
      let files = FixedSizeRecordingJournalFiles(
        journalSizeBytes: 32 * 1024 * 1024)
      let adapterA = makeAdapter(
        ownerProvider: TestRecordingJournalOwnerProvider(
          owner(key: String(repeating: "a", count: 64))),
        backend: TestRecordingJournalBackend(), vault: vault, files: files, root: root)
      let adapterB = makeAdapter(
        ownerProvider: TestRecordingJournalOwnerProvider(
          owner(key: String(repeating: "b", count: 64))),
        backend: TestRecordingJournalBackend(), vault: vault, files: files, root: root)

      for _ in 0..<2 {
        let input = journalInput(captureId: UUID().uuidString)
        _ = try await createJournal(on: adapterA, input: input)
      }
      for _ in 0..<2 {
        let input = journalInput(captureId: UUID().uuidString)
        _ = try await createJournal(on: adapterB, input: input)
      }
      let overflow = await capturedError {
        let input = journalInput(captureId: UUID().uuidString)
        _ = try await createJournal(on: adapterA, input: input)
      }

      XCTAssertEqual(overflow as? EncryptedRecordingJournalError, .storageLimitExceeded)
      let journalsA = try await adapterA.listRecordingJournals()
      let journalsB = try await adapterB.listRecordingJournals()
      XCTAssertEqual(journalsA.count, 2)
      XCTAssertEqual(journalsB.count, 2)
    }

    func testRestartReplaysSavedSessionWithoutOpeningAnotherSession() async throws {
      let root = try temporaryRoot()
      defer { try? FileManager.default.removeItem(at: root) }
      let vault = SyntheticRecordingJournalVault()
      let files = POSIXAtomicRecordingJournalFiles()
      let ownerProvider = TestRecordingJournalOwnerProvider(owner())
      let firstBackend = TestRecordingJournalBackend(failFirstAudioRequest: true)
      let firstAdapter = makeAdapter(
        ownerProvider: ownerProvider, backend: firstBackend,
        vault: vault, files: files, root: root)
      let journal = try await createJournal(on: firstAdapter)
      _ = try await firstAdapter.appendRecordingJournal(
        handle: journal.handle, entry: packetEntry, expectedEntryCount: 1)

      let firstDrainError = await capturedError {
        try await drainRecordingJournal(firstAdapter, handle: journal.handle)
      }
      XCTAssertEqual(firstDrainError as? TransportFailure, .transportFailed)
      let interrupted = try await firstAdapter.readRecordingJournal(handle: journal.handle)
      XCTAssertEqual(interrupted.sessionId, TestRecordingJournalBackend.sessionID)
      XCTAssertTrue(interrupted.entries.contains(stopEntry))

      let secondBackend = TestRecordingJournalBackend()
      let restartedAdapter = makeAdapter(
        ownerProvider: ownerProvider, backend: secondBackend,
        vault: vault, files: files, root: root)
      let completed = try await drainRecordingJournal(
        restartedAdapter, handle: journal.handle)

      XCTAssertEqual(completed?.id, TestRecordingJournalBackend.sessionID)
      let firstPaths = await firstBackend.requestPaths()
      XCTAssertEqual(
        firstPaths,
        [
          "/v1/device-sessions",
          "/v1/device-sessions/\(TestRecordingJournalBackend.sessionID)/audio",
        ])
      let replayPaths = await secondBackend.requestPaths()
      XCTAssertEqual(
        replayPaths,
        [
          "/v1/device-sessions/\(TestRecordingJournalBackend.sessionID)/audio",
          "/v1/device-sessions/\(TestRecordingJournalBackend.sessionID)/complete",
        ])
      let remainingJournals = try await restartedAdapter.listRecordingJournals()
      XCTAssertTrue(remainingJournals.isEmpty)
    }

    func testPartialWriteAndCorruptionNeverReplaceOrDeleteSavedJournal() async throws {
      let root = try temporaryRoot()
      defer { try? FileManager.default.removeItem(at: root) }
      let vault = SyntheticRecordingJournalVault()
      let faultingFiles = FaultInjectingRecordingJournalFiles()
      let adapter = makeAdapter(
        ownerProvider: TestRecordingJournalOwnerProvider(owner()),
        backend: TestRecordingJournalBackend(), vault: vault,
        files: faultingFiles, root: root)
      let journal = try await createJournal(on: adapter)
      let target = journalURL(
        root: root, partition: try vault.partitionIdentifier(for: owner()),
        handle: journal.handle)
      let originalCiphertext = try Data(contentsOf: target)

      faultingFiles.failNextWriteWithPartialTemporaryFile()
      let writeError = await capturedError {
        try await adapter.appendRecordingJournal(
          handle: journal.handle, entry: packetEntry, expectedEntryCount: 1)
      }
      XCTAssertEqual(writeError as? EncryptedRecordingJournalError, .storageFailure)
      XCTAssertEqual(try Data(contentsOf: target), originalCiphertext)
      XCTAssertTrue(
        try FileManager.default.contentsOfDirectory(
          at: target.deletingLastPathComponent(), includingPropertiesForKeys: nil
        )
        .contains { $0.lastPathComponent.hasSuffix(".pending") })

      let afterPartialWrite = try await adapter.readRecordingJournal(handle: journal.handle)
      XCTAssertTrue(afterPartialWrite.entries.isEmpty)
      var damagedBytes = Array(originalCiphertext)
      damagedBytes[damagedBytes.count - 1] ^= 0x01
      let corrupted = Data(damagedBytes)
      try corrupted.write(to: target, options: .atomic)

      let corruptionError = await capturedError {
        try await adapter.readRecordingJournal(handle: journal.handle)
      }
      XCTAssertEqual(corruptionError as? EncryptedRecordingJournalError, .corruptJournal)
      XCTAssertEqual(try Data(contentsOf: target), corrupted)
    }

    func testPostCommitRetryIsIdempotentWithoutDeduplicatingEqualEntries() async throws {
      let root = try temporaryRoot()
      defer { try? FileManager.default.removeItem(at: root) }
      let vault = SyntheticRecordingJournalVault()
      let faultingFiles = FaultInjectingRecordingJournalFiles()
      let adapter = makeAdapter(
        ownerProvider: TestRecordingJournalOwnerProvider(owner()),
        backend: TestRecordingJournalBackend(), vault: vault,
        files: faultingFiles, root: root)
      let journal = try await createJournal(on: adapter)

      let firstAppend = try await adapter.appendRecordingJournal(
        handle: journal.handle, entry: packetEntry, expectedEntryCount: 1)
      XCTAssertEqual(firstAppend, 1)
      let repeatedPayloadAppend = try await adapter.appendRecordingJournal(
        handle: journal.handle, entry: packetEntry, expectedEntryCount: 2)
      XCTAssertEqual(repeatedPayloadAppend, 2)

      faultingFiles.failAfterNextSuccessfulWrite()
      let firstError = await capturedError {
        try await adapter.appendRecordingJournal(
          handle: journal.handle, entry: packetEntry, expectedEntryCount: 3)
      }
      XCTAssertEqual(firstError as? EncryptedRecordingJournalError, .storageFailure)
      let persistedAfterFailure = try await adapter.readRecordingJournal(
        handle: journal.handle)
      XCTAssertEqual(persistedAfterFailure.entries, [packetEntry, packetEntry, packetEntry])

      let retryAcknowledgement = try await adapter.appendRecordingJournal(
        handle: journal.handle, entry: packetEntry, expectedEntryCount: 3)
      XCTAssertEqual(retryAcknowledgement, 3)
      let persistedAfterRetry = try await adapter.readRecordingJournal(
        handle: journal.handle)
      XCTAssertEqual(persistedAfterRetry.entries, [packetEntry, packetEntry, packetEntry])
    }

    func testLogoutRetiresAdapterAndKeepsOldLoginPartitionForRecoveryPolicy() async throws {
      let root = try temporaryRoot()
      defer { try? FileManager.default.removeItem(at: root) }
      let vault = SyntheticRecordingJournalVault()
      let files = POSIXAtomicRecordingJournalFiles()
      let firstOwnerKey = String(repeating: "a", count: 64)
      let firstOwner = owner(key: firstOwnerKey)
      let provider = TestRecordingJournalOwnerProvider(firstOwner)
      let adapter = makeAdapter(
        ownerProvider: provider, backend: TestRecordingJournalBackend(),
        vault: vault, files: files, root: root)
      let journal = try await createJournal(on: adapter)
      _ = try await adapter.appendRecordingJournal(
        handle: journal.handle, entry: packetEntry, expectedEntryCount: 1)
      let oldPath = journalURL(
        root: root, partition: try vault.partitionIdentifier(for: firstOwner),
        handle: journal.handle)
      let retainedBytes = try Data(contentsOf: oldPath)

      await provider.setOwner(nil)
      await adapter.retireForLogout()
      let retiredRead = await capturedError {
        try await adapter.listRecordingJournals()
      }
      XCTAssertEqual(retiredRead as? EncryptedRecordingJournalError, .retired)
      await adapter.removeRecordingJournal(handle: journal.handle)
      XCTAssertEqual(try Data(contentsOf: oldPath), retainedBytes)

      let nextLogin = owner(
        key: firstOwnerKey,
        generation: "323e4567-e89b-42d3-a456-426614174000")
      let newLoginAdapter = makeAdapter(
        ownerProvider: TestRecordingJournalOwnerProvider(nextLogin),
        backend: TestRecordingJournalBackend(), vault: vault, files: files, root: root)
      let newLoginJournals = try await newLoginAdapter.listRecordingJournals()
      XCTAssertTrue(newLoginJournals.isEmpty)
      XCTAssertTrue(FileManager.default.fileExists(atPath: oldPath.path))
    }

    func testSameHandleCreateAndRepeatedSessionAckAreStable() async throws {
      let root = try temporaryRoot()
      defer { try? FileManager.default.removeItem(at: root) }
      let vault = SyntheticRecordingJournalVault()
      let backend = TestRecordingJournalBackend()
      let faultingFiles = FaultInjectingRecordingJournalFiles()
      let adapter = makeAdapter(
        ownerProvider: TestRecordingJournalOwnerProvider(owner()), backend: backend,
        vault: vault, files: faultingFiles, root: root)

      let input = journalInput(captureId: TestRecordingJournalBackend.handle)
      faultingFiles.failAfterNextSuccessfulWrite()
      let lostCreateAcknowledgement = await capturedError {
        try await createJournal(on: adapter, input: input)
      }
      XCTAssertEqual(
        lostCreateAcknowledgement as? EncryptedRecordingJournalError, .storageFailure)

      let first = try await createJournal(on: adapter, input: input)
      let path = journalURL(
        root: root, partition: try vault.partitionIdentifier(for: owner()),
        handle: first.handle)
      let firstBytes = try Data(contentsOf: path)
      let duplicateCreate = try await createJournal(on: adapter, input: input)
      XCTAssertEqual(duplicateCreate, first)
      XCTAssertEqual(first.handle, input.captureId)
      XCTAssertEqual(first.captureId, input.captureId)
      XCTAssertEqual(try Data(contentsOf: path), firstBytes)

      let conflictingInput = RecordingJournalInput(
        captureId: input.captureId, capturedAtMs: input.capturedAtMs,
        deviceId: "different-device", deviceName: input.deviceName, codec: input.codec)
      let conflictingCreate = await capturedError {
        try await createJournal(on: adapter, input: conflictingInput)
      }
      XCTAssertEqual(
        conflictingCreate as? EncryptedRecordingJournalError, .invalidHandle)
      let savedAfterConflictingCreate = try await adapter.readRecordingJournal(
        handle: first.handle)
      XCTAssertEqual(savedAfterConflictingCreate, first)
      let recordingIDRequests = await backend.recordingIDRequestCount()
      XCTAssertEqual(recordingIDRequests, 0)

      let openRequest = BackendRequest(
        id: "synthetic-open", method: .POST, path: "/v1/device-sessions",
        body:
          #"{"captureId":"\#(first.captureId)","deviceId":"device-1","deviceName":"Synthetic Pin","codec":21,"capturedAtMs":123}"#
      )
      _ = try await adapter.requestRecordingJournal(
        handle: first.handle, request: openRequest)
      let acknowledgedBytes = try Data(contentsOf: path)
      _ = try await adapter.requestRecordingJournal(
        handle: first.handle, request: openRequest)
      XCTAssertEqual(try Data(contentsOf: path), acknowledgedBytes)
      let opened = try await adapter.readRecordingJournal(handle: first.handle)
      XCTAssertEqual(opened.sessionId, TestRecordingJournalBackend.sessionID)
      let requestCount = await backend.requestPaths().count
      XCTAssertEqual(requestCount, 2)
    }

    func testUnavailableSecureVaultFailsClosedWithoutWritingPlaintext() async throws {
      let root = try temporaryRoot()
      defer { try? FileManager.default.removeItem(at: root) }
      let adapter = makeAdapter(
        ownerProvider: TestRecordingJournalOwnerProvider(owner()),
        backend: TestRecordingJournalBackend(), vault: UnavailableRecordingJournalVault(),
        files: POSIXAtomicRecordingJournalFiles(), root: root)
      let error = await capturedError { try await createJournal(on: adapter) }
      XCTAssertEqual(error as? EncryptedRecordingJournalError, .secureVaultUnavailable)
      XCTAssertEqual(
        try FileManager.default.contentsOfDirectory(atPath: root.path), [".storage.lock"])
      let partitions = try POSIXAtomicRecordingJournalFiles().listPartitionDirectories(in: root)
      XCTAssertTrue(partitions.isEmpty)
      let lockAttributes = try FileManager.default.attributesOfItem(
        atPath: root.appendingPathComponent(".storage.lock").path)
      XCTAssertEqual((lockAttributes[.posixPermissions] as? NSNumber)?.intValue, 0o600)
    }

    private func createJournal(
      on adapter: EncryptedRecordingJournalTransport,
      input: RecordingJournalInput? = nil
    ) async throws -> RecordingJournalRecord {
      let requestInput = input ?? journalInput(captureId: TestRecordingJournalBackend.handle)
      return try await adapter.createRecordingJournal(requestInput)
    }

    private func journalInput(
      captureId: String, capturedAtMs: Int64? = 123
    ) -> RecordingJournalInput {
      RecordingJournalInput(
        captureId: captureId.lowercased(), capturedAtMs: capturedAtMs,
        deviceId: "device-1", deviceName: "Synthetic Pin", codec: 21)
    }

    private func makeAdapter(
      ownerProvider: TestRecordingJournalOwnerProvider,
      backend: TestRecordingJournalBackend,
      vault: RecordingJournalSecureVault,
      files: RecordingJournalFileAccess,
      root: URL
    ) -> EncryptedRecordingJournalTransport {
      EncryptedRecordingJournalTransport(
        backend: backend, ownerProvider: ownerProvider,
        vault: vault, files: files, root: root)
    }

    private func temporaryRoot() throws -> URL {
      let root = FileManager.default.temporaryDirectory
        .appendingPathComponent("omi-encrypted-journal-\(UUID().uuidString)", isDirectory: true)
      try FileManager.default.createDirectory(
        at: root, withIntermediateDirectories: true,
        attributes: [.posixPermissions: 0o700])
      return root
    }

    private func owner(
      key: String = String(repeating: "a", count: 64),
      generation: String = "423e4567-e89b-42d3-a456-426614174000"
    ) -> RecordingJournalOwnerContext {
      RecordingJournalOwnerContext(
        backendOrigin: "https://api.example.test",
        ownerKey: "capture-owner-v1:\(key)", loginGeneration: generation,
        ownershipReceipt:
          "capture1.\(key).\(String(repeating: "c", count: 64))")
    }

    private func journalURL(root: URL, partition: String, handle: String) -> URL {
      root.appendingPathComponent(partition, isDirectory: true)
        .appendingPathComponent(handle).appendingPathExtension("journal")
    }

    private func capturedError<Value>(
      _ operation: () async throws -> Value
    ) async -> Error? {
      do {
        _ = try await operation()
        return nil
      } catch {
        return error
      }
    }

    private let packetEntry = "[\"p\",\"AQID\"]"
    private let stopEntry = "[\"s\"]"
  }

  /// Rendezvous immediately before the real root lock so competing adapters
  /// are guaranteed to begin their transactions together in regression tests.
  private final class RecordingJournalStorageLockBarrier: @unchecked Sendable {
    private let condition = NSCondition()
    private var isArmed = false
    private var arrivals = 0
    private var released = false
    private var timedOut = false

    func arm() {
      condition.lock()
      isArmed = true
      condition.unlock()
    }

    func arriveAndWait() {
      condition.lock()
      guard isArmed else {
        condition.unlock()
        return
      }
      arrivals += 1
      if arrivals >= 2 {
        released = true
        condition.broadcast()
      } else {
        let deadline = Date(timeIntervalSinceNow: 5)
        while !released {
          if !condition.wait(until: deadline) {
            timedOut = true
            released = true
            condition.broadcast()
          }
        }
      }
      condition.unlock()
    }

    func arrivalCount() -> Int {
      condition.lock()
      defer { condition.unlock() }
      return arrivals
    }

    func didTimeout() -> Bool {
      condition.lock()
      defer { condition.unlock() }
      return timedOut
    }
  }

  private struct BarrierRecordingJournalFiles: RecordingJournalFileAccess {
    private let barrier: RecordingJournalStorageLockBarrier
    private let base = POSIXAtomicRecordingJournalFiles()

    init(barrier: RecordingJournalStorageLockBarrier) { self.barrier = barrier }

    func withGlobalStorageLock(
      in root: URL, _ operation: () throws -> Void
    ) throws {
      barrier.arriveAndWait()
      try base.withGlobalStorageLock(in: root, operation)
    }

    func listPartitionDirectories(in root: URL) throws -> [URL] {
      try base.listPartitionDirectories(in: root)
    }
    func listStorageFiles(in directory: URL) throws -> [URL] {
      try base.listStorageFiles(in: directory)
    }
    func listJournalFiles(in directory: URL) throws -> [URL] {
      try base.listJournalFiles(in: directory)
    }
    func fileSize(at url: URL) throws -> Int { try base.fileSize(at: url) }
    func readFile(at url: URL, maximumBytes: Int) throws -> Data {
      try base.readFile(at: url, maximumBytes: maximumBytes)
    }
    func writeAtomically(_ data: Data, to url: URL) throws {
      try base.writeAtomically(data, to: url)
    }
    func removeFile(at url: URL) throws { try base.removeFile(at: url) }
  }

  private actor TestRecordingJournalOwnerProvider: RecordingJournalOwnerContextProviding {
    private var owner: RecordingJournalOwnerContext?

    init(_ owner: RecordingJournalOwnerContext?) { self.owner = owner }
    func currentRecordingJournalOwner() async throws -> RecordingJournalOwnerContext? { owner }
    func setOwner(_ owner: RecordingJournalOwnerContext?) { self.owner = owner }
  }

  final class SyntheticRecordingJournalVault: RecordingJournalSecureVault,
    @unchecked Sendable
  {
    private let key = Data(repeating: 0x5a, count: 32)

    func partitionIdentifier(for owner: RecordingJournalOwnerContext) throws -> String {
      let material =
        "omi-recording-partition-v1\n\(owner.backendOrigin)\n\(owner.ownerKey)\n\(owner.loginGeneration)"
      return SHA256.hash(data: Data(material.utf8))
        .map { String(format: "%02x", $0) }.joined()
    }

    func seal(
      _ plaintext: Data, authenticating data: Data,
      owner: RecordingJournalOwnerContext
    ) throws -> Data {
      _ = try partitionIdentifier(for: owner)
      guard
        let combined = try AES.GCM.seal(
          plaintext, using: SymmetricKey(data: key), authenticating: data
        ).combined
      else { throw RecordingJournalSecureVaultError.unavailable }
      return combined
    }

    func open(
      _ ciphertext: Data, authenticating data: Data,
      owner: RecordingJournalOwnerContext
    ) throws -> Data {
      _ = try partitionIdentifier(for: owner)
      do {
        return try AES.GCM.open(
          AES.GCM.SealedBox(combined: ciphertext),
          using: SymmetricKey(data: key), authenticating: data)
      } catch {
        throw RecordingJournalSecureVaultError.authenticationFailed
      }
    }
  }

  struct UnavailableRecordingJournalVault: RecordingJournalSecureVault {
    func partitionIdentifier(for owner: RecordingJournalOwnerContext) throws -> String {
      _ = owner
      throw RecordingJournalSecureVaultError.unavailable
    }
    func seal(
      _ plaintext: Data, authenticating data: Data,
      owner: RecordingJournalOwnerContext
    ) throws -> Data {
      _ = plaintext
      _ = data
      _ = owner
      throw RecordingJournalSecureVaultError.unavailable
    }
    func open(
      _ ciphertext: Data, authenticating data: Data,
      owner: RecordingJournalOwnerContext
    ) throws -> Data {
      _ = ciphertext
      _ = data
      _ = owner
      throw RecordingJournalSecureVaultError.unavailable
    }
  }

  private actor TestRecordingJournalBackend: BackendTransport, RecordingJournalOwnerRequesting {
    func requestRecordingJournal(_ request: BackendRequest,
      owner: RecordingJournalOwnerContext) async throws -> BackendResponse {
      try await self.request(request)
    }
    static let handle = "123e4567-e89b-42d3-a456-426614174000"
    static let sessionID = "223e4567-e89b-42d3-a456-426614174000"

    private let failFirstAudioRequest: Bool
    private var failedAudioRequest = false
    private var paths = [String]()
    private var recordingIDRequests = 0

    init(failFirstAudioRequest: Bool = false) {
      self.failFirstAudioRequest = failFirstAudioRequest
    }

    func request(_ request: BackendRequest) async throws -> BackendResponse {
      paths.append(request.path)
      if failFirstAudioRequest, !failedAudioRequest,
        request.path.hasSuffix("/audio")
      {
        failedAudioRequest = true
        throw TransportFailure.transportFailed
      }
      if request.path == "/v1/device-sessions" {
        return sessionResponse(state: "open", byteCount: 0, chunkCount: 0)
      }
      if request.path.hasSuffix("/audio") {
        return sessionResponse(state: "open", byteCount: 3, chunkCount: 1)
      }
      if request.path.hasSuffix("/complete") {
        return sessionResponse(state: "complete", byteCount: 3, chunkCount: 1)
      }
      throw TestRecordingJournalBackendError.unexpectedPath
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
    func createWriteId() async throws -> String { "synthetic-write-id" }
    func createRecordingId() async throws -> String {
      recordingIDRequests += 1
      return Self.handle
    }
    func apiContract() async -> APIContract? { .canonical }
    func softwarePlane() async -> SoftwarePlane? { .new }
    func setSoftwarePlane(_ plane: SoftwarePlane) async -> SoftwarePlane? { plane }
    func stampedBackendOrigin() async -> String? { "https://api.example.test" }
    func requestPaths() -> [String] { paths }
    func recordingIDRequestCount() -> Int { recordingIDRequests }

    private func sessionResponse(
      state: String, byteCount: Int, chunkCount: Int
    ) -> BackendResponse {
      let endedAt = state == "complete" ? "200" : "null"
      let body = """
        {"session":{"capturedAtMs":123,"id":"\(Self.sessionID)","deviceId":"device-1","deviceName":"Synthetic Pin","codec":21,"state":"\(state)","byteCount":\(byteCount),"chunkCount":\(chunkCount),"startedAt":100,"endedAt":\(endedAt)}}
        """
      return BackendResponse(id: "synthetic-response", status: 200, body: body)
    }
  }

  private enum TestRecordingJournalBackendError: Error {
    case unexpectedPath
  }

  private final class FaultInjectingRecordingJournalFiles: RecordingJournalFileAccess,
    @unchecked Sendable
  {
    private let base = POSIXAtomicRecordingJournalFiles()
    private let lock = NSLock()
    private var failNextWrite = false
    private var failAfterNextCommitError = false

    func failNextWriteWithPartialTemporaryFile() {
      lock.lock()
      failNextWrite = true
      lock.unlock()
    }

    func failAfterNextSuccessfulWrite() {
      lock.lock()
      failAfterNextCommitError = true
      lock.unlock()
    }

    func withGlobalStorageLock(
      in root: URL, _ operation: () throws -> Void
    ) throws {
      try base.withGlobalStorageLock(in: root, operation)
    }

    func listJournalFiles(in directory: URL) throws -> [URL] {
      try base.listJournalFiles(in: directory)
    }
    func listPartitionDirectories(in root: URL) throws -> [URL] {
      try base.listPartitionDirectories(in: root)
    }
    func listStorageFiles(in directory: URL) throws -> [URL] {
      try base.listStorageFiles(in: directory)
    }
    func fileSize(at url: URL) throws -> Int { try base.fileSize(at: url) }
    func readFile(at url: URL, maximumBytes: Int) throws -> Data {
      try base.readFile(at: url, maximumBytes: maximumBytes)
    }
    func removeFile(at url: URL) throws { try base.removeFile(at: url) }

    func writeAtomically(_ data: Data, to url: URL) throws {
      lock.lock()
      let shouldFail = failNextWrite
      let shouldFailAfterCommit = failAfterNextCommitError
      failNextWrite = false
      failAfterNextCommitError = false
      lock.unlock()
      if shouldFailAfterCommit {
        try base.writeAtomically(data, to: url)
        throw RecordingJournalFileError.unavailable
      }
      guard shouldFail else {
        try base.writeAtomically(data, to: url)
        return
      }
      let temporary = url.deletingLastPathComponent()
        .appendingPathComponent(".\(url.lastPathComponent).injected.pending")
      try Data([0x01, 0x02, 0x03]).write(to: temporary)
      throw RecordingJournalFileError.unavailable
    }
  }

  private struct FixedSizeRecordingJournalFiles: RecordingJournalFileAccess {
    private let base = POSIXAtomicRecordingJournalFiles()
    private let journalSizeBytes: Int

    init(journalSizeBytes: Int) { self.journalSizeBytes = journalSizeBytes }

    func withGlobalStorageLock(
      in root: URL, _ operation: () throws -> Void
    ) throws {
      try base.withGlobalStorageLock(in: root, operation)
    }

    func listPartitionDirectories(in root: URL) throws -> [URL] {
      try base.listPartitionDirectories(in: root)
    }
    func listStorageFiles(in directory: URL) throws -> [URL] {
      try base.listStorageFiles(in: directory)
    }
    func listJournalFiles(in directory: URL) throws -> [URL] {
      try base.listJournalFiles(in: directory)
    }
    func fileSize(at url: URL) throws -> Int {
      let actualSize = try base.fileSize(at: url)
      return url.pathExtension == "journal" ? journalSizeBytes : actualSize
    }
    func readFile(at url: URL, maximumBytes: Int) throws -> Data {
      try base.readFile(at: url, maximumBytes: maximumBytes)
    }
    func writeAtomically(_ data: Data, to url: URL) throws {
      try base.writeAtomically(data, to: url)
    }
    func removeFile(at url: URL) throws { try base.removeFile(at: url) }
  }
#endif
