import 'package:flutter/widgets.dart';

import 'app_shell.dart';
import 'chat_page.dart';
import 'conversation_page.dart';
import 'mock_data.dart';
import 'search_page.dart';
import 'settings_pages.dart';
import 'upgrade_page.dart';
import 'app_state.dart';

/// Every app screen, for the launcher's jump list and the screenshots.
/// Each builder runs inside [OmiApp], so it can read [OmiAppScope].
final List<(String, WidgetBuilder)> appScreens = <(String, WidgetBuilder)>[
  ('A1 Home', (_) => const AppHome()),
  ('A2 Tasks', (_) => const AppHome(initialTab: 1)),
  ('A3 Conversation · Summary', (c) => ConversationPage(conversation: _data(c).conversation('launch'))),
  (
    'A4 Conversation · Transcript',
    (c) => ConversationPage(conversation: _data(c).conversation('launch'), initialTab: 1),
  ),
  ('A5 Daily recap', (c) => RecapPage(recap: _data(c).recaps.first)),
  ('A6 Ask Omi', (_) => const ChatPage()),
  ('A7 Ask Omi · answer', (_) => ChatPage(initialQuestion: MockData.chatSuggestions[1])),
  ('A8 Search', (_) => const SearchPage()),
  ('A9 Settings', (_) => const SettingsPage()),
  ('A10 Plan & Usage', (_) => const PlanUsagePage()),
  ('A11 Upgrade · cap hit', (c) => UpgradePage(state: OmiAppScope.of(c), capHit: true)),
  ('A12 Device', (_) => const DevicePage()),
  ('A13 Memories', (_) => const MemoriesPage()),
  ('A14 Integrations', (_) => const AppsPage()),
  ('A15 App detail', (_) => AppDetailPage(app: MockData.apps[0])),
  ('A16 Recording', (_) => const RecordingPage()),
];

MockData _data(BuildContext context) => OmiAppScope.of(context).data;
