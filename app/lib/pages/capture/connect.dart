import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/home/page.dart';
import 'package:omi/pages/onboarding/find_device/page.dart';
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/connection_guide_sheet.dart';
import 'package:omi/widgets/device_widget.dart';
import 'package:omi/widgets/scanning_ripple.dart';

class ConnectDevicePage extends StatefulWidget {
  const ConnectDevicePage({super.key});

  @override
  State<ConnectDevicePage> createState() => _ConnectDevicePageState();
}

class _ConnectDevicePageState extends State<ConnectDevicePage> {
  @override
  void initState() {
    super.initState();
    MixpanelManager().connectDevicePageOpened();
  }

  void _showConnectionGuide() {
    MixpanelManager().connectionGuideOpened();
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (_) => const ConnectionGuideSheet(),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0D0D0D),
      appBar: AppBar(
        backgroundColor: const Color(0xFF0D0D0D),
        elevation: 0,
        automaticallyImplyLeading: false,
        leading: Padding(
          padding: const EdgeInsets.only(left: 12),
          child: GestureDetector(
            onTap: () => Navigator.of(context).pop(),
            child: Container(
              width: 36,
              height: 36,
              decoration: const BoxDecoration(
                color: Color(0xFF1F1F25),
                shape: BoxShape.circle,
              ),
              child: const Icon(
                FontAwesomeIcons.chevronLeft,
                size: 16,
                color: Colors.white70,
              ),
            ),
          ),
        ),
        title: Text(
          context.l10n.connect,
          style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
        ),
        centerTitle: true,
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 8),
            child: Container(
              width: 36,
              height: 36,
              decoration: const BoxDecoration(
                color: Color(0xFF1F1F25),
                shape: BoxShape.circle,
              ),
              child: IconButton(
                padding: EdgeInsets.zero,
                icon: const Icon(
                  FontAwesomeIcons.gear,
                  size: 16,
                  color: Colors.white70,
                ),
                onPressed: () {
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (context) => const DeviceSettings(),
                    ),
                  );
                },
              ),
            ),
          ),
        ],
      ),
      body: Consumer<OnboardingProvider>(
        builder: (context, onboardingProvider, child) {
          return ListView(
            children: [
              const SizedBox(height: 16),
              Stack(
                alignment: Alignment.center,
                children: [
                  if (!onboardingProvider.isConnected)
                    ScanningRippleWidget(
                      isScanning: !onboardingProvider.isConnected,
                      size: MediaQuery.sizeOf(context).height <= 700 ? 280 : 360,
                    ),
                  DeviceAnimationWidget(
                    isConnected: onboardingProvider.isConnected,
                    deviceName: onboardingProvider.deviceName,
                    deviceType: onboardingProvider.deviceType,
                    animatedBackground: onboardingProvider.isConnected,
                  ),
                ],
              ),
              FindDevicesPage(
                isFromOnboarding: false,
                goNext: () {
                  Logger.debug('onConnected from FindDevicesPage');
                  routeToPage(context, const HomePageWrapper(), replace: true);
                },
                includeSkip: false,
              ),
            ],
          );
        },
      ),
      bottomNavigationBar: Consumer<OnboardingProvider>(
        builder: (context, onboardingProvider, child) {
          if (onboardingProvider.isConnected) return const SizedBox.shrink();
          return Padding(
            padding: EdgeInsets.only(bottom: MediaQuery.of(context).padding.bottom + 16, top: 12),
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: _showConnectionGuide,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.info_outline, color: Colors.grey.shade400, size: 16),
                  const SizedBox(width: 6),
                  Text(
                    context.l10n.connectionGuide,
                    style: TextStyle(
                      color: Colors.grey.shade400,
                      fontSize: 13,
                      fontWeight: FontWeight.w400,
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}
