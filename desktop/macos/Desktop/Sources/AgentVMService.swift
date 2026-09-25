import Foundation
@preconcurrency import GRDB
import OmiSupport

final class GzipProcessController: @unchecked Sendable {
  private let lock = NSLock()
  private var process: Process?
  private var cancelled = false

  func run(_ process: Process) throws {
    lock.lock()
    guard !cancelled else {
      lock.unlock()
      throw CancellationError()
    }
    self.process = process
    do {
      // Launch while holding the same lock used by cancel(). Cancellation
      // therefore either wins before launch or observes the running process.
      try process.run()
      lock.unlock()
    } catch {
      self.process = nil
      lock.unlock()
      throw error
    }
  }

  func cancel() {
    lock.lock()
    cancelled = true
    let process = process
    lock.unlock()
    if process?.isRunning == true {
      process?.terminate()
    }
  }
}

/// Manages the cloud agent VM lifecycle: provisioning, status polling, and database upload.
/// All operations are fire-and-forget from the caller's perspective.
actor AgentVMService {
  static let shared = AgentVMService()

  private var isRunning = false
  private var lifecycleGeneration: UInt64 = 0
  private var pipelineTask: Task<Void, Never>?

  /// Revoke every suspended VM operation before an effective-owner transition
  /// publishes the next account. Late status, upload, and token-send results
  /// remain harmless because each continuation revalidates this generation.
  func cancelForOwnerTransition() async {
    lifecycleGeneration &+= 1
    let task = pipelineTask
    task?.cancel()
    pipelineTask = nil
    isRunning = false
    await task?.value
    log("AgentVMService: Cancelled owner-bound lifecycle work")
  }

  /// Adopt an existing agent VM on signed-in launch warmup.
  /// Never creates a VM: missing status or a status-check failure returns
  /// without calling `provisionAgentVM` / `runPipeline`. Use `startPipeline()`
  /// for onboarding and other explicit first-agent-use paths.
  func ensureProvisioned() {
    startOwnerBoundPipeline(checkExisting: true)
  }

  /// Kick off the full VM setup pipeline: provision → poll status → upload DB.
  /// Safe to call multiple times — only one pipeline runs at a time.
  func startPipeline() {
    startOwnerBoundPipeline(checkExisting: false)
  }

  private func startOwnerBoundPipeline(checkExisting: Bool) {
    guard !isRunning else {
      log("AgentVMService: Pipeline already running, skipping")
      return
    }
    guard let ownerID = RuntimeOwnerIdentity.currentOwnerId() else {
      log("AgentVMService: No effective owner; provisioning not started")
      return
    }
    isRunning = true
    let generation = lifecycleGeneration

    pipelineTask = Task {
      defer {
        if lifecycleGeneration == generation {
          isRunning = false
          pipelineTask = nil
        }
      }
      if checkExisting {
        await ensureExistingOrProvision(ownerID: ownerID, generation: generation)
      } else {
        await runPipeline(ownerID: ownerID, generation: generation)
      }
    }
  }

  enum WarmupAction: Equatable {
    case adoptReady
    case pollUntilReady
    case skip
  }

  /// Launch warmup may only reconnect to an existing VM. A missing box, an
  /// unrecognized status, or a failed status check must not create one.
  static func warmupAction(
    status: String?,
    ip: String?,
    statusCheckFailed: Bool = false
  ) -> WarmupAction {
    if statusCheckFailed {
      return .skip
    }
    switch status {
    case "ready":
      return ip == nil ? .pollUntilReady : .adoptReady
    case "provisioning", "stopped":
      return .pollUntilReady
    default:
      return .skip
    }
  }

  private func ensureExistingOrProvision(ownerID: String, generation: UInt64) async {
    let status: APIClient.AgentStatusResponse?
    do {
      status = try await APIClient.shared.getAgentStatus()
    } catch {
      guard isCurrent(ownerID: ownerID, generation: generation) else { return }
      log("AgentVMService: Status check failed — \(error.localizedDescription), not provisioning")
      return
    }
    guard isCurrent(ownerID: ownerID, generation: generation) else { return }

    switch Self.warmupAction(status: status?.status, ip: status?.ip) {
    case .adoptReady:
      guard let status, let ip = status.ip else { return }
      await prepareReadyVM(status, ip: ip, ownerID: ownerID, generation: generation)
    case .pollUntilReady:
      if let result = await pollUntilReady(
        maxAttempts: 75,
        intervalSeconds: 5,
        ownerID: ownerID,
        generation: generation),
        let ip = result.ip
      {
        await prepareReadyVM(result, ip: ip, ownerID: ownerID, generation: generation)
      }
    case .skip:
      log("AgentVMService: No adoptable VM on warmup — not provisioning")
    }
  }

  private func runPipeline(ownerID: String, generation: UInt64) async {
    guard isCurrent(ownerID: ownerID, generation: generation) else { return }
    // Step 1: Provision (idempotent — returns existing VM if already provisioned)
    log("AgentVMService: Starting provisioning...")
    let provisionResult: APIClient.AgentProvisionResponse
    do {
      provisionResult = try await APIClient.shared.provisionAgentVM()
      guard isCurrent(ownerID: ownerID, generation: generation) else { return }
      log(
        "AgentVMService: Provision response — vmName=\(provisionResult.vmName) status=\(provisionResult.status) ip=\(provisionResult.ip ?? "none")"
      )
    } catch {
      log("AgentVMService: Provision failed — \(error.localizedDescription)")
      return
    }

    // Step 2: Poll until VM is ready with an IP
    var vmIP = provisionResult.ip
    var authToken = provisionResult.authToken

    if vmIP == nil || provisionResult.agentStatus == "provisioning" {
      log("AgentVMService: Waiting for VM to be ready...")
      let pollResult = await pollUntilReady(
        maxAttempts: 75,
        intervalSeconds: 5,
        ownerID: ownerID,
        generation: generation)
      if let result = pollResult {
        vmIP = result.ip
        authToken = result.authToken
        log("AgentVMService: VM ready — ip=\(vmIP ?? "none")")
      } else {
        log("AgentVMService: VM did not become ready in time")
        return
      }
    }

    guard let ip = vmIP else {
      log("AgentVMService: No IP available after provisioning")
      return
    }

    // Step 3: Check if DB exists and upload it
    let status = APIClient.AgentStatusResponse(
      vmName: provisionResult.vmName,
      zone: "",
      ip: ip,
      status: "ready",
      authToken: authToken,
      createdAt: "",
      lastQueryAt: nil)
    await prepareReadyVM(status, ip: ip, ownerID: ownerID, generation: generation)
  }

  private func prepareReadyVM(
    _ status: APIClient.AgentStatusResponse,
    ip: String,
    ownerID: String,
    generation: UInt64
  ) async {
    guard isCurrent(ownerID: ownerID, generation: generation) else { return }
    if await checkVMNeedsDatabase(vmIP: ip, authToken: status.authToken) {
      let uploaded = await uploadDatabase(
        vmIP: ip,
        authToken: status.authToken,
        ownerID: ownerID,
        generation: generation)
      if !uploaded {
        // AgentSync owns the in-session recovery path for a missing VM database.
        // Keep it running after a transient initial upload failure so it can retry
        // rather than leaving this launch permanently unsynchronised.
        log("AgentVMService: Initial database upload failed; starting incremental sync recovery")
      }
    }
    guard isCurrent(ownerID: ownerID, generation: generation) else { return }
    await startIncrementalSync(
      vmIP: ip,
      authToken: status.authToken,
      ownerID: ownerID,
      generation: generation)
  }

  /// Poll GET /v2/agent/status until status is "ready" and IP is available.
  private func pollUntilReady(
    maxAttempts: Int,
    intervalSeconds: UInt64,
    ownerID: String,
    generation: UInt64
  ) async -> APIClient.AgentStatusResponse? {
    for attempt in 1...maxAttempts {
      guard isCurrent(ownerID: ownerID, generation: generation) else { return nil }
      do {
        let status: APIClient.AgentStatusResponse? = try await APIClient.shared.getAgentStatus()
        guard isCurrent(ownerID: ownerID, generation: generation) else { return nil }
        if let status = status, status.status == "ready", status.ip != nil {
          return status
        }
        if let status = status, status.status == "error" {
          log("AgentVMService: VM in error state, aborting")
          return nil
        }
        log("AgentVMService: Poll \(attempt)/\(maxAttempts) — status=\(status?.status ?? "none")")
      } catch {
        log("AgentVMService: Poll error — \(error.localizedDescription)")
      }
      do {
        try await Task.sleep(nanoseconds: intervalSeconds * 1_000_000_000)
      } catch {
        return nil
      }
    }
    return nil
  }

  private func isCurrent(ownerID: String, generation: UInt64) -> Bool {
    Self.lifecycleWorkIsCurrent(
      ownerID: ownerID,
      generation: generation,
      currentOwnerID: RuntimeOwnerIdentity.currentOwnerId(),
      currentGeneration: lifecycleGeneration,
      isCancelled: Task.isCancelled)
  }

  static func lifecycleWorkIsCurrent(
    ownerID: String,
    generation: UInt64,
    currentOwnerID: String?,
    currentGeneration: UInt64,
    isCancelled: Bool
  ) -> Bool {
    !isCancelled
      && currentGeneration == generation
      && currentOwnerID == ownerID
  }

  /// Check if the VM needs a database upload by hitting its /health endpoint.
  private func checkVMNeedsDatabase(vmIP: String, authToken: String) async -> Bool {
    guard let healthURL = URL(string: "http://\(vmIP):8080/health?token=\(authToken)") else { return true }
    var request = URLRequest(url: healthURL)
    request.setValue("Bearer \(authToken)", forHTTPHeaderField: "Authorization")
    request.timeoutInterval = 10

    do {
      let (data, _) = try await URLSession.shared.data(for: request)
      if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
        let dbReady = json["databaseReady"] as? Bool
      {
        return !dbReady
      }
    } catch {
      log("AgentVMService: Health check failed — \(error.localizedDescription)")
    }
    // If we can't reach the health endpoint, assume it needs a DB
    return true
  }

  /// Re-upload the database to a VM that lost its data (e.g. after a restart).
  /// Called by AgentSyncService when it detects databaseReady: false on the VM.
  func reuploadDatabase(vmIP: String, authToken: String) async -> Bool {
    guard let ownerID = RuntimeOwnerIdentity.currentOwnerId() else { return false }
    let generation = lifecycleGeneration
    log("AgentVMService: Re-uploading database to VM (triggered by sync failure)")
    return await uploadDatabase(
      vmIP: vmIP,
      authToken: authToken,
      ownerID: ownerID,
      generation: generation)
  }

  /// Compression ratio as a whole-number percent. Guards against a zero
  /// original size: a 0-byte or unreadable `omi.db` (which still passes the
  /// `fileExists` check and gzips to a non-empty stub) would otherwise trap on
  /// unsigned integer division by zero and crash the app during upload.
  static func compressionPercent(compressed: UInt64, original: UInt64) -> UInt64 {
    guard original > 0 else { return 0 }
    return compressed * 100 / original
  }

  private static func createConsistentSnapshot(sourcePool: DatabasePool, destination: URL) async throws {
    try await withThrowingTaskGroup(of: Void.self) { group in
      group.addTask(priority: .utility) {
        try? FileManager.default.removeItem(at: destination)
        let destinationQueue = try DatabaseQueue(path: destination.path)
        try sourcePool.backup(to: destinationQueue, pagesPerStep: 128) { _ in
          try Task.checkCancellation()
        }
      }
      try await group.waitForAll()
    }
  }

  private static func gzip(source: URL, destination: URL) async throws -> Int32 {
    let controller = GzipProcessController()
    return try await withTaskCancellationHandler {
      try await withCheckedThrowingContinuation { continuation in
        DispatchQueue.global(qos: .utility).async {
          let process = Process()
          process.executableURL = URL(fileURLWithPath: "/usr/bin/gzip")
          process.arguments = ["-c", source.path]
          do {
            try? FileManager.default.removeItem(at: destination)
            FileManager.default.createFile(atPath: destination.path, contents: nil)
            guard let output = FileHandle(forWritingAtPath: destination.path) else {
              throw CocoaError(.fileWriteUnknown)
            }
            defer { try? output.close() }
            process.standardOutput = output
            try controller.run(process)
            process.waitUntilExit()
            if process.terminationReason == .uncaughtSignal {
              throw CancellationError()
            }
            continuation.resume(returning: process.terminationStatus)
          } catch {
            continuation.resume(throwing: error)
          }
        }
      }
    } onCancel: {
      controller.cancel()
    }
  }

  /// Upload the local omi.db (gzip-compressed) to the VM's /upload endpoint.
  /// Pauses AgentSync during upload to prevent competing for memory and network.
  private func uploadDatabase(
    vmIP: String,
    authToken: String,
    ownerID: String,
    generation: UInt64
  ) async -> Bool {
    guard isCurrent(ownerID: ownerID, generation: generation) else { return false }
    await AgentSyncService.shared.pause()
    defer {
      Task {
        guard self.isCurrent(ownerID: ownerID, generation: generation) else { return }
        await AgentSyncService.shared.resume()
      }
    }
    // Find the local database path
    let dbPath = await MainActor.run {
      return DesktopLocalProfile.applicationSupportURL()
        .appendingPathComponent("users", isDirectory: true)
        .appendingPathComponent(ownerID, isDirectory: true)
        .appendingPathComponent("omi.db")
    }

    guard FileManager.default.fileExists(atPath: dbPath.path) else {
      log("AgentVMService: Local database not found at \(dbPath.path), skipping upload")
      return false
    }

    // Snapshot through SQLite's online-backup API. Compressing the live main
    // file alone can omit committed WAL pages and upload a torn database.
    guard let sourcePool = await RewindDatabase.shared.getDatabaseQueue() else {
      log("AgentVMService: Rewind database is not initialized")
      return false
    }
    let snapshotPath = dbPath.appendingPathExtension("upload.snapshot")
    let tempGzPath = snapshotPath.appendingPathExtension("gz")
    defer {
      try? FileManager.default.removeItem(at: snapshotPath)
      try? FileManager.default.removeItem(at: tempGzPath)
    }
    do {
      try await Self.createConsistentSnapshot(sourcePool: sourcePool, destination: snapshotPath)
    } catch {
      log("AgentVMService: Database snapshot failed — \(error.localizedDescription)")
      return false
    }
    guard isCurrent(ownerID: ownerID, generation: generation) else { return false }

    // Get original file size
    let originalSize: UInt64
    do {
      let attrs = try FileManager.default.attributesOfItem(atPath: snapshotPath.path)
      originalSize = attrs[.size] as? UInt64 ?? 0
    } catch {
      log("AgentVMService: Failed to get DB size — \(error.localizedDescription)")
      return false
    }

    log("AgentVMService: Compressing database (\(originalSize / 1024 / 1024) MB) via streaming gzip...")

    // Stream-compress to a temp file using shell gzip (uses ~0 MB memory vs loading entire DB)
    do {
      let terminationStatus = try await Self.gzip(source: snapshotPath, destination: tempGzPath)
      guard terminationStatus == 0 else {
        log("AgentVMService: gzip failed with exit code \(terminationStatus)")
        return false
      }

      let compressedAttrs = try FileManager.default.attributesOfItem(atPath: tempGzPath.path)
      let compressedSize = compressedAttrs[.size] as? UInt64 ?? 0
      log(
        "AgentVMService: Compressed \(originalSize / 1024 / 1024) MB → \(compressedSize / 1024 / 1024) MB (\(Self.compressionPercent(compressed: compressedSize, original: originalSize))%)"
      )
    } catch {
      log("AgentVMService: Compression failed — \(error.localizedDescription)")
      return false
    }

    log("AgentVMService: Uploading compressed database to \(vmIP)...")
    guard isCurrent(ownerID: ownerID, generation: generation) else {
      return false
    }

    // Send token both as query param (backward compat) and header (preferred)
    guard let uploadURL = URL(string: "http://\(vmIP):8080/upload?token=\(authToken)") else {
      log("AgentVMService: Invalid upload URL for IP \(vmIP)")
      try? FileManager.default.removeItem(at: tempGzPath)
      return false
    }
    var request = URLRequest(url: uploadURL)
    request.httpMethod = "POST"
    request.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
    request.setValue("gzip", forHTTPHeaderField: "Content-Encoding")
    request.setValue("Bearer \(authToken)", forHTTPHeaderField: "Authorization")
    request.timeoutInterval = 600

    for attempt in 1...3 {
      guard isCurrent(ownerID: ownerID, generation: generation) else { return false }
      do {
        // Upload from file — streams from disk, doesn't load into memory.
        let (data, response) = try await URLSession.shared.upload(for: request, fromFile: tempGzPath)
        guard isCurrent(ownerID: ownerID, generation: generation) else { return false }
        guard let httpResponse = response as? HTTPURLResponse else {
          log("AgentVMService: Upload failed — invalid response")
          return false
        }
        if httpResponse.statusCode == 200 {
          if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let bytes = json["bytesReceived"] as? Int
          {
            log("AgentVMService: Upload complete — \(bytes / 1024 / 1024) MB received by server")
          } else {
            log("AgentVMService: Upload complete")
          }
          return true
        }
        let body = String(data: data, encoding: .utf8) ?? ""
        let retryable =
          httpResponse.statusCode == 408 || httpResponse.statusCode == 429
          || (500...599).contains(httpResponse.statusCode)
        log(
          "AgentVMService: Upload attempt \(attempt) failed — HTTP \(httpResponse.statusCode): \(body)"
        )
        guard retryable, attempt < 3 else { return false }
      } catch {
        guard attempt < 3, !Task.isCancelled else {
          log("AgentVMService: Upload failed — \(error.localizedDescription)")
          return false
        }
        log("AgentVMService: Upload attempt \(attempt) failed — \(error.localizedDescription)")
      }
      do {
        try await Task.sleep(nanoseconds: UInt64(attempt) * 1_000_000_000)
      } catch {
        return false
      }
    }
    return false
  }

  /// Start incremental sync after VM is confirmed ready.
  private func startIncrementalSync(
    vmIP: String,
    authToken: String,
    ownerID: String,
    generation: UInt64
  ) async {
    guard isCurrent(ownerID: ownerID, generation: generation) else { return }
    await AgentSyncService.shared.start(vmIP: vmIP, authToken: authToken)
    guard isCurrent(ownerID: ownerID, generation: generation) else {
      await AgentSyncService.shared.stop(flushPendingChanges: false)
      return
    }
    // Send Firebase token so the VM can call backend tools
    await sendFirebaseToken(
      vmIP: vmIP,
      authToken: authToken,
      ownerID: ownerID,
      generation: generation)
  }

  /// Send the user's Firebase ID token to the VM so it can call Python backend tools.
  private func sendFirebaseToken(
    vmIP: String,
    authToken: String,
    ownerID: String,
    generation: UInt64
  ) async {
    guard isCurrent(ownerID: ownerID, generation: generation) else { return }
    do {
      let idToken = try await AuthService.shared.getIdToken()
      guard isCurrent(ownerID: ownerID, generation: generation) else { return }
      // Send token both as query param (backward compat) and header (preferred)
      guard let url = URL(string: "http://\(vmIP):8080/auth?token=\(authToken)") else { return }
      var request = URLRequest(url: url)
      request.httpMethod = "POST"
      request.setValue("application/json", forHTTPHeaderField: "Content-Type")
      request.setValue("Bearer \(authToken)", forHTTPHeaderField: "Authorization")
      request.timeoutInterval = 15

      let body: [String: String] = ["firebaseToken": idToken]
      request.httpBody = try JSONSerialization.data(withJSONObject: body)

      let (data, response) = try await URLSession.shared.data(for: request)
      guard isCurrent(ownerID: ownerID, generation: generation) else { return }
      guard let httpResponse = response as? HTTPURLResponse else { return }

      if httpResponse.statusCode == 200 {
        if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
          let toolCount = json["toolsRegistered"] as? Int
        {
          log("AgentVMService: Firebase token sent to VM (\(toolCount) backend tools registered)")
        } else {
          log("AgentVMService: Firebase token sent to VM")
        }
      } else {
        let body = String(data: data, encoding: .utf8) ?? ""
        log("AgentVMService: Failed to send Firebase token — HTTP \(httpResponse.statusCode): \(body)")
      }
    } catch {
      log("AgentVMService: Failed to send Firebase token — \(error.localizedDescription)")
    }
  }

}
