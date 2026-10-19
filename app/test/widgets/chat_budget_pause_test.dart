import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/models/plan_storefront.dart';
import 'package:omi/pages/chat/widgets/chat_budget_pause.dart';
import 'storefront_plans_content_test.dart' show pumpSheet, capture;

void main() {
  testWidgets('chat pause renders backend copy and upgrade without a send action', (tester) async {
    for (final plan in ['basic', 'plus', 'operator', 'architect']) {
      final raw = jsonDecode(File('../backend/tests/fixtures/chat_at_cap_$plan.json').readAsStringSync())
          as Map<String, dynamic>;
      final state = ChatAtCap.fromJson(raw);
      var upgraded = false;
      await pumpSheet(tester,
          title: null,
          content: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              const SafeArea(child: Text('Chat', style: TextStyle(fontSize: 24))),
              const Spacer(),
              const Text('What were the highlights of my day?'),
              const SizedBox(height: 24),
              ChatPauseCard(state: state, onUpgrade: () => upgraded = true),
              const SizedBox(height: 24),
            ]),
          ));
      expect(find.text(state.title), findsOneWidget);
      expect(find.text(state.body), findsOneWidget);
      expect(find.text(state.resetLine), findsOneWidget);
      expect(find.byType(TextField), findsNothing);
      await capture(tester, '020-mobile-ios-chat-at-cap-$plan.png');
      if (state.upgradeLabel != null) {
        await tester.tap(find.text(state.upgradeLabel!));
        await tester.pump();
        expect(upgraded, isTrue);
      }
      expect(tester.takeException(), isNull);
    }
  });

  test('reset expiry releases the composer state', () {
    final state = ChatAtCap.fromJson({
      'state': 'paused',
      'trigger': 'usage_budget',
      'title': 'Chat is paused',
      'body': 'body',
      'reset_line': 'reset',
      'reset_at': 1
    });
    expect(state.active, isFalse);
  });
}
