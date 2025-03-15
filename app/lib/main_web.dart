import 'package:flutter/material.dart';
import 'package:friend_private/pages/onboarding/web_onboarding.dart';
import 'package:friend_private/providers/web_auth_provider.dart';
import 'package:friend_private/services/web_notification_service.dart';
import 'package:friend_private/services/web_service_manager.dart';
import 'package:friend_private/utils/platform_utils.dart';
import 'package:provider/provider.dart';

/// Web-specific entry point that avoids Firebase imports
void main() {
  WidgetsFlutterBinding.ensureInitialized();
  debugPrint('Starting web-specific entry point');
  runApp(const WebApp());
}

class WebApp extends StatefulWidget {
  const WebApp({Key? key}) : super(key: key);

  @override
  State<WebApp> createState() => _WebAppState();
  
  static final GlobalKey<NavigatorState> navigatorKey = GlobalKey<NavigatorState>();
}

class _WebAppState extends State<WebApp> {
  @override
  void initState() {
    super.initState();
    _initializeWebServices();
  }
  
  Future<void> _initializeWebServices() async {
    try {
      // Initialize web-specific services
      WebServiceManager.init();
      await WebNotificationService.instance.initialize();
      await WebServiceManager.instance().start();
      debugPrint('Web services initialized successfully');
    } catch (e) {
      debugPrint('Error initializing web services: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider<WebAuthenticationProvider>(
          create: (context) => WebAuthenticationProvider(),
        ),
      ],
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        title: 'Omi Web',
        navigatorKey: WebApp.navigatorKey,
        theme: ThemeData(
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
        ),
        themeMode: ThemeMode.dark,
        home: const WebOnboardingPage(),
      ),
    );
  }
}
