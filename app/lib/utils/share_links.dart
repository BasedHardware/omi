import 'dart:math';

import 'package:flutter/foundation.dart';

// Public share-link base URL for self-hosting (#4339).
//
// Matches backend `OMI_SHARE_BASE_URL` / desktop share helpers.
// Override at build time with `--dart-define=OMI_SHARE_BASE_URL=https://share.example.com`.

const defaultShareBaseUrl = 'https://h.omi.me';

const _shareBaseFromDefine = String.fromEnvironment('OMI_SHARE_BASE_URL');

final _hostOk = RegExp(r'^[A-Za-z0-9.-]+$');

/// Return the configured share origin (no trailing slash).
///
/// [raw] is for tests; production callers omit it so the dart-define / default apply.
String shareBaseUrl([String? raw]) {
  var value = (raw ?? _shareBaseFromDefine).trim();
  if (value.isEmpty) {
    value = defaultShareBaseUrl;
  }
  if (!value.contains('://')) {
    value = 'https://$value';
  }
  final uri = Uri.tryParse(value);
  if (uri == null ||
      uri.host.isEmpty ||
      uri.userInfo.isNotEmpty ||
      uri.hasQuery ||
      uri.hasFragment ||
      (uri.scheme != 'http' && uri.scheme != 'https') ||
      !_hostOk.hasMatch(uri.host)) {
    return defaultShareBaseUrl;
  }
  final origin = uri.hasPort ? '${uri.scheme}://${uri.host}:${uri.port}' : '${uri.scheme}://${uri.host}';
  final path = uri.path.replaceFirst(RegExp(r'/+$'), '');
  if (path.isEmpty || path == '/') {
    return origin;
  }
  return '$origin$path';
}

/// Join [shareBaseUrl] with a path (leading slash optional).
String buildShareUrl(String path, {String? raw, String? source, String? sid}) {
  final normalized = path.startsWith('/') ? path : '/$path';
  return Uri.parse(
    '${shareBaseUrl(raw)}$normalized',
  ).replace(queryParameters: {'s': source ?? mobileShareSource(), 'sid': sid ?? newShareId()}).toString();
}

String mobileShareSource() => switch (defaultTargetPlatform) {
      TargetPlatform.iOS => 'ios',
      TargetPlatform.android => 'android',
      _ => 'unknown',
    };

/// Random per-share attempt; never derived from the sender or content.
String newShareId() {
  final random = Random.secure();
  return List.generate(16, (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0')).join();
}

String conversationShareUrl(String conversationId, {String? raw, String? source, String? sid}) =>
    buildShareUrl('/conversations/$conversationId', raw: raw, source: source, sid: sid);

String appShareUrl(String appId, {String? raw, String? source, String? sid}) =>
    buildShareUrl('/apps/$appId', raw: raw, source: source, sid: sid);

String recapShareUrl(String summaryId, {String? raw, String? source, String? sid}) =>
    buildShareUrl('/recaps/$summaryId', raw: raw, source: source, sid: sid);

/// Share Plus reports a platform activity/package when available. Keep the event bounded.
String? shareTargetApp(String raw) {
  final value = raw.toLowerCase();
  if (value.isEmpty || value.contains('/share/unavailable')) return null;
  if (value.contains('whatsapp')) return 'whatsapp';
  if (value.contains('telegram')) return 'telegram';
  if (value.contains('slack')) return 'slack';
  if (value.contains('discord')) return 'discord';
  if (value.contains('signal')) return 'signal';
  if (value.contains('message') || value.contains('sms')) return 'messages';
  if (value.contains('mail') || value.contains('gmail')) return 'email';
  if (value.contains('airdrop')) return 'airdrop';
  if (value.contains('copy')) return 'copy';
  if (value.contains('facebook') || value.contains('messenger')) return 'meta';
  if (value.contains('twitter') || value.contains('tweet')) return 'x';
  if (value.contains('linkedin')) return 'linkedin';
  return 'other';
}
