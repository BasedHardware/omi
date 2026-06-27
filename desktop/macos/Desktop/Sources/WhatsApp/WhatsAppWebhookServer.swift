import Foundation
import Network

actor WhatsAppWebhookServer {
  static let shared = WhatsAppWebhookServer()

  private static let defaultPort: UInt16 = 47779
  private static let maxRequestBytes = 1024 * 1024

  private let queue = DispatchQueue(label: "com.omi.desktop.whatsapp-webhook")
  private var listener: NWListener?
  private var listeningPort: UInt16 = WhatsAppWebhookServer.configuredPort()

  var url: String {
    get async {
      "http://127.0.0.1:\(listeningPort)/v1/whatsapp/webhook"
    }
  }

  func startIfNeeded() {
    guard listener == nil else { return }

    do {
      let parameters = NWParameters.tcp
      parameters.allowLocalEndpointReuse = true
      guard let loopback = IPv4Address("127.0.0.1"),
        let port = NWEndpoint.Port(rawValue: listeningPort)
      else {
        log("WhatsAppWebhookServer: invalid loopback or port")
        return
      }
      parameters.requiredLocalEndpoint = .hostPort(host: .ipv4(loopback), port: port)

      let listener = try NWListener(using: parameters)
      listener.newConnectionHandler = { [weak self] connection in
        self?.handleConnection(connection)
      }
      listener.stateUpdateHandler = { state in
        log("WhatsAppWebhookServer: listener state changed to \(String(describing: state))")
      }
      listener.start(queue: queue)
      self.listener = listener
      log("WhatsAppWebhookServer: listening on http://127.0.0.1:\(listeningPort)/v1/whatsapp/webhook")
    } catch {
      log("WhatsAppWebhookServer: failed to start listener on \(listeningPort): \(error.localizedDescription)")
    }
  }

  private nonisolated func handleConnection(_ connection: NWConnection) {
    connection.start(queue: queue)
    receiveRequest(on: connection, buffer: Data())
  }

  private nonisolated func receiveRequest(on connection: NWConnection, buffer: Data) {
    connection.receive(minimumIncompleteLength: 1, maximumLength: 128 * 1024) { [weak self] data, _, isComplete, error in
      guard let self else { return }

      if let error {
        Self.send(status: 500, body: "receive_failed: \(error.localizedDescription)", on: connection)
        return
      }

      var accumulated = buffer
      if let data {
        accumulated.append(data)
      }

      if accumulated.count > Self.maxRequestBytes {
        Self.send(status: 413, body: "request_too_large", on: connection)
        return
      }

      if let request = Self.parseRequest(from: accumulated) {
        Task {
          await self.route(request)
          Self.send(status: 200, body: "{\"ok\":true}", on: connection)
        }
        return
      }

      if isComplete {
        Self.send(status: 400, body: "incomplete_request", on: connection)
        return
      }

      self.receiveRequest(on: connection, buffer: accumulated)
    }
  }

  private func route(_ request: WhatsAppWebhookRequest) async {
    guard request.method == "POST", request.path == "/v1/whatsapp/webhook" else {
      log("WhatsAppWebhookServer: unsupported route \(request.method) \(request.path)")
      return
    }

    guard let json = try? JSONSerialization.jsonObject(with: request.body) else {
      log("WhatsAppWebhookServer: invalid webhook JSON")
      return
    }

    let handled = await handleWebhookJSON(json)
    log("WhatsAppWebhookServer: handled webhook messages=\(handled)")
  }

  private func handleWebhookJSON(_ json: Any) async -> Int {
    if let array = json as? [Any] {
      var count = 0
      for item in array {
        count += await handleWebhookJSON(item)
      }
      return count
    }

    guard let object = json as? [String: Any] else {
      return 0
    }

    var count = 0
    for candidate in webhookMessageCandidates(from: object) {
      if let message = WAIncomingMessage(event: candidate) {
        await WhatsAppReplyCoordinator.shared.handle(message)
        count += 1
      } else {
        log("WhatsAppWebhookServer: skipped non-message candidate keys=\(candidate.keys.sorted().joined(separator: ","))")
      }
    }
    return count
  }

  private func webhookMessageCandidates(from object: [String: Any]) -> [[String: Any]] {
    var candidates = [object]
    for key in ["message", "data", "payload", "event"] {
      if let nested = object[key] as? [String: Any] {
        candidates.append(nested)
      }
      if let nestedString = object[key] as? String,
        key == "message",
        !nestedString.isEmpty
      {
        var copy = object
        copy["Text"] = nestedString
        candidates.append(copy)
      }
      if let array = object[key] as? [[String: Any]] {
        candidates.append(contentsOf: array)
      }
    }
    if let messages = object["messages"] as? [[String: Any]] {
      candidates.append(contentsOf: messages)
    }
    return candidates
  }

  private nonisolated static func parseRequest(from data: Data) -> WhatsAppWebhookRequest? {
    guard let headerRange = data.range(of: Data("\r\n\r\n".utf8)),
      let headerString = String(data: data[..<headerRange.lowerBound], encoding: .utf8)
    else {
      return nil
    }

    let lines = headerString.components(separatedBy: "\r\n")
    guard let requestLine = lines.first else { return nil }
    let requestParts = requestLine.split(separator: " ")
    guard requestParts.count >= 2 else { return nil }

    var contentLength = 0
    for line in lines.dropFirst() {
      let pieces = line.split(separator: ":", maxSplits: 1)
      guard pieces.count == 2 else { continue }
      if pieces[0].trimmingCharacters(in: .whitespaces).lowercased() == "content-length" {
        contentLength = Int(pieces[1].trimmingCharacters(in: .whitespaces)) ?? 0
      }
    }

    let bodyStart = headerRange.upperBound
    let expectedLength = data.distance(from: data.startIndex, to: bodyStart) + contentLength
    guard data.count >= expectedLength else { return nil }
    let body = Data(data[bodyStart..<data.index(bodyStart, offsetBy: contentLength)])

    return WhatsAppWebhookRequest(
      method: String(requestParts[0]),
      path: String(requestParts[1]),
      body: body
    )
  }

  private nonisolated static func send(status: Int, body: String, on connection: NWConnection) {
    let reason = status == 200 ? "OK" : "Error"
    let data = Data(
      """
      HTTP/1.1 \(status) \(reason)\r
      Content-Type: application/json\r
      Content-Length: \(body.utf8.count)\r
      Connection: close\r
      \r
      \(body)
      """.utf8
    )
    connection.send(content: data, completion: .contentProcessed { _ in
      connection.cancel()
    })
  }

  private static func configuredPort() -> UInt16 {
    if let value = ProcessInfo.processInfo.environment["OMI_WHATSAPP_WEBHOOK_PORT"],
      let port = UInt16(value)
    {
      return port
    }
    return defaultPort
  }
}

private struct WhatsAppWebhookRequest {
  let method: String
  let path: String
  let body: Data
}
