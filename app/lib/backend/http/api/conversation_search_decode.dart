part of 'conversations.dart';

/// Keep generated search normalization while carrying the list-only Home projection
/// that older generated DTOs do not declare. Unknown/absent projections stay optional.
ConversationSearchResult decodeConversationSearchResponse(Map<String, dynamic> json,
    {wire.GeneratedSearchConversationsResponse? generated, int statusCode = 200}) {
  final data = generated ?? wire.GeneratedSearchConversationsResponse.fromJson(json);
  final rawItems = json['items'] as List;
  return ConversationSearchResult(
    items: [
      for (var i = 0; i < data.items.length; i++)
        ServerConversation.fromJson({
          ...data.items[i].toJson(),
          if ((rawItems[i] as Map).containsKey('home_step')) 'home_step': rawItems[i]['home_step'],
        }),
    ],
    currentPage: data.currentPage,
    totalPages: data.totalPages,
    outcome: ConversationSearchResultOutcome.success,
    statusCode: statusCode,
  );
}
