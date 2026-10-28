// Synthetic Home lifecycle capture. No Firebase session or backend requests.
import 'package:flutter/material.dart';
import 'package:marionette_flutter/marionette_flutter.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/services/capture/optimistic_processing.dart';
import 'package:omi/ui/ui.dart';

import '../test/support/typed_conversation_screen.dart';

Future<void> main() async {
  MarionetteBinding.ensureInitialized();
  ServerConversation? serverRow;
  var reachable = false;
  final provider = ConversationProvider(
    isSignedIn: () => true,
    conversationListFetcher: () async => (items: [if (serverRow != null) serverRow!], ok: true),
    conversationLifecycleFetcher: (_) async => (item: serverRow, ok: reachable),
  )..isLoadingConversations = false;
  final home = await buildTypedConversationScreen(provider, theme: buildOmiTheme(brightness: Brightness.light));
  void pending() {
    reachable = false;
    serverRow = null;
    provider.addProcessingConversation(OptimisticProcessingPlaceholder.conversation(targetConversationId: 'fixture'));
  }

  pending();
  runApp(MaterialApp(
    home: Scaffold(
      body: home,
      bottomNavigationBar: SafeArea(
        child: Row(mainAxisAlignment: MainAxisAlignment.spaceEvenly, children: [
          TextButton(key: const Key('fixture_pending'), onPressed: pending, child: const Text('Pending fixture')),
          TextButton(
            key: const Key('fixture_complete'),
            onPressed: () async {
              reachable = true;
              serverRow = ServerConversation(
                id: 'fixture',
                createdAt: DateTime.now(),
                structured: Structured('Finished recording', ''),
                status: ConversationStatus.completed,
              );
              await provider.forceRefreshConversations();
            },
            child: const Text('Complete fixture'),
          ),
        ]),
      ),
    ),
  ));
}
