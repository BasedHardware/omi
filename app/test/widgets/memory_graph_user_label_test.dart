import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/memories/widgets/memory_graph_page.dart';
import 'package:omi/utils/platform/platform_manager.dart';

Future<Map<String, dynamic>> _graph() async => {
      'nodes': [
        {'id': 'u1', 'label': 'Me', 'node_type': 'user'},
        {'id': 'c1', 'label': 'Coffee', 'node_type': 'concept'},
      ],
      'edges': [],
    };

Future<String> _userNodeLabel(WidgetTester tester, Locale locale) async {
  await tester.pumpWidget(
    MaterialApp(
      locale: locale,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: const MemoryGraphPage(trackOpenEvent: false, loadGraph: _graph),
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 100));
  final dynamic state = tester.state(find.byType(MemoryGraphPage));
  final nodes = (state.simulation.nodes as List).cast<dynamic>();
  final label = nodes.singleWhere((n) => n.id == 'u1').label as String;
  // Unmount before the test ends so the simulation's ticker stops.
  await tester.pumpWidget(const SizedBox.shrink());
  return label;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  // #19246: with no given name the reader's node read "Me" in every language.
  testWidgets('with no given name the reader\'s node says "You" in the app language', (tester) async {
    final german = lookupAppLocalizations(const Locale('de'));
    expect(await _userNodeLabel(tester, const Locale('de')), german.you);
  });

  testWidgets('with a given name the reader\'s node shows it', (tester) async {
    SharedPreferencesUtil().givenName = 'Ada';
    expect(await _userNodeLabel(tester, const Locale('en')), 'Ada');
  });
}
