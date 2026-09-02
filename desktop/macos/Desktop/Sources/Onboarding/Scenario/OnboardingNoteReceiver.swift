import Foundation
import Network

@MainActor
final class OnboardingNoteReceiver {
  enum ParseResult: Equatable {
    case accepted(note: String)
    case rejected
  }

  enum ReceiverError: Error {
    case alreadyStarting
    case listenerStopped
    case missingBoundPort
  }

  private enum RejectionReason: String {
    case alreadyAccepted = "already_accepted"
    case emptyNote = "empty_note"
    case malformedRequest = "malformed_request"
    case missingNonce = "missing_nonce"
    case missingNote = "missing_note"
    case oversizedRequest = "oversized_request"
    case receiveFailed = "receive_failed"
    case timedOut = "timed_out"
    case tooManyConnections = "too_many_connections"
    case wrongMethod = "wrong_method"
    case wrongNonce = "wrong_nonce"
    case wrongPath = "wrong_path"
  }

  private struct ParseDecision {
    let result: ParseResult
    let rejectionReason: RejectionReason?

    static func accept(_ note: String) -> ParseDecision {
      ParseDecision(result: .accepted(note: note), rejectionReason: nil)
    }

    static func reject(_ reason: RejectionReason) -> ParseDecision {
      ParseDecision(result: .rejected, rejectionReason: reason)
    }
  }

  private struct ConnectionState {
    let connection: NWConnection
    var requestData = Data()
    var timeoutTask: Task<Void, Never>?
  }

  private nonisolated static let maximumRequestBytes = 16 * 1024
  private nonisolated static let maximumNoteScalars = 1_500
  private static let maximumConnections = 8
  private static let connectionLifetime: Duration = .seconds(3)
  private static let response204 = Data("HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n".utf8)
  private static let response404 = Data("HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n".utf8)

  /// Called at most once, on the main actor, with the decoded and bounded note.
  var onNote: ((String) -> Void)?

  private let nonce: String
  private let listenerQueue = DispatchQueue(label: "com.omi.desktop.onboarding-note-receiver")
  private var listener: NWListener?
  private var startContinuation: CheckedContinuation<UInt16, Error>?
  private var boundPort: UInt16?
  private var connections: [UUID: ConnectionState] = [:]
  private var hasAcceptedNote = false

  /// Creates a receiver that accepts requests carrying exactly this nonce.
  init(nonce: String) {
    self.nonce = nonce
  }

  /// Binds an IPv4 loopback listener on an ephemeral port and returns that port.
  func start() async throws -> UInt16 {
    if let boundPort {
      return boundPort
    }
    guard listener == nil, startContinuation == nil else {
      throw ReceiverError.alreadyStarting
    }

    let parameters = NWParameters.tcp
    guard let loopback = IPv4Address("127.0.0.1") else {
      throw ReceiverError.missingBoundPort
    }
    parameters.requiredLocalEndpoint = .hostPort(host: .ipv4(loopback), port: .any)

    let listener = try NWListener(using: parameters)
    listener.stateUpdateHandler = { [weak self] state in
      Task { @MainActor in
        self?.handleListenerState(state)
      }
    }
    listener.newConnectionHandler = { [weak self] connection in
      Task { @MainActor in
        self?.accept(connection)
      }
    }
    self.listener = listener

    return try await withCheckedThrowingContinuation { continuation in
      startContinuation = continuation
      listener.start(queue: listenerQueue)
    }
  }

  /// Closes the listener and all accepted connections. Safe to call repeatedly.
  func stop() {
    let wasActive = listener != nil || !connections.isEmpty || startContinuation != nil

    listener?.stateUpdateHandler = nil
    listener?.newConnectionHandler = nil
    listener?.cancel()
    listener = nil
    boundPort = nil

    let pendingStart = startContinuation
    startContinuation = nil
    pendingStart?.resume(throwing: ReceiverError.listenerStopped)

    for state in connections.values {
      state.timeoutTask?.cancel()
      state.connection.cancel()
    }
    connections.removeAll()

    if wasActive {
      log("OnboardingNoteReceiver: stopped")
    }
  }

  // No deinit: `isolated deinit` needs the macOS 15 runtime and the app deploys to 14. The owner
  // (`SBOnboardingModel`) calls `stop()` from every teardown path; `stop()` is idempotent.

  /// Parses an HTTP request head without opening a socket.
  nonisolated static func parse(requestHead: String, nonce: String) -> ParseResult {
    parseDecision(requestHead: requestHead, nonce: nonce).result
  }

  private func handleListenerState(_ state: NWListener.State) {
    switch state {
    case .ready:
      guard let port = listener?.port?.rawValue else {
        failStart(with: ReceiverError.missingBoundPort)
        return
      }
      boundPort = port
      let continuation = startContinuation
      startContinuation = nil
      continuation?.resume(returning: port)
      log("OnboardingNoteReceiver: listening on 127.0.0.1:\(port)")
    case .failed(let error):
      failStart(with: error)
    case .cancelled:
      let continuation = startContinuation
      startContinuation = nil
      continuation?.resume(throwing: ReceiverError.listenerStopped)
    default:
      break
    }
  }

  private func failStart(with error: Error) {
    listener?.cancel()
    listener = nil
    boundPort = nil
    let continuation = startContinuation
    startContinuation = nil
    continuation?.resume(throwing: error)
    log("OnboardingNoteReceiver: listener failed to start")
  }

  private func accept(_ connection: NWConnection) {
    guard !hasAcceptedNote else {
      rejectUntracked(connection, reason: .alreadyAccepted)
      return
    }
    guard connections.count < Self.maximumConnections else {
      rejectUntracked(connection, reason: .tooManyConnections)
      return
    }

    let id = UUID()
    connections[id] = ConnectionState(connection: connection)
    connections[id]?.timeoutTask = Task { @MainActor [weak self] in
      do {
        try await Task.sleep(for: Self.connectionLifetime)
      } catch {
        return
      }
      self?.reject(id, reason: .timedOut)
    }

    connection.start(queue: listenerQueue)
    receive(on: id)
  }

  private func receive(on id: UUID) {
    guard let state = connections[id] else { return }
    let remaining = Self.maximumRequestBytes - state.requestData.count
    state.connection.receive(minimumIncompleteLength: 1, maximumLength: max(1, remaining + 1)) {
      [weak self] data, _, isComplete, error in
      Task { @MainActor in
        self?.handleReceivedData(data, isComplete: isComplete, error: error, connectionID: id)
      }
    }
  }

  private func handleReceivedData(_ data: Data?, isComplete: Bool, error: NWError?, connectionID id: UUID) {
    guard var state = connections[id] else { return }

    if error != nil {
      reject(id, reason: .receiveFailed)
      return
    }
    if let data {
      state.requestData.append(data)
      connections[id] = state
    }
    guard state.requestData.count <= Self.maximumRequestBytes else {
      reject(id, reason: .oversizedRequest)
      return
    }

    let headerTerminator = Data("\r\n\r\n".utf8)
    if let terminatorRange = state.requestData.range(of: headerTerminator) {
      let headData = state.requestData[..<terminatorRange.lowerBound]
      guard let requestHead = String(data: headData, encoding: .utf8) else {
        reject(id, reason: .malformedRequest)
        return
      }
      handleRequestHead(requestHead, connectionID: id)
      return
    }

    if isComplete {
      reject(id, reason: .malformedRequest)
    } else {
      receive(on: id)
    }
  }

  private func handleRequestHead(_ requestHead: String, connectionID id: UUID) {
    guard !hasAcceptedNote else {
      reject(id, reason: .alreadyAccepted)
      return
    }

    let decision = Self.parseDecision(requestHead: requestHead, nonce: nonce)
    switch decision.result {
    case .accepted(let note):
      hasAcceptedNote = true
      sendAccepted(note, connectionID: id)
    case .rejected:
      reject(id, reason: decision.rejectionReason ?? .malformedRequest)
    }
  }

  private func sendAccepted(_ note: String, connectionID id: UUID) {
    guard let state = connections[id] else { return }
    state.timeoutTask?.cancel()
    state.connection.send(
      content: Self.response204,
      completion: .contentProcessed { [weak self] _ in
        Task { @MainActor in
          guard let self else { return }
          self.finishConnection(id)
          self.onNote?(note)
          self.stop()
        }
      })
  }

  private func reject(_ id: UUID, reason: RejectionReason) {
    guard let state = connections[id] else { return }
    state.timeoutTask?.cancel()
    log("OnboardingNoteReceiver: rejected request (reason=\(reason.rawValue))")
    state.connection.send(
      content: Self.response404,
      completion: .contentProcessed { [weak self] _ in
        Task { @MainActor in
          self?.finishConnection(id)
        }
      })
  }

  private func rejectUntracked(_ connection: NWConnection, reason: RejectionReason) {
    log("OnboardingNoteReceiver: rejected request (reason=\(reason.rawValue))")
    connection.start(queue: listenerQueue)
    connection.send(
      content: Self.response404,
      completion: .contentProcessed { _ in
        connection.cancel()
      })
  }

  private func finishConnection(_ id: UUID) {
    guard let state = connections.removeValue(forKey: id) else { return }
    state.timeoutTask?.cancel()
    state.connection.cancel()
  }

  private nonisolated static func parseDecision(requestHead: String, nonce: String) -> ParseDecision {
    guard requestHead.utf8.count <= maximumRequestBytes else {
      return .reject(.oversizedRequest)
    }
    guard let requestLine = requestHead.components(separatedBy: "\r\n").first else {
      return .reject(.malformedRequest)
    }
    let requestParts = requestLine.split(separator: " ", omittingEmptySubsequences: false)
    guard requestParts.count == 3 else {
      return .reject(.malformedRequest)
    }
    guard requestParts[0] == "GET" else {
      return .reject(.wrongMethod)
    }
    guard requestParts[2] == "HTTP/1.1" else {
      return .reject(.malformedRequest)
    }

    let targetParts = requestParts[1].split(separator: "?", maxSplits: 1, omittingEmptySubsequences: false)
    guard targetParts.first == "/onboarding/note" else {
      return .reject(.wrongPath)
    }
    guard targetParts.count == 2 else {
      return .reject(.missingNonce)
    }

    var receivedNonces: [String] = []
    var receivedNotes: [String] = []
    for item in targetParts[1].split(separator: "&", omittingEmptySubsequences: false) {
      let pair = item.split(separator: "=", maxSplits: 1, omittingEmptySubsequences: false)
      guard let encodedName = pair.first,
        let name = String(encodedName).removingPercentEncoding
      else {
        return .reject(.malformedRequest)
      }
      let encodedValue = pair.count == 2 ? String(pair[1]) : ""
      guard let value = encodedValue.removingPercentEncoding else {
        return .reject(.malformedRequest)
      }
      switch name {
      case "nonce": receivedNonces.append(value)
      case "note": receivedNotes.append(value)
      default: break
      }
    }

    guard receivedNonces.count == 1, let receivedNonce = receivedNonces.first else {
      return .reject(.missingNonce)
    }
    guard receivedNonce == nonce else {
      return .reject(.wrongNonce)
    }
    guard receivedNotes.count == 1, let encodedNote = receivedNotes.first else {
      return .reject(.missingNote)
    }

    let withoutControls = encodedNote.unicodeScalars.filter {
      !CharacterSet.controlCharacters.contains($0)
    }
    let trimmed = String(String.UnicodeScalarView(withoutControls))
      .trimmingCharacters(in: .whitespacesAndNewlines)
    let bounded = String(String.UnicodeScalarView(trimmed.unicodeScalars.prefix(maximumNoteScalars)))
    guard !bounded.isEmpty else {
      return .reject(.emptyNote)
    }
    return .accept(bounded)
  }
}
