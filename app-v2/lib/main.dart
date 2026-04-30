import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/env_flags.dart';
import 'package:nooto_v2/firebase_options.dart';
import 'package:nooto_v2/home/home_storage.dart';
import 'package:nooto_v2/mobile_app.dart';
import 'package:nooto_v2/onboarding/onboarding_chat_provider.dart';
import 'package:nooto_v2/providers/action_items_provider.dart';
import 'package:nooto_v2/providers/auth_provider.dart';
import 'package:nooto_v2/providers/locale_provider.dart';
import 'package:nooto_v2/services/api_client.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  if (kEnableFirebaseAuth) {
    await Firebase.initializeApp(
      options: DefaultFirebaseOptions.currentPlatform,
    );
  }
  await Hive.initFlutter();
  await Future.wait([
    Hive.openBox<Map>(HomeBoxes.cards),
    Hive.openBox<Map>(HomeBoxes.brief),
    Hive.openBox<Map>(HomeBoxes.actions),
  ]);
  final localeProvider = LocaleProvider();
  await localeProvider.hydrate();
  final apiClient = ApiClient();
  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AuthChangeProvider()),
        ChangeNotifierProvider(create: (_) => OnboardingChatProvider()),
        ChangeNotifierProvider.value(value: localeProvider),
        ChangeNotifierProvider(
          create: (_) => ActionItemsProvider(client: apiClient),
        ),
      ],
      child: const MobileApp(),
    ),
  );
}
