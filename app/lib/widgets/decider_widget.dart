import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/pages/onboarding/device_selection.dart';
import 'package:omi/pages/onboarding/wrapper.dart';
import 'package:omi/pages/persona/persona_profile.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/platform_check.dart';
import 'package:provider/provider.dart';

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
    if (!ExecutionGuard.isWeb) {
      initDeepLinks();
    }
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (context.read<ConnectivityProvider>().isConnected) {
        NotificationService.instance.saveNotificationToken();
      }

      if (context.read<AuthenticationProvider>().isSignedIn()) {
        context.read<HomeProvider>().setupHasSpeakerProfile();
        context.read<MessageProvider>().setMessagesFromCache();
        context.read<AppProvider>().setAppsFromCache();
        context.read<MessageProvider>().refreshMessages();
      }

      if (!ExecutionGuard.isWeb) {
        try {
          if (context.read<AuthenticationProvider>().isSignedIn()) {
            await IntercomManager.instance.intercom.loginIdentifiedUser(
              userId: SharedPreferencesUtil().uid,
            );
          } else {
            await IntercomManager.instance.intercom.loginUnidentifiedUser();
            IntercomManager.instance.setUserAttributes();
          }
        } catch (e) {
          debugPrint('Failed to login to Intercom: $e');
        }
      }
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

