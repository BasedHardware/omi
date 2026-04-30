import 'package:flutter/material.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/env_flags.dart';
import 'package:nooto_v2/home/home_storage.dart';
import 'package:nooto_v2/mobile_app.dart';
import 'package:nooto_v2/onboarding/onboarding_chat_provider.dart';
import 'package:nooto_v2/providers/auth_provider.dart';
import 'package:nooto_v2/providers/locale_provider.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  if (kEnableFirebaseAuth) {
    // Firebase init lands together with Task #12 once v2 bundle IDs are
    // registered. Until then we boot with the dev fake-auth bypass.
  }
  await Hive.initFlutter();
  await Future.wait([
    Hive.openBox<Map>(HomeBoxes.cards),
    Hive.openBox<Map>(HomeBoxes.brief),
    Hive.openBox<Map>(HomeBoxes.actions),
  ]);
  final localeProvider = LocaleProvider();
  await localeProvider.hydrate();
  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AuthChangeProvider()),
        ChangeNotifierProvider(create: (_) => OnboardingChatProvider()),
        ChangeNotifierProvider.value(value: localeProvider),
      ],
      child: const MobileApp(),
    ),
  );
}
