import OmiTheme
import SwiftUI
import WebKit

struct HelpPage: View {
  var body: some View {
    // Crisp is remote content and serves its own opaque white page, so `drawsBackground = false`
    // on the `WKWebView` buys nothing: full-bleed and `ignoresSafeArea`, it landed as a white sheet
    // pasted edge to edge over the window's ground, square-cornered against the shell's 22 pt
    // corners. Nothing here can restyle someone else's page — but it can stop pretending to *be*
    // the window. Inset to the pane gutters and cut to the card corner, it reads as a panel of
    // content sitting on the ground, which is what every other page on this surface is.
    CrispWebView()
      .clipShape(
        RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
      )
      .overlay(
        RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
          .strokeBorder(Ink.separator, lineWidth: 1)
      )
      .padding(.horizontal, SettingsGlassMetrics.paneHorizontalPadding)
      .padding(.top, SettingsGlassMetrics.paneTopPadding)
      .padding(.bottom, SettingsGlassMetrics.paneBottomPadding)
      .onAppear {
        CrispManager.shared.isViewingHelp = true
      }
      .onDisappear {
        CrispManager.shared.isViewingHelp = false
      }
  }
}

/// Visible Crisp chat webview — separate from CrispManager's background monitoring webview.
struct CrispWebView: NSViewRepresentable {
  private let websiteID = "0dcf3d1f-863d-4576-a534-31f2bb102ae5"

  func makeNSView(context: Context) -> WKWebView {
    let config = WKWebViewConfiguration()
    config.defaultWebpagePreferences.allowsContentJavaScript = true
    let webView = WKWebView(frame: .zero, configuration: config)
    // The Crisp document loads asynchronously. Keep its native view transparent during that
    // interval so the shared PageGlassLane remains the only ground instead of flashing a white
    // rectangle inside the glass panel.
    webView.setValue(false, forKeyPath: "opaque")
    webView.underPageBackgroundColor = .clear
    webView.setValue(false, forKeyPath: "drawsBackground")

    var urlString = "https://go.crisp.chat/chat/embed/?website_id=\(websiteID)"
    if let email = AuthState.shared.userEmail,
      let encodedEmail = email.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed)
    {
      urlString += "&user_email=\(encodedEmail)"
    }
    let name = AuthService.shared.displayName
    if !name.isEmpty,
      let encodedName = name.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed)
    {
      urlString += "&user_nickname=\(encodedName)"
    }

    if let url = URL(string: urlString) {
      webView.load(URLRequest(url: url))
    }
    return webView
  }

  func updateNSView(_ nsView: WKWebView, context: Context) {}
}
