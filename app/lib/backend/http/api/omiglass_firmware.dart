import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:omi/utils/logger.dart';

/// Fetches the latest OmiGlass firmware release from GitHub Releases API.
/// Returns a map with: version, download_url, changelog, tag
/// Returns empty map if no release found or on error.
Future<Map<String, dynamic>> getLatestOmiGlassFirmware() async {
  try {
    final response = await http.get(
      Uri.parse('https://api.github.com/repos/BasedHardware/omi/releases?per_page=20'),
      headers: {'Accept': 'application/vnd.github.v3+json'},
    );

    if (response.statusCode != 200) {
      Logger.debug('OmiGlass firmware check: GitHub API returned ${response.statusCode}');
      return {};
    }

    final List<dynamic> releases = jsonDecode(response.body);

    for (final release in releases) {
      if (release['draft'] == true) continue;

      final String tag = release['tag_name'] ?? '';
      if (!tag.startsWith('omiglass-fw-v')) continue;

      // Extract version from tag: "omiglass-fw-v2.2.0" → "2.2.0"
      final version = tag.replaceFirst('omiglass-fw-v', '');

      // Get firmware binary download URL from assets
      String? downloadUrl;
      final List<dynamic> assets = release['assets'] ?? [];
      for (final asset in assets) {
        final String name = asset['name'] ?? '';
        if (name.endsWith('.bin')) {
          downloadUrl = asset['browser_download_url'];
          break;
        }
      }

      if (downloadUrl == null) continue;

      return {
        'version': version,
        'download_url': downloadUrl,
        'changelog': release['body'] ?? '',
        'tag': tag,
      };
    }

    Logger.debug('OmiGlass firmware check: No matching release found');
    return {};
  } catch (e) {
    Logger.debug('OmiGlass firmware check error: $e');
    return {};
  }
}
