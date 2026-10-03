import Foundation

extension APIClient {
  enum DataExportError: LocalizedError {
    case incompleteExport
    case unexpectedContentType

    var errorDescription: String? {
      switch self {
      case .incompleteExport:
        return "The export download did not finish completely. Please try again."
      case .unexpectedContentType:
        return "The export response was not valid JSON."
      }
    }
  }

  static var exportCompletionSuffix: Data { Data(",\n  \"export_complete\": true\n}\n".utf8) }

  func exportUserData(
    to destination: URL,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    onProgress: @escaping @Sendable (Int64) -> Void
  ) async throws {
    var authPolicy = RequestAuthPolicy.ownerBound(authorizationSnapshot)
    // An export is an interactive, session-bound request. If the forced refresh
    // still receives 401, invalidate only while this captured owner is current.
    authPolicy.signOutOn401 = true
    try validateExpectedOwner(authPolicy)
    guard let url = URL(string: baseURL + "v1/users/export?stream=true") else {
      throw APIError.invalidResponse
    }
    var request = URLRequest(url: url)
    request.httpMethod = "GET"
    request.timeoutInterval = 120
    request.allHTTPHeaderFields = try await buildHeaders(
      requireAuth: true,
      includeBYOK: false,
      expectedAuthOwnerId: authorizationSnapshot.ownerID)
    try validateExpectedOwner(authPolicy)

    let result = try await performExportDownload(
      request,
      authPolicy: authPolicy,
      retriedAuth: false,
      onProgress: onProgress)
    defer { try? FileManager.default.removeItem(at: result.fileURL) }
    try Task.checkCancellation()
    try validateExpectedOwner(authPolicy)

    guard result.response.statusCode == 200 else {
      throw APIError.httpError(statusCode: result.response.statusCode)
    }
    guard Self.isJSONContentType(result.response) else {
      throw DataExportError.unexpectedContentType
    }
    let stagedSize =
      (try? FileManager.default.attributesOfItem(atPath: result.fileURL.path)[.size] as? Int64) ?? 0
    try Self.validateExportFile(at: result.fileURL, expectedLength: result.response.expectedContentLength)
    onProgress(stagedSize)

    try Self.publishExportFile(from: result.fileURL, to: destination) {
      try Task.checkCancellation()
      try validateExpectedOwner(authPolicy)
    }
  }

  private func performExportDownload(
    _ request: URLRequest,
    authPolicy: RequestAuthPolicy,
    retriedAuth: Bool,
    onProgress: @escaping @Sendable (Int64) -> Void
  ) async throws -> (fileURL: URL, response: HTTPURLResponse) {
    let stagingURL = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-export-\(UUID().uuidString).part")
    var handedOff = false
    defer {
      if !handedOff { try? FileManager.default.removeItem(at: stagingURL) }
    }

    let delegate = DataExportDownloadDelegate(stagingURL: stagingURL, onProgress: onProgress)
    let (downloadedURL, response) = try await session.download(for: request, delegate: delegate)
    guard let httpResponse = response as? HTTPURLResponse else {
      throw APIError.invalidResponse
    }
    try validateExpectedOwner(authPolicy)

    if httpResponse.statusCode == 401 {
      guard authPolicy.allowsAuthRetry else { throw APIError.unauthorized }
      let endpoint = endpointLabel(for: request)
      if !retriedAuth, authPolicy.recordsAuthRetryTelemetry {
        DesktopDiagnosticsManager.shared.recordApiAuthRetry(endpoint: endpoint, outcome: "retrying")
      }
      guard
        let retryRequest = try await authorizedRetryRequest(
          from: request,
          retriedAuth: retriedAuth,
          authPolicy: authPolicy
        )
      else {
        if authPolicy.recordsAuthRetryTelemetry {
          DesktopDiagnosticsManager.shared.recordApiAuthRetry(endpoint: endpoint, outcome: "unauthorized")
        }
        throw APIError.unauthorized
      }
      do {
        let result = try await performExportDownload(
          retryRequest,
          authPolicy: authPolicy,
          retriedAuth: true,
          onProgress: onProgress)
        let outcome = (200...299).contains(result.response.statusCode) ? "succeeded" : "failed"
        if authPolicy.recordsAuthRetryTelemetry {
          DesktopDiagnosticsManager.shared.recordApiAuthRetry(endpoint: endpoint, outcome: outcome)
        }
        return result
      } catch {
        if authPolicy.recordsAuthRetryTelemetry, case APIError.unauthorized = error {
          throw error
        } else if authPolicy.recordsAuthRetryTelemetry {
          DesktopDiagnosticsManager.shared.recordApiAuthRetry(endpoint: endpoint, outcome: "failed")
        }
        throw error
      }
    }

    if let stagingError = delegate.stagingError { throw stagingError }
    if !delegate.didStage {
      if FileManager.default.fileExists(atPath: downloadedURL.path) {
        try FileManager.default.moveItem(at: downloadedURL, to: stagingURL)
      } else {
        throw APIError.invalidResponse
      }
    }
    handedOff = true
    return (stagingURL, httpResponse)
  }

  static func isJSONContentType(_ response: HTTPURLResponse) -> Bool {
    guard let contentType = response.value(forHTTPHeaderField: "Content-Type") else { return false }
    return
      contentType
      .split(separator: ";")
      .first?
      .trimmingCharacters(in: .whitespaces)
      .lowercased() == "application/json"
  }

  static func validateExportFile(at url: URL, expectedLength: Int64) throws {
    let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
    guard let size = attributes[.size] as? Int64, size > 0 else {
      throw DataExportError.incompleteExport
    }
    if expectedLength >= 0, expectedLength != size {
      throw DataExportError.incompleteExport
    }
    let suffix = Self.exportCompletionSuffix
    guard size >= suffix.count else { throw DataExportError.incompleteExport }
    let handle = try FileHandle(forReadingFrom: url)
    defer { try? handle.close() }
    try handle.seek(toOffset: UInt64(size) - UInt64(suffix.count))
    let tail = try handle.readToEnd() ?? Data()
    guard tail == suffix else { throw DataExportError.incompleteExport }
  }

  static func publishExportFile(
    from stagedDownload: URL,
    to destination: URL,
    beforeCommit: () throws -> Void
  ) throws {
    let stagedDestination = destination.deletingLastPathComponent()
      .appendingPathComponent(".\(destination.lastPathComponent).\(UUID().uuidString).part")
    do {
      try FileManager.default.moveItem(at: stagedDownload, to: stagedDestination)
      try FileManager.default.setAttributes(
        [.posixPermissions: 0o600],
        ofItemAtPath: stagedDestination.path)
      try beforeCommit()
      if FileManager.default.fileExists(atPath: destination.path) {
        _ = try FileManager.default.replaceItemAt(
          destination,
          withItemAt: stagedDestination,
          options: .usingNewMetadataOnly)
      } else {
        try FileManager.default.moveItem(at: stagedDestination, to: destination)
      }
    } catch {
      try? FileManager.default.removeItem(at: stagedDestination)
      throw error
    }
  }
}

private final class DataExportDownloadDelegate: NSObject, URLSessionDownloadDelegate, @unchecked Sendable {
  let stagingURL: URL
  let onProgress: @Sendable (Int64) -> Void
  private let lock = NSLock()
  private var staged = false
  private var moveError: Error?

  init(stagingURL: URL, onProgress: @escaping @Sendable (Int64) -> Void) {
    self.stagingURL = stagingURL
    self.onProgress = onProgress
  }

  var didStage: Bool { lock.withLock { staged } }
  var stagingError: Error? { lock.withLock { moveError } }

  func urlSession(
    _ session: URLSession,
    downloadTask: URLSessionDownloadTask,
    didFinishDownloadingTo location: URL
  ) {
    do {
      try FileManager.default.moveItem(at: location, to: stagingURL)
      try FileManager.default.setAttributes(
        [.posixPermissions: 0o600],
        ofItemAtPath: stagingURL.path)
      lock.withLock { staged = true }
    } catch {
      lock.withLock { moveError = error }
    }
  }

  func urlSession(
    _ session: URLSession,
    downloadTask: URLSessionDownloadTask,
    didWriteData bytesWritten: Int64,
    totalBytesWritten: Int64,
    totalBytesExpectedToWrite: Int64
  ) {
    onProgress(totalBytesWritten)
  }
}
