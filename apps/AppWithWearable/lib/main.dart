import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart' as ble;
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:friend_private/backend/database/box.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/flavors.dart';
import 'package:friend_private/pages/home/page.dart';
import 'package:friend_private/pages/onboarding/wrapper.dart';
import 'package:friend_private/utils/notifications.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:onesignal_flutter/onesignal_flutter.dart';
import 'package:opus_dart/opus_dart.dart';
import 'package:opus_flutter/opus_flutter.dart' as opus_flutter;

import 'backend/preferences.dart';
import 'env/env.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  ble.FlutterBluePlus.setLogLevel(ble.LogLevel.info, color: true);
  await initializeNotifications();
  await SharedPreferencesUtil.init();
  await MixpanelManager.init();
  await ObjectBoxUtil.init();
  initOpus(await opus_flutter.load());

  if (Env.oneSignalAppId != null) {
    OneSignal.Debug.setLogLevel(OSLogLevel.verbose);
    OneSignal.initialize(Env.oneSignalAppId!);
    OneSignal.login(SharedPreferencesUtil().uid);
  }

  if (Env.instabugApiKey != null) {
    runZonedGuarded(
      () {
        Instabug.init(
          token: Env.instabugApiKey!,
          invocationEvents: [InvocationEvent.shake, InvocationEvent.screenshot],
        );
        FlutterError.onError = (FlutterErrorDetails details) {
          Zone.current.handleUncaughtError(details.exception, details.stack ?? StackTrace.empty);
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

_getRunApp() {
  return runApp(const MyApp());
}

class MyApp extends StatefulWidget {
  const MyApp({super.key});

  @override
  State<MyApp> createState() => _MyAppState();

  static _MyAppState of(BuildContext context) => context.findAncestorStateOfType<_MyAppState>()!;

  // The navigator key is necessary to navigate using static methods
  static final GlobalKey<NavigatorState> navigatorKey = GlobalKey<NavigatorState>();
}

class _MyAppState extends State<MyApp> {
  @override
  void initState() {
    NotificationUtil.initializeNotificationsEventListeners();
    NotificationUtil.initializeIsolateReceivePort();
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      navigatorObservers: [InstabugNavigatorObserver()],
      debugShowCheckedModeBanner: F.env == Environment.dev,
      title: F.title,
      navigatorKey: MyApp.navigatorKey,
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
          // dialogTheme: const DialogTheme(
          //   backgroundColor: Colors.black,
          //   titleTextStyle: TextStyle(fontSize: 18, color: Colors.white),
          //   contentTextStyle: TextStyle(fontSize: 16, color: Colors.white),
          // ),
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
      // home: const HasBackupPage(),
      home: (SharedPreferencesUtil().onboardingCompleted) //  && SharedPreferencesUtil().deviceId != ''
          ? const HomePageWrapper()
          : const OnboardingWrapper(),
    );
  }
}

// Do not run me directly, instead use main_dev.dart
