import SwiftUI
import WebKit

struct HelpPage: View {
    var body: some View {
        CrispWebView()
            .ignoresSafeArea()
    }
}

struct CrispWebView: NSViewRepresentable {
    private let websiteID = "0dcf3d1f-863d-4576-a534-31f2bb102ae5"

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.defaultWebpagePreferences.allowsContentJavaScript = true
        let webView = WKWebView(frame: .zero, configuration: config)
        webView.setValue(false, forKey: "drawsBackground")

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
            webView.load(URLRequest(url: url))
        }
        return webView
    }

    func updateNSView(_ nsView: WKWebView, context: Context) {}
}
