import 'dart:async';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart' as ble;
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:friend_private/backend/auth.dart';
import 'package:friend_private/backend/database/box.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/env/dev_env.dart';
import 'package:friend_private/env/env.dart';
import 'package:friend_private/env/prod_env.dart';
import 'package:friend_private/firebase_options_dev.dart' as dev;
import 'package:friend_private/firebase_options_prod.dart' as prod;
import 'package:friend_private/flavors.dart';
import 'package:friend_private/pages/home/page.dart';
import 'package:friend_private/pages/onboarding/wrapper.dart';
import 'package:friend_private/services/notification_service.dart';
import 'package:friend_private/utils/analytics/growthbook.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/features/calendar.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:onesignal_flutter/onesignal_flutter.dart';
import 'package:opus_dart/opus_dart.dart';
import 'package:opus_flutter/opus_flutter.dart' as opus_flutter;

Future<bool> _init() async {
  ble.FlutterBluePlus.setLogLevel(ble.LogLevel.info, color: true);
  if (F.env == Environment.prod) {
    await Firebase.initializeApp(options: prod.DefaultFirebaseOptions.currentPlatform, name: 'prod');
  } else {
    await Firebase.initializeApp(options: dev.DefaultFirebaseOptions.currentPlatform, name: 'dev');
  }

  await NotificationService.instance.initialize();
  await SharedPreferencesUtil.init();
  await ObjectBoxUtil.init();
  await MixpanelManager.init();

  listenAuthTokenChanges();
  bool isAuth = false;
  try {
    isAuth = (await getIdToken()) != null;
  } catch (e) {} // if no connect this will fail

  if (isAuth) MixpanelManager().identify();

  initOpus(await opus_flutter.load());

  await GrowthbookUtil.init();
  CalendarUtil.init();
  if (Env.oneSignalAppId != null) {
    OneSignal.Debug.setLogLevel(OSLogLevel.verbose);
    OneSignal.initialize(Env.oneSignalAppId!);
    OneSignal.login(SharedPreferencesUtil().uid);
  }
  return isAuth;
}

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  if (F.env == Environment.prod) {
    Env.init(ProdEnv());
  } else {
    Env.init(DevEnv());
  }
  FlutterForegroundTask.initCommunicationPort();
  bool isAuth = await _init();
  if (Env.instabugApiKey != null) {
    Instabug.setWelcomeMessageMode(WelcomeMessageMode.disabled);
    runZonedGuarded(
      () async {
        Instabug.init(
          token: Env.instabugApiKey!,
          invocationEvents: [InvocationEvent.shake, InvocationEvent.screenshot],
        );
        if (isAuth) {
          Instabug.identifyUser(
            FirebaseAuth.instance.currentUser?.email ?? '',
            SharedPreferencesUtil().fullName,
            SharedPreferencesUtil().uid,
          );
        }
        FlutterError.onError = (FlutterErrorDetails details) {
          Zone.current.handleUncaughtError(details.exception, details.stack ?? StackTrace.empty);
        };
        Instabug.setColorTheme(ColorTheme.dark);
        runApp(MyApp(isAuth: isAuth));
      },
      CrashReporting.reportCrash,
    );
  } else {
    runApp(MyApp(isAuth: isAuth));
  }
}

class MyApp extends StatefulWidget {
  final bool isAuth;

  const MyApp({super.key, required this.isAuth});

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
    NotificationService.instance.saveNotificationToken();
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return WithForegroundTask(
      child: MaterialApp(
        navigatorObservers: [
          if (Env.instabugApiKey != null) InstabugNavigatorObserver(),
        ],
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
        home: (SharedPreferencesUtil().onboardingCompleted && widget.isAuth)
            ? const HomePageWrapper()
            : const OnboardingWrapper(),
      ),
    );
  }
}
