import 'dart:async';

import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart' show debugPrint;
import 'package:flutter/material.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/apps/apps_provider.dart';
import 'package:nooto_v2/apps/apps_storage.dart';
import 'package:nooto_v2/chat/chat_provider.dart';
import 'package:nooto_v2/chat/chat_storage.dart';
import 'package:nooto_v2/library/conversations_provider.dart';
import 'package:nooto_v2/library/library_provider.dart';
import 'package:nooto_v2/env_flags.dart';
import 'package:nooto_v2/firebase_options.dart';
import 'package:nooto_v2/home/home_storage.dart';
import 'package:nooto_v2/mobile_app.dart';
import 'package:nooto_v2/onboarding/onboarding_chat_provider.dart';
import 'package:nooto_v2/plan/plan_storage.dart';
import 'package:nooto_v2/providers/action_items_provider.dart';
import 'package:nooto_v2/providers/auth_provider.dart';
import 'package:nooto_v2/providers/locale_provider.dart';
import 'package:nooto_v2/services/api_client.dart';
import 'package:nooto_v2/services/app_links_service.dart';
import 'package:nooto_v2/services/chat_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  if (kEnableFirebaseAuth) {
    await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
  }
  await Hive.initFlutter();
  await Future.wait([
    Hive.openBox<Map>(HomeBoxes.cards),
    Hive.openBox<Map>(HomeBoxes.brief),
    Hive.openBox<Map>(HomeBoxes.actions),
    Hive.openBox<Map>(ChatBoxes.messages),
    Hive.openBox<Map>(ChatBoxes.sessions),
    Hive.openBox<Map>(AppsBoxes.prefs),
    Hive.openBox<dynamic>(PlanBoxes.prefs),
  ]);
  final localeProvider = LocaleProvider();
  await localeProvider.hydrate();
  final apiClient = ApiClient();
  final chatService = ChatService(client: apiClient);
  final appLinksService = AppLinksService();
  // App-startup deep-link wiring. AppsProvider drains the cold-start link
  // (captured before apps load) and listens for warm links thereafter. The
  // AppsProvider construction below grabs both via the closure.
  final appsProvider = AppsProvider(client: apiClient);
  // Cold-start: capture any pending nooto:// URI iOS handed us on launch.
  // AppsProvider.load() drains it after first successful apps fetch.
  unawaited(
    appLinksService.loadColdStartLink().then((link) async {
      if (link is AppSetupComplete) {
        // Wait for apps to load before retrying enable, so the lookup in
        // handleSetupComplete finds the app row.
        while (!appsProvider.hasFetched) {
          await Future<void>.delayed(const Duration(milliseconds: 50));
        }
        appsProvider.handleSetupComplete(link.appId, link.status);
      }
    }),
  );
  // Warm path: every subsequent nooto:// URL while the app is running.
  appLinksService.linkStream.listen(
    (link) {
      debugPrint('[main] warm deep-link received: $link');
      if (link is AppSetupComplete) {
        debugPrint('[main] → dispatching handleSetupComplete(${link.appId}, ${link.status})');
        appsProvider.handleSetupComplete(link.appId, link.status);
      }
    },
    onError: (e) {
      debugPrint('[main] linkStream error: $e');
    },
  );
  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AuthChangeProvider()),
        ChangeNotifierProvider(create: (_) => OnboardingChatProvider()),
        ChangeNotifierProvider.value(value: localeProvider),
        ChangeNotifierProvider(create: (_) => ActionItemsProvider(client: apiClient)),
        ChangeNotifierProvider.value(value: appsProvider),
        ChangeNotifierProvider(create: (_) => LibraryProvider(client: apiClient)),
        ChangeNotifierProvider(create: (_) => ConversationsProvider(client: apiClient)),
        Provider<ChatService>.value(value: chatService),
        ChangeNotifierProvider(create: (_) => ChatProvider(service: chatService)),
      ],
      child: const MobileApp(),
    ),
  );
}
