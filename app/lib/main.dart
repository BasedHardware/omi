import 'dart:async';
import 'dart:ui';

import 'package:awesome_notifications/awesome_notifications.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_crashlytics/firebase_crashlytics.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart' as ble;
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/core/app_shell.dart';
import 'package:omi/env/dev_env.dart';
import 'package:omi/env/env.dart';
import 'package:omi/env/prod_env.dart';
import 'package:omi/firebase_options_dev.dart' as dev;
import 'package:omi/firebase_options_prod.dart' as prod;
import 'package:omi/flavors.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/settings/ai_app_generator_provider.dart';
import 'package:omi/pages/payments/payment_method_provider.dart';
import 'package:omi/pages/persona/persona_provider.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/developer_mode_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/mcp_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/providers/calendar_provider.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/speech_profile_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/voice_recorder_provider.dart';
import 'package:omi/providers/locale_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/desktop_update_service.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/services/notifications/action_item_notification_handler.dart';
import 'package:omi/services/notifications/merge_notification_handler.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/analytics/growthbook.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/debugging/crashlytics_manager.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:opus_dart/opus_dart.dart';
import 'package:opus_flutter/opus_flutter.dart' as opus_flutter;
import 'package:provider/provider.dart';
import 'package:talker_flutter/talker_flutter.dart';
import 'package:window_manager/window_manager.dart';

/// Background message handler for FCM data messages
@pragma('vm:entry-point')
Future<void> _firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp();

  await AwesomeNotifications().initialize(
    null,
    [
      NotificationChannel(
        channelKey: 'channel',
        channelName: 'Omi Notifications',
        channelDescription: 'Notification channel for Omi',
        defaultColor: const Color(0xFF9D50DD),
        ledColor: Colors.white,
      )
    ],
  );

  final data = message.data;
  final messageType = data['type'];
  const channelKey = 'channel';

  // Handle action item messages
  if (messageType == 'action_item_reminder') {
    await ActionItemNotificationHandler.handleReminderMessage(data, channelKey);
  } else if (messageType == 'action_item_update') {
    await ActionItemNotificationHandler.handleUpdateMessage(data, channelKey);
  } else if (messageType == 'action_item_delete') {
    await ActionItemNotificationHandler.handleDeletionMessage(data);
  } else if (messageType == 'merge_completed') {
    await MergeNotificationHandler.handleMergeCompleted(
      data,
      channelKey,
      isAppInForeground: false,
    );
  }
}

Future _init() async {
  // Env
  if (PlatformService.isWindows) {
    // Windows does not support flavors`
    Env.init(ProdEnv());
  } else {
    if (F.env == Environment.prod) {
      Env.init(ProdEnv());
    } else {
      Env.init(DevEnv());
    }
  }

  FlutterForegroundTask.initCommunicationPort();

  // Service manager
  await ServiceManager.init();

  // Firebase
  if (PlatformService.isWindows) {
    // Windows does not support flavors
    await Firebase.initializeApp(options: prod.DefaultFirebaseOptions.currentPlatform);
  } else {
    if (F.env == Environment.prod) {
      await Firebase.initializeApp(options: prod.DefaultFirebaseOptions.currentPlatform);
    } else {
      await Firebase.initializeApp(options: dev.DefaultFirebaseOptions.currentPlatform);
    }
  }

  await PlatformManager.initializeServices();
  await NotificationService.instance.initialize();

  // Register FCM background message handler
  if (PlatformManager().isFCMSupported) {
    FirebaseMessaging.onBackgroundMessage(_firebaseMessagingBackgroundHandler);
  }

  await SharedPreferencesUtil.init();

  bool isAuth = (await AuthService.instance.getIdToken()) != null;
  if (isAuth) PlatformManager.instance.mixpanel.identify();
  if (PlatformService.isMobile) initOpus(await opus_flutter.load());

  await GrowthbookUtil.init();
  if (!PlatformService.isWindows) {
    ble.FlutterBluePlus.setOptions(restoreState: true);
    ble.FlutterBluePlus.setLogLevel(ble.LogLevel.info, color: true);
  }

  await CrashlyticsManager.init();
  if (isAuth) {
    PlatformManager.instance.crashReporter.identifyUser(
      FirebaseAuth.instance.currentUser?.email ?? '',
      SharedPreferencesUtil().fullName,
      SharedPreferencesUtil().uid,
    );
  }
  FlutterError.onError = (FlutterErrorDetails details) {
    FirebaseCrashlytics.instance.recordFlutterFatalError(details);
  };

  PlatformDispatcher.instance.onError = (error, stack) {
    FirebaseCrashlytics.instance.recordError(error, stack, fatal: true);
    return true;
  };

  // Initialize desktop updater
  if (PlatformService.isDesktop) {
    await DesktopUpdateService().initialize();
  }

  await ServiceManager.instance().start();
  return;
}

void main() {
  runZonedGuarded(
    () async {
      // Ensure
      WidgetsFlutterBinding.ensureInitialized();
      if (PlatformService.isDesktop) {
        await windowManager.ensureInitialized();
        WindowOptions windowOptions = const WindowOptions(
          size: Size(1300, 800),
          minimumSize: Size(1100, 700),
          center: true,
          title: "Omi",
          titleBarStyle: TitleBarStyle.hidden,
        );
        windowManager.waitUntilReadyToShow(windowOptions, () async {
          await windowManager.setAsFrameless();
          await windowManager.show();
          await windowManager.focus();
        });
      }

      await _init();
      runApp(const MyApp());
    },
    (error, stack) => FirebaseCrashlytics.instance.recordError(
      error,
      stack,
      fatal: true,
    ),
  );
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
    if (SharedPreferencesUtil().devLogsToFileEnabled) {
      DebugLogManager.setEnabled(true);
    }

    // Auto-start macOS recording if enabled
    if (PlatformService.isDesktop) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _autoStartMacOSRecording();
      });
    }

    super.initState();
  }

  Future<void> _autoStartMacOSRecording() async {
    await Future.delayed(const Duration(seconds: 2));

    if (!SharedPreferencesUtil().autoRecordingEnabled) return;

    try {
      final context = MyApp.navigatorKey.currentContext;
      if (context == null) return;

      final captureProvider = Provider.of<CaptureProvider>(context, listen: false);
      if (captureProvider.recordingState == RecordingState.stop) {
        await captureProvider.streamSystemAudioRecording();
      }
    } catch (e) {
      debugPrint('[AutoRecord] Error: $e');
    }
  }

  void _deinit() {
    debugPrint("App > _deinit");
    ServiceManager.instance().deinit();
    ApiClient.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    super.didChangeAppLifecycleState(state);

    if (state == AppLifecycleState.paused) {
      _onAppPaused();
    } else if (state == AppLifecycleState.detached) {
      _deinit();
    }
  }

  void _onAppPaused() {
    imageCache.clear();
    imageCache.clearLiveImages();
  }

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
        providers: [
          ListenableProvider(create: (context) => ConnectivityProvider()),
          ChangeNotifierProvider(create: (context) => AuthenticationProvider()),
          ChangeNotifierProvider(create: (context) => ConversationProvider()),
          ListenableProvider(create: (context) => AppProvider()),
          ChangeNotifierProvider(create: (context) => PeopleProvider()),
          ChangeNotifierProvider(create: (context) => UsageProvider()),
          ChangeNotifierProxyProvider<AppProvider, MessageProvider>(
            create: (context) => MessageProvider(),
            update: (BuildContext context, value, MessageProvider? previous) =>
                (previous?..updateAppProvider(value)) ?? MessageProvider(),
          ),
          ChangeNotifierProxyProvider4<ConversationProvider, MessageProvider, PeopleProvider, UsageProvider,
              CaptureProvider>(
            create: (context) => CaptureProvider(),
            update: (BuildContext context, conversation, message, people, usage, CaptureProvider? previous) =>
                (previous?..updateProviderInstances(conversation, message, people, usage)) ?? CaptureProvider(),
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
          ChangeNotifierProvider(create: (context) => DeveloperModeProvider()..initialize()),
          ChangeNotifierProvider(create: (context) => McpProvider()),
          ChangeNotifierProxyProvider<AppProvider, AddAppProvider>(
            create: (context) => AddAppProvider(),
            update: (BuildContext context, value, AddAppProvider? previous) =>
                (previous?..setAppProvider(value)) ?? AddAppProvider(),
          ),
          ChangeNotifierProxyProvider<AppProvider, AiAppGeneratorProvider>(
            create: (context) => AiAppGeneratorProvider(),
            update: (BuildContext context, value, AiAppGeneratorProvider? previous) =>
                (previous?..setAppProvider(value)) ?? AiAppGeneratorProvider(),
          ),
          ChangeNotifierProvider(create: (context) => PaymentMethodProvider()),
          ChangeNotifierProvider(create: (context) => PersonaProvider()),
          ChangeNotifierProxyProvider<ConnectivityProvider, MemoriesProvider>(
            create: (context) => MemoriesProvider(),
            update: (context, connectivity, previous) =>
                (previous?..setConnectivityProvider(connectivity)) ?? MemoriesProvider(),
          ),
          ChangeNotifierProvider(create: (context) => UserProvider()),
          ChangeNotifierProvider(create: (context) => ActionItemsProvider()),
          ChangeNotifierProvider(create: (context) => SyncProvider()),
          ChangeNotifierProvider(create: (context) => TaskIntegrationProvider()),
          ChangeNotifierProvider(create: (context) => IntegrationProvider()),
          ChangeNotifierProvider(create: (context) => CalendarProvider(), lazy: false),
          ChangeNotifierProvider(create: (context) => FolderProvider()),
          ChangeNotifierProvider(create: (context) => LocaleProvider()),
          ChangeNotifierProvider(create: (context) => VoiceRecorderProvider()),
        ],
        builder: (context, child) {
          return WithForegroundTask(
            child: MaterialApp(
              debugShowCheckedModeBanner: F.env == Environment.dev,
              title: F.title,
              navigatorKey: MyApp.navigatorKey,
              locale: context.watch<LocaleProvider>().locale,
              localizationsDelegates: const [
                AppLocalizations.delegate,
                GlobalMaterialLocalizations.delegate,
                GlobalWidgetsLocalizations.delegate,
                GlobalCupertinoLocalizations.delegate,
              ],
              supportedLocales: AppLocalizations.supportedLocales,
              theme: ThemeData(
                  useMaterial3: false,
                  colorScheme: const ColorScheme.dark(
                    primary: Colors.black,
                    secondary: Colors.deepPurple,
                    surface: Colors.black38,
                  ),
                  snackBarTheme: const SnackBarThemeData(
                    backgroundColor: Color(0xFF1F1F25),
                    contentTextStyle: TextStyle(fontSize: 16, color: Colors.white, fontWeight: FontWeight.w500),
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
                    DebugLogManager.logError(details.exception, details.stack, 'FlutterError');
                  });
                };
                ErrorWidget.builder = (errorDetails) {
                  return CustomErrorWidget(errorMessage: errorDetails.exceptionAsString());
                };
                return child!;
              },
              home: TalkerWrapper(
                talker: Logger.instance.talker,
                options: const TalkerWrapperOptions(
                  enableErrorAlerts: false,
                  enableExceptionAlerts: false,
                ),
                child: const AppShell(),
              ),
            ),
          );
        });
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
            Text(
              context.l10n.somethingWentWrong,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 18.0, fontWeight: FontWeight.bold),
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
                    SnackBar(
                      content: Text(context.l10n.errorCopied),
                    ),
                  );
                },
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    Text(context.l10n.copyErrorMessage),
                    const SizedBox(width: 10),
                    const Icon(Icons.copy_rounded),
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
