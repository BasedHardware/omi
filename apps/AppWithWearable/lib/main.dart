import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart' as ble;
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:friend_private/backend/database/box.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/flavors.dart';
import 'package:friend_private/pages/home/page.dart';
import 'package:friend_private/pages/onboarding/welcome/page.dart';
import 'package:friend_private/utils/notifications.dart';
import 'package:instabug_flutter/instabug_flutter.dart';

import 'backend/preferences.dart';
import 'env/env.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  ble.FlutterBluePlus.setLogLevel(ble.LogLevel.info, color: true);

  _initializeFlavors();

  await initializeNotifications();
  await SharedPreferencesUtil.init();
  await MixpanelManager.init();
  await ObjectBoxUtil.init();
  if (Env.instabugApiKey != null) {
    runZonedGuarded(
      () {
        Instabug.init(
          token: Env.instabugApiKey!,
          invocationEvents: [InvocationEvent.shake, InvocationEvent.screenshot],
        );
        FlutterError.onError = (FlutterErrorDetails details) {
          Zone.current.handleUncaughtError(details.exception, details.stack!);
        };
        Instabug.setColorTheme(ColorTheme.dark);
        _getRunApp();
      },
      CrashReporting.reportCrash,
    );
  } else {
    _getRunApp();
  }
}

void _initializeFlavors() {
  if (appFlavor == 'production') {
    F.appFlavor = Flavor.production;
  } else {
    F.appFlavor = Flavor.development;
  }
}

_getRunApp() {
  return runApp(const MyApp());
}

class MyApp extends StatefulWidget {
  const MyApp({super.key});

  @override
  State<MyApp> createState() => _MyAppState();

  static _MyAppState of(BuildContext context) => context.findAncestorStateOfType<_MyAppState>()!;
}

class _MyAppState extends State<MyApp> {
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      navigatorObservers: [InstabugNavigatorObserver()],
      debugShowCheckedModeBanner: false,
      title: 'Friend',
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: const [Locale('en')],
      theme: ThemeData(
          useMaterial3: false,
          colorScheme: const ColorScheme.dark(
            primary: Colors.black,
            secondary: Colors.deepPurple,
            surface: Colors.black38,
          ),
          snackBarTheme: SnackBarThemeData(
            backgroundColor: Colors.grey.shade900,
            contentTextStyle: const TextStyle(fontSize: 16, color: Colors.white, fontWeight: FontWeight.w500),
          ),
          textTheme: TextTheme(
            titleLarge: const TextStyle(fontSize: 18, color: Colors.white),
            titleMedium: const TextStyle(fontSize: 16, color: Colors.white),
            bodyMedium: const TextStyle(fontSize: 14, color: Colors.white),
            labelMedium: TextStyle(fontSize: 12, color: Colors.grey.shade200),
          ),
          textSelectionTheme: const TextSelectionThemeData(
            cursorColor: Colors.white,
            selectionColor: Colors.deepPurple,
          )),
      themeMode: ThemeMode.dark,
      home: (SharedPreferencesUtil().onboardingCompleted && SharedPreferencesUtil().deviceId != '')
          ? const HomePageWrapper()
          : const WelcomePage(),
    );
  }
}
