import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:omi/env/env.dart';
import 'package:omi/pages/settings/chat_apps/channel_link_waiter.dart';
import 'package:omi/providers/messaging_channels_provider.dart';

import 'chat_apps_fixture.dart';

class _Waiter extends StatefulWidget {
  const _Waiter({super.key});
  @override
  State<_Waiter> createState() => _WaiterState();
}

class _WaiterState extends State<_Waiter> with WidgetsBindingObserver, ChannelLinkWaiter<_Waiter> {
  @override
  ChatChannel get waitChannel => ChatChannel.telegram;
  @override
  void onLinked(ChannelLink link) {}
  @override
  Widget build(BuildContext context) => const SizedBox();
}

void main() {
  setUpAll(() => Env.init(ChatAppsTestEnv()));
  setUp(initChatAppsTest);

  testWidgets('polls only pending proofs, backs off, pauses in background and stops', (tester) async {
    ChannelLinkWaiter.interval = const Duration(milliseconds: 100);
    final backend = FakeMessagingBackend();
    final key = GlobalKey<_WaiterState>();
    await tester.pumpWidget(ChangeNotifierProvider.value(
      value: backend.provider(),
      child: _Waiter(key: key),
    ));
    await tester.pump(const Duration(seconds: 1));
    expect(backend.count('GET', 'v1/messaging/links'), 0);
    key.currentState!.startWaiting(until: DateTime.now().add(const Duration(minutes: 10)));
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump();
    expect(backend.count('GET', 'v1/messaging/links'), 1);
    await tester.pump(const Duration(milliseconds: 100));
    expect(backend.count('GET', 'v1/messaging/links'), 1);
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump();
    expect(backend.count('GET', 'v1/messaging/links'), 2);
    key.currentState!.didChangeAppLifecycleState(AppLifecycleState.paused);
    await tester.pump(const Duration(seconds: 1));
    expect(backend.count('GET', 'v1/messaging/links'), 2);
    key.currentState!.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await tester.pump();
    expect(backend.count('GET', 'v1/messaging/links'), 3);
    key.currentState!.stopWaiting();
    await tester.pump(const Duration(seconds: 5));
    expect(backend.count('GET', 'v1/messaging/links'), 3);
    await tester.pumpWidget(const SizedBox());
  });
}
