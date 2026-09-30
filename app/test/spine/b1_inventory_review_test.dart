import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/dev_controls/addressability_catalog.dart';

import '../support/spine/contract.dart';
import 'b1_surface_contract.dart' show catalogControl;

void main() {
  contractTest('B1 inventory includes the fourth tab and distinct local-dev auth control', () {
    pendingContract('B1');
    final routes = (jsonDecode(addressableRoutesJson) as List).cast<Map<String, dynamic>>();
    final controls = jsonDecode(addressableControlsJson) as Map<String, dynamic>;
    expect({for (final route in routes.where((r) => r['reach']['kind'] == 'tab')) route['reach']['tab']: route['id']},
        {0: 'home', 1: 'conversations', 2: 'tasks', 3: 'apps'});
    expect((controls['home'] as List).map((c) => c['key']), contains('omi.home.tab_apps'));
    expect((controls['onboarding'] as List).map((c) => c['key']),
        containsAll(['omi.onboarding.google', 'omi.onboarding.local_dev']));
    final apps = routes.singleWhere((route) => route['id'] == 'apps');
    expect(apps['widget'], 'AppsPage');
    expect(apps['root'], 'omi.apps.root');
  });

  contractTest('B1 labels reference ARB or record titles, never a duplicate English copy', () {
    pendingContract('B1');
    final controls = jsonDecode(addressableControlsJson) as Map<String, dynamic>;
    final arb = jsonDecode(File('lib/l10n/app_en.arb').readAsStringSync()) as Map<String, dynamic>;
    const labels = {
      'omi.chat.input': 'askAnything',
      'omi.chat.send': 'send',
      'omi.home.tab_home': 'home',
      'omi.home.tab_conversations': 'conversations',
      'omi.home.tab_tasks': 'tasks',
      'omi.home.tab_apps': 'apps',
      'omi.conversation_detail.back': 'back',
      'omi.conversation_detail.ask': 'askAboutThisConversation',
      'omi.memories.create': 'createMemoryTooltip',
      'omi.tasks.create': 'createActionItem',
      'omi.settings.profile': 'profile',
      'omi.settings.done': 'done',
      'omi.onboarding.google': 'signInWithGoogle',
      'omi.onboarding.local_dev': 'localDevSignIn',
      'omi.devices.back': 'back',
      'omi.devices.guide': 'connectionGuide',
    };
    for (final entries in controls.values) {
      for (final item in entries as List) {
        expect(item.containsKey('label_en'), isFalse);
        if (item['row_id'] == null) {
          if (labels.containsKey(item['key'])) expect(item['label_arb'], labels[item['key']]);
          expect(item['label_arb'], isA<String>());
          expect(arb[item['label_arb']], isA<String>());
          expect(arb[item['label_arb']], isNotEmpty);
          expect(arb[item['label_arb']], isNot(contains('{')), reason: 'initial static controls need plain ARB labels');
        } else {
          expect(item['label_arb'], isNull, reason: 'row title comes from the record');
        }
      }
    }
  });

  testWidgets('B1 root scoping tolerates cached copies but preserves ambiguity within a visible root', (tester) async {
    const key = ValueKey<String>('omi.conversations.row.rsynthetic');
    Widget root(String id, {int count = 1}) => Column(
          key: ValueKey(id),
          children: List.generate(
              count, (_) => const SizedBox(child: TextButton(key: key, onPressed: null, child: Text('Row')))),
        );
    await tester.pumpWidget(MaterialApp(home: Column(children: [root('one'), root('two')])));
    expect(find.byKey(key), findsNWidgets(2));
    expect(catalogControl(find.byKey(const ValueKey('one')), key, scope: 'root'), findsOneWidget);
    expect(catalogControl(find.byKey(const ValueKey('one')), key, scope: 'shell'), findsNWidgets(2));
    await tester.pumpWidget(MaterialApp(home: IndexedStack(index: 0, children: [root('one'), root('two')])));
    expect(find.byKey(key, skipOffstage: false), findsNWidgets(2));
    expect(catalogControl(find.byKey(const ValueKey('two')), key, scope: 'root'), findsNothing);
    await tester.pumpWidget(MaterialApp(home: root('one', count: 2)));
    expect(catalogControl(find.byKey(const ValueKey('one')), key, scope: 'root'), findsNWidgets(2));
  });
}
