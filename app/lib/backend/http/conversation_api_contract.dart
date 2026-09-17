import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';

import 'api_presentation.dart';
import 'api_result.dart';

export 'package:omi/backend/http/api/conversations.dart' show ConversationApi;

/// Must return the real provider; forceRefreshConversations consumes this API.
ConversationProvider composeTypedConversationProvider(ConversationApi api) =>
    ConversationProvider(conversationApi: api, isSignedIn: () => true, dailySummariesChecker: () async => false);

/// Extracted status region used by ConversationsPage, not a second list screen.
/// Builder installs it before the empty hero in conversations_page.dart.
class ConversationApiStatus extends StatelessWidget {
  const ConversationApiStatus({super.key, required this.provider});
  final ConversationProvider provider;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: provider,
      builder: (context, _) {
        final view = provider.apiViewState;
        final keyName = switch (view.phase) {
          ApiViewPhase.error => 'omi.conversations.error',
          ApiViewPhase.locked => 'omi.conversations.locked',
          ApiViewPhase.terminal => 'omi.conversations.terminal',
          ApiViewPhase.authenticationRequired => 'omi.conversations.auth',
          ApiViewPhase.empty => 'omi.conversations.empty',
          ApiViewPhase.data => null,
        };
        if (keyName == null) return const SizedBox.shrink();
        final copy = switch (view.phase) {
          ApiViewPhase.empty => context.l10n.noConversationsYet,
          _ => context.l10n.somethingWentWrong,
        };
        return Semantics(
          container: true,
          liveRegion: view.phase == ApiViewPhase.error,
          label: copy,
          child: Padding(
            key: ValueKey(keyName),
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  copy,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Colors.white),
                ),
                if (view.problem?.retryable == true)
                  TextButton(onPressed: () => provider.forceRefreshConversations(), child: Text(context.l10n.retry)),
              ],
            ),
          ),
        );
      },
    );
  }
}
