import AppKit

/// The ⌘V path from "content on the system pasteboard" to "a chat attachment",
/// the paste counterpart of the drag path (`ChatAttachmentDropHandler`) and the
/// screen-frame staging path (`RecentScreenFrameStaging`).
///
/// Copied files stage through `ChatAttachment.from(url:)` exactly as dragged
/// ones do — the source file belongs to the user and is never deleted by the
/// app. Image bytes with no file behind them (a screenshot copied to the
/// clipboard) enter through an app-owned temp file, so the same lifecycle that
/// deletes a staged screen frame deletes a pasted shot that never got sent.
enum PasteboardAttachmentStaging {
  /// Reads and stages everything attachable, in board order, and returns what
  /// landed. `ChatProvider.addAttachments` owns the attachment-count cap.
  @MainActor
  static func stageAttachments(from pasteboard: NSPasteboard = .general) -> [ChatAttachment] {
    var staged: [ChatAttachment] = []

    let fileURLs =
      pasteboard.readObjects(
        forClasses: [NSURL.self], options: [.urlReadingFileURLsOnly: true]
      ) as? [URL] ?? []
    for url in fileURLs {
      if let attachment = ChatAttachment.from(url: url) {
        staged.append(attachment)
      }
    }

    let images = pasteboard.readObjects(forClasses: [NSImage.self]) as? [NSImage] ?? []
    for image in images {
      guard let jpeg = flattenedJPEGData(from: image),
        let attachment = appOwnedAttachment(jpegData: jpeg)
      else { continue }
      staged.append(attachment)
    }

    return staged
  }

  /// JPEG bytes for a pasted image, flattened onto white first: JPEG has no
  /// alpha, and a pasted PNG's transparency encoded without a ground becomes
  /// black mud.
  static func flattenedJPEGData(from image: NSImage, quality: CGFloat = 0.85) -> Data? {
    guard
      let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil),
      let context = CGContext(
        data: nil, width: cgImage.width, height: cgImage.height,
        bitsPerComponent: 8, bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGImageAlphaInfo.noneSkipFirst.rawValue)
    else { return nil }
    context.setFillColor(CGColor(gray: 1.0, alpha: 1.0))
    context.fill(CGRect(x: 0, y: 0, width: cgImage.width, height: cgImage.height))
    context.draw(cgImage, in: CGRect(x: 0, y: 0, width: cgImage.width, height: cgImage.height))
    guard let flattened = context.makeImage() else { return nil }
    return ScreenCaptureManager.jpegData(from: flattened, quality: quality)
  }

  /// Writes the bytes to an app-owned temp file and returns the attachment.
  /// Created on demand; the OS reaps it like any temp content, and a staged
  /// paste outliving its file behaves exactly like a user attachment whose
  /// source file has since moved.
  static func appOwnedAttachment(jpegData: Data) -> ChatAttachment? {
    let url =
      imagesDirectory
      .appendingPathComponent("Pasted image \(fileNameFormatter.string(from: Date())) \(UUID().uuidString).jpg")
    do {
      try jpegData.write(to: url, options: .atomic)
    } catch {
      return nil
    }
    guard var attachment = ChatAttachment.from(url: url) else { return nil }
    attachment.appOwnedFileURL = url
    return attachment
  }

  private static var imagesDirectory: URL {
    let url =
      URL(fileURLWithPath: NSTemporaryDirectory())
      .appendingPathComponent("OmiPastedImages", isDirectory: true)
    try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
    return url
  }

  /// The staging directory, for tests asserting that pasted images land
  /// directly inside it.
  static var imagesDirectoryForTesting: URL { imagesDirectory }

  private static let fileNameFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.dateFormat = "HHmmss"
    return formatter
  }()
}
