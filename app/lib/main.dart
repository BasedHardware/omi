import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart' as ble;
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:omi/backend/auth.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/dev_env.dart';
import 'package:omi/env/env.dart';
import 'package:omi/env/prod_env.dart';
import 'package:omi/firebase_options_dev.dart' as dev;
import 'package:omi/firebase_options_prod.dart' as prod;
import 'package:omi/flavors.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/onboarding/device_selection.dart';
import 'package:omi/pages/onboarding/wrapper.dart';
import 'package:omi/pages/persona/persona_profile.dart';
import 'package:omi/pages/persona/persona_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/calendar_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/developer_mode_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/facts_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/pages/payments/payment_method_provider.dart';
import 'package:omi/providers/speech_profile_provider.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/analytics/growthbook.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/features/calendar.dart';
import 'package:omi/utils/logger.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:opus_dart/opus_dart.dart';
import 'package:opus_flutter/opus_flutter.dart' as opus_flutter;
import 'package:posthog_flutter/posthog_flutter.dart';
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

  bool isAuth = (await getIdToken()) != null;
  if (isAuth) MixpanelManager().identify();
  initOpus(await opus_flutter.load());

  await GrowthbookUtil.init();
  CalendarUtil.init();
  ble.FlutterBluePlus.setLogLevel(ble.LogLevel.info, color: true);
  return isAuth;
}

Future<void> initPostHog() async {
  final config = PostHogConfig(Env.posthogApiKey!);
  config.debug = true;
  config.captureApplicationLifecycleEvents = true;
  config.host = 'https://us.i.posthog.com';
  await Posthog().setup(config);
}

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  if (F.env == Environment.prod) {
    Env.init(ProdEnv());
  } else {
    Env.init(DevEnv());
  }
  FlutterForegroundTask.initCommunicationPort();
  if (Env.posthogApiKey != null) {
    await initPostHog();
  }
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
          ChangeNotifierProvider(create: (context) => ConversationProvider()),
          ListenableProvider(create: (context) => AppProvider()),
          ChangeNotifierProxyProvider<AppProvider, MessageProvider>(
            create: (context) => MessageProvider(),
            update: (BuildContext context, value, MessageProvider? previous) =>
                (previous?..updateAppProvider(value)) ?? MessageProvider(),
          ),
          ChangeNotifierProxyProvider2<ConversationProvider, MessageProvider, CaptureProvider>(
            create: (context) => CaptureProvider(),
            update: (BuildContext context, conversation, message, CaptureProvider? previous) =>
                (previous?..updateProviderInstances(conversation, message)) ?? CaptureProvider(),
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
          ChangeNotifierProxyProvider2<AppProvider, ConversationProvider, ConversationDetailProvider>(
            create: (context) => ConversationDetailProvider(),
            update: (BuildContext context, app, conversation, ConversationDetailProvider? previous) =>
                (previous?..setProviders(app, conversation)) ?? ConversationDetailProvider(),
          ),
          ChangeNotifierProvider(create: (context) => CalenderProvider()),
          ChangeNotifierProvider(create: (context) => DeveloperModeProvider()),
          ChangeNotifierProxyProvider<AppProvider, AddAppProvider>(
            create: (context) => AddAppProvider(),
            update: (BuildContext context, value, AddAppProvider? previous) =>
                (previous?..setAppProvider(value)) ?? AddAppProvider(),
          ),
          ChangeNotifierProvider(create: (context) => PaymentMethodProvider()),
          ChangeNotifierProvider(create: (context) => PersonaProvider()),
          ChangeNotifierProvider(create: (context) => FactsProvider()),
        ],
        builder: (context, child) {
          return WithForegroundTask(
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
  late AppLinks _appLinks;
  StreamSubscription<Uri>? _linkSubscription;

  Future<void> initDeepLinks() async {
    _appLinks = AppLinks();

    // Handle links
    _linkSubscription = _appLinks.uriLinkStream.distinct().listen((uri) {
      debugPrint('onAppLink: $uri');
      openAppLink(uri);
    });
  }

  void openAppLink(Uri uri) async {
    if (uri.pathSegments.first == 'apps') {
      if (mounted) {
        var app = await context.read<AppProvider>().getAppFromId(uri.pathSegments[1]);
        if (app != null) {
          MixpanelManager().track('App Opened From DeepLink', properties: {'appId': app.id});
          if (mounted) {
            Navigator.of(context).push(MaterialPageRoute(builder: (context) => AppDetailPage(app: app)));
          }
        } else {
          debugPrint('App not found: ${uri.pathSegments[1]}');
          AppSnackbar.showSnackbarError('Oops! Looks like the app you are looking for is not available.');
        }
      }
    } else {
      debugPrint('Unknown link: $uri');
    }
  }

  @override
  void initState() {
    initDeepLinks();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (context.read<ConnectivityProvider>().isConnected) {
        NotificationService.instance.saveNotificationToken();
      }

      if (context.read<AuthenticationProvider>().isSignedIn()) {
        context.read<HomeProvider>().setupHasSpeakerProfile();
        try {
          await IntercomManager.instance.intercom.loginIdentifiedUser(
            userId: SharedPreferencesUtil().uid,
          );
        } catch (e) {
          debugPrint('Failed to login to Intercom: $e');
        }

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
        if (authProvider.isSignedIn()) {
          if (SharedPreferencesUtil().onboardingCompleted) {
            return const HomePageWrapper();
          } else {
            return const OnboardingWrapper();
          }
        } else if (SharedPreferencesUtil().hasOmiDevice == false &&
            SharedPreferencesUtil().hasPersonaCreated &&
            SharedPreferencesUtil().verifiedPersonaId != null) {
          return const PersonaProfilePage();
        } else {
          return const DeviceSelectionPage();
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
