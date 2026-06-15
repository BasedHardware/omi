import Foundation
import Network

// MARK: - Hand-rolled WebSocket client (RFC 6455 over Network.framework TCP+TLS)
//
// Apple's WebSocket stacks cannot reach Google's Gemini Live endpoint:
//   • URLSessionWebSocketTask → "Socket is not connected" (HTTP/2 upgrade reset)
//   • NWProtocolWebSocket     → ECONNABORTED (POSIX 53), even with ALPN pinned
// Node's `ws` (a plain HTTP/1.1 Upgrade) connects fine, so the problem is Apple's
// WS framing, not the endpoint. This minimal client does the HTTP/1.1 Upgrade and
// frame codec by hand over a raw TLS NWConnection — verified to reach
// "101 Switching Protocols" + setupComplete against Gemini BidiGenerateContent.
//
// Client → server frames are masked (required); server → client frames are not.
// Text (0x1) and binary (0x2) data frames are both delivered as Data (Gemini sends
// JSON in binary frames). Continuation (0x0) frames are reassembled; pings are
// answered with pongs.

final class RawWebSocket {
  var onOpen: (() -> Void)?
  var onMessage: ((Data) -> Void)?
  var onClose: ((Int, String) -> Void)?
  var onError: ((String) -> Void)?

  private let url: URL
  private let queue: DispatchQueue
  private var conn: NWConnection?
  private var handshakeDone = false
  private var inbound = Data()
  // Reassembly across fragmented frames.
  private var fragment = Data()
  private var closed = false

  init(url: URL, queue: DispatchQueue) {
    self.url = url
    self.queue = queue
  }

  func connect() {
    let host = url.host ?? ""
    let port = UInt16(url.port ?? 443)
    let tls = NWProtocolTLS.Options()
    sec_protocol_options_add_tls_application_protocol(tls.securityProtocolOptions, "http/1.1")
    let params = NWParameters(tls: tls)
    let c = NWConnection(host: NWEndpoint.Host(host), port: NWEndpoint.Port(rawValue: port)!, using: params)
    conn = c
    c.stateUpdateHandler = { [weak self] state in
      guard let self else { return }
      switch state {
      case .ready: self.sendUpgrade()
      case .failed(let e): self.fail("connection failed: \(e)")
      case .waiting(let e): log("RawWebSocket: waiting \(e)")
      default: break
      }
    }
    c.start(queue: queue)
  }

  func sendText(_ text: String) {
    send(frame(opcode: 0x1, payload: Data(text.utf8)))
  }

  func close() {
    guard !closed else { return }
    closed = true
    send(frame(opcode: 0x8, payload: Data()))
    conn?.cancel()
    conn = nil
  }

  // MARK: - Handshake

  private func sendUpgrade() {
    var keyBytes = [UInt8](repeating: 0, count: 16)
    for i in 0..<16 { keyBytes[i] = UInt8.random(in: 0...255) }
    let wsKey = Data(keyBytes).base64EncodedString()
    var pathWithQuery = url.path
    if let q = url.query { pathWithQuery += "?\(q)" }
    let host = url.host ?? ""
    let req =
      "GET \(pathWithQuery) HTTP/1.1\r\n"
      + "Host: \(host)\r\n"
      + "Upgrade: websocket\r\n"
      + "Connection: Upgrade\r\n"
      + "Sec-WebSocket-Key: \(wsKey)\r\n"
      + "Sec-WebSocket-Version: 13\r\n\r\n"
    conn?.send(content: Data(req.utf8), completion: .contentProcessed { [weak self] e in
      if let e { self?.fail("upgrade send: \(e)") }
    })
    readLoop()
  }

  private func readLoop() {
    conn?.receive(minimumIncompleteLength: 1, maximumLength: 1 << 16) { [weak self] data, _, isComplete, error in
      guard let self else { return }
      if let error { self.fail("receive: \(error)"); return }
      if let data, !data.isEmpty {
        if !self.handshakeDone {
          self.inbound.append(data)
          self.tryFinishHandshake()
        } else {
          self.inbound.append(data)
          self.parseFrames()
        }
      }
      if isComplete { self.fail("stream closed"); return }
      if !self.closed { self.readLoop() }
    }
  }

  private func tryFinishHandshake() {
    guard let s = String(data: inbound, encoding: .utf8), let range = s.range(of: "\r\n\r\n") else { return }
    let head = String(s[s.startIndex..<range.lowerBound])
    let statusLine = head.components(separatedBy: "\r\n").first ?? ""
    guard statusLine.contains("101") else {
      fail("handshake failed: \(statusLine)")
      return
    }
    handshakeDone = true
    // Any bytes after the header terminator are the first WS frame(s).
    let headerByteLen = (head + "\r\n\r\n").utf8.count
    inbound.removeFirst(min(headerByteLen, inbound.count))
    onOpen?()
    if !inbound.isEmpty { parseFrames() }
  }

  // MARK: - Frame codec

  private func frame(opcode: UInt8, payload: Data) -> Data {
    var f = Data([0x80 | opcode])  // FIN + opcode
    let n = payload.count
    if n < 126 {
      f.append(UInt8(0x80 | n))
    } else if n < 65536 {
      f.append(0x80 | 126)
      f.append(UInt8(n >> 8)); f.append(UInt8(n & 0xff))
    } else {
      f.append(0x80 | 127)
      for i in stride(from: 56, through: 0, by: -8) { f.append(UInt8((n >> i) & 0xff)) }
    }
    var mask = [UInt8](repeating: 0, count: 4)
    for i in 0..<4 { mask[i] = UInt8.random(in: 0...255) }
    f.append(contentsOf: mask)
    let bytes = [UInt8](payload)
    var masked = [UInt8](repeating: 0, count: bytes.count)
    for i in 0..<bytes.count { masked[i] = bytes[i] ^ mask[i % 4] }
    f.append(contentsOf: masked)
    return f
  }

  private func parseFrames() {
    while inbound.count >= 2 {
      let base = inbound.startIndex
      let b0 = inbound[base], b1 = inbound[base + 1]
      let fin = (b0 & 0x80) != 0
      let opcode = b0 & 0x0f
      let masked = (b1 & 0x80) != 0  // servers must not mask
      var len = Int(b1 & 0x7f)
      var hdr = 2
      if len == 126 {
        guard inbound.count >= 4 else { return }
        len = Int(inbound[base + 2]) << 8 | Int(inbound[base + 3]); hdr = 4
      } else if len == 127 {
        guard inbound.count >= 10 else { return }
        len = 0
        for i in 0..<8 { len = len << 8 | Int(inbound[base + 2 + i]) }
        hdr = 10
      }
      let maskLen = masked ? 4 : 0
      guard inbound.count >= hdr + maskLen + len else { return }
      var payload = inbound.subdata(in: (base + hdr + maskLen)..<(base + hdr + maskLen + len))
      if masked {
        let mask = [UInt8](inbound.subdata(in: (base + hdr)..<(base + hdr + 4)))
        var pb = [UInt8](payload)
        for i in 0..<pb.count { pb[i] ^= mask[i % 4] }
        payload = Data(pb)
      }
      inbound.removeFirst(hdr + maskLen + len)

      switch opcode {
      case 0x0:  // continuation
        fragment.append(payload)
        if fin { onMessage?(fragment); fragment.removeAll() }
      case 0x1, 0x2:  // text / binary
        if fin {
          if fragment.isEmpty { onMessage?(payload) }
          else { fragment.append(payload); onMessage?(fragment); fragment.removeAll() }
        } else {
          fragment.append(payload)
        }
      case 0x8:  // close
        var code = 0
        var reason = ""
        if payload.count >= 2 { code = Int(payload[payload.startIndex]) << 8 | Int(payload[payload.startIndex + 1]) }
        if payload.count > 2 {
          reason = String(data: payload.subdata(in: (payload.startIndex + 2)..<payload.endIndex), encoding: .utf8) ?? ""
        }
        closed = true
        onClose?(code, reason)
        conn?.cancel(); conn = nil
      case 0x9:  // ping → pong
        send(frame(opcode: 0xA, payload: payload))
      case 0xA:  // pong
        break
      default:
        break
      }
    }
  }

  private func send(_ data: Data) {
    conn?.send(content: data, completion: .contentProcessed { [weak self] e in
      if let e { self?.fail("send: \(e)") }
    })
  }

  private func fail(_ message: String) {
    guard !closed else { return }
    closed = true
    onError?(message)
    conn?.cancel(); conn = nil
  }
}
