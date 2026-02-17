import Foundation
import WebKit

/// Persistent manager that keeps a Crisp chat WKWebView alive in the background,
/// listens for incoming operator messages, fires macOS notifications, and tracks unread count.
@MainActor
class CrispManager: NSObject, ObservableObject, WKScriptMessageHandler {
    static let shared = CrispManager()

    private let websiteID = "0dcf3d1f-863d-4576-a534-31f2bb102ae5"

    /// The persistent background webview for monitoring messages
    private var webView: WKWebView?

    /// Number of unread operator messages (shown as badge in sidebar)
    @Published private(set) var unreadCount = 0

    /// Whether the user is currently viewing the Help tab
    var isViewingHelp = false {
        didSet {
            if isViewingHelp {
                unreadCount = 0
            }
        }
    }

    /// Track message keys to avoid duplicate notifications
    private var seenMessages = Set<String>()

    /// Whether initial page load has completed (skip notifications for pre-existing messages)
    private var initialLoadComplete = false

    /// Timer to keep the webview's JS context alive
    private var keepAliveTimer: Timer?

    private override init() {
        super.init()
    }

    /// Call once after sign-in to start loading the Crisp chat in the background
    func start() {
        guard webView == nil else { return }

        let config = WKWebViewConfiguration()
        config.defaultWebpagePreferences.allowsContentJavaScript = true

        // Register JS→Swift bridge
        config.userContentController.add(self, name: "crispMessage")
        config.userContentController.add(self, name: "crispReady")

        // Inject $crisp SDK listener (MutationObserver won't work reliably offscreen)
        let script = WKUserScript(source: """
            (function() {
                function watchCrispSDK() {
                    var attempts = 0;
                    var check = setInterval(function() {
                        attempts++;
                        if (attempts > 120) { clearInterval(check); return; }
                        if (window.$crisp) {
                            clearInterval(check);
                            try {
                                window.webkit.messageHandlers.crispReady.postMessage("ready");
                            } catch(e) {}
                            try {
                                $crisp.push(["on", "message:received", function(data) {
                                    var text = "";
                                    if (data && data.content) text = data.content;
                                    else if (typeof data === "string") text = data;
                                    if (text) {
                                        try {
                                            window.webkit.messageHandlers.crispMessage.postMessage(text);
                                        } catch(e) {}
                                    }
                                }]);
                            } catch(e) {}
                        }
                    }, 500);
                }
                watchCrispSDK();
            })();
            """, injectionTime: .atDocumentEnd, forMainFrameOnly: false)
        config.userContentController.addUserScript(script)

        let wv = WKWebView(frame: CGRect(x: -1, y: -1, width: 1, height: 1), configuration: config)
        wv.setValue(false, forKey: "drawsBackground")
        self.webView = wv

        // Attach to the main window's content view so macOS doesn't suspend the web process
        attachToWindow(wv)

        loadCrispPage()
        startKeepAlive()
        log("CrispManager: started, loading Crisp in background")
    }

    /// Attach the hidden webview to the app's main window so WKWebView stays active
    private func attachToWindow(_ wv: WKWebView) {
        // Try to find the main Omi window
        if let window = NSApp.windows.first(where: { $0.title == "Omi" }),
           let contentView = window.contentView {
            wv.frame = CGRect(x: -1, y: -1, width: 1, height: 1)
            wv.alphaValue = 0
            contentView.addSubview(wv)
            log("CrispManager: attached hidden webview to main window")
        } else {
            // Retry after a short delay (window might not be ready yet)
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { [weak self] in
                guard let self, let wv = self.webView else { return }
                if let window = NSApp.windows.first(where: { $0.title == "Omi" }),
                   let contentView = window.contentView {
                    wv.frame = CGRect(x: -1, y: -1, width: 1, height: 1)
                    wv.alphaValue = 0
                    contentView.addSubview(wv)
                    log("CrispManager: attached hidden webview to main window (retry)")
                } else {
                    log("CrispManager: WARNING - could not find main window to attach webview")
                }
            }
        }
    }

    private func loadCrispPage() {
        var urlString = "https://go.crisp.chat/chat/embed/?website_id=\(websiteID)"
        if let email = AuthState.shared.userEmail,
           let encodedEmail = email.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) {
            urlString += "&user_email=\(encodedEmail)"
        }
        let name = AuthService.shared.displayName
        if !name.isEmpty,
           let encodedName = name.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) {
            urlString += "&user_nickname=\(encodedName)"
        }

        if let url = URL(string: urlString) {
            webView?.load(URLRequest(url: url))
        }
    }

    /// Periodically poke the webview to prevent macOS from throttling the web process
    private func startKeepAlive() {
        keepAliveTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in
            Task { @MainActor in
                _ = try? await self?.webView?.evaluateJavaScript("1+1")
            }
        }
    }

    /// Mark messages as read (called when user opens Help tab)
    func markAsRead() {
        unreadCount = 0
    }

    // MARK: - WKScriptMessageHandler

    nonisolated func userContentController(_ userContentController: WKUserContentController,
                                           didReceive message: WKScriptMessage) {
        Task { @MainActor in
            if message.name == "crispReady" {
                log("CrispManager: Crisp SDK ready, initial load complete")
                // Small delay to let any pre-existing messages render first
                DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
                    self.initialLoadComplete = true
                    log("CrispManager: now listening for new messages")
                }
                return
            }

            guard message.name == "crispMessage" else { return }

            let text = (message.body as? String) ?? "New message"
            let key = String(text.prefix(80))

            // Deduplicate
            guard !seenMessages.contains(key) else { return }
            seenMessages.insert(key)

            // Skip notifications for pre-existing messages on initial load
            guard initialLoadComplete else {
                log("CrispManager: skipping pre-existing message: \(String(text.prefix(50)))")
                return
            }

            let preview = text.count > 100 ? String(text.prefix(100)) + "..." : text
            log("CrispManager: new operator message: \(preview)")

            // Update unread count if not currently viewing help
            if !isViewingHelp {
                unreadCount += 1
            }

            // Send macOS notification
            NotificationService.shared.sendNotification(
                title: "Help from Founder",
                message: preview,
                assistantId: "crisp"
            )
        }
    }
}
