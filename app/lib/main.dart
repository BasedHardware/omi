import 'dart:async';
import 'dart:io';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_crashlytics/firebase_crashlytics.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_native_splash/flutter_native_splash.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_timezone/flutter_timezone.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/env/env.dart';
import 'package:friend_private/firebase_options.dart';
import 'package:friend_private/pages/home/page.dart';
import 'package:friend_private/pages/onboarding/wrapper.dart';
import 'package:friend_private/providers/connectivity_provider.dart';
import 'package:friend_private/providers/device_provider.dart';
import 'package:friend_private/providers/home_provider.dart';
import 'package:friend_private/providers/memory_detail_provider.dart';
import 'package:friend_private/providers/memory_provider.dart';
import 'package:friend_private/providers/message_provider.dart';
import 'package:friend_private/providers/onboarding_provider.dart';
import 'package:friend_private/providers/plugin_provider.dart';
import 'package:friend_private/providers/speech_profile_provider.dart';
import 'package:friend_private/utils/analytics/growthbook.dart';
import 'package:friend_private/utils/analytics/intercom.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/analytics/posthog.dart';
import 'package:friend_private/utils/audio/opus_codec.dart';
import 'package:friend_private/utils/features/calendar.dart';
import 'package:friend_private/utils/notifications.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:opus_dart/opus_dart.dart';
import 'package:opus_flutter/opus_flutter.dart' as opus_flutter;
import 'package:provider/provider.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'package:timezone/data/latest.dart' as tz;

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  WidgetsBinding widgetsBinding = WidgetsFlutterBinding.ensureInitialized();
  FlutterNativeSplash.preserve(widgetsBinding: widgetsBinding);

  // Initialize with error recovery
  await _initWithErrorHandling();
  
  runApp(const MyApp());
}

Future<void> _initWithErrorHandling() async {
  bool criticalError = false;
  String? errorMessage;
  
  try {
    // Critical initialization - app cannot run without these
    await _initCriticalServices();
  } catch (e) {
    criticalError = true;
    errorMessage = 'Critical initialization failed: $e';
    print('CRITICAL ERROR: $errorMessage');
  }
  
  if (!criticalError) {
    // Non-critical initialization - app can run with fallbacks
    await _initNonCriticalServices();
  } else {
    // Show error UI instead of crashing
    runApp(ErrorApp(message: errorMessage ?? 'Unknown error'));
    return;
  }
  
  // Remove splash screen
  FlutterNativeSplash.remove();
}

Future<void> _initCriticalServices() async {
  try {
    // Load environment variables with timeout
    await dotenv.load(fileName: ".env").timeout(
      const Duration(seconds: 5),
      onTimeout: () {
        print('Warning: .env file load timed out, using defaults');
      },
    );
  } catch (e) {
    print('Warning: Failed to load .env file: $e');
    // Continue with default values
  }

  // Initialize SharedPreferences with retry
  int retries = 3;
  while (retries > 0) {
    try {
      SharedPreferencesUtil.sharedPreferencesInstance = 
          await SharedPreferences.getInstance().timeout(
        const Duration(seconds: 5),
      );
      break;
    } catch (e) {
      retries--;
      if (retries == 0) rethrow;
      await Future.delayed(const Duration(seconds: 1));
    }
  }

  // Initialize Supabase with error handling
  try {
    await Supabase.initialize(
      url: Env.supabaseUrl ?? '',
      anonKey: Env.supabaseAnonKey ?? '',
    ).timeout(const Duration(seconds: 10));
  } catch (e) {
    print('Warning: Supabase initialization failed: $e');
    // App can work offline
  }
}

Future<void> _initNonCriticalServices() async {
  // Firebase - wrap in try-catch
  try {
    await Firebase.initializeApp(
      options: DefaultFirebaseOptions.currentPlatform,
    ).timeout(const Duration(seconds: 10));
    
    // Crashlytics
    try {
      await FirebaseCrashlytics.instance
          .setCrashlyticsCollectionEnabled(!Platform.isLinux);
      FlutterError.onError = FirebaseCrashlytics.instance.recordFlutterError;
    } catch (e) {
      print('Warning: Crashlytics setup failed: $e');
    }
  } catch (e) {
    print('Warning: Firebase initialization failed: $e');
    // Continue without Firebase
  }

  // Analytics services - all non-critical
  try {
    await IntercomManager.instance.init();
  } catch (e) {
    print('Warning: Intercom init failed: $e');
  }

  try {
    await PostHog.instance.init();
  } catch (e) {
    print('Warning: PostHog init failed: $e');
  }

  try {
    await MixpanelManager.instance.init();
  } catch (e) {
    print('Warning: Mixpanel init failed: $e');
  }

  try {
    await GrowthbookManager.instance.init();
  } catch (e) {
    print('Warning: Growthbook init failed: $e');
  }

  // Notifications
  try {
    await NotificationService.instance.initialize();
  } catch (e) {
    print('Warning: Notification service init failed: $e');
  }

  // Opus codec
  try {
    if (Platform.isAndroid || Platform.isIOS || Platform.isMacOS) {
      initOpus();
    }
  } catch (e) {
    print('Warning: Opus codec init failed: $e');
  }

  // Instabug
  if (Platform.isAndroid || Platform.isIOS) {
    try {
      if (Env.instabugApiKey != null && Env.instabugApiKey!.isNotEmpty) {
        await Instabug.init(
          token: Env.instabugApiKey!,
          invocationEvents: [InvocationEvent.shake, InvocationEvent.screenshot],
        );
      }
    } catch (e) {
      print('Warning: Instabug init failed: $e');
    }
  }

  // Timezone
  try {
    tz.initializeTimeZones();
    final String currentTimeZone = await FlutterTimezone.getLocalTimezone();
    SharedPreferencesUtil().timezone = currentTimeZone;
  } catch (e) {
    print('Warning: Timezone init failed: $e');
  }

  // Calendar
  try {
    await CalendarUtil.init();
  } catch (e) {
    print('Warning: Calendar init failed: $e');
  }
}

// Error recovery app
class ErrorApp extends StatelessWidget {
  final String message;
  
  const ErrorApp({Key? key, required this.message}) : super(key: key);
  
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      home: Scaffold(
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Icon(Icons.error_outline, size: 64, color: Colors.red),
                const SizedBox(height: 20),
                const Text(
                  'Failed to initialize app',
                  style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 10),
                Text(
                  message,
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: 14),
                ),
                const SizedBox(height: 30),
                ElevatedButton(
                  onPressed: () {
                    // Try to restart the app
                    SystemNavigator.pop();
                  },
                  child: const Text('Close App'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// Rest of the MyApp class remains the same...
class MyApp extends StatefulWidget {
  const MyApp({super.key});

  @override
  State<MyApp> createState() => _MyAppState();
}

class _MyAppState extends State<MyApp> {
  @override
  void initState() {
    super.initState();
    _handleBluetoothPermission();
  }

  void _handleBluetoothPermission() async {
    try {
      if (await FlutterBluePlus.isSupported == false) {
        debugPrint("Bluetooth not supported by this device");
        return;
      }
      
      if (Platform.isAndroid) {
        await FlutterBluePlus.turnOn();
      }
    } catch (e) {
      debugPrint('Bluetooth permission error: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return ScreenUtilInit(
      designSize: const Size(360, 800),
      minTextAdapt: true,
      splitScreenMode: true,
      builder: (_, child) {
        return MultiProvider(
          providers: [
            ChangeNotifierProvider(create: (context) => ConnectivityProvider()),
            ChangeNotifierProvider(create: (context) => MemoryProvider()),
            ChangeNotifierProvider(create: (context) => MessageProvider()),
            ChangeNotifierProvider(create: (context) => PluginProvider()),
            ChangeNotifierProvider(create: (context) => HomeProvider()),
            ChangeNotifierProvider(create: (context) => OnboardingProvider()),
            ChangeNotifierProvider(create: (context) => DeviceProvider()),
            ChangeNotifierProvider(create: (context) => MemoryDetailProvider()),
            ChangeNotifierProvider(create: (context) => SpeechProfileProvider()),
          ],
          child: MaterialApp(
            navigatorKey: navigatorKey,
            debugShowCheckedModeBanner: false,
            title: 'Friend',
            theme: ThemeData(
              useMaterial3: false,
              primarySwatch: Colors.blue,
              primaryColor: const Color(0xFF000000),
              primaryColorDark: const Color(0xFF000000),
              primaryColorLight: const Color(0xFF000000),
              scaffoldBackgroundColor: const Color(0xFF0D0F0F),
              canvasColor: const Color(0xFF0D0F0F),
              colorScheme: const ColorScheme.dark(
                primary: Color(0xFF000000),
                surface: Color(0xFF0D0F0F),
              ),
            ),
            localizationsDelegates: const [
              GlobalMaterialLocalizations.delegate,
              GlobalWidgetsLocalizations.delegate,
              GlobalCupertinoLocalizations.delegate,
            ],
            supportedLocales: const [Locale('en', '')],
            themeMode: ThemeMode.dark,
            home: child,
          ),
        );
      },
      child: FutureBuilder<bool>(
        future: isSignedIn(),
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Scaffold(
              backgroundColor: Color(0xFF0D0F0F),
              body: Center(child: CircularProgressIndicator()),
            );
          }
          if (snapshot.hasError) {
            return Scaffold(
              backgroundColor: const Color(0xFF0D0F0F),
              body: Center(
                child: Text('Error: ${snapshot.error}'),
              ),
            );
          }
          if (snapshot.data == true) {
            return const HomePageWrapper();
          } else {
            return const OnboardingWrapper();
          }
        },
      ),
    );
  }

  GlobalKey<NavigatorState> navigatorKey = GlobalKey<NavigatorState>();

  Future<bool> isSignedIn() async {
    try {
      return SharedPreferencesUtil().uid.isNotEmpty;
    } catch (e) {
      return false;
    }
  }
}