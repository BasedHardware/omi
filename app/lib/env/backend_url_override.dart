import 'package:flutter/foundation.dart';

import 'package:omi/env/env.dart';

final class BackendUrlOverride {
  const BackendUrlOverride._(this.url);

  final String url;

  factory BackendUrlOverride.parse(String input) {
    final value = input.trim();
    final uri = Uri.tryParse(value);
    if (uri == null || uri.host.isEmpty || (uri.scheme != 'http' && uri.scheme != 'https')) {
      throw const FormatException('Enter a valid HTTP or HTTPS backend URL.');
    }
    if (uri.userInfo.isNotEmpty || uri.hasFragment || uri.hasQuery) {
      throw const FormatException('Backend URLs cannot contain credentials, queries, or fragments.');
    }
    if (uri.scheme == 'http' && !_isPrivateHost(uri.host)) {
      throw const FormatException('Public backend URLs must use HTTPS.');
    }

    final normalizedPath = uri.path.endsWith('/') ? uri.path : '${uri.path}/';
    return BackendUrlOverride._(uri.replace(path: normalizedPath).toString());
  }

  static bool restore(String persistedUrl, {bool runtimeAllowed = !kReleaseMode}) {
    if (!runtimeAllowed) {
      Env.clearApiBaseUrlOverride();
      return false;
    }
    final value = persistedUrl.trim();
    if (value.isEmpty) {
      Env.clearApiBaseUrlOverride();
      return true;
    }
    try {
      Env.overrideApiBaseUrl(BackendUrlOverride.parse(value).url);
      return true;
    } on FormatException {
      Env.clearApiBaseUrlOverride();
      return false;
    }
  }

  static bool _isPrivateHost(String host) {
    final normalized = host.toLowerCase();
    if (normalized == 'localhost' || normalized == 'host.docker.internal' || normalized == '::1') return true;

    final octets = normalized.split('.').map(int.tryParse).toList();
    if (octets.length != 4 || octets.any((octet) => octet == null || octet < 0 || octet > 255)) return false;
    final first = octets[0]!;
    final second = octets[1]!;
    return first == 10 ||
        first == 127 ||
        (first == 172 && second >= 16 && second <= 31) ||
        (first == 192 && second == 168) ||
        (first == 100 && second >= 64 && second <= 127);
  }
}
