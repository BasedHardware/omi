import 'dart:async';

import 'package:flutter/material.dart';

import 'package:app_links/app_links.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/action_items.dart' as action_items_api;
import 'package:omi/backend/preferences.dart';
import 'package:omi/desktop/desktop_app.dart';
import 'package:omi/mobile/mobile_app.dart';
import 'package:omi/pages/action_items/widgets/accept_shared_tasks_sheet.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/settings/asana_settings_page.dart';
import 'package:omi/pages/settings/clickup_settings_page.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/pages/settings/wrapped_2025_page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/integration_provider.dart';
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
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
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

    // Handle initial link (cold start — app launched by deep link)
    final initialUri = await _appLinks.getInitialLink();
    if (initialUri != null) {
      Logger.debug('onInitialAppLink: $initialUri');
      openAppLink(initialUri);
    }

    // Handle subsequent links (warm start — app already running)
    _linkSubscription = _appLinks.uriLinkStream.distinct().listen((uri) {
      Logger.debug('onAppLink: $uri');
      openAppLink(uri);
    });
  }

  void openAppLink(Uri uri) async {
    if (uri.pathSegments.isEmpty) {
      Logger.debug('No path segments in URI: $uri');
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
          Logger.debug('App not found: ${uri.pathSegments[1]}');
          AppSnackbar.showSnackbarError(context.l10n.appNotAvailable);
        }
      }
    } else if (uri.pathSegments.first == 'wrapped') {
      if (mounted) {
        PlatformManager.instance.mixpanel.track('Wrapped Opened From DeepLink');
        Navigator.of(context).push(MaterialPageRoute(builder: (context) => const Wrapped2025Page()));
      }
    } else if (uri.pathSegments.first == 'tasks' && uri.pathSegments.length > 1) {
      if (mounted) {
        final token = uri.pathSegments[1];
        PlatformManager.instance.mixpanel.track('Shared Tasks Opened From DeepLink', properties: {'token': token});
        _handleSharedTasksDeepLink(token);
      }
    } else if (uri.pathSegments.first == 'unlimited') {
      if (mounted) {
        PlatformManager.instance.mixpanel.track('Plans Opened From DeepLink');
        Navigator.of(context).push(MaterialPageRoute(builder: (context) => const UsagePage(showUpgradeDialog: true)));
      }
    } else if (uri.host == 'todoist' && uri.pathSegments.isNotEmpty && uri.pathSegments.first == 'callback') {
      // Handle Todoist OAuth callback
      final error = uri.queryParameters['error'];
      if (error != null) {
        Logger.debug('Todoist OAuth error: $error');
        AppSnackbar.showSnackbarError(context.l10n.failedToConnectTodoist);
        return;
      }

      final success = uri.queryParameters['success'];
      if (success == 'true') {
        Logger.debug('Todoist OAuth successful (tokens in Firebase)');
        _handleTodoistCallback();
      } else {
        Logger.debug('Todoist callback received but no success flag');
      }
    } else if (uri.host == 'asana' && uri.pathSegments.isNotEmpty && uri.pathSegments.first == 'callback') {
      // Handle Asana OAuth callback
      final error = uri.queryParameters['error'];
      if (error != null) {
        Logger.debug('Asana OAuth error: $error');
        AppSnackbar.showSnackbarError(context.l10n.failedToConnectAsana);
        return;
      }

      final success = uri.queryParameters['success'];
      final requiresSetup = uri.queryParameters['requires_setup'];
      if (success == 'true') {
        Logger.debug('Asana OAuth successful (tokens in Firebase)');
        _handleAsanaCallback(requiresSetup == 'true');
      } else {
        Logger.debug('Asana callback received but no success flag');
      }
    } else if (uri.host == 'google-tasks' && uri.pathSegments.isNotEmpty && uri.pathSegments.first == 'callback') {
      // Handle Google Tasks OAuth callback
      final error = uri.queryParameters['error'];
      if (error != null) {
        Logger.debug('Google Tasks OAuth error: $error');
        AppSnackbar.showSnackbarError(context.l10n.failedToConnectGoogleTasks);
        return;
      }

      final success = uri.queryParameters['success'];
      if (success == 'true') {
        Logger.debug('Google Tasks OAuth successful (tokens in Firebase)');
        _handleGoogleTasksCallback();
      } else {
        Logger.debug('Google Tasks callback received but no success flag');
      }
    } else if (uri.host == 'clickup' && uri.pathSegments.isNotEmpty && uri.pathSegments.first == 'callback') {
      // Handle ClickUp OAuth callback
      final error = uri.queryParameters['error'];
      if (error != null) {
        Logger.debug('ClickUp OAuth error: $error');
        AppSnackbar.showSnackbarError(context.l10n.failedToConnectClickUp);
        return;
      }

      final success = uri.queryParameters['success'];
      final requiresSetup = uri.queryParameters['requires_setup'];
      if (success == 'true') {
        Logger.debug('ClickUp OAuth successful (tokens in Firebase)');
        _handleClickUpCallback(requiresSetup == 'true');
      } else {
        Logger.debug('ClickUp callback received but no success flag');
      }
    } else if (uri.host == 'google_calendar' && uri.pathSegments.isNotEmpty && uri.pathSegments.first == 'callback') {
      await _handleOAuthCallback(uri, 'Google', 'Google Calendar', _handleGoogleCalendarCallback);
    } else {
      Logger.debug('Unknown link: $uri');
    }
  }

  Future<void> _handleOAuthCallback(
    Uri uri,
    String errorDisplayName,
    String oauthLogName,
    Future<void> Function() onSuccess,
  ) async {
    final error = uri.queryParameters['error'];
    if (error != null) {
      Logger.debug('$oauthLogName OAuth error: $error');
      AppSnackbar.showSnackbarError(context.l10n.failedToConnectServiceWithError(errorDisplayName, error));
      return;
    }

    final success = uri.queryParameters['success'];
    if (success == 'true') {
      Logger.debug('$oauthLogName OAuth successful (tokens in Firebase)');
      await onSuccess();
    } else {
      Logger.debug('$oauthLogName callback received but no success flag');
    }
  }

  Future<void> _handleSharedTasksDeepLink(String token) async {
    final data = await action_items_api.getSharedActionItems(token);
    if (!mounted) return;

    if (data == null) {
      AppSnackbar.showSnackbarError('Shared tasks not found or link expired');
      return;
    }

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => AcceptSharedTasksSheet(
        token: token,
        senderName: data['sender_name'] ?? 'Someone',
        tasks: (data['tasks'] as List<dynamic>? ?? [])
            .map((t) => {'description': t['description'] ?? '', 'due_at': t['due_at']})
            .toList(),
        onAccepted: () {
          // Refresh action items after accepting
          if (mounted) {
            context.read<ActionItemsProvider>().forceRefreshActionItems();
          }
        },
      ),
    );
  }

  Future<void> _handleTodoistCallback() async {
    final todoistService = TodoistService();
    final success = await todoistService.handleCallback();

    if (!mounted) return;

    if (success) {
      Logger.debug('✓ Todoist authentication completed successfully');
      Logger.debug('✓ Task integration enabled: Todoist - authentication complete');
      AppSnackbar.showSnackbar(context.l10n.successfullyConnectedTodoist);

      // Notify task integration provider to refresh UI from Firebase
      context.read<TaskIntegrationProvider>().refresh();
    } else {
      Logger.debug('Failed to complete Todoist authentication');
      AppSnackbar.showSnackbarError(context.l10n.failedToConnectTodoistRetry);
    }
  }

  Future<void> _handleAsanaCallback(bool requiresSetup) async {
    final asanaService = AsanaService();
    final success = await asanaService.handleCallback();

    if (!mounted) return;

    if (success) {
      Logger.debug('✓ Asana authentication completed successfully');
      Logger.debug('✓ Task integration enabled: Asana - authentication complete');
      AppSnackbar.showSnackbar(context.l10n.successfullyConnectedAsana);

      // Notify task integration provider to refresh UI from Firebase
      context.read<TaskIntegrationProvider>().refresh();

      // Auto-open settings page for configuration
      if (requiresSetup && mounted) {
        Navigator.of(context).push(MaterialPageRoute(builder: (context) => const AsanaSettingsPage()));
      }
    } else {
      Logger.debug('Failed to complete Asana authentication');
      AppSnackbar.showSnackbarError(context.l10n.failedToConnectAsanaRetry);
    }
  }

  Future<void> _handleGoogleTasksCallback() async {
    final googleTasksService = GoogleTasksService();
    final success = await googleTasksService.handleCallback();

    if (!mounted) return;

    if (success) {
      Logger.debug('✓ Google Tasks authentication completed successfully');
      Logger.debug('✓ Task integration enabled: Google Tasks - authentication complete');
      AppSnackbar.showSnackbar(context.l10n.successfullyConnectedGoogleTasks);

      // Notify task integration provider to refresh UI from Firebase
      context.read<TaskIntegrationProvider>().refresh();
    } else {
      Logger.debug('Failed to complete Google Tasks authentication');
      AppSnackbar.showSnackbarError(context.l10n.failedToConnectGoogleTasksRetry);
    }
  }

  Future<void> _handleClickUpCallback(bool requiresSetup) async {
    final clickupService = ClickUpService();
    final success = await clickupService.handleCallback();

    if (!mounted) return;

    if (success) {
      Logger.debug('✓ ClickUp authentication completed successfully');
      Logger.debug('✓ Task integration enabled: ClickUp - authentication complete');
      AppSnackbar.showSnackbar(context.l10n.successfullyConnectedClickUp);

      // Notify task integration provider to refresh UI from Firebase
      context.read<TaskIntegrationProvider>().refresh();

      // Auto-open settings page for configuration
      if (requiresSetup && mounted) {
        Navigator.of(context).push(MaterialPageRoute(builder: (context) => const ClickUpSettingsPage()));
      }
    } else {
      Logger.debug('Failed to complete ClickUp authentication');
      AppSnackbar.showSnackbarError(context.l10n.failedToConnectClickUpRetry);
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
      Logger.debug('✓ Google authentication completed successfully');
      AppSnackbar.showSnackbar(context.l10n.successfullyConnectedGoogle);
    } catch (e) {
      Logger.debug('Error handling Google Calendar callback: $e');
      if (mounted) {
        AppSnackbar.showSnackbarError(context.l10n.failedToRefreshGoogleStatus);
      }
    }
  }

  @override
  void initState() {
    super.initState();
    initDeepLinks();
    WidgetsBinding.instance.addPostFrameCallback((_) => _initializeProviders());
  }

  Future<void> _initializeProviders() async {
    if (!mounted) return;
    final isSignedIn = context.read<AuthenticationProvider>().isSignedIn();
    if (isSignedIn) {
      context.read<HomeProvider>().setupHasSpeakerProfile();
      context.read<HomeProvider>().setupUserPrimaryLanguage();
      context.read<UserProvider>().initialize();
      context.read<PeopleProvider>().initialize();
      try {
        await PlatformManager.instance.intercom.loginIdentifiedUser(SharedPreferencesUtil().uid);
      } catch (e) {
        Logger.debug('Failed to login to Intercom: $e');
      }

      if (!mounted) return;
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
      if (!mounted) return;
    }
    PlatformManager.instance.intercom.setUserAttributes();
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
