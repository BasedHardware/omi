import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:omi/env/env.dart';
import 'package:omi/flavors.dart';
import 'package:omi/pages/custom_error/page.dart';
import 'package:omi/providers/get_all_providers.dart';
import 'package:omi/utils/app_init.dart';
import 'package:omi/widgets/decider_widget.dart';
import 'package:responsive_framework/responsive_framework.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/logger.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:omi/utils/platform_check.dart';
import 'package:posthog_flutter/posthog_flutter.dart';
import 'package:provider/provider.dart';
import 'package:talker_flutter/talker_flutter.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await appInit();
}

class MyApp extends StatefulWidget {
  const MyApp({super.key});

  @override
  State<MyApp> createState() => _MyAppState();

  static _MyAppState of(BuildContext context) => context.findAncestorStateOfType<_MyAppState>()!;

  // The navigator key is necessary to navigate using static methods
  static final GlobalKey<NavigatorState> navigatorKey = GlobalKey<NavigatorState>();
}

class _MyAppState extends State<MyApp> with WidgetsBindingObserver {
  @override
  void initState() {
    if (!ExecutionGuard.isWeb) {
      NotificationUtil.initializeNotificationsEventListeners();
      NotificationUtil.initializeIsolateReceivePort();
    }
    WidgetsBinding.instance.addObserver(this);
    super.initState();
  }

  void _deinit() {
    debugPrint("App > _deinit");
    ServiceManager.instance().deinit();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    super.didChangeAppLifecycleState(state);
    if (state == AppLifecycleState.detached) {
      _deinit();
    }
  }

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
        providers: getAllProviders(),
        builder: (context, child) {
          return WithForegroundTaskConditionally(
            child: MaterialApp(
              navigatorObservers: [
                if (Env.instabugApiKey != null) InstabugNavigatorObserver(),
                if (Env.posthogApiKey != null) PosthogObserver(),
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
                    selectionHandleColor: Colors.white,
                  ),
                  cupertinoOverrideTheme: const CupertinoThemeData(
                    primaryColor: Colors.white, // Controls the selection handles on iOS
                  )),
              themeMode: ThemeMode.dark,
              builder: (context, child) {
                FlutterError.onError = (FlutterErrorDetails details) {
                  WidgetsBinding.instance.addPostFrameCallback((_) {
                    Logger.instance.talker.handle(details.exception, details.stack);
                  });
                };
                ErrorWidget.builder = (errorDetails) {
                  return CustomErrorWidget(errorMessage: errorDetails.exceptionAsString());
                };
                return ResponsiveBreakpoints.builder(
                  child: child!,
                  breakpoints: [
                    const Breakpoint(start: 0, end: 450, name: MOBILE),
                    const Breakpoint(start: 451, end: 800, name: TABLET),
                    const Breakpoint(start: 801, end: 1920, name: DESKTOP),
                    const Breakpoint(start: 1921, end: double.infinity, name: '4K'),
                  ],
                );
              },
              onGenerateRoute: (RouteSettings settings) {
                return MaterialPageRoute(builder: (context) {
                  return ResponsiveScaledBox(
                    width: ResponsiveValue<double>(context, conditionalValues: [
                      const Condition.equals(name: MOBILE, value: 450),
                      const Condition.between(start: 451, end: 800, value: 800),
                      const Condition.between(start: 801, end: 1920, value: 1920),
                      Condition.between(start: 1921, end: double.infinity.toInt(), value: 1920),
                    ]).value,
                    child: BouncingScrollWrapper.builder(context, child!, dragWithMouse: true),
                  );
                });
              },
              home: TalkerWrapper(
                talker: Logger.instance.talker,
                options: TalkerWrapperOptions(
                  enableErrorAlerts: true,
                  enableExceptionAlerts: true,
                  errorAlertBuilder: (context, data) {
                    return LoggerSnackbar(error: data);
                  },
                  exceptionAlertBuilder: (context, data) {
                    return LoggerSnackbar(exception: data);
                  },
                ),
                child: const DeciderWidget(),
              ),
            ),
          );
        });
  }
}

class WithForegroundTaskConditionally extends StatelessWidget {
  final Widget child;
  const WithForegroundTaskConditionally({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    if (ExecutionGuard.isWeb) {
      return child;
    } else {
      return WithForegroundTask(child: child);
    }
  }
}
