import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';

// The seams [ConversationProvider] fetches through (tests inject fakes). Exported by
// conversation_provider.dart, so importing the provider brings them in.

typedef ConversationListFetcher = Future<({List<ServerConversation> items, bool ok})> Function();
typedef ConversationPageFetcher = Future<({List<ServerConversation> items, bool ok, bool truncated})> Function();
typedef ConversationLifecycleFetcher = Future<({ServerConversation? item, bool ok})> Function(String id);

/// Returns null when the check could not be made, so the caller keeps the
/// last known answer instead of reading a failure as "no recaps".
typedef DailySummariesChecker = Future<bool?> Function();
typedef ConversationSearchFetcher = Future<(List<ServerConversation>, int, int)> Function(
  String query, {
  int? page,
  int? limit,
  required bool includeDiscarded,
  DateTime? startDate,
  DateTime? endDate,
  String? speakerId,
});
typedef ConversationSearchResultFetcher = Future<ConversationSearchResult> Function(
  String query, {
  int? page,
  int? limit,
  required bool includeDiscarded,
  DateTime? startDate,
  DateTime? endDate,
  String? speakerId,
});
typedef ConversationDetailsFetcher = Future<ServerConversation?> Function(String conversationId);
