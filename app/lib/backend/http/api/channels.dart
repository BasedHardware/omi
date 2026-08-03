import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/gen/channels_wire.g.dart' as wire;
import 'package:omi/env/env.dart';

typedef ChannelBinding = wire.GeneratedChannelBindingResponse;
typedef ChannelStatus = wire.GeneratedChannelStatusResponse;
typedef ChannelLinkResponse = wire.GeneratedLinkChannelResponse;

Future<ChannelStatus?> getChannelStatus() async {
  final response = await makeApiCall(url: '${Env.apiBaseUrl}v1/channels', headers: {}, method: 'GET', body: '');
  if (response?.statusCode != 200) return null;
  return wire.GeneratedChannelStatusResponse.fromJson(
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
  return wire.GeneratedLinkChannelResponse.fromJson(
    jsonDecode(utf8.decode(response!.bodyBytes)) as Map<String, dynamic>,
  );
}
