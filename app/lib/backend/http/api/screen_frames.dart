import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/screen_frames_wire.g.dart' as wire;
import 'package:omi/env/env.dart';

/// One approved meeting screenshot, as the conversation note shows it.
///
/// Both URLs are signed and die at [urlExpiresAt] (60 minutes after the fetch that minted them).
/// A holder that outlives that must re-fetch the set rather than retry a URL.
class ConversationScreenshot {
  const ConversationScreenshot({
    required this.id,
    required this.capturedAt,
    required this.isBanner,
    required this.caption,
    required this.width,
    required this.height,
    required this.contentUrl,
    required this.thumbnailUrl,
    required this.urlExpiresAt,
    this.sourceBadge,
  });

  final String id;
  final DateTime capturedAt;
  final bool isBanner;
  final String caption;
  final int width;
  final int height;
  final String contentUrl;
  final String thumbnailUrl;
  final DateTime urlExpiresAt;

  /// `code`, `browser`, `document`, `slides` or `product`; null when the judge named none.
  final String? sourceBadge;

  factory ConversationScreenshot.fromGenerated(wire.GeneratedConversationScreenFrame frame) {
    return ConversationScreenshot(
      id: frame.id,
      capturedAt: frame.capturedAt,
      isBanner: frame.role == 'banner',
      caption: frame.caption,
      width: frame.width,
      height: frame.height,
      contentUrl: frame.contentUrl,
      thumbnailUrl: frame.thumbnailUrl,
      urlExpiresAt: frame.urlExpiresAt,
      sourceBadge: frame.sourceBadge,
    );
  }
}

/// A conversation's persisted screenshot set, flattened for a strip: the banner first, then the
/// strip in the server's rank order. Mobile has no header banner, so the banner frame is simply
/// the first tile — the same picture the Mac shows in its note header.
class ConversationScreenshots {
  const ConversationScreenshots({required this.revision, required this.frames});

  static const empty = ConversationScreenshots(revision: 0, frames: []);

  final int revision;
  final List<ConversationScreenshot> frames;

  bool get isEmpty => frames.isEmpty;

  /// The earliest URL expiry in the set; null when the set is empty. Every URL in one response is
  /// minted together, but taking the minimum costs nothing and never trusts that.
  DateTime? get urlsExpireAt {
    DateTime? earliest;
    for (final frame in frames) {
      if (earliest == null || frame.urlExpiresAt.isBefore(earliest)) earliest = frame.urlExpiresAt;
    }
    return earliest;
  }

  factory ConversationScreenshots.fromGenerated(wire.GeneratedConversationScreenFrameSet set) {
    final banner = set.banner;
    return ConversationScreenshots(
      revision: set.revision,
      frames: [
        if (banner != null) ConversationScreenshot.fromGenerated(banner),
        for (final frame in set.strip ?? const <wire.GeneratedConversationScreenFrame>[])
          if (frame.id != banner?.id) ConversationScreenshot.fromGenerated(frame),
      ],
    );
  }
}

ConversationScreenshots _decodeSet(String body) {
  final decoded = jsonDecode(body);
  if (decoded is! Map<String, dynamic>) throw const FormatException('Expected a JSON object');
  return ConversationScreenshots.fromGenerated(wire.GeneratedConversationScreenFrameSet.fromJson(decoded));
}

String _screenshotsUrl(String conversationId) =>
    '${Env.apiBaseUrl}v1/conversations/${Uri.encodeComponent(conversationId)}/screenshots';

/// `GET /v1/conversations/{id}/screenshots`: the owner's persisted meeting screenshots. The server
/// returns an empty set when the account's `meeting_note_screenshots_enabled` setting is off, so
/// the client never needs its own copy of that gate.
Future<ApiResult<ConversationScreenshots>> getConversationScreenshots(String conversationId, {ApiSend? send}) =>
    executeApi(
      request: ApiRequest(url: _screenshotsUrl(conversationId), method: 'GET'),
      send: send,
      decode: _decodeSet,
    );

/// `DELETE /v1/conversations/{id}/screenshots/{frame_id}`: removes one frame and returns the set
/// as it now stands (the server may promote another frame to banner).
Future<ApiResult<ConversationScreenshots>> deleteConversationScreenshot(
  String conversationId,
  String frameId, {
  ApiSend? send,
}) =>
    executeApi(
      request: ApiRequest(
        url: '${_screenshotsUrl(conversationId)}/${Uri.encodeComponent(frameId)}',
        method: 'DELETE',
      ),
      send: send,
      decode: _decodeSet,
    );
