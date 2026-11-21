import Foundation
import OmiExtras
import UserNotifications

/// Rich pushes: downloads the image a push names (`fcm_options.image`, set by FCM for a
/// notification with an image, and `mutable-content: 1`) and attaches it. Anything else, or a
/// failed download, delivers the push unchanged.
final class NotificationService: UNNotificationServiceExtension, @unchecked Sendable {
    /// iOS allows about 30 s; leave room to deliver before `serviceExtensionTimeWillExpire`.
    private static let timeout: TimeInterval = 20

    private let lock = NSLock()
    private var contentHandler: ((UNNotificationContent) -> Void)?
    private var content: UNMutableNotificationContent?
    private var download: URLSessionDownloadTask?

    override func didReceive(
        _ request: UNNotificationRequest,
        withContentHandler contentHandler: @escaping (UNNotificationContent) -> Void
    ) {
        guard let content = request.content.mutableCopy() as? UNMutableNotificationContent else {
            contentHandler(request.content)
            return
        }
        lock.withLock {
            self.contentHandler = contentHandler
            self.content = content
        }
        guard let url = NotificationImage.url(in: request.content.userInfo) else {
            deliver()
            return
        }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForResource = Self.timeout
        let task = URLSession(configuration: configuration).downloadTask(with: url) { [weak self] location, response, _ in
            guard let self else { return }
            if let location, let attachment = Self.attachment(at: location, response: response, url: url) {
                lock.withLock { self.content?.attachments = [attachment] }
            }
            deliver()
        }
        lock.withLock { download = task }
        task.resume()
    }

    override func serviceExtensionTimeWillExpire() {
        lock.withLock { download }?.cancel()
        deliver()
    }

    /// Hands the content over once; later calls do nothing.
    private func deliver() {
        let (handler, content) = lock.withLock {
            defer {
                contentHandler = nil
                download = nil
            }
            return (contentHandler, self.content)
        }
        guard let handler, let content else { return }
        handler(content)
    }

    /// Moves the download where the attachment can keep it, named so iOS knows its type.
    private static func attachment(at location: URL, response: URLResponse?, url: URL) -> UNNotificationAttachment? {
        if let http = response as? HTTPURLResponse, !(200 ..< 300).contains(http.statusCode) { return nil }
        guard let ext = NotificationImage.fileExtension(mimeType: response?.mimeType, url: url) else { return nil }
        let file = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString).appendingPathExtension(ext)
        do {
            try FileManager.default.moveItem(at: location, to: file)
            return try UNNotificationAttachment(identifier: "image", url: file)
        } catch {
            return nil
        }
    }
}
