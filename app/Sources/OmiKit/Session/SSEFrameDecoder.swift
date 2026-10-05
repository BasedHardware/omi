import Foundation

/// Retains incomplete UTF-8 lines between network chunks. SSE permits LF,
/// CRLF and CR line endings; only a blank line completes a frame.
struct SSEFrameDecoder {
  private var line = [UInt8]()
  private var lines = [String]()
  private var afterCarriageReturn = false
  private var firstLine = true

  mutating func append(_ byte: UInt8) -> String? {
    if afterCarriageReturn && byte == ASCII.lineFeed {
      afterCarriageReturn = false
      return nil
    }
    afterCarriageReturn = byte == ASCII.carriageReturn
    guard byte == ASCII.lineFeed || byte == ASCII.carriageReturn else {
      line.append(byte)
      return nil
    }
    var text = decodeUTF8Lossy(line)
    line.removeAll(keepingCapacity: true)
    if firstLine {
      firstLine = false
      if text.hasPrefix("\u{FEFF}") { text = String(text.dropFirst()) }
    }
    if text.isEmpty {
      guard !lines.isEmpty else { return nil }
      let frame = lines.joined(separator: "\n")
      lines.removeAll(keepingCapacity: true)
      return frame
    }
    lines.append(text)
    return nil
  }

  mutating func finish() -> String? {
    if !line.isEmpty {
      lines.append(decodeUTF8Lossy(line))
      line.removeAll(keepingCapacity: true)
    }
    guard !lines.isEmpty else { return nil }
    let frame = lines.joined(separator: "\n")
    lines.removeAll(keepingCapacity: true)
    return frame
  }
}
