import 'dart:convert';

import 'package:omi/models/stt_provider.dart';

/// Rotate only headers still bound to the previous provider-generated key.
/// Deliberate header overrides and all other request customizations survive.
String updateSttRequestApiKey({
  required SttProvider provider,
  required String requestJson,
  required String? previousKey,
  required String nextKey,
}) {
  if (previousKey == nextKey) return requestJson;
  try {
    final request = jsonDecode(requestJson);
    if (request is! Map<String, dynamic> || request['headers'] is! Map) return requestJson;
    final defaults = SttProviderConfig.get(provider);
    final before = defaults.buildRequestConfig(apiKey: previousKey)['headers'] as Map? ?? {};
    final after = defaults.buildRequestConfig(apiKey: nextKey)['headers'] as Map? ?? {};
    final headers = Map<String, dynamic>.from(request['headers'] as Map);
    var changed = false;
    for (final entry in before.entries) {
      if (after[entry.key] == entry.value) continue;
      for (final name in headers.keys.toList()) {
        if (name.toLowerCase() == (entry.key as String).toLowerCase() && headers[name] == entry.value) {
          headers[name] = after[entry.key];
          changed = true;
        }
      }
    }
    return changed ? const JsonEncoder.withIndent('  ').convert({...request, 'headers': headers}) : requestJson;
  } on FormatException {
    // Keep malformed JSON visible to the existing validation/recovery flow.
    return requestJson;
  }
}
