import AppKit
import CoreFoundation
import Foundation
import WebKit

struct ChatMultipartBody {
  let fileURL: URL
  let contentLength: Int64
  let sourceSize: Int64
  let maximumChunkBytes: Int
  let boundary: String
}

enum ChatMultipartBodyError: Error {
  case notRegularFile
  case invalidSize
  case cancelled
  case io
}

enum ChatMultipartBodyBuilder {
  static let maximumAttachmentBytes: Int64 = 50 * 1_024 * 1_024
  static let chunkBytes = 64 * 1_024

  static func build(
    sourceURL: URL,
    temporaryDirectory: URL = FileManager.default.temporaryDirectory,
    cancelled: () -> Bool = { false },
    registerHandles: (FileHandle?, FileHandle?) -> Void = { _, _ in }
  ) throws -> ChatMultipartBody {
    let values = try sourceURL.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey])
    guard values.isRegularFile == true else { throw ChatMultipartBodyError.notRegularFile }
    guard let size = values.fileSize, size > 0, Int64(size) <= maximumAttachmentBytes else {
      throw ChatMultipartBodyError.invalidSize
    }
    let boundary = "omi-chat-\(UUID().uuidString.lowercased())"
    let filename = safeFilename(sourceURL.lastPathComponent)
    let escapedFilename = filename.replacingOccurrences(of: "\\", with: "\\\\")
      .replacingOccurrences(of: "\"", with: "\\\"")
    let header = Data(
      "--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"\(escapedFilename)\"\r\n\r\n"
        .utf8)
    let trailer = Data("\r\n--\(boundary)--\r\n".utf8)
    let bodyURL = temporaryDirectory.appendingPathComponent(
      "omi-chat-multipart-\(UUID().uuidString)", isDirectory: false)
    guard FileManager.default.createFile(
      atPath: bodyURL.path, contents: nil,
      attributes: [.posixPermissions: NSNumber(value: Int16(0o600))])
    else { throw ChatMultipartBodyError.io }

    do {
      let input = try FileHandle(forReadingFrom: sourceURL)
      let output = try FileHandle(forWritingTo: bodyURL)
      registerHandles(input, output)
      defer {
        registerHandles(nil, nil)
        try? input.close()
        try? output.close()
      }
      try output.write(contentsOf: header)
      var observed = 0
      while true {
        if cancelled() { throw ChatMultipartBodyError.cancelled }
        guard let chunk = try input.read(upToCount: chunkBytes), !chunk.isEmpty else { break }
        observed = max(observed, chunk.count)
        try output.write(contentsOf: chunk)
      }
      if cancelled() { throw ChatMultipartBodyError.cancelled }
      try output.write(contentsOf: trailer)
      try output.synchronize()
      let bodySize = Int64(header.count) + Int64(size) + Int64(trailer.count)
      return ChatMultipartBody(
        fileURL: bodyURL, contentLength: bodySize, sourceSize: Int64(size),
        maximumChunkBytes: observed, boundary: boundary)
    } catch {
      try? FileManager.default.removeItem(at: bodyURL)
      throw error
    }
  }

  private static func safeFilename(_ value: String) -> String {
    let normalized = value.precomposedStringWithCanonicalMapping.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !normalized.isEmpty, normalized != ".", normalized != "..",
      normalized.utf8.count <= 255,
      normalized.unicodeScalars.allSatisfy({ $0.value >= 0x20 && $0.value != 0x7f })
    else { return "upload" }
    return normalized
  }
}

struct StagedChatAttachmentDescriptor {
  let id: String
  let mimeType: String
  let sizeBytes: Int64
  let state: String
  let expiresAt: String

  var bridgeValue: [String: Any] {
    [
      "id": id,
      "mimeType": mimeType,
      "sizeBytes": NSNumber(value: sizeBytes),
      "state": state,
      "expiresAt": expiresAt,
    ]
  }
}

enum ChatAttachmentStagingPolicy {
  static func prepareRequest(
    baseURL: URL,
    token: String?,
    runId: String?,
    multipart: ChatMultipartBody
  ) -> URLRequest? {
    guard let token, !token.isEmpty,
      var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false),
      components.scheme == "http" || components.scheme == "https",
      components.host != nil
    else { return nil }
    components.path = "/v1/chat-attachments"
    components.query = nil
    components.fragment = nil
    guard let url = components.url else { return nil }
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    request.setValue(
      "multipart/form-data; boundary=\(multipart.boundary)",
      forHTTPHeaderField: "Content-Type")
    request.setValue(String(multipart.contentLength), forHTTPHeaderField: "Content-Length")
    request.setValue(
      NativeChatRequestContract.contractVersion,
      forHTTPHeaderField: NativeChatRequestContract.contractVersionHeader)
    if let clientId = BridgeHttpPolicy.shellClientId(runId: runId) {
      request.setValue(clientId, forHTTPHeaderField: NativeChatRequestContract.clientIdHeader)
    }
    return request
  }

  static func parseResponse(
    data: Data,
    response: URLResponse?,
    expectedSize: Int64
  ) -> StagedChatAttachmentDescriptor? {
    guard data.count <= 64 * 1_024,
      let http = response as? HTTPURLResponse, http.statusCode == 201,
      let object = try? JSONSerialization.jsonObject(with: data),
      let envelope = object as? [String: Any], Set(envelope.keys) == ["attachment"],
      let attachment = envelope["attachment"] as? [String: Any],
      Set(attachment.keys) == BridgeChatAttachmentStagingContract.descriptorFields,
      let id = attachment["id"] as? String,
      id.range(of: #"^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$"#, options: .regularExpression) != nil,
      let mimeType = attachment["mimeType"] as? String,
      mimeType.utf8.count <= 127,
      mimeType.range(
        of: #"^[!#$%&'*+.^_`|~0-9A-Za-z-]+/[!#$%&'*+.^_`|~0-9A-Za-z-]+$"#,
        options: .regularExpression) != nil,
      let sizeNumber = attachment["sizeBytes"] as? NSNumber,
      CFGetTypeID(sizeNumber) != CFBooleanGetTypeID(),
      sizeNumber.doubleValue.isFinite,
      sizeNumber.doubleValue.rounded() == sizeNumber.doubleValue,
      sizeNumber.int64Value > 0,
      sizeNumber.int64Value == expectedSize,
      attachment["state"] as? String == BridgeChatAttachmentStagingContract.stagedState,
      let expiresAt = attachment["expiresAt"] as? String,
      canonicalExpiry(expiresAt)
    else { return nil }
    return StagedChatAttachmentDescriptor(
      id: id, mimeType: mimeType, sizeBytes: sizeNumber.int64Value,
      state: BridgeChatAttachmentStagingContract.stagedState, expiresAt: expiresAt)
  }

  private static func canonicalExpiry(_ value: String) -> Bool {
    guard value.utf8.count == 24 else { return false }
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    guard let date = formatter.date(from: value) else { return false }
    return formatter.string(from: date) == value
  }
}

protocol ChatAttachmentUploadCancelling: AnyObject {
  func cancel()
}

extension URLSessionTask: ChatAttachmentUploadCancelling {}

typealias ChatAttachmentUploadCompletion = @Sendable (Data?, URLResponse?, Error?) -> Void

typealias ChatAttachmentUploadStarter = (
  URLRequest,
  URL,
  @escaping ChatAttachmentUploadCompletion
) -> ChatAttachmentUploadCancelling

private final class ChatAttachmentUploadDelegate: NSObject, URLSessionTaskDelegate {
  func urlSession(
    _ session: URLSession,
    task: URLSessionTask,
    willPerformHTTPRedirection response: HTTPURLResponse,
    newRequest request: URLRequest,
    completionHandler: @escaping (URLRequest?) -> Void
  ) {
    completionHandler(nil)
  }
}

private final class ChatStagingOperation: @unchecked Sendable {
  let id: String
  let sourceURL: URL
  let securityScoped: Bool
  let reply: (Any?, String?) -> Void
  private let lock = NSLock()
  private var cancelled = false
  private var input: FileHandle?
  private var output: FileHandle?
  private var multipartURL: URL?
  private var upload: ChatAttachmentUploadCancelling?
  private var cleaned = false

  init(id: String, sourceURL: URL, securityScoped: Bool, reply: @escaping (Any?, String?) -> Void) {
    self.id = id
    self.sourceURL = sourceURL
    self.securityScoped = securityScoped
    self.reply = reply
  }

  func isCancelled() -> Bool {
    lock.lock()
    defer { lock.unlock() }
    return cancelled
  }

  func registerHandles(_ input: FileHandle?, _ output: FileHandle?) {
    lock.lock()
    self.input = input
    self.output = output
    let shouldClose = cancelled
    lock.unlock()
    if shouldClose {
      try? input?.close()
      try? output?.close()
    }
  }

  func registerMultipart(_ url: URL) -> Bool {
    lock.lock()
    multipartURL = url
    let active = !cancelled
    lock.unlock()
    if !active { try? FileManager.default.removeItem(at: url) }
    return active
  }

  func registerUpload(_ task: ChatAttachmentUploadCancelling) -> Bool {
    lock.lock()
    upload = task
    let active = !cancelled
    lock.unlock()
    if !active { task.cancel() }
    return active
  }

  func cancelAndCleanup() {
    lock.lock()
    cancelled = true
    let input = self.input
    let output = self.output
    let upload = self.upload
    lock.unlock()
    try? input?.close()
    try? output?.close()
    upload?.cancel()
    cleanup()
  }

  func cleanup() {
    lock.lock()
    guard !cleaned else {
      lock.unlock()
      return
    }
    cleaned = true
    let multipartURL = self.multipartURL
    lock.unlock()
    if let multipartURL { try? FileManager.default.removeItem(at: multipartURL) }
    if securityScoped { sourceURL.stopAccessingSecurityScopedResource() }
  }
}

/// Reply-capable host for native file picking and fixed-route staging.
@MainActor
final class ChatAttachmentStagingHandler: NSObject, WKScriptMessageHandlerWithReply {
  static let channel = BridgeChatAttachmentStagingContract.channel

  private let baseURL: URL
  private let custody: ShellCredentialCustody
  private let runId: String?
  private let picker: () -> URL?
  private let startUpload: ChatAttachmentUploadStarter
  private var operations: [String: ChatStagingOperation] = [:]
  private var tornDown = false
  private let uploadDelegate: ChatAttachmentUploadDelegate?
  private let uploadSession: URLSession?

  init(
    baseURL: URL,
    custody: ShellCredentialCustody,
    runId: String?,
    picker: (() -> URL?)? = nil,
    startUpload: ChatAttachmentUploadStarter? = nil
  ) {
    self.baseURL = baseURL
    self.custody = custody
    self.runId = runId
    self.picker = picker ?? Self.pickOneRegularFile
    if let startUpload {
      self.startUpload = startUpload
      self.uploadDelegate = nil
      self.uploadSession = nil
    } else {
      let delegate = ChatAttachmentUploadDelegate()
      let configuration = URLSessionConfiguration.ephemeral
      configuration.httpCookieStorage = nil
      configuration.httpShouldSetCookies = false
      configuration.httpCookieAcceptPolicy = .never
      let session = URLSession(configuration: configuration, delegate: delegate, delegateQueue: nil)
      self.uploadDelegate = delegate
      self.uploadSession = session
      self.startUpload = { request, bodyFile, completion in
        let task = session.uploadTask(with: request, fromFile: bodyFile, completionHandler: completion)
        task.resume()
        return task
      }
    }
    super.init()
  }

  func userContentController(
    _ userContentController: WKUserContentController,
    didReceive message: WKScriptMessage,
    replyHandler: @escaping (Any?, String?) -> Void
  ) {
    receive(body: message.body, replyHandler: replyHandler)
  }

  /// Controllable production seam used by the compiled staging proofs.
  func receive(body: Any, replyHandler: @escaping (Any?, String?) -> Void) {
    guard !tornDown,
      let request = body as? [String: Any],
      Set(request.keys) == BridgeChatAttachmentStagingContract.requestFields,
      request["t"] as? String == BridgeChatAttachmentStagingContract.requestAction,
      let id = request["id"] as? String,
      safeRequestId(id), operations[id] == nil
    else {
      let candidate = (body as? [String: Any])?["id"] as? String
      let id = candidate.flatMap { safeRequestId($0) ? $0 : nil } ?? "?"
      replyHandler(failure(id: id, reason: .shellError), nil)
      return
    }
    guard custody.currentToken() != nil else {
      replyHandler(failure(id: id, reason: .unavailable), nil)
      return
    }
    guard let sourceURL = picker() else {
      replyHandler(failure(id: id, reason: .cancelled), nil)
      return
    }
    let values = try? sourceURL.resourceValues(forKeys: [.isRegularFileKey])
    guard sourceURL.isFileURL, values?.isRegularFile == true else {
      replyHandler(failure(id: id, reason: .shellError), nil)
      return
    }

    let securityScoped = sourceURL.startAccessingSecurityScopedResource()
    let operation = ChatStagingOperation(
      id: id, sourceURL: sourceURL, securityScoped: securityScoped, reply: replyHandler)
    operations[id] = operation
    DispatchQueue.global(qos: .userInitiated).async { [weak self, weak operation] in
      guard let operation else { return }
      let result = Result {
        try ChatMultipartBodyBuilder.build(
          sourceURL: sourceURL,
          cancelled: { operation.isCancelled() },
          registerHandles: { operation.registerHandles($0, $1) })
      }
      DispatchQueue.main.async { [weak self, weak operation] in
        guard let self, let operation, self.operations[id] === operation,
          !operation.isCancelled()
        else {
          if case .success(let multipart) = result {
            try? FileManager.default.removeItem(at: multipart.fileURL)
          }
          operation?.cleanup()
          return
        }
        switch result {
        case .failure:
          self.finish(operation, reply: self.failure(id: id, reason: .shellError))
        case .success(let multipart):
          self.beginUpload(operation, multipart: multipart)
        }
      }
    }
  }

  func cancelAll() {
    let current = Array(operations.values)
    operations.removeAll()
    for operation in current { operation.cancelAndCleanup() }
  }

  func teardown() {
    guard !tornDown else { return }
    tornDown = true
    cancelAll()
    uploadSession?.invalidateAndCancel()
  }

  private func beginUpload(_ operation: ChatStagingOperation, multipart: ChatMultipartBody) {
    guard operation.registerMultipart(multipart.fileURL),
      let request = ChatAttachmentStagingPolicy.prepareRequest(
        baseURL: baseURL, token: custody.currentToken(), runId: runId, multipart: multipart)
    else {
      finish(operation, reply: failure(id: operation.id, reason: .unavailable))
      return
    }
    let task = startUpload(request, multipart.fileURL) { [weak self, weak operation] data, response, error in
      DispatchQueue.main.async {
        guard let self, let operation, self.operations[operation.id] === operation,
          !operation.isCancelled()
        else {
          operation?.cleanup()
          return
        }
        guard error == nil, let data,
          let descriptor = ChatAttachmentStagingPolicy.parseResponse(
            data: data, response: response, expectedSize: multipart.sourceSize)
        else {
          self.finish(operation, reply: self.failure(id: operation.id, reason: .shellError))
          return
        }
        self.finish(operation, reply: [
          "ok": true,
          "id": operation.id,
          "attachment": descriptor.bridgeValue,
        ])
      }
    }
    _ = operation.registerUpload(task)
  }

  private func finish(_ operation: ChatStagingOperation, reply: [String: Any]) {
    guard operations.removeValue(forKey: operation.id) === operation else {
      operation.cleanup()
      return
    }
    operation.cleanup()
    guard !tornDown else { return }
    operation.reply(reply, nil)
  }

  private func failure(
    id: String,
    reason: BridgeChatAttachmentStagingContract.FailureReason
  ) -> [String: Any] {
    ["ok": false, "id": id, "reason": reason.rawValue]
  }

  private func safeRequestId(_ id: String) -> Bool {
    id.count <= 128
      && id.range(of: #"^[A-Za-z0-9][A-Za-z0-9._-]*$"#, options: .regularExpression) != nil
  }

  private static func pickOneRegularFile() -> URL? {
    let panel = NSOpenPanel()
    panel.allowsMultipleSelection = false
    panel.canChooseDirectories = false
    panel.canChooseFiles = true
    panel.canCreateDirectories = false
    panel.resolvesAliases = true
    guard panel.runModal() == .OK, panel.urls.count == 1 else { return nil }
    let url = panel.urls[0]
    let values = try? url.resourceValues(forKeys: [.isRegularFileKey])
    return values?.isRegularFile == true ? url : nil
  }
}
