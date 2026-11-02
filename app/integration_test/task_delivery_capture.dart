// Offline native acceptance target: real production composition and task UI, synthetic transport only.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:marionette_flutter/marionette_flutter.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/http/action_items_api_contract.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/action_items/action_items_page.dart';
import 'package:omi/pages/conversation_detail/widgets/summary_task_recovery.dart';
import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'support/task_delivery_fixture.dart';

class _LoadedIntegrations extends TaskIntegrationProvider {
  @override
  bool get hasLoaded => true;
  @override
  Future<void> loadFromBackend({bool silent = false, bool forceRefresh = false}) async {}
}

Future<void> main() async {
  MarionetteBinding.ensureInitialized();
  SharedPreferences.setMockInitialValues({});
  await SharedPreferencesUtil.init();
  Env.overrideApiBaseUrl('http://127.0.0.1:18965/');
  final fixture = TaskDeliveryFixture()..expectedSummaryIndex = 3;
  final summary = ServerConversation(
    id: 'synthetic-conversation',
    createdAt: DateTime.utc(2026, 10, 10),
    source: ConversationSource.desktop,
    status: ConversationStatus.completed,
    transcriptSegments: [],
    structured: Structured.fromJson({
      'title': 'Project notes',
      'overview': '',
      'action_items': [
        '',
        null,
        {'description': 'Invalid date', 'completed': false, 'due_at': 'bad-date'},
        {'description': TaskDeliveryFixture.description, 'completed': false},
      ],
    }),
  );
  final cachedSummary = ServerConversation.fromJson(jsonDecode(jsonEncode(summary.toJson())));
  final provider = createProductionActionItemsProvider(send: fixture.send);
  await provider.ensureLoaded();
  OmiColors.active = OmiColors.forBrightness(Brightness.dark);
  runApp(MultiProvider(
    providers: [
      ChangeNotifierProvider<ActionItemsProvider>.value(value: provider),
      ChangeNotifierProvider(create: (_) => GoalsProvider()),
      ChangeNotifierProvider<TaskIntegrationProvider>(create: (_) => _LoadedIntegrations()),
    ],
    child: MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: buildOmiTheme(brightness: Brightness.dark),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Builder(
          builder: (context) => Scaffold(
                appBar: AppBar(title: Text(context.l10n.tasks), actions: [
                  IconButton(
                    key: const ValueKey('capture_integrations'),
                    tooltip: context.l10n.taskIntegrations,
                    icon: const Icon(Icons.ios_share_rounded),
                    onPressed: () => Navigator.of(context)
                        .push(MaterialPageRoute<void>(builder: (_) => const TaskIntegrationsPage())),
                  ),
                  IconButton(
                    key: const ValueKey('capture_summary'),
                    tooltip: context.l10n.actionItems,
                    icon: const Icon(Icons.description_outlined),
                    onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
                        builder: (_) => Scaffold(
                              appBar: AppBar(title: Text(context.l10n.actionItems)),
                              body: Padding(
                                  padding: const EdgeInsets.all(OmiSpacing.md),
                                  child: SummaryTaskRecovery(
                                    conversation: cachedSummary,
                                  )),
                            ))),
                  ),
                ]),
                body: const ActionItemsPage(),
              )),
    ),
  ));
}
