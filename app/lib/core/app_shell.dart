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
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/notifications.dart';
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
    } else {
      debugPrint('Unknown link: $uri');
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
        // TODO: Create a cache for chat sessions
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
