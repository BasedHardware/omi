import 'dart:async';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart' as ble;
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:friend_private/backend/auth.dart';
import 'package:friend_private/backend/http/api/custom_auth.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/env/dev_env.dart';
import 'package:friend_private/env/env.dart';
import 'package:friend_private/env/prod_env.dart';
import 'package:friend_private/firebase_options_dev.dart' as dev;
import 'package:friend_private/firebase_options_prod.dart' as prod;
import 'package:friend_private/flavors.dart';
import 'package:friend_private/pages/apps/providers/add_app_provider.dart';
import 'package:friend_private/pages/home/page.dart';
import 'package:friend_private/pages/memory_detail/memory_detail_provider.dart';
import 'package:friend_private/pages/onboarding/wrapper.dart';
import 'package:friend_private/providers/app_provider.dart';
import 'package:friend_private/providers/auth_provider.dart';
import 'package:friend_private/providers/calendar_provider.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/providers/connectivity_provider.dart';
import 'package:friend_private/providers/developer_mode_provider.dart';
import 'package:friend_private/providers/device_provider.dart';
import 'package:friend_private/providers/home_provider.dart';
import 'package:friend_private/providers/memory_provider.dart';
import 'package:friend_private/providers/message_provider.dart';
import 'package:friend_private/providers/onboarding_provider.dart';
import 'package:friend_private/providers/speech_profile_provider.dart';
import 'package:friend_private/services/notifications.dart';
import 'package:friend_private/services/services.dart';
import 'package:friend_private/utils/analytics/growthbook.dart';
import 'package:friend_private/utils/analytics/intercom.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/features/calendar.dart';
import 'package:friend_private/utils/logger.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:opus_dart/opus_dart.dart';
import 'package:opus_flutter/opus_flutter.dart' as opus_flutter;
import 'package:provider/provider.dart';
import 'package:talker_flutter/talker_flutter.dart';

Future<bool> _init() async {
  // Service manager
  ServiceManager.init();

  // Firebase
  if (F.env == Environment.prod) {
    await Firebase.initializeApp(options: prod.DefaultFirebaseOptions.currentPlatform, name: 'prod');
  } else {
    await Firebase.initializeApp(options: dev.DefaultFirebaseOptions.currentPlatform, name: 'dev');
  }

  await IntercomManager().initIntercom();
  await NotificationService.instance.initialize();
  await SharedPreferencesUtil.init();
  await MixpanelManager.init();

  // TODO: thinh, move to app start
  await ServiceManager.instance().start();

  bool isAuth = false;
  try {
    if (SharedPreferencesUtil().customBackendUrl.isNotEmpty) {
      isAuth = await customAuthSignIn(SharedPreferencesUtil().email, SharedPreferencesUtil().customAuthPassword);
    } else {
      isAuth = (await getIdToken()) != null;
    }
  } catch (e) {} // if no connect this will fail

  if (isAuth) MixpanelManager().identify();
  initOpus(await opus_flutter.load());

  await GrowthbookUtil.init();
  CalendarUtil.init();
  ble.FlutterBluePlus.setLogLevel(ble.LogLevel.info, color: true);
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
  // _setupAudioSession();
  bool isAuth = await _init();
  if (Env.instabugApiKey != null) {
    await Instabug.setWelcomeMessageMode(WelcomeMessageMode.disabled);
    runZonedGuarded(
      () async {
        Instabug.init(
          token: Env.instabugApiKey!,
          invocationEvents: [InvocationEvent.none],
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
        runApp(const MyApp());
      },
      CrashReporting.reportCrash,
    );
  } else {
    runApp(const MyApp());
  }
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
    NotificationUtil.initializeNotificationsEventListeners();
    NotificationUtil.initializeIsolateReceivePort();
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
        providers: [
          ListenableProvider(create: (context) => ConnectivityProvider()),
          ChangeNotifierProvider(create: (context) => AuthenticationProvider()),
          ChangeNotifierProvider(create: (context) => MemoryProvider()),
          ListenableProvider(create: (context) => AppProvider()),
          ChangeNotifierProxyProvider<AppProvider, MessageProvider>(
            create: (context) => MessageProvider(),
            update: (BuildContext context, value, MessageProvider? previous) =>
                (previous?..updateAppProvider(value)) ?? MessageProvider(),
          ),
          ChangeNotifierProxyProvider2<MemoryProvider, MessageProvider, CaptureProvider>(
            create: (context) => CaptureProvider(),
            update: (BuildContext context, memory, message, CaptureProvider? previous) =>
                (previous?..updateProviderInstances(memory, message)) ?? CaptureProvider(),
          ),
          ChangeNotifierProxyProvider<CaptureProvider, DeviceProvider>(
            create: (context) => DeviceProvider(),
            update: (BuildContext context, captureProvider, DeviceProvider? previous) =>
                (previous?..setProviders(captureProvider)) ?? DeviceProvider(),
          ),
          ChangeNotifierProxyProvider<DeviceProvider, OnboardingProvider>(
            create: (context) => OnboardingProvider(),
            update: (BuildContext context, value, OnboardingProvider? previous) =>
                (previous?..setDeviceProvider(value)) ?? OnboardingProvider(),
          ),
          ListenableProvider(create: (context) => HomeProvider()),
          ChangeNotifierProxyProvider<DeviceProvider, SpeechProfileProvider>(
            create: (context) => SpeechProfileProvider(),
            update: (BuildContext context, device, SpeechProfileProvider? previous) =>
                (previous?..setProviders(device)) ?? SpeechProfileProvider(),
          ),
          ChangeNotifierProxyProvider2<AppProvider, MemoryProvider, MemoryDetailProvider>(
            create: (context) => MemoryDetailProvider(),
            update: (BuildContext context, app, memory, MemoryDetailProvider? previous) =>
                (previous?..setProviders(app, memory)) ?? MemoryDetailProvider(),
          ),
          ChangeNotifierProvider(create: (context) => CalenderProvider()),
          ChangeNotifierProvider(create: (context) => DeveloperModeProvider()),
          ChangeNotifierProxyProvider<AppProvider, AddAppProvider>(
            create: (context) => AddAppProvider(),
            update: (BuildContext context, value, AddAppProvider? previous) =>
                (previous?..setAppProvider(value)) ?? AddAppProvider(),
          ),
        ],
        builder: (context, child) {
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
              builder: (context, child) {
                FlutterError.onError = (FlutterErrorDetails details) {
                  WidgetsBinding.instance.addPostFrameCallback((_) {
                    Logger.instance.talker.handle(details.exception, details.stack);
                  });
                };
                ErrorWidget.builder = (errorDetails) {
                  return CustomErrorWidget(errorMessage: errorDetails.exceptionAsString());
                };
                return child!;
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

class DeciderWidget extends StatefulWidget {
  const DeciderWidget({super.key});

  @override
  State<DeciderWidget> createState() => _DeciderWidgetState();
}

class _DeciderWidgetState extends State<DeciderWidget> {
  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (context.read<ConnectivityProvider>().isConnected) {
        NotificationService.instance.saveNotificationToken();
      }

      if (context.read<AuthenticationProvider>().user != null ||
          (SharedPreferencesUtil().customBackendUrl.isNotEmpty && SharedPreferencesUtil().authToken.isNotEmpty)) {
        context.read<HomeProvider>().setupHasSpeakerProfile();
        IntercomManager.instance.intercom.loginIdentifiedUser(
          userId: SharedPreferencesUtil().uid,
        );
        context.read<MessageProvider>().setMessagesFromCache();
        context.read<AppProvider>().setAppsFromCache();
        context.read<MessageProvider>().refreshMessages();
      } else {
        await IntercomManager.instance.intercom.loginUnidentifiedUser();
      }
      IntercomManager.instance.setUserAttributes();
    });
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AuthenticationProvider>(
      builder: (context, authProvider, child) {
        if (SharedPreferencesUtil().onboardingCompleted &&
            (authProvider.user != null ||
                (SharedPreferencesUtil().customBackendUrl.isNotEmpty &&
                    SharedPreferencesUtil().authToken.isNotEmpty))) {
          return const HomePageWrapper();
        } else {
          return const OnboardingWrapper();
        }
      },
    );
  }
}

class CustomErrorWidget extends StatelessWidget {
  final String errorMessage;

  const CustomErrorWidget({super.key, required this.errorMessage});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(
              Icons.error_outline,
              color: Colors.red,
              size: 50.0,
            ),
            const SizedBox(height: 10.0),
            const Text(
              'Something went wrong! Please try again later.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 18.0, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 10.0),
            Container(
              padding: const EdgeInsets.all(10),
              margin: const EdgeInsets.all(16),
              height: 200,
              decoration: BoxDecoration(
                color: const Color.fromARGB(255, 63, 63, 63),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Text(
                errorMessage,
                textAlign: TextAlign.start,
                style: const TextStyle(fontSize: 16.0),
              ),
            ),
            const SizedBox(height: 10.0),
            SizedBox(
              width: 210,
              child: ElevatedButton(
                style: ElevatedButton.styleFrom(backgroundColor: Colors.red),
                onPressed: () {
                  Clipboard.setData(ClipboardData(text: errorMessage));
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(
                      content: Text('Error message copied to clipboard'),
                    ),
                  );
                },
                child: const Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    Text('Copy error message'),
                    SizedBox(width: 10),
                    Icon(Icons.copy_rounded),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
