import 'dart:async';
import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:omi/mobile/mobile_app.dart';
import 'package:omi/desktop/desktop_app.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/settings/asana_settings_page.dart';
import 'package:omi/pages/settings/clickup_settings_page.dart';
import 'package:omi/pages/settings/github_settings_page.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/asana_service.dart';
import 'package:omi/services/clickup_service.dart';
import 'package:omi/services/google_tasks_service.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/services/todoist_service.dart';
import 'package:omi/providers/integration_provider.dart';
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
      final error = uri.queryParameters['error'];
      if (error != null) {
        debugPrint('Todoist OAuth error: $error');
        AppSnackbar.showSnackbarError('Failed to connect to Todoist');
        return;
      }

      final success = uri.queryParameters['success'];
      if (success == 'true') {
        debugPrint('Todoist OAuth successful (tokens in Firebase)');
        _handleTodoistCallback();
      } else {
        debugPrint('Todoist callback received but no success flag');
      }
    } else if (uri.host == 'asana' && uri.pathSegments.isNotEmpty && uri.pathSegments.first == 'callback') {
      // Handle Asana OAuth callback
      final error = uri.queryParameters['error'];
      if (error != null) {
        debugPrint('Asana OAuth error: $error');
        AppSnackbar.showSnackbarError('Failed to connect to Asana');
        return;
      }

      final success = uri.queryParameters['success'];
      final requiresSetup = uri.queryParameters['requires_setup'];
      if (success == 'true') {
        debugPrint('Asana OAuth successful (tokens in Firebase)');
        _handleAsanaCallback(requiresSetup == 'true');
      } else {
        debugPrint('Asana callback received but no success flag');
      }
    } else if (uri.host == 'google-tasks' && uri.pathSegments.isNotEmpty && uri.pathSegments.first == 'callback') {
      // Handle Google Tasks OAuth callback
      final error = uri.queryParameters['error'];
      if (error != null) {
        debugPrint('Google Tasks OAuth error: $error');
        AppSnackbar.showSnackbarError('Failed to connect to Google Tasks');
        return;
      }

      final success = uri.queryParameters['success'];
      if (success == 'true') {
        debugPrint('Google Tasks OAuth successful (tokens in Firebase)');
        _handleGoogleTasksCallback();
      } else {
        debugPrint('Google Tasks callback received but no success flag');
      }
    } else if (uri.host == 'clickup' && uri.pathSegments.isNotEmpty && uri.pathSegments.first == 'callback') {
      // Handle ClickUp OAuth callback
      final error = uri.queryParameters['error'];
      if (error != null) {
        debugPrint('ClickUp OAuth error: $error');
        AppSnackbar.showSnackbarError('Failed to connect to ClickUp');
        return;
      }

      final success = uri.queryParameters['success'];
      final requiresSetup = uri.queryParameters['requires_setup'];
      if (success == 'true') {
        debugPrint('ClickUp OAuth successful (tokens in Firebase)');
        _handleClickUpCallback(requiresSetup == 'true');
      } else {
        debugPrint('ClickUp callback received but no success flag');
      }
    } else if (uri.host == 'notion' && uri.pathSegments.isNotEmpty && uri.pathSegments.first == 'callback') {
      await _handleOAuthCallback(uri, 'Notion', 'Notion', _handleNotionCallback);
    } else if (uri.host == 'google_calendar' && uri.pathSegments.isNotEmpty && uri.pathSegments.first == 'callback') {
      await _handleOAuthCallback(uri, 'Google', 'Google Calendar', _handleGoogleCalendarCallback);
    } else if (uri.host == 'whoop' && uri.pathSegments.isNotEmpty && uri.pathSegments.first == 'callback') {
      await _handleOAuthCallback(uri, 'Whoop', 'Whoop', _handleWhoopCallback);
    } else if (uri.host == 'github' && uri.pathSegments.isNotEmpty && uri.pathSegments.first == 'callback') {
      await _handleOAuthCallback(uri, 'GitHub', 'GitHub', _handleGitHubCallback);
    } else {
      debugPrint('Unknown link: $uri');
    }
  }

  Future<void> _handleOAuthCallback(
      Uri uri, String errorDisplayName, String oauthLogName, Future<void> Function() onSuccess) async {
    final error = uri.queryParameters['error'];
    if (error != null) {
      debugPrint('$oauthLogName OAuth error: $error');
      AppSnackbar.showSnackbarError('Failed to connect to $errorDisplayName: $error');
      return;
    }

    final success = uri.queryParameters['success'];
    if (success == 'true') {
      debugPrint('$oauthLogName OAuth successful (tokens in Firebase)');
      await onSuccess();
    } else {
      debugPrint('$oauthLogName callback received but no success flag');
    }
  }

  Future<void> _handleTodoistCallback() async {
    final todoistService = TodoistService();
    final success = await todoistService.handleCallback();

    if (!mounted) return;

    if (success) {
      debugPrint('✓ Todoist authentication completed successfully');
      debugPrint('✓ Task integration enabled: Todoist - authentication complete');
      AppSnackbar.showSnackbar('Successfully connected to Todoist!');

      // Notify task integration provider to refresh UI from Firebase
      context.read<TaskIntegrationProvider>().refresh();
    } else {
      debugPrint('Failed to complete Todoist authentication');
      AppSnackbar.showSnackbarError('Failed to connect to Todoist. Please try again.');
    }
  }

  Future<void> _handleAsanaCallback(bool requiresSetup) async {
    final asanaService = AsanaService();
    final success = await asanaService.handleCallback();

    if (!mounted) return;

    if (success) {
      debugPrint('✓ Asana authentication completed successfully');
      debugPrint('✓ Task integration enabled: Asana - authentication complete');
      AppSnackbar.showSnackbar('Successfully connected to Asana!');

      // Notify task integration provider to refresh UI from Firebase
      context.read<TaskIntegrationProvider>().refresh();

      // Auto-open settings page for configuration
      if (requiresSetup && mounted) {
        Navigator.of(context).push(MaterialPageRoute(builder: (context) => const AsanaSettingsPage()));
      }
    } else {
      debugPrint('Failed to complete Asana authentication');
      AppSnackbar.showSnackbarError('Failed to connect to Asana. Please try again.');
    }
  }

  Future<void> _handleGoogleTasksCallback() async {
    final googleTasksService = GoogleTasksService();
    final success = await googleTasksService.handleCallback();

    if (!mounted) return;

    if (success) {
      debugPrint('✓ Google Tasks authentication completed successfully');
      debugPrint('✓ Task integration enabled: Google Tasks - authentication complete');
      AppSnackbar.showSnackbar('Successfully connected to Google Tasks!');

      // Notify task integration provider to refresh UI from Firebase
      context.read<TaskIntegrationProvider>().refresh();
    } else {
      debugPrint('Failed to complete Google Tasks authentication');
      AppSnackbar.showSnackbarError('Failed to connect to Google Tasks. Please try again.');
    }
  }

  Future<void> _handleClickUpCallback(bool requiresSetup) async {
    final clickupService = ClickUpService();
    final success = await clickupService.handleCallback();

    if (!mounted) return;

    if (success) {
      debugPrint('✓ ClickUp authentication completed successfully');
      debugPrint('✓ Task integration enabled: ClickUp - authentication complete');
      AppSnackbar.showSnackbar('Successfully connected to ClickUp!');

      // Notify task integration provider to refresh UI from Firebase
      context.read<TaskIntegrationProvider>().refresh();

      // Auto-open settings page for configuration
      if (requiresSetup && mounted) {
        Navigator.of(context).push(MaterialPageRoute(builder: (context) => const ClickUpSettingsPage()));
      }
    } else {
      debugPrint('Failed to complete ClickUp authentication');
      AppSnackbar.showSnackbarError('Failed to connect to ClickUp. Please try again.');
    }
  }

  Future<void> _handleNotionCallback() async {
    if (!mounted) return;

    try {
      // Capture provider before async operation to avoid use_build_context_synchronously
      final integrationProvider = context.read<IntegrationProvider>();

      // IntegrationProvider.loadFromBackend() fetches all connection statuses
      // and syncs SharedPreferences for backward compatibility
      await integrationProvider.loadFromBackend();

      if (!mounted) return;
      debugPrint('✓ Notion authentication completed successfully');
      AppSnackbar.showSnackbar('Successfully connected to Notion!');
    } catch (e) {
      debugPrint('Error handling Notion callback: $e');
      if (mounted) {
        AppSnackbar.showSnackbarError('Failed to refresh Notion connection status.');
      }
    }
  }

  Future<void> _handleGoogleCalendarCallback() async {
    if (!mounted) return;

    try {
      // Capture provider before async operation to avoid use_build_context_synchronously
      final integrationProvider = context.read<IntegrationProvider>();

      // IntegrationProvider.loadFromBackend() fetches all connection statuses
      // and syncs SharedPreferences for backward compatibility
      await integrationProvider.loadFromBackend();

      if (!mounted) return;
      debugPrint('✓ Google authentication completed successfully');
      AppSnackbar.showSnackbar('Successfully connected to Google!');
    } catch (e) {
      debugPrint('Error handling Google Calendar callback: $e');
      if (mounted) {
        AppSnackbar.showSnackbarError('Failed to refresh Google connection status.');
      }
    }
  }

  Future<void> _handleWhoopCallback() async {
    if (!mounted) return;

    try {
      // Capture provider before async operation to avoid use_build_context_synchronously
      final integrationProvider = context.read<IntegrationProvider>();

      // IntegrationProvider.loadFromBackend() fetches all connection statuses
      // and syncs SharedPreferences for backward compatibility
      await integrationProvider.loadFromBackend();

      if (!mounted) return;
      debugPrint('✓ Whoop authentication completed successfully');
      AppSnackbar.showSnackbar('Successfully connected to Whoop!');
    } catch (e) {
      debugPrint('Error handling Whoop callback: $e');
      if (mounted) {
        AppSnackbar.showSnackbarError('Failed to refresh Whoop connection status.');
      }
    }
  }

  Future<void> _handleGitHubCallback() async {
    if (!mounted) return;

    try {
      // Capture provider before async operation to avoid use_build_context_synchronously
      final integrationProvider = context.read<IntegrationProvider>();

      // IntegrationProvider.loadFromBackend() fetches all connection statuses
      // and syncs SharedPreferences for backward compatibility
      await integrationProvider.loadFromBackend();

      if (!mounted) return;
      debugPrint('✓ GitHub authentication completed successfully');
      AppSnackbar.showSnackbar('Successfully connected to GitHub!');

      // Open GitHub settings page to select default repository
      if (mounted) {
        await Future.delayed(const Duration(milliseconds: 500)); // Small delay for UI
        if (mounted) {
          Navigator.of(context).push(
            MaterialPageRoute(
              builder: (context) => const GitHubSettingsPage(),
            ),
          );
        }
      }
    } catch (e) {
      debugPrint('Error handling GitHub callback: $e');
      if (mounted) {
        AppSnackbar.showSnackbarError('Failed to refresh GitHub connection status.');
      }
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
        context.read<TaskIntegrationProvider>().loadFromBackend();

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
