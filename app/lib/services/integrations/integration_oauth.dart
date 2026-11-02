import 'dart:async';

import 'package:url_launcher/url_launcher.dart';

typedef IntegrationBrowserLauncher = Future<bool> Function(Uri uri);

/// Starts authorization; only a subsequent server status read proves connection.
/// Querying canLaunchUrl first can incorrectly reject an installed Android browser.
Future<bool> launchIntegrationOAuth(
  Future<String?> Function() fetchUrl, {
  IntegrationBrowserLauncher? openBrowser,
  bool Function()? isCurrent,
  Duration deadline = const Duration(seconds: 45),
}) async {
  final elapsed = Stopwatch()..start();
  try {
    if (isCurrent != null && !isCurrent()) return false;
    final url = await Future.sync(fetchUrl).timeout(deadline);
    final uri = url == null ? null : Uri.tryParse(url);
    if (uri == null || !['https', 'http'].contains(uri.scheme) || uri.host.isEmpty || uri.userInfo.isNotEmpty) {
      return false;
    }
    if (isCurrent != null && !isCurrent()) return false;
    final remaining = deadline - elapsed.elapsed;
    if (remaining <= Duration.zero) return false;
    final launch = openBrowser ?? (Uri uri) => launchUrl(uri, mode: LaunchMode.externalApplication);
    final opened = await launch(uri).timeout(remaining);
    return opened && (isCurrent?.call() ?? true);
  } catch (_) {
    // URLs may contain OAuth state; do not include them in errors or logs.
    return false;
  } finally {
    elapsed.stop();
  }
}
