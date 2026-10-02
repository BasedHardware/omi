import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/pages/home/home_navigation.dart';
import 'package:omi/pages/onboarding/find_device/page.dart';
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/connection_guide_sheet.dart';
import 'package:omi/widgets/device_widget.dart';
import 'package:omi/widgets/scanning_ripple.dart';

final _omiStoreUrl = Uri.parse('https://www.omi.me/?_ref=omi_connect_device');

Future<void> openOmiStore({Future<bool> Function(Uri)? launcher}) async {
  PlatformManager.instance.analytics.getOmiDeviceClicked();
  await (launcher ?? (url) => launchUrl(url, mode: LaunchMode.externalApplication))(_omiStoreUrl);
}

class ConnectDevicePage extends StatefulWidget {
  const ConnectDevicePage({super.key});

  @override
  State<ConnectDevicePage> createState() => _ConnectDevicePageState();
}

class _ConnectDevicePageState extends State<ConnectDevicePage> {
  @override
  void initState() {
    super.initState();
    PlatformManager.instance.analytics.connectDevicePageOpened();
  }

  void _showConnectionGuide() {
    PlatformManager.instance.analytics.connectionGuideOpened();
    ConnectionGuideSheet.show(context);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: OmiColors.surface0,
      appBar: AppBar(
        leading: const OmiBackButton(),
        title: Text(context.l10n.connect),
        actions: [
          OmiIconButton.filled(
            icon: const FaIcon(FontAwesomeIcons.gear, size: 16),
            label: context.l10n.deviceSettings,
            onPressed: () => routeToPage(context, const DeviceSettings()),
          ),
          const SizedBox(width: OmiSpacing.xxs),
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
                  // Back to the Home already underneath, not a second Home on top of it.
                  HomeNavigation.returnHome(context);
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
            padding: EdgeInsets.only(bottom: MediaQuery.of(context).padding.bottom + OmiSpacing.md, top: OmiSpacing.sm),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                OmiButton.tertiary(
                  key: const Key('get_omi_device_button'),
                  label: context.l10n.getOmiDevice,
                  onPressed: openOmiStore,
                ),
                OmiButton.tertiary(
                  key: const Key('connection_guide_button'),
                  label: context.l10n.connectionGuide,
                  icon: Icons.info_outline,
                  size: OmiButtonSize.compact,
                  onPressed: _showConnectionGuide,
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}
