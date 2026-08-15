import Foundation

enum ScreenIngestCodec {
  static func encodeOCR(_ ocr: ScreenOCRAttachment) -> String {
    let payload: [String: Any] = [
      "full_text": ocr.fullText,
      "blocks": ocr.blocks.map { block -> [String: Any] in
        [
          "id": block.id,
          "text": block.text,
          "x": block.x,
          "y": block.y,
          "w": block.w,
          "h": block.h,
          "confidence": block.confidence,
        ]
      },
    ]
    let data = (try? JSONSerialization.data(withJSONObject: payload)) ?? Data("null".utf8)
    return String(data: data, encoding: .utf8) ?? "null"
  }

  static func ingestBody(
    sessionId: String,
    deviceName: String,
    clientDeviceId: String,
    rows: [ScreenIndexRow]
  ) -> Data? {
    let frames: [[String: Any]] = rows.compactMap { row in
      guard let ocrRaw = row.ocrJSON,
        let ocrObj = try? JSONSerialization.jsonObject(with: Data(ocrRaw.utf8))
      else { return nil }
      return [
        "id": row.id,
        "captured_at": row.capturedAt,
        "app_bundle_id": row.appBundleId,
        "app_name": row.appName,
        "window_title": row.windowTitle,
        "device_name": deviceName,
        "client_device_id": clientDeviceId,
        "frame_ref": ["kind": "opaque", "ref": row.frameRef],
        "dhash": row.dhash,
        "ocr": ocrObj,
      ]
    }
    guard !frames.isEmpty else { return nil }
    let body: [String: Any] = [
      "capture_session_id": sessionId,
      "frames": frames,
    ]
    return try? JSONSerialization.data(withJSONObject: body)
  }
}

struct ScreenHTTPResult {
  var status: Int
  var body: Data
}

enum ScreenHTTPPolicy {
  static func prepare(
    method: String,
    path: String,
    body: Data?,
    baseURL: URL,
    token: String?,
    clientId: String?
  ) -> BridgeHttpPolicyDecision {
    let bodyString = body.flatMap { String(data: $0, encoding: .utf8) }
    return BridgeHttpPolicy.prepare(
      id: "screen-ingest",
      method: method,
      path: path,
      headers: [:],
      body: bodyString,
      baseURL: baseURL,
      token: token,
      clientId: clientId)
  }
}

final class ScreenIngestClient: @unchecked Sendable {
  private let session: URLSession
  private let baseURL: URL
  private let custody: ShellCredentialCustody
  private let clientId: String?

  init(baseURL: URL, custody: ShellCredentialCustody, clientId: String?, session: URLSession? = nil)
  {
    self.baseURL = baseURL
    self.custody = custody
    self.clientId = clientId
    if let session {
      self.session = session
    } else {
      self.session = URLSession(configuration: BridgeHttpPolicy.sessionConfiguration())
    }
  }

  func postFrames(_ body: Data) throws -> ScreenHTTPResult {
    try perform(method: "POST", path: "/v1/screen/frames", body: body)
  }

  func getRetired() throws -> ScreenHTTPResult {
    try perform(method: "GET", path: "/v1/screen/retired", body: nil)
  }

  func putRetention(days: Int) throws -> ScreenHTTPResult {
    let body = try JSONSerialization.data(withJSONObject: ["days": days])
    return try perform(method: "PUT", path: "/v1/screen/retention", body: body)
  }

  func getTimeline(day: String) throws -> ScreenHTTPResult {
    try perform(method: "GET", path: "/v1/screen/timeline?day=\(day)", body: nil)
  }

  private func perform(method: String, path: String, body: Data?) throws -> ScreenHTTPResult {
    let decision = ScreenHTTPPolicy.prepare(
      method: method, path: path, body: body, baseURL: baseURL,
      token: custody.currentToken(), clientId: clientId)
    guard case let .dispatch(prepared) = decision else {
      throw ScreenIngestError.notAuthenticated
    }
    let sem = DispatchSemaphore(value: 0)
    var captured: Result<ScreenHTTPResult, Error>?
    session.dataTask(with: prepared.request) { data, response, error in
      if let error {
        captured = .failure(error)
      } else if let http = response as? HTTPURLResponse {
        captured = .success(ScreenHTTPResult(status: http.statusCode, body: data ?? Data()))
      } else {
        captured = .failure(ScreenIngestError.transport)
      }
      sem.signal()
    }.resume()
    sem.wait()
    switch captured {
    case .success(let value): return value
    case .failure(let error): throw error
    case .none: throw ScreenIngestError.transport
    }
  }
}

enum ScreenIngestError: Error {
  case notAuthenticated
  case transport
}

enum ScreenIngestSync {
  static func flush(
    store: ScreenLocalStore,
    client: ScreenIngestClient,
    sessionId: String,
    deviceName: String,
    now: Date
  ) -> String {
    let cursor = store.ingestCursor()
    if !cursor.canAttempt(now: now) { return "backoff" }
    let rows = store.pendingOCRRows(limit: ScreenIngestCursor.maxBatch)
    guard !rows.isEmpty else { return "idle" }
    guard
      let body = ScreenIngestCodec.ingestBody(
        sessionId: sessionId,
        deviceName: deviceName,
        clientDeviceId: store.clientDeviceId,
        rows: rows)
    else { return "encode-failed" }
    do {
      let result = try client.postFrames(body)
      if (200..<300).contains(result.status) {
        let ids = rows.map(\.id)
        store.markIngested(ids: ids)
        store.setIngestCursor(cursor.afterSuccess(acceptedIds: ids))
        return "ok:\(ids.count):\(result.status)"
      }
      store.setIngestCursor(cursor.afterFailure(now: now))
      return "http:\(result.status)"
    } catch {
      store.setIngestCursor(cursor.afterFailure(now: now))
      return "transport"
    }
  }

  static func collectRetired(store: ScreenLocalStore, client: ScreenIngestClient) -> String {
    do {
      let result = try client.getRetired()
      guard (200..<300).contains(result.status),
        let obj = try JSONSerialization.jsonObject(with: result.body) as? [String: Any],
        let retired = obj["retired"] as? [[String: Any]]
      else { return "http:\(result.status)" }
      var refs: [String] = []
      for item in retired {
        if let refObj = item["frame_ref"] as? [String: Any] {
          if let ref = refObj["ref"] as? String { refs.append(ref) }
          if let path = refObj["path"] as? String { refs.append(path) }
        }
      }
      if !refs.isEmpty { store.applyRetiredRefs(refs) }
      return "retired:\(refs.count)"
    } catch {
      return "transport"
    }
  }
}
