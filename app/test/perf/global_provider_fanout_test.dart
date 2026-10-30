import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/coordinators/provider_capture_external_actions.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/services.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _Offline extends ConnectivityPlatform {
  @override
  Future<List<ConnectivityResult>> checkConnectivity() async => [ConnectivityResult.none];
  @override
  Stream<List<ConnectivityResult>> get onConnectivityChanged => const Stream.empty();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    ConnectivityPlatform.instance = _Offline();
    await ServiceManager.init();
  });

  for (final semantics in [false, true]) {
    testWidgets('root capture/device proxies do not amplify notifications semantics=$semantics', (tester) async {
      final handle = semantics ? tester.ensureSemantics() : null;
      try {
        final conversations = ConversationProvider(isSignedIn: () => false);
        final messages = MessageProvider();
        final people = PeopleProvider(loadPeople: () async => null);
        final usage = UsageProvider();
        final episodes = EpisodeProvider();
        final recordings = LocalRecordingsProvider(initialize: false);
        for (final provider in [conversations, messages, people, usage, episodes, recordings]) {
          addTearDown(provider.dispose);
        }
        final capture = CaptureProvider();
        final device = DeviceProvider();
        var captureNotifies = 0;
        var deviceNotifies = 0;
        var peopleNotifies = 0;
        var tabBuilds = 0;
        capture.addListener(() => captureNotifies++);
        device.addListener(() => deviceNotifies++);
        people.addListener(() => peopleNotifies++);
        await tester.pumpWidget(MultiProvider(
          providers: [
            ChangeNotifierProvider.value(value: conversations),
            ChangeNotifierProvider.value(value: messages),
            ChangeNotifierProvider.value(value: people),
            ChangeNotifierProvider.value(value: usage),
            ChangeNotifierProvider.value(value: episodes),
            ChangeNotifierProvider.value(value: recordings),
            ChangeNotifierProxyProvider5<ConversationProvider, MessageProvider, PeopleProvider, UsageProvider,
                EpisodeProvider, CaptureProvider>(
              create: (_) => capture,
              update: (_, conversations, messages, people, usage, episodes, previous) => previous!
                ..updateExternalActions(ProviderCaptureExternalActions(
                  conversationProvider: conversations,
                  messageProvider: messages,
                  peopleProvider: people,
                  usageProvider: usage,
                  episodeProvider: episodes,
                )),
            ),
            ChangeNotifierProxyProvider2<CaptureProvider, LocalRecordingsProvider, DeviceProvider>(
              create: (_) => device,
              update: (_, capture, recordings, previous) => previous!..setProviders(capture, recordings),
            ),
          ],
          child: MaterialApp(
              home: IndexedStack(children: [
            // Deliberately broad tab consumers expose every propagated notify.
            // These model fan-out; real page rebuild scope has its own tests.
            for (final tab in ['Home', 'Tasks', 'Chat'])
              Consumer3<CaptureProvider, DeviceProvider, PeopleProvider>(builder: (_, capture, device, people, child) {
                tabBuilds++;
                return Text(tab);
              }),
          ])),
        ));
        await tester.pump();
        for (final source in [people, capture, device]) {
          captureNotifies = deviceNotifies = peopleNotifies = tabBuilds = 0;
          for (var event = 0; event < 20; event++) {
            source.notifyListeners();
            await tester.pump();
          }
          debugPrint('GLOBAL proxyGraph semantics=$semantics source=${source.runtimeType} events=20 '
              'captureNotifies=$captureNotifies deviceNotifies=$deviceNotifies '
              'peopleNotifies=$peopleNotifies tabConsumerBuilds=$tabBuilds');
          expect(captureNotifies, identical(source, capture) ? 20 : 0);
          expect(deviceNotifies, identical(source, device) ? 20 : 0);
          expect(peopleNotifies, identical(source, people) ? 20 : 0);
          expect(tabBuilds, 60);
        }
        await tester.pumpWidget(const SizedBox.shrink());
      } finally {
        handle?.dispose();
      }
    });
  }
}
