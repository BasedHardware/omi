import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';

class ChannelBinding {
  final String channel;
  final DateTime linkedAt;

  const ChannelBinding({required this.channel, required this.linkedAt});

  factory ChannelBinding.fromJson(Map<String, dynamic> json) {
    return ChannelBinding(
      channel: json['channel'] as String,
      linkedAt: DateTime.parse(json['linked_at'] as String),
    );
  }
}

class ChannelStatus {
  final List<ChannelBinding> bindings;
  final bool phoneRegistered;

  const ChannelStatus({required this.bindings, required this.phoneRegistered});

  factory ChannelStatus.fromJson(Map<String, dynamic> json) {
    return ChannelStatus(
      bindings: (json['bindings'] as List<dynamic>? ?? const [])
          .whereType<Map<String, dynamic>>()
          .map(ChannelBinding.fromJson)
          .toList(),
      phoneRegistered: json['phone_registered'] == true,
    );
  }
}

class ChannelLinkResponse {
  final String channel;
  final String code;
  final DateTime expiresAt;
  final String instructions;

  const ChannelLinkResponse({
    required this.channel,
    required this.code,
    required this.expiresAt,
    required this.instructions,
  });

  factory ChannelLinkResponse.fromJson(Map<String, dynamic> json) {
    return ChannelLinkResponse(
      channel: json['channel'] as String,
      code: json['code'] as String,
      expiresAt: DateTime.parse(json['expires_at'] as String),
      instructions: json['instructions'] as String,
    );
  }
}

Future<ChannelStatus?> getChannelStatus() async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/channels',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response?.statusCode != 200) return null;
  return ChannelStatus.fromJson(
    jsonDecode(utf8.decode(response!.bodyBytes)) as Map<String, dynamic>,
  );
}

Future<ChannelLinkResponse?> createChannelLink(String channel) async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/channels/$channel/link',
    headers: {'Content-Type': 'application/json'},
    method: 'POST',
    body: '',
  );
  if (response?.statusCode != 200) return null;
  return ChannelLinkResponse.fromJson(
    jsonDecode(utf8.decode(response!.bodyBytes)) as Map<String, dynamic>,
  );
}
