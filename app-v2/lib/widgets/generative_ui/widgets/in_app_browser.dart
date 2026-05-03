import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

/// Lightweight URL launcher used by the generative UI when the renderer needs
/// to open an external link.
///
/// The legacy `/app` ships a full WebView-based bottom sheet (back/forward
/// buttons, share, progress bar). app-v2 doesn't ship `webview_flutter` /
/// `share_plus` and we don't want to expand the dependency surface for a
/// renderer that's only used inside summary content. Falling back to the
/// system browser gives the user the same affordance with one tap.
class InAppBrowser {
  static Future<void> open(BuildContext context, String url, {String? title}) async {
    final uri = Uri.tryParse(url);
    if (uri == null) return;
    try {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    } catch (_) {
      // Swallow — link rendering should never crash the surrounding card.
    }
  }
}
