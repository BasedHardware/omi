import 'dart:async';
import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:omi/mobile/mobile_app.dart';
import 'package:omi/desktop/desktop_app.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/asana_service.dart';
import 'package:omi/services/google_tasks_service.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/services/todoist_service.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/platform/platform_manager.dart';

class AppShell extends StatefulWidget {
  const AppShell({super.key});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
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
    if (uri.pathSegments.isEmpty) {
      debugPrint('No path segments in URI: $uri');
      return;
    }

    if (uri.pathSegments.first == 'apps') {
      if (mounted) {
        var app = await context.read<AppProvider>().getAppFromId(uri.pathSegments[1]);
        if (app != null) {
          PlatformManager.instance.mixpanel.track('App Opened From DeepLink', properties: {'appId': app.id});
          if (mounted) {
            Navigator.of(context).push(MaterialPageRoute(builder: (context) => AppDetailPage(app: app)));
          }
        } else {
          debugPrint('App not found: ${uri.pathSegments[1]}');
          AppSnackbar.showSnackbarError('Oops! Looks like the app you are looking for is not available.');
        }
      }
    } else if (uri.host == 'todoist' && uri.pathSegments.isNotEmpty && uri.pathSegments.first == 'callback') {
      // Handle Todoist OAuth callback
      final code = uri.queryParameters['code'];
      if (code != null) {
        debugPrint('Received Todoist OAuth code: ${code.substring(0, 10)}...');
        _handleTodoistCallback(code);
      } else {
        debugPrint('Todoist callback received but no code found');
      }
    } else if (uri.host == 'asana' && uri.pathSegments.isNotEmpty && uri.pathSegments.first == 'callback') {
      // Handle Asana OAuth callback
      final code = uri.queryParameters['code'];
      if (code != null) {
        debugPrint('Received Asana OAuth code: ${code.substring(0, 10)}...');
        _handleAsanaCallback(code);
      } else {
        debugPrint('Asana callback received but no code found');
      }
    } else if (uri.host == 'google-tasks' && uri.pathSegments.isNotEmpty && uri.pathSegments.first == 'callback') {
      // Handle Google Tasks OAuth callback
      final code = uri.queryParameters['code'];
      if (code != null) {
        debugPrint('Received Google Tasks OAuth code: ${code.substring(0, 10)}...');
        _handleGoogleTasksCallback(code);
      } else {
        debugPrint('Google Tasks callback received but no code found');
      }
    } else {
      debugPrint('Unknown link: $uri');
    }
  }

  Future<void> _handleTodoistCallback(String code) async {
    final todoistService = TodoistService();
    final success = await todoistService.handleCallback(code);

    if (!mounted) return;

    if (success) {
      debugPrint('✓ Todoist authentication completed successfully');
      debugPrint('✓ Task integration enabled: Todoist - authentication complete');
      AppSnackbar.showSnackbar('Successfully connected to Todoist!');

      // Notify task integration provider to refresh UI
      context.read<TaskIntegrationProvider>().refresh();
    } else {
      debugPrint('Failed to complete Todoist authentication');
      AppSnackbar.showSnackbarError('Failed to connect to Todoist. Please try again.');
    }
  }

  Future<void> _handleAsanaCallback(String code) async {
    final asanaService = AsanaService();
    final success = await asanaService.handleCallback(code);

    if (!mounted) return;

    if (success) {
      debugPrint('✓ Asana authentication completed successfully');
      debugPrint('✓ Task integration enabled: Asana - authentication complete');
      AppSnackbar.showSnackbar('Successfully connected to Asana!');

      // Notify task integration provider to refresh UI
      context.read<TaskIntegrationProvider>().refresh();
    } else {
      debugPrint('Failed to complete Asana authentication');
      AppSnackbar.showSnackbarError('Failed to connect to Asana. Please try again.');
    }
  }

  Future<void> _handleGoogleTasksCallback(String code) async {
    final googleTasksService = GoogleTasksService();
    final success = await googleTasksService.handleCallback(code);

    if (!mounted) return;

    if (success) {
      debugPrint('✓ Google Tasks authentication completed successfully');
      debugPrint('✓ Task integration enabled: Google Tasks - authentication complete');
      AppSnackbar.showSnackbar('Successfully connected to Google Tasks!');

      // Notify task integration provider to refresh UI
      context.read<TaskIntegrationProvider>().refresh();
    } else {
      debugPrint('Failed to complete Google Tasks authentication');
      AppSnackbar.showSnackbarError('Failed to connect to Google Tasks. Please try again.');
    }
  }

  @override
  void initState() {
    initDeepLinks();

    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (context.read<AuthenticationProvider>().isSignedIn()) {
        context.read<HomeProvider>().setupHasSpeakerProfile();
        context.read<HomeProvider>().setupUserPrimaryLanguage();
        context.read<UserProvider>().initialize();
        context.read<PeopleProvider>().initialize();
        try {
          await PlatformManager.instance.intercom.loginIdentifiedUser(SharedPreferencesUtil().uid);
        } catch (e) {
          debugPrint('Failed to login to Intercom: $e');
        }

        context.read<MessageProvider>().setMessagesFromCache();
        context.read<AppProvider>().setAppsFromCache();
        context.read<MessageProvider>().refreshMessages();
        context.read<UsageProvider>().fetchSubscription();

        NotificationService.instance.saveNotificationToken();
      } else {
        if (!PlatformManager.instance.isAnalyticsSupported) {
          await PlatformManager.instance.intercom.loginUnidentifiedUser();
        }
      }
      PlatformManager.instance.intercom.setUserAttributes();
    });
    super.initState();
  }

  @override
  void dispose() {
    _linkSubscription?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        // Route to appropriate app tree based on screen width
        if (constraints.maxWidth >= 1100) {
          return const DesktopApp(); // Desktop app tree
        } else {
          return const MobileApp(); // Mobile app tree
        }
      },
    );
  }
}
