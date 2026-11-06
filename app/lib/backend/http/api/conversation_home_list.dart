part of 'conversations.dart';

/// Typed Home list: the storage cursor and acknowledged fallback snapshots travel together.
Future<ApiResult<List<ServerConversation>>> _listHomeConversations(
  ConversationApi api, {
  required int limit,
  required int offset,
  required List<ConversationStatus> statuses,
  required bool includeDiscarded,
  DateTime? startDate,
  DateTime? endDate,
  String? folderId,
  bool? starred,
  required Map<String, List<ServerConversation>> heldHomeEpisodes,
  void Function(int)? onStorageCount,
}) async {
  final held = <String, ServerConversation>{};
  final pairs = <String>[];
  for (final entry in heldHomeEpisodes.entries) {
    for (final member in entry.value) {
      if (pairs.length == 50) break;
      pairs.add('${entry.key}:${member.id}');
      held[member.id] = member;
    }
    if (pairs.length == 50) break;
  }
  var headers = const <String, String>{};
  final sent = await executeApi<String>(
    request: ApiRequest(
      url: conversationCollectionUrl(api._baseUrl,
          limit: limit,
          offset: offset,
          statuses: statuses,
          includeDiscarded: includeDiscarded,
          startDate: startDate,
          endDate: endDate,
          folderId: folderId,
          starred: starred),
      method: 'GET',
      headers: {if (pairs.isNotEmpty) 'X-Omi-Home-Episode-Ids': pairs.join(',')},
    ),
    send: api._send,
    onResponseHeaders: (value) => headers = value,
    decode: (body) => body,
  );
  if (sent case ApiFailure(:final problem)) return ApiFailure(problem);
  final success = sent as ApiSuccess<String>;
  final decoded = await ConversationApi.decodeOffUi(success.data, conversationRowsDecoder);
  if (decoded case ApiFailure(:final problem)) return ApiFailure(problem);
  final rows = decoded as ApiSuccess<List<ServerConversation>>;
  onStorageCount
      ?.call(int.tryParse(headers['x-omi-conversation-page-size'] ?? '') ?? rows.data.length + rows.rejectedRows);
  return ConversationApi._rows(
    retainSuppressedHomeMembers(rows.data, held, (headers['x-omi-home-suppressed-ids'] ?? '').split(',')),
    rows.rejectedRows,
    success.truncated,
  );
}
