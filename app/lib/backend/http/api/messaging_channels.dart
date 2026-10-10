import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/messaging_wire.g.dart' as wire;
import 'package:omi/env/env.dart';

/// Chat-app links (`/v1/messaging/*`): mint a one-time link proof, list, unlink, and the per-link
/// "show in app" switch. Every call returns a typed [ApiResult].
///
/// Minting answers 403 while the channel gateway is off, outside the rollout cohort, or without
/// the Pro entitlement. Listing and unlinking stay available after entitlement loss so a user can
/// always disconnect.
class MessagingChannelsApi {
  const MessagingChannelsApi({this.send});

  /// Injected transport for tests; production uses the shared authenticated path.
  final ApiSend? send;

  static Map<String, dynamic> _object(String body) {
    final row = jsonDecode(body);
    if (row is! Map<String, dynamic>) throw const FormatException('Expected a JSON object');
    return row;
  }

  static String _id(String id) => Uri.encodeComponent(id);

  /// [kind] is `token` (app-to-channel deep link) or `code` (the user texts it to Omi).
  Future<ApiResult<wire.GeneratedChannelLinkProof>> mintProof({
    required String channel,
    required String provider,
    required String kind,
  }) =>
      executeApi(
        request: ApiRequest(
          url: '${Env.apiBaseUrl}v1/messaging/link-proofs',
          method: 'POST',
          body: jsonEncode(
            wire.GeneratedChannelLinkRequest(
              channel: channel,
              kind: kind,
              provider: provider,
            ).toJson(),
          ),
        ),
        send: send,
        decode: (body) => wire.GeneratedChannelLinkProof.fromJson(_object(body)),
      );

  Future<ApiResult<List<wire.GeneratedChannelLink>>> listLinks() => executeApi(
        request: ApiRequest(
          url: '${Env.apiBaseUrl}v1/messaging/links',
          method: 'GET',
        ),
        send: send,
        decode: (body) => wire.GeneratedChannelLinksResponse.fromJson(_object(body)).links,
      );

  Future<ApiResult<void>> unlink(String linkId) => executeApi<void>(
        request: ApiRequest(
          url: '${Env.apiBaseUrl}v1/messaging/links/${_id(linkId)}',
          method: 'DELETE',
        ),
        send: send,
        decode: (_) {},
      );

  Future<ApiResult<void>> setVisibleInApp(String linkId, bool visible) => _patch(
        linkId,
        wire.GeneratedChannelVisibilityRequest(visibleInApp: visible),
      );

  Future<ApiResult<void>> setVoiceNotes(String linkId, bool enabled) => _patch(
        linkId,
        wire.GeneratedChannelVisibilityRequest(voiceNotes: enabled),
      );

  Future<ApiResult<void>> setKeepPrivateMemoriesInApp(
    String linkId,
    bool enabled,
  ) =>
      _patch(
        linkId,
        wire.GeneratedChannelVisibilityRequest(keepPrivateMemoriesInApp: enabled),
      );

  Future<ApiResult<void>> _patch(
    String linkId,
    wire.GeneratedChannelVisibilityRequest request,
  ) {
    final body = request.toJson()..removeWhere((_, value) => value == null);
    return executeApi<void>(
      request: ApiRequest(
        url: '${Env.apiBaseUrl}v1/messaging/links/${_id(linkId)}',
        method: 'PATCH',
        body: jsonEncode(body),
      ),
      send: send,
      decode: (_) {},
    );
  }
}
