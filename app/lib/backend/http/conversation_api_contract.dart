import 'package:flutter/widgets.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'api_presentation.dart';
import 'api_result.dart';

/// First migrated API file is api/conversations.dart. These signatures are its
/// future typed surface; retain legacy entrypoints only for unmigrated callers.
class ConversationApi {
  ConversationApi({required String baseUrl, ApiSend? send});
  Future<ApiResult<List<ServerConversation>>> list() => throw UnimplementedError('C3 conversation list');
  Future<ApiResult<ServerConversation>> byId(String id) => throw UnimplementedError('C3 conversation detail');
}

/// Must return the real provider; forceRefreshConversations consumes this API.
ConversationProvider composeTypedConversationProvider(ConversationApi api) =>
    throw UnimplementedError('C3 first provider consumer');

extension ConversationApiProjection on ConversationProvider {
  Future<void> refreshTypedDetail(String id) => throw UnimplementedError('C3 terminal detail lifecycle');
  ApiViewState<ServerConversation> typedDetailState(String id) => throw UnimplementedError('C3 detail projection');
  ApiViewState<List<ServerConversation>> get apiViewState => throw UnimplementedError('C3 provider projection');
}

/// Extracted status region used by ConversationsPage, not a second list screen.
/// Builder installs it before the empty hero in conversations_page.dart.
class ConversationApiStatus extends StatelessWidget {
  const ConversationApiStatus({super.key, required this.provider});
  final ConversationProvider provider;
  @override
  Widget build(BuildContext context) => throw UnimplementedError('C3 accessible error/locked/terminal status');
}
