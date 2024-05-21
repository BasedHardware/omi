import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_web_plugins/url_strategy.dart';
import 'package:friend_private/pages/home/page.dart';
import 'package:friend_private/utils/notifications.dart';
import 'package:sentry_flutter/sentry_flutter.dart';
import 'package:sentry_logging/sentry_logging.dart';

import 'backend/preferences.dart';
import 'env/env.dart';
import 'flutter_flow/flutter_flow_util.dart';
import 'flutter_flow/internationalization.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  usePathUrlStrategy();

  await initializeNotifications();
  await SharedPreferencesUtil.init();
  if (Env.sentryDSNKey?.isNotEmpty ?? false) {
    debugPrint('Sentry key: ${Env.sentryDSNKey}');
    await SentryFlutter.init(
      (options) {
        options.dsn = Env.sentryDSNKey;
        options.tracesSampleRate = 1.0;
        options.profilesSampleRate = 1.0;
        options.attachScreenshot = false;
        options.debug = true;
        options.addIntegration(LoggingIntegration());
        options.enableAutoPerformanceTracing = true;
      },
      appRunner: () => _getRunApp(),
    );
  } else {
    _getRunApp();
  }
}

_getRunApp() {
  return runApp(MyApp(
    entryPage: SharedPreferencesUtil().onboardingCompleted ? const HomePageWrapper(btDevice: null) : null,
  ));
}

class MyApp extends StatefulWidget {
  const MyApp({super.key, this.entryPage});

  // This widget is the root of your application.
  @override
  State<MyApp> createState() => _MyAppState();

  static _MyAppState of(BuildContext context) => context.findAncestorStateOfType<_MyAppState>()!;

  final Widget? entryPage;
}

class _MyAppState extends State<MyApp> {
  Locale? _locale;
  ThemeMode _themeMode = ThemeMode.system;

  late AppStateNotifier _appStateNotifier;
  late GoRouter _router;

  @override
  void initState() {
    super.initState();

    _appStateNotifier = AppStateNotifier.instance;
    _router = createRouter(_appStateNotifier, widget.entryPage);

    Future.delayed(
        const Duration(milliseconds: 1000), () => setState(() => _appStateNotifier.stopShowingSplashImage()));
  }

  void setLocale(String language) {
    setState(() => _locale = createLocale(language));
  }

  void setThemeMode(ThemeMode mode) => setState(() {
        _themeMode = mode;
      });

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      debugShowCheckedModeBanner: false,
      title: 'Friend',
      localizationsDelegates: const [
        FFLocalizationsDelegate(),
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      locale: _locale,
      supportedLocales: const [
        Locale('en'),
      ],
      theme: ThemeData(
        brightness: Brightness.light,
        useMaterial3: false,
      ),
      themeMode: _themeMode,
      routerConfig: _router,
    );
  }
}
