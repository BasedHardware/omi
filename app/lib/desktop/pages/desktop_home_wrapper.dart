import 'package:flutter/material.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:provider/provider.dart';
import 'desktop_home_page.dart';

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
