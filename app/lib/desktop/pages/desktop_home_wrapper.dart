import 'package:flutter/material.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:provider/provider.dart';
import 'desktop_home_page.dart';

/// Desktop home wrapper - handles initialization same as mobile but with desktop UI
class DesktopHomePageWrapper extends StatefulWidget {
  final String? navigateToRoute;
  const DesktopHomePageWrapper({super.key, this.navigateToRoute});

  @override
  State<DesktopHomePageWrapper> createState() => _DesktopHomePageWrapperState();
}

class _DesktopHomePageWrapperState extends State<DesktopHomePageWrapper> {
  String? _navigateToRoute;

  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      // Same initialization logic as mobile
      // if (SharedPreferencesUtil().notificationsEnabled != await Permission.notification.isGranted) {
      //   SharedPreferencesUtil().notificationsEnabled = await Permission.notification.isGranted;
      //   AnalyticsManager().setUserAttribute('Notifications Enabled', SharedPreferencesUtil().notificationsEnabled);
      // }
      // if (SharedPreferencesUtil().notificationsEnabled) {
      //   NotificationService.instance.register();
      // }
      // if (SharedPreferencesUtil().locationEnabled != await Permission.location.isGranted) {
      //   SharedPreferencesUtil().locationEnabled = await Permission.location.isGranted;
      //   AnalyticsManager().setUserAttribute('Location Enabled', SharedPreferencesUtil().locationEnabled);
      // }
      if (mounted) {
        context.read<DeviceProvider>().periodicConnect('coming from DesktopHomePageWrapper');
      }
      if (mounted) {
        await context.read<ConversationProvider>().getInitialConversations();
      }
    });
    _navigateToRoute = widget.navigateToRoute;
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return DesktopHomePage(navigateToRoute: _navigateToRoute);
  }
}
