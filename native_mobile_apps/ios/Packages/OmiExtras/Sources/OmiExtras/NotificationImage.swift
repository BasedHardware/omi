import Foundation

/// The picture a push asks to show. FCM puts a notification's `image` at `fcm_options.image` of
/// the APNs payload (what `FIRMessagingExtensionHelper` reads, as the Flutter extension did); plain
/// keys are accepted for pushes sent straight through APNs.
public enum NotificationImage {
    public static let keys = ["image", "image_url", "imageUrl", "attachment-url", "attachment_url"]

    public static func url(in userInfo: [AnyHashable: Any]) -> URL? {
        if let options = userInfo["fcm_options"] as? [AnyHashable: Any], let url = secureURL(options["image"]) {
            return url
        }
        for key in keys {
            if let url = secureURL(userInfo[key]) { return url }
        }
        return nil
    }

    /// The extension an attachment file needs, from the response's MIME type, else the URL's own;
    /// nil for anything iOS cannot attach as an image.
    public static func fileExtension(mimeType: String?, url: URL) -> String? {
        let byMime: [String: String] = [
            "image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png", "image/gif": "gif",
            "image/heic": "heic", "image/webp": "webp",
        ]
        if let mime = mimeType?.lowercased().split(separator: ";").first.map({ $0.trimmingCharacters(in: .whitespaces) }),
           let ext = byMime[mime]
        {
            return ext
        }
        let ext = url.pathExtension.lowercased()
        return ["jpg", "jpeg", "png", "gif", "heic", "webp"].contains(ext) ? ext : nil
    }

    /// HTTPS only: the extension has no exception from App Transport Security.
    private static func secureURL(_ value: Any?) -> URL? {
        guard let text = (value as? String)?.trimmingCharacters(in: .whitespacesAndNewlines), !text.isEmpty,
              let url = URL(string: text), url.scheme?.lowercased() == "https", url.host?.isEmpty == false
        else { return nil }
        return url
    }
}
