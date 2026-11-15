import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/pages/home/widgets/home_daily_recaps.dart';
import 'package:omi/pages/home/widgets/home_daily_recaps_setting.dart';
import 'package:omi/providers/conversation_provider.dart';

import '../../support/typed_conversation_screen.dart';

final _recap = DailySummary(
  id: 'r1',
  date: '2026-10-20',
  createdAt: DateTime.utc(2026, 10, 21, 4),
  headline: 'Dashboards and paperwork',
  overview: 'A day of dashboards and forms.',
  stats: DayStats(totalConversations: 6, actionItemsCount: 2),
);

void main() {
  late int reads;
  Future<({List<DailySummary> items, bool ok})> load() async {
    reads++;
    return (items: [_recap], ok: true);
  }

  Future<ConversationProvider> pumpHome(WidgetTester tester, {Map<String, Object> prefs = const {}}) async {
    reads = 0;
    final provider = ConversationProvider(
        conversationListFetcher: () async => (items: <ServerConversation>[], ok: true), isSignedIn: () => true);
    final screen = await tester.runAsync(() async {
      SharedPreferences.setMockInitialValues(prefs);
      await SharedPreferencesUtil.init();
      return buildTypedConversationScreen(provider, loadRecaps: load, initializePreferences: false);
    });
    await tester.pumpWidget(screen!);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    return provider;
  }

  Future<void> unmount(WidgetTester tester, ConversationProvider provider) async {
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 1));
    provider.dispose();
    HomeDailyRecapsSetting.enabled = false;
  }

  testWidgets('Home hides Daily Recaps by default and never fetches them', (tester) async {
    final provider = await pumpHome(tester);
    expect(HomeDailyRecapsSetting.enabled, isFalse);
    expect(find.byType(HomeDailyRecaps), findsNothing);
    expect(find.text('Daily Recaps'), findsNothing);
    expect(reads, 0);
    await unmount(tester, provider);
  });

  testWidgets('turning the setting on shows the row on the live Home, and off hides it', (tester) async {
    final provider = await pumpHome(tester);
    expect(find.text('Daily Recaps'), findsNothing);

    HomeDailyRecapsSetting.enabled = true;
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Daily Recaps'), findsOneWidget);
    expect(find.text(_recap.headline), findsOneWidget);
    expect(reads, 1);
    expect(SharedPreferencesUtil().getBool('homeDailyRecapsEnabled'), isTrue);

    HomeDailyRecapsSetting.enabled = false;
    await tester.pump();
    expect(find.byType(HomeDailyRecaps), findsNothing);
    expect(reads, 1);
    await unmount(tester, provider);
  });

  testWidgets('a saved opt-in shows the row on the next launch', (tester) async {
    final provider = await pumpHome(tester, prefs: {'homeDailyRecapsEnabled': true});
    expect(find.text('Daily Recaps'), findsOneWidget);
    expect(reads, 1);
    await unmount(tester, provider);
  });
}
