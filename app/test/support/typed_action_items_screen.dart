import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/action_items/action_items_page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _LoadedTaskIntegrationProvider extends TaskIntegrationProvider {
  @override
  bool get hasLoaded => true;
}

/// Builder-owned fixture composition only: supply inert explicit collaborators
/// around the real ActionItemsPage and this exact real provider. Never replace
/// its build method or construct default CaptureProvider.
Future<Widget> buildTypedActionItemsScreen(ActionItemsProvider provider) async {
  SharedPreferences.setMockInitialValues({});
  await SharedPreferencesUtil.init();

  return MaterialApp(
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: const [Locale('en')],
    home: MultiProvider(
      providers: [
        ChangeNotifierProvider<ActionItemsProvider>.value(value: provider),
        ChangeNotifierProvider<GoalsProvider>.value(value: GoalsProvider()),
        ChangeNotifierProvider<TaskIntegrationProvider>.value(value: _LoadedTaskIntegrationProvider()),
      ],
      child: const Scaffold(body: ActionItemsPage()),
    ),
  );
}
