import Foundation

#if !SKIP && canImport(CryptoKit)
  import CryptoKit
#endif

#if !SKIP && canImport(Security)
  import Security
#endif

#if !SKIP && canImport(Darwin)
  import Darwin
  import Darwin.sys.file
#elseif !SKIP && canImport(Glibc)
  import Glibc
#endif

/// A native owner assertion already checked by the authenticated host transport.
/// The provider must verify `/v1/device-sessions/ownership`, or reuse only its
/// exact cached receipt after a classified connectivity failure. It preserves
/// loginGeneration across token refresh, changes it on explicit sign-in, and
/// returns nil after sign-out. The receipt is never written to a journal file.
public struct RecordingJournalOwnerContext: Sendable, Hashable {
  public let backendOrigin: String
  public let ownerKey: String
  public let loginGeneration: String
  public let ownershipReceipt: String

  public init(
    backendOrigin: String, ownerKey: String, loginGeneration: String,
    ownershipReceipt: String
  ) {
    self.backendOrigin = backendOrigin
    self.ownerKey = ownerKey
    self.loginGeneration = loginGeneration
    self.ownershipReceipt = ownershipReceipt
  }

  fileprivate var partitionMaterial: String {
    "omi-recording-partition-v1\n\(backendOrigin)\n\(ownerKey)\n\(loginGeneration)"
  }

  func validate() throws {
    guard
      let components = URLComponents(string: backendOrigin),
      components.scheme == "https" || components.scheme == "http",
      components.host != nil,
      components.path.isEmpty || components.path == "/",
      components.query == nil, components.fragment == nil,
      validHexToken(ownerKey, prefix: "capture-owner-v1:", hexCount: 64),
      isCaptureUUID(loginGeneration),
      validReceipt(ownershipReceipt),
      ownershipReceipt.split(separator: ".")[1] == ownerKey.dropFirst("capture-owner-v1:".count)
    else {
      throw EncryptedRecordingJournalError.invalidOwnerContext
    }
  }
}

/// The native host owns this seam. A context is trusted only after the host has
/// authenticated and validated its ownership receipt against the current login.
public protocol RecordingJournalOwnerContextProviding: Sendable {
  func currentRecordingJournalOwner() async throws -> RecordingJournalOwnerContext?
  func freshRecordingJournalOwner() async throws -> RecordingJournalOwnerContext?
}

extension RecordingJournalOwnerContextProviding {
  public func freshRecordingJournalOwner() async throws -> RecordingJournalOwnerContext? {
    try await currentRecordingJournalOwner()
  }
}

/// Authenticated transports must bind the receipt, bearer, origin and login in
/// one request snapshot. Plain BackendTransport cannot safely replay journals.
public protocol RecordingJournalOwnerRequesting: Sendable {
  func requestRecordingJournal(_ request: BackendRequest,
    owner: RecordingJournalOwnerContext) async throws -> BackendResponse
}

extension RecordingJournalOwnerContext {
  func hasSameIdentity(as other: RecordingJournalOwnerContext) -> Bool {
    backendOrigin == other.backendOrigin && ownerKey == other.ownerKey
      && loginGeneration == other.loginGeneration
  }
}

/// Required secure-vault bridge for journal encryption and owner partitioning.
/// Implementations must keep key material in the platform vault and bind the
/// sealed bytes to the supplied additional authenticated data. There is no
/// plaintext implementation or default key.
public protocol RecordingJournalSecureVault: Sendable {
  func partitionIdentifier(
    for owner: RecordingJournalOwnerContext
  ) throws -> String
  func seal(
    _ plaintext: Data, authenticating data: Data,
    owner: RecordingJournalOwnerContext
  ) throws -> Data
  func open(
    _ ciphertext: Data, authenticating data: Data,
    owner: RecordingJournalOwnerContext
  ) throws -> Data
}

/// Durable host-file bridge. Implementations must atomically replace a journal,
/// sync the file before returning, sync its containing directory after rename,
/// use private file permissions, reject symlinks, and enumerate hidden pending
/// files for global quota accounting.
public protocol RecordingJournalFileAccess: Sendable {
  /// Serializes the quota check and replacement transaction across every
  /// adapter that shares this storage root, including other processes.
  func withGlobalStorageLock(in root: URL, _ operation: () throws -> Void) throws
  func listPartitionDirectories(in root: URL) throws -> [URL]
  func listStorageFiles(in directory: URL) throws -> [URL]
  func listJournalFiles(in directory: URL) throws -> [URL]
  func fileSize(at url: URL) throws -> Int
  func readFile(at url: URL, maximumBytes: Int) throws -> Data
  func writeAtomically(_ data: Data, to url: URL) throws
  func removeFile(at url: URL) throws
}

public enum EncryptedRecordingJournalError: Error, Sendable, Equatable {
  case ownerUnavailable
  case ownerChanged
  case invalidOwnerContext
  case secureVaultUnavailable
  case retired
  case invalidHandle
  case invalidAppendSequence
  case journalNotFound
  case corruptJournal
  case invalidJournal
  case invalidRequest
  case invalidNativeAcknowledgement
  case storageFailure
  case storageLimitExceeded
}

public enum RecordingJournalSecureVaultError: Error, Sendable, Equatable {
  case unavailable
  case invalidKey
  case authenticationFailed
}

public enum RecordingJournalFileError: Error, Sendable, Equatable {
  case notFound
  case invalidFile
  case unavailable
}

private func validHexToken(_ value: String, prefix: String, hexCount: Int) -> Bool {
  guard value.hasPrefix(prefix), value.count == prefix.count + hexCount else {
    return false
  }
  return Array(String(value.dropFirst(prefix.count)).utf8).allSatisfy({ ASCII.isLowerHex($0) })
}

private func validReceipt(_ value: String) -> Bool {
  let parts = value.split(separator: ".", omittingEmptySubsequences: false)
  guard parts.count == 3, parts[0] == "capture1", parts[1].count == 64,
    parts[2].count == 64
  else { return false }
  return Array(String(parts[1]).utf8).allSatisfy({ ASCII.isLowerHex($0) })
    && Array(String(parts[2]).utf8).allSatisfy({ ASCII.isLowerHex($0) })
}


#if !SKIP && canImport(CryptoKit) && canImport(Security)
  /// Apple journal keys are separate from the token key. One AES-GCM key is kept
  /// in Keychain per origin/owner/login partition, with the same first-unlock
  /// availability as the journal files. Sign-out does not delete keys or files:
  /// the next explicit login receives a new generation and cannot see old data.
  public final class AppleKeychainRecordingJournalVault: RecordingJournalSecureVault,
    @unchecked Sendable
  {
    public static let keychainService = "app.omi.v5.recording-journal"

    public init() {}

    public func partitionIdentifier(
      for owner: RecordingJournalOwnerContext
    ) throws -> String {
      try owner.validate()
      let digest = SHA256.hash(data: Data(owner.partitionMaterial.utf8))
      return digest.map { String(format: "%02x", $0) }.joined()
    }

    public func seal(
      _ plaintext: Data, authenticating data: Data,
      owner: RecordingJournalOwnerContext
    ) throws -> Data {
      let partition = try partitionIdentifier(for: owner)
      let key = try loadKey(partition: partition, createIfMissing: true)
      do {
        guard
          let combined = try AES.GCM.seal(
            plaintext, using: SymmetricKey(data: key), authenticating: data
          ).combined
        else {
          throw RecordingJournalSecureVaultError.unavailable
        }
        return combined
      } catch let error as RecordingJournalSecureVaultError {
        throw error
      } catch {
        throw RecordingJournalSecureVaultError.unavailable
      }
    }

    public func open(
      _ ciphertext: Data, authenticating data: Data,
      owner: RecordingJournalOwnerContext
    ) throws -> Data {
      let partition = try partitionIdentifier(for: owner)
      let key = try loadKey(partition: partition, createIfMissing: false)
      do {
        let box = try AES.GCM.SealedBox(combined: ciphertext)
        return try AES.GCM.open(box, using: SymmetricKey(data: key), authenticating: data)
      } catch {
        throw RecordingJournalSecureVaultError.authenticationFailed
      }
    }

    private func loadKey(partition: String, createIfMissing: Bool) throws -> Data {
      let base: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: Self.keychainService,
        kSecAttrAccount as String: partition,
      ]
      var query = base
      query[kSecReturnData as String] = true
      query[kSecMatchLimit as String] = kSecMatchLimitOne
      var item: CFTypeRef?
      let status = SecItemCopyMatching(query as CFDictionary, &item)
      if status == errSecSuccess {
        guard let key = item as? Data, key.count == 32 else {
          throw RecordingJournalSecureVaultError.invalidKey
        }
        return key
      }
      guard status == errSecItemNotFound, createIfMissing else {
        throw RecordingJournalSecureVaultError.unavailable
      }

      let key = Data(SymmetricKey(size: .bits256).withUnsafeBytes { Array($0) })
      var add = base
      add[kSecValueData as String] = key
      add[kSecAttrAccessible as String] =
        kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
      let addStatus = SecItemAdd(add as CFDictionary, nil)
      if addStatus == errSecSuccess { return key }
      if addStatus == errSecDuplicateItem {
        return try loadKey(partition: partition, createIfMissing: false)
      }
      throw RecordingJournalSecureVaultError.unavailable
    }
  }
#endif

#if !SKIP && (canImport(Darwin) || canImport(Glibc))
  /// POSIX implementation used by native hosts that also supply a secure vault.
  /// It creates 0700 partition directories and 0600 journal files. A journal
  /// acknowledgement follows file fsync, atomic rename, and directory fsync.
  public struct POSIXAtomicRecordingJournalFiles: RecordingJournalFileAccess {
    public init() {}

    public func withGlobalStorageLock(
      in root: URL, _ operation: () throws -> Void
    ) throws {
      do {
        try FileManager.default.createDirectory(
          at: root, withIntermediateDirectories: true,
          attributes: [.posixPermissions: 0o700])
        try rejectSymlink(root)
        guard root.path.withCString({ journalChmod($0, 0o700) }) == 0 else {
          throw RecordingJournalFileError.unavailable
        }
      } catch {
        if let fileError = error as? RecordingJournalFileError { throw fileError }
        throw RecordingJournalFileError.unavailable
      }

      let lockFile = root.appendingPathComponent(".storage.lock")
      do {
        try rejectSymlink(lockFile)
      } catch let error as RecordingJournalFileError where error == .notFound {
        // A new root lock file is expected to be absent.
      } catch {
        throw RecordingJournalFileError.unavailable
      }
      let descriptor = lockFile.path.withCString {
        journalOpen($0, O_RDWR | O_CREAT | O_CLOEXEC, 0o600)
      }
      guard descriptor >= 0 else { throw RecordingJournalFileError.unavailable }
      defer { _ = journalClose(descriptor) }
      guard lockFile.path.withCString({ journalChmod($0, 0o600) }) == 0 else {
        throw RecordingJournalFileError.unavailable
      }
      while journalFlock(descriptor, LOCK_EX) != 0 {
        if errno == EINTR { continue }
        throw RecordingJournalFileError.unavailable
      }
      defer { _ = journalFlock(descriptor, LOCK_UN) }
      try operation()
    }

    public func listPartitionDirectories(in root: URL) throws -> [URL] {
      guard FileManager.default.fileExists(atPath: root.path) else { return [] }
      try rejectSymlink(root)
      do {
        let children = try FileManager.default.contentsOfDirectory(
          at: root,
          includingPropertiesForKeys: [.isDirectoryKey, .isRegularFileKey, .isSymbolicLinkKey],
          options: [])
        var partitions = [URL]()
        for child in children {
          try rejectSymlink(child)
          if child.lastPathComponent == ".storage.lock" {
            guard
              try child.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile == true
            else { throw RecordingJournalFileError.invalidFile }
            continue
          }
          let values = try child.resourceValues(forKeys: [.isDirectoryKey])
          guard values.isDirectory == true,
            child.lastPathComponent.utf8.count == 64,
            Array(child.lastPathComponent.utf8).allSatisfy({ ASCII.isLowerHex($0) })
          else { throw RecordingJournalFileError.invalidFile }
          partitions.append(child)
        }
        return partitions.sorted { $0.lastPathComponent < $1.lastPathComponent }
      } catch let error as RecordingJournalFileError {
        throw error
      } catch {
        throw RecordingJournalFileError.unavailable
      }
    }

    /// Includes hidden `.pending` files so abandoned atomic-write fragments
    /// consume the same global disk budget as committed journals.
    public func listStorageFiles(in directory: URL) throws -> [URL] {
      guard FileManager.default.fileExists(atPath: directory.path) else { return [] }
      try rejectSymlink(directory)
      do {
        let children = try FileManager.default.contentsOfDirectory(
          at: directory,
          includingPropertiesForKeys: [.isRegularFileKey, .isSymbolicLinkKey],
          options: [])
        var storageFiles = [URL]()
        for child in children {
          try rejectSymlink(child)
          guard try child.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile == true else {
            throw RecordingJournalFileError.invalidFile
          }
          storageFiles.append(child)
        }
        return storageFiles.sorted { $0.lastPathComponent < $1.lastPathComponent }
      } catch let error as RecordingJournalFileError {
        throw error
      } catch {
        throw RecordingJournalFileError.unavailable
      }
    }

    public func listJournalFiles(in directory: URL) throws -> [URL] {
      guard FileManager.default.fileExists(atPath: directory.path) else { return [] }
      try rejectSymlink(directory)
      do {
        let files = try FileManager.default.contentsOfDirectory(
          at: directory, includingPropertiesForKeys: [.isRegularFileKey, .isSymbolicLinkKey],
          options: [.skipsHiddenFiles])
        var journals = [URL]()
        for file in files where file.pathExtension == "journal" {
          try rejectSymlink(file)
          guard try file.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile == true else {
            throw RecordingJournalFileError.invalidFile
          }
          journals.append(file)
        }
        return journals.sorted { $0.lastPathComponent < $1.lastPathComponent }
      } catch let error as RecordingJournalFileError {
        throw error
      } catch {
        throw RecordingJournalFileError.unavailable
      }
    }

    public func fileSize(at url: URL) throws -> Int {
      try rejectSymlink(url)
      do {
        let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
        guard let number = attributes[.size] as? NSNumber,
          attributes[.type] as? FileAttributeType == .typeRegular
        else { throw RecordingJournalFileError.invalidFile }
        return number.intValue
      } catch let error as RecordingJournalFileError {
        throw error
      } catch {
        if !FileManager.default.fileExists(atPath: url.path) {
          throw RecordingJournalFileError.notFound
        }
        throw RecordingJournalFileError.unavailable
      }
    }

    public func readFile(at url: URL, maximumBytes: Int) throws -> Data {
      let size = try fileSize(at: url)
      guard size >= 0, size <= maximumBytes else {
        throw RecordingJournalFileError.invalidFile
      }
      do {
        return try Data(contentsOf: url, options: [.mappedIfSafe])
      } catch {
        throw RecordingJournalFileError.unavailable
      }
    }

    public func writeAtomically(_ data: Data, to url: URL) throws {
      let directory = url.deletingLastPathComponent()
      let directoryAlreadyExisted = FileManager.default.fileExists(atPath: directory.path)
      do {
        try FileManager.default.createDirectory(
          at: directory, withIntermediateDirectories: true,
          attributes: [.posixPermissions: 0o700])
        try rejectSymlink(directory)
        guard directory.path.withCString({ journalChmod($0, 0o700) }) == 0 else {
          throw RecordingJournalFileError.unavailable
        }
      } catch {
        if let fileError = error as? RecordingJournalFileError { throw fileError }
        throw RecordingJournalFileError.unavailable
      }

      do {
        try rejectSymlink(url)
      } catch let error as RecordingJournalFileError where error == .notFound {
        // A new journal path is expected to be absent.
      } catch {
        throw RecordingJournalFileError.unavailable
      }
      if !directoryAlreadyExisted {
        try syncDirectory(directory.deletingLastPathComponent())
      }

      let temporary = directory.appendingPathComponent(
        ".\(url.lastPathComponent).\(UUID().uuidString.lowercased()).pending")
      let descriptor = temporary.path.withCString {
        journalOpen($0, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0o600)
      }
      guard descriptor >= 0 else { throw RecordingJournalFileError.unavailable }
      var didClose = false
      defer {
        if !didClose { _ = journalClose(descriptor) }
        _ = temporary.path.withCString { journalUnlink($0) }
      }

      do {
        try data.withUnsafeBytes { bytes in
          guard let base = bytes.baseAddress else { return }
          var offset = 0
          while offset < bytes.count {
            let written = journalWrite(
              descriptor, base.advanced(by: offset), bytes.count - offset)
            if written < 0 && errno == EINTR { continue }
            guard written > 0 else { throw RecordingJournalFileError.unavailable }
            offset += written
          }
        }
        guard journalFsync(descriptor) == 0 else {
          throw RecordingJournalFileError.unavailable
        }
        guard journalClose(descriptor) == 0 else {
          didClose = true
          throw RecordingJournalFileError.unavailable
        }
        didClose = true
        let renamed = temporary.path.withCString { source in
          url.path.withCString { destination in journalRename(source, destination) }
        }
        guard renamed == 0 else { throw RecordingJournalFileError.unavailable }
        try syncDirectory(directory)
      } catch let error as RecordingJournalFileError {
        throw error
      } catch {
        throw RecordingJournalFileError.unavailable
      }
    }

    public func removeFile(at url: URL) throws {
      try rejectSymlink(url)
      let result = url.path.withCString { journalUnlink($0) }
      guard result == 0 else {
        if errno == ENOENT { throw RecordingJournalFileError.notFound }
        throw RecordingJournalFileError.unavailable
      }
      try syncDirectory(url.deletingLastPathComponent())
    }

    private func rejectSymlink(_ url: URL) throws {
      let values: URLResourceValues
      do {
        values = try url.resourceValues(forKeys: [.isSymbolicLinkKey])
      } catch {
        if !FileManager.default.fileExists(atPath: url.path) {
          throw RecordingJournalFileError.notFound
        }
        throw RecordingJournalFileError.unavailable
      }
      guard values.isSymbolicLink != true else {
        throw RecordingJournalFileError.invalidFile
      }
    }

    private func syncDirectory(_ url: URL) throws {
      let descriptor = url.path.withCString { journalOpen($0, O_RDONLY | O_CLOEXEC, 0) }
      guard descriptor >= 0 else { throw RecordingJournalFileError.unavailable }
      defer { _ = journalClose(descriptor) }
      guard journalFsync(descriptor) == 0 else {
        throw RecordingJournalFileError.unavailable
      }
    }
  }

  #if canImport(Darwin)
    private func journalOpen(_ path: UnsafePointer<CChar>, _ flags: Int32, _ mode: mode_t) -> Int32
    {
      Darwin.open(path, flags, mode)
    }
    private func journalWrite(_ fd: Int32, _ buffer: UnsafeRawPointer, _ count: Int) -> Int {
      Darwin.write(fd, buffer, count)
    }
    private func journalFsync(_ fd: Int32) -> Int32 { Darwin.fsync(fd) }
    private func journalFlock(_ fd: Int32, _ operation: Int32) -> Int32 {
      flock(fd, operation)
    }
    private func journalClose(_ fd: Int32) -> Int32 { Darwin.close(fd) }
    private func journalChmod(_ path: UnsafePointer<CChar>, _ mode: mode_t) -> Int32 {
      Darwin.chmod(path, mode)
    }
    private func journalRename(_ from: UnsafePointer<CChar>, _ to: UnsafePointer<CChar>) -> Int32 {
      Darwin.rename(from, to)
    }
    private func journalUnlink(_ path: UnsafePointer<CChar>) -> Int32 { Darwin.unlink(path) }
  #elseif canImport(Glibc)
    private func journalOpen(_ path: UnsafePointer<CChar>, _ flags: Int32, _ mode: mode_t) -> Int32
    {
      Glibc.open(path, flags, mode)
    }
    private func journalWrite(_ fd: Int32, _ buffer: UnsafeRawPointer, _ count: Int) -> Int {
      Glibc.write(fd, buffer, count)
    }
    private func journalFsync(_ fd: Int32) -> Int32 { Glibc.fsync(fd) }
    private func journalFlock(_ fd: Int32, _ operation: Int32) -> Int32 {
      flock(fd, operation)
    }
    private func journalClose(_ fd: Int32) -> Int32 { Glibc.close(fd) }
    private func journalChmod(_ path: UnsafePointer<CChar>, _ mode: mode_t) -> Int32 {
      Glibc.chmod(path, mode)
    }
    private func journalRename(_ from: UnsafePointer<CChar>, _ to: UnsafePointer<CChar>) -> Int32 {
      Glibc.rename(from, to)
    }
    private func journalUnlink(_ path: UnsafePointer<CChar>) -> Int32 { Glibc.unlink(path) }
  #endif
#endif

#if !SKIP
  /// Encrypted, owner-partitioned local journal adapter. Hosts must supply all
  /// three dependencies; without a validated owner, secure vault, or durable file
  /// bridge they must leave their BackendTransport unwrapped so capture does not
  /// advertise journal support. Android, Linux, and Windows bridges are not
  /// currently wired in this rewrite.
  public actor EncryptedRecordingJournalTransport: BackendTransport,
    RecordingJournalStoring
  {
    private let backend: BackendTransport
    private let ownerProvider: RecordingJournalOwnerContextProviding
    private let vault: RecordingJournalSecureVault
    private let files: RecordingJournalFileAccess
    private let root: URL
    private var retired = false

    private static let maximumEncryptedJournalBytes = 32 * 1024 * 1024
    private static let maximumJournalFiles = 64
    private static let maximumJournalStorageBytes = 128 * 1024 * 1024

    public init(
      backend: BackendTransport,
      ownerProvider: RecordingJournalOwnerContextProviding,
      vault: RecordingJournalSecureVault,
      files: RecordingJournalFileAccess,
      root: URL
    ) {
      self.backend = backend
      self.ownerProvider = ownerProvider
      self.vault = vault
      self.files = files
      self.root = root
    }

    /// Retires this instance on logout or terminal auth invalidation. It has no
    /// cached open file handles; encrypted records remain for their original
    /// login partition and cannot be reassigned to the next account.
    public func retireForLogout() { retired = true }

    public func request(_ request: BackendRequest) async throws -> BackendResponse {
      try await backend.request(request)
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

    public func createRecordingJournal(
      _ input: RecordingJournalInput
    ) async throws -> RecordingJournalRecord {
      let owner = try await currentOwner()
      guard isOptionalCaptureTimestamp(input.capturedAtMs) else {
        throw EncryptedRecordingJournalError.invalidJournal
      }
      let handle = input.captureId
      guard isCaptureUUID(handle) else { throw EncryptedRecordingJournalError.invalidHandle }
      try await requireCurrent(owner)

      let journal = RecordingJournalRecord(
        capturedAtMs: input.capturedAtMs, handle: handle, captureId: handle,
        deviceId: input.deviceId, deviceName: input.deviceName,
        codec: input.codec, sessionId: nil, entries: [])
      var createdOrExisting = journal
      try withStorageLock {
        do {
          let existing = try readJournal(handle: handle, owner: owner)
          guard sameCaptureIdentity(existing, input) else {
            throw EncryptedRecordingJournalError.invalidHandle
          }
          createdOrExisting = existing
          return
        } catch let error as EncryptedRecordingJournalError where error == .journalNotFound {
          // Only a missing capture can be created; the check is inside the lock.
        }
        try validate(journal)
        try persistLocked(journal, owner: owner, allowCreate: true)
      }
      return createdOrExisting
    }

    public func listRecordingJournals() async throws -> [RecordingJournalRecord] {
      let owner = try await currentOwner()
      let directory = try partitionDirectory(owner)
      var records = [RecordingJournalRecord]()
      try withStorageLock {
        let urls: [URL]
        do {
          urls = try files.listJournalFiles(in: directory)
        } catch {
          throw EncryptedRecordingJournalError.storageFailure
        }
        let usage = try storageUsage()
        guard usage.files.count <= Self.maximumJournalFiles,
          usage.byteCount <= Self.maximumJournalStorageBytes
        else {
          throw EncryptedRecordingJournalError.storageLimitExceeded
        }
        records = try urls.map { url in
          let handle = url.deletingPathExtension().lastPathComponent
          guard isCaptureUUID(handle), url.pathExtension == "journal" else {
            throw EncryptedRecordingJournalError.corruptJournal
          }
          return try readJournal(handle: handle, owner: owner)
        }
      }
      return records
    }

    public func readRecordingJournal(handle: String) async throws -> RecordingJournalRecord {
      let owner = try await currentOwner()
      return try readJournal(handle: handle, owner: owner)
    }

    @discardableResult
    public func appendRecordingJournal(
      handle: String, entry: String, expectedEntryCount: Int
    ) async throws -> Int {
      let owner = try await currentOwner()
      guard expectedEntryCount > 0 else {
        throw EncryptedRecordingJournalError.invalidAppendSequence
      }
      try withStorageLock {
        var journal = try readJournal(handle: handle, owner: owner)
        if journal.entries.count == expectedEntryCount {
          guard journal.entries.last == entry else {
            throw EncryptedRecordingJournalError.invalidAppendSequence
          }
          // A replacement may be visible even when directory sync failed.
          // Re-persist the exact sequence before acknowledging its retry.
          try persistLocked(journal, owner: owner)
          return
        }
        guard journal.entries.count + 1 == expectedEntryCount else {
          throw EncryptedRecordingJournalError.invalidAppendSequence
        }
        journal.entries.append(entry)
        try validate(journal)
        try persistLocked(journal, owner: owner)
      }
      return expectedEntryCount
    }

    public func requestRecordingJournal(
      handle: String, request: BackendRequest
    ) async throws -> BackendResponse {
      let owner = try await currentOwner(fresh: true)
      let journal = try readJournal(handle: handle, owner: owner)
      try validateOwnedRequest(request, journal: journal)
      guard let boundBackend = backend as? RecordingJournalOwnerRequesting else {
        throw EncryptedRecordingJournalError.ownerUnavailable
      }
      let response = try await boundBackend.requestRecordingJournal(request, owner: owner)
      try await requireCurrent(owner, fresh: true)
      guard request.path == "/v1/device-sessions", request.method == .POST,
        (200..<300).contains(response.status)
      else { return response }

      let sessionId = try acknowledgedSession(response, journal: journal)
      try await requireCurrent(owner)
      try withStorageLock {
        var current = try readJournal(handle: handle, owner: owner)
        guard sameCaptureIdentity(current, journal) else {
          throw EncryptedRecordingJournalError.invalidNativeAcknowledgement
        }
        if let existingSessionId = current.sessionId {
          guard existingSessionId == sessionId else {
            throw EncryptedRecordingJournalError.invalidNativeAcknowledgement
          }
          return
        }
        current.sessionId = sessionId
        try validate(current)
        try persistLocked(current, owner: owner)
      }
      return response
    }

    public func removeRecordingJournal(handle: String) async {
      guard let owner = try? await currentOwner(), isCaptureUUID(handle),
        let url = try? journalURL(handle: handle, owner: owner)
      else { return }
      do {
        try withStorageLock {
          try files.removeFile(at: url)
        }
      } catch {
        // The API is intentionally best-effort; failed removal retains data.
      }
    }

    private func currentOwner(fresh: Bool = false) async throws -> RecordingJournalOwnerContext {
      guard !retired else { throw EncryptedRecordingJournalError.retired }
      let resolved = fresh
        ? try await ownerProvider.freshRecordingJournalOwner()
        : try await ownerProvider.currentRecordingJournalOwner()
      guard !retired else { throw EncryptedRecordingJournalError.retired }
      guard let owner = resolved else {
        throw EncryptedRecordingJournalError.ownerUnavailable
      }
      try owner.validate()
      return owner
    }

    private func requireCurrent(_ expected: RecordingJournalOwnerContext, fresh: Bool = false) async throws {
      let current = try await currentOwner(fresh: fresh)
      guard current.hasSameIdentity(as: expected) else { throw EncryptedRecordingJournalError.ownerChanged }
    }

    private func partitionDirectory(_ owner: RecordingJournalOwnerContext) throws -> URL {
      let identifier: String
      do {
        identifier = try vault.partitionIdentifier(for: owner)
      } catch {
        throw EncryptedRecordingJournalError.secureVaultUnavailable
      }
      guard identifier.count == 64, Array(identifier.utf8).allSatisfy({ ASCII.isLowerHex($0) }) else {
        throw EncryptedRecordingJournalError.secureVaultUnavailable
      }
      return root.appendingPathComponent(identifier, isDirectory: true)
    }

    private func storageUsage() throws -> (files: [URL], byteCount: Int) {
      do {
        let partitions = try files.listPartitionDirectories(in: root)
        var storageFiles = [URL]()
        var byteCount = 0
        for partition in partitions {
          let partitionFiles = try files.listStorageFiles(in: partition)
          storageFiles.append(contentsOf: partitionFiles)
          guard storageFiles.count <= Self.maximumJournalFiles else {
            throw EncryptedRecordingJournalError.storageLimitExceeded
          }
          for file in partitionFiles {
            let size = try files.fileSize(at: file)
            guard size >= 0 else { throw EncryptedRecordingJournalError.storageFailure }
            let (next, overflow) = byteCount.addingReportingOverflow(size)
            guard !overflow else { throw EncryptedRecordingJournalError.storageLimitExceeded }
            byteCount = next
            guard byteCount <= Self.maximumJournalStorageBytes else {
              throw EncryptedRecordingJournalError.storageLimitExceeded
            }
          }
        }
        return (storageFiles, byteCount)
      } catch let error as EncryptedRecordingJournalError {
        throw error
      } catch {
        throw EncryptedRecordingJournalError.storageFailure
      }
    }

    private func journalURL(
      handle: String, owner: RecordingJournalOwnerContext
    ) throws -> URL {
      guard isCaptureUUID(handle) else { throw EncryptedRecordingJournalError.invalidHandle }
      return try partitionDirectory(owner)
        .appendingPathComponent(handle.lowercased()).appendingPathExtension("journal")
    }

    private func aad(
      handle: String, owner: RecordingJournalOwnerContext
    ) throws -> Data {
      let partition = try vault.partitionIdentifier(for: owner)
      return Data("omi-recording-journal-v1\n\(partition)\n\(handle)".utf8)
    }

    private func readJournal(
      handle: String, owner: RecordingJournalOwnerContext
    ) throws -> RecordingJournalRecord {
      let url = try journalURL(handle: handle, owner: owner)
      let ciphertext: Data
      do {
        ciphertext = try files.readFile(
          at: url, maximumBytes: Self.maximumEncryptedJournalBytes)
      } catch let error as RecordingJournalFileError where error == .notFound {
        throw EncryptedRecordingJournalError.journalNotFound
      } catch {
        throw EncryptedRecordingJournalError.storageFailure
      }
      let plaintext: Data
      do {
        plaintext = try vault.open(
          ciphertext, authenticating: aad(handle: handle, owner: owner), owner: owner)
      } catch let error as RecordingJournalSecureVaultError where error == .authenticationFailed {
        throw EncryptedRecordingJournalError.corruptJournal
      } catch {
        throw EncryptedRecordingJournalError.secureVaultUnavailable
      }
      let envelope: PersistedRecordingJournal
      do {
        envelope = try JSONDecoder().decode(PersistedRecordingJournal.self, from: plaintext)
      } catch {
        throw EncryptedRecordingJournalError.corruptJournal
      }
      guard envelope.version == 1,
        envelope.backendOrigin == owner.backendOrigin,
        envelope.ownerKey == owner.ownerKey,
        envelope.loginGeneration == owner.loginGeneration,
        envelope.journal.handle == handle,
        envelope.journal.captureId == handle
      else { throw EncryptedRecordingJournalError.corruptJournal }
      do {
        try validate(envelope.journal.journal)
      } catch {
        throw EncryptedRecordingJournalError.corruptJournal
      }
      return envelope.journal.journal
    }

    /// The caller must hold the root lock for the complete read/modify/write
    /// transaction; actor isolation alone does not protect other adapters.
    private func persistLocked(
      _ journal: RecordingJournalRecord, owner: RecordingJournalOwnerContext,
      allowCreate: Bool = false
    ) throws {
      let target = try journalURL(handle: journal.handle, owner: owner)
      let envelope = PersistedRecordingJournal(
        version: 1, backendOrigin: owner.backendOrigin,
        ownerKey: owner.ownerKey, loginGeneration: owner.loginGeneration,
        journal: journal)
      let plaintext: Data
      do {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        plaintext = try encoder.encode(envelope)
      } catch {
        throw EncryptedRecordingJournalError.invalidJournal
      }
      let ciphertext: Data
      do {
        ciphertext = try vault.seal(
          plaintext, authenticating: aad(handle: journal.handle, owner: owner), owner: owner)
      } catch {
        throw EncryptedRecordingJournalError.secureVaultUnavailable
      }
      guard ciphertext.count <= Self.maximumEncryptedJournalBytes else {
        throw EncryptedRecordingJournalError.storageLimitExceeded
      }
      let targetPath = target.standardizedFileURL.path
      let targetFiles = try files.listStorageFiles(
        in: target.deletingLastPathComponent())
      let targetAlreadyExists = targetFiles.contains {
        $0.standardizedFileURL.path == targetPath
      }
      if targetAlreadyExists {
        let existing = try readJournal(handle: journal.handle, owner: owner)
        guard sameCaptureIdentity(existing, journal) else {
          throw EncryptedRecordingJournalError.invalidHandle
        }
      } else if !allowCreate {
        throw EncryptedRecordingJournalError.journalNotFound
      }

      let usage = try storageUsage()
      let oldSize: Int
      if targetAlreadyExists {
        oldSize = try files.fileSize(at: target)
      } else {
        oldSize = 0
      }
      let resultingFileCount = usage.files.count + (targetAlreadyExists ? 0 : 1)
      guard resultingFileCount <= Self.maximumJournalFiles else {
        throw EncryptedRecordingJournalError.storageLimitExceeded
      }
      let (remainingBytes, underflow) = usage.byteCount.subtractingReportingOverflow(oldSize)
      let (resultingBytes, overflow) = remainingBytes.addingReportingOverflow(ciphertext.count)
      guard !underflow, !overflow,
        resultingBytes <= Self.maximumJournalStorageBytes
      else {
        throw EncryptedRecordingJournalError.storageLimitExceeded
      }
      try files.writeAtomically(ciphertext, to: target)
    }

    private func withStorageLock(_ operation: () throws -> Void) throws {
      do {
        try files.withGlobalStorageLock(in: root, operation)
      } catch let error as EncryptedRecordingJournalError {
        throw error
      } catch {
        throw EncryptedRecordingJournalError.storageFailure
      }
    }

    private func validate(_ journal: RecordingJournalRecord) throws {
      guard isCaptureUUID(journal.handle), journal.handle == journal.captureId,
        journal.deviceId.utf8.count > 0, journal.deviceId.utf8.count <= 256,
        journal.codec >= 0, journal.codec <= 255,
        isOptionalCaptureTimestamp(journal.capturedAtMs)
      else { throw EncryptedRecordingJournalError.invalidJournal }
      do {
        _ = try restoreRecording(journal)
      } catch {
        throw EncryptedRecordingJournalError.invalidJournal
      }
    }

    private func sameCaptureIdentity(
      _ lhs: RecordingJournalRecord, _ rhs: RecordingJournalRecord
    ) -> Bool {
      lhs.handle == rhs.handle && lhs.captureId == rhs.captureId
        && lhs.capturedAtMs == rhs.capturedAtMs && lhs.deviceId == rhs.deviceId
        && lhs.deviceName == rhs.deviceName && lhs.codec == rhs.codec
    }

    private func sameCaptureIdentity(
      _ journal: RecordingJournalRecord, _ input: RecordingJournalInput
    ) -> Bool {
      journal.handle == input.captureId && journal.captureId == input.captureId
        && journal.capturedAtMs == input.capturedAtMs && journal.deviceId == input.deviceId
        && journal.deviceName == input.deviceName && journal.codec == input.codec
    }

    private func validateOwnedRequest(
      _ request: BackendRequest, journal: RecordingJournalRecord
    ) throws {
      guard request.method == .POST, !request.path.contains("?"),
        !request.path.contains("#")
      else { throw EncryptedRecordingJournalError.invalidRequest }
      if request.path == "/v1/device-sessions" {
        guard let body = request.body.flatMap(JSON.parseOrNull), body.isRecord,
          body["captureId"]?.stringValue == journal.captureId,
          body["deviceId"]?.stringValue == journal.deviceId,
          body["codec"]?.safeIntegerValue == Int64(journal.codec),
          optionalTextMatches(body["deviceName"], expected: journal.deviceName),
          optionalIntegerMatches(body["capturedAtMs"], expected: journal.capturedAtMs)
        else { throw EncryptedRecordingJournalError.invalidRequest }
        return
      }
      guard let sessionId = journal.sessionId, isCaptureUUID(sessionId),
        request.path == "/v1/device-sessions/\(sessionId)/audio"
          || request.path == "/v1/device-sessions/\(sessionId)/complete"
      else { throw EncryptedRecordingJournalError.invalidRequest }
    }

    private func acknowledgedSession(
      _ response: BackendResponse, journal: RecordingJournalRecord
    ) throws -> String {
      guard let body = response.body.flatMap(JSON.parseOrNull), body.isRecord,
        let session = body["session"], session.isRecord,
        let identifier = session["id"]?.stringValue,
        isCaptureUUID(identifier),
        session["deviceId"]?.stringValue == journal.deviceId,
        session["codec"]?.safeIntegerValue == Int64(journal.codec),
        optionalTextMatches(session["deviceName"], expected: journal.deviceName),
        optionalIntegerMatches(session["capturedAtMs"], expected: journal.capturedAtMs),
        session["state"]?.stringValue != "failed"
      else { throw EncryptedRecordingJournalError.invalidNativeAcknowledgement }
      return identifier
    }
  }

  private struct PersistedRecordingJournal: Codable {
    var version: Int
    var backendOrigin: String
    var ownerKey: String
    var loginGeneration: String
    var journal: PersistedJournal

    init(
      version: Int, backendOrigin: String, ownerKey: String,
      loginGeneration: String, journal: RecordingJournalRecord
    ) {
      self.version = version
      self.backendOrigin = backendOrigin
      self.ownerKey = ownerKey
      self.loginGeneration = loginGeneration
      self.journal = PersistedJournal(journal)
    }
  }

  private struct PersistedJournal: Codable {
    var capturedAtMs: Int64?
    var handle: String
    var captureId: String
    var deviceId: String
    var deviceName: String?
    var codec: Int
    var sessionId: String?
    var entries: [String]

    init(_ journal: RecordingJournalRecord) {
      capturedAtMs = journal.capturedAtMs
      handle = journal.handle
      captureId = journal.captureId
      deviceId = journal.deviceId
      deviceName = journal.deviceName
      codec = journal.codec
      sessionId = journal.sessionId
      entries = journal.entries
    }

    var journal: RecordingJournalRecord {
      RecordingJournalRecord(
        capturedAtMs: capturedAtMs, handle: handle, captureId: captureId,
        deviceId: deviceId, deviceName: deviceName, codec: codec,
        sessionId: sessionId, entries: entries)
    }
  }

  extension PersistedRecordingJournal {
    fileprivate init(from decoder: Decoder) throws {
      let container = try decoder.container(keyedBy: CodingKeys.self)
      version = try container.decode(Int.self, forKey: .version)
      backendOrigin = try container.decode(String.self, forKey: .backendOrigin)
      ownerKey = try container.decode(String.self, forKey: .ownerKey)
      loginGeneration = try container.decode(String.self, forKey: .loginGeneration)
      journal = try container.decode(PersistedJournal.self, forKey: .journal)
    }
  }

  private func optionalTextMatches(_ value: JSONValue?, expected: String?) -> Bool {
    guard let expected else { return value == nil || value?.isNull == true }
    return value?.stringValue == expected
  }

  private func optionalIntegerMatches(_ value: JSONValue?, expected: Int64?) -> Bool {
    guard let expected else { return value == nil || value?.isNull == true }
    return value?.safeIntegerValue == expected
  }
#endif
