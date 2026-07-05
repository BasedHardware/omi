import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/pages/meta_wearables/meta_glasses_page.dart';
import 'package:omi/pages/onboarding/find_device/page.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/providers/meta_wearables_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
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
  /// Multi-device: once the glasses are connected the BLE scanner collapses
  /// behind a "connect another device" button instead of stacking a Searching
  /// screen under the connected state.
  bool _connectAnotherDevice = false;

  @override
  void initState() {
    super.initState();
    PlatformManager.instance.analytics.connectDevicePageOpened();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) context.read<MetaWearablesProvider>().init();
    });
  }

  void _showConnectionGuide() {
    PlatformManager.instance.analytics.connectionGuideOpened();
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (_) => const ConnectionGuideSheet(),
    );
  }

  Widget _buildMetaGlassesConnectedCard(BuildContext context, MetaWearablesProvider metaProvider) {
    final name = metaProvider.selectedDevice?.name;
    return GestureDetector(
      onTap: () {
        Navigator.of(context).push(MaterialPageRoute(builder: (context) => const MetaGlassesPage()));
      },
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
        decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(18)),
        child: Row(
          children: [
            Padding(
              padding: const EdgeInsets.all(16.0),
              child: Image.asset(Assets.images.omiGlass.path, width: 32, height: 32),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 12.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      name != null && name.isNotEmpty ? name : context.l10n.metaGlasses,
                      style: const TextStyle(fontWeight: FontWeight.w500, fontSize: 18, color: Colors.black),
                    ),
                    Text(
                      context.l10n.connected,
                      style: const TextStyle(fontSize: 13, color: Colors.green, fontWeight: FontWeight.w500),
                    ),
                  ],
                ),
              ),
            ),
            const Padding(
              padding: EdgeInsets.only(right: 16.0),
              child: Icon(FontAwesomeIcons.chevronRight, size: 14, color: Colors.black45),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildMetaGlassesCard(BuildContext context) {
    return GestureDetector(
      onTap: () {
        Navigator.of(context).push(MaterialPageRoute(builder: (context) => const MetaGlassesPage()));
      },
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
        decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(18)),
        child: Row(
          children: [
            Padding(
              padding: const EdgeInsets.all(16.0),
              child: Image.asset(Assets.images.omiGlass.path, width: 32, height: 32),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 16.0),
                child: Text(
                  context.l10n.metaGlasses,
                  style: const TextStyle(fontWeight: FontWeight.w500, fontSize: 18, color: Colors.black),
                ),
              ),
            ),
            const Padding(
              padding: EdgeInsets.only(right: 16.0),
              child: Icon(FontAwesomeIcons.chevronRight, size: 14, color: Colors.black45),
            ),
          ],
        ),
      ),
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
              decoration: const BoxDecoration(color: Color(0xFF1F1F25), shape: BoxShape.circle),
              child: const Icon(FontAwesomeIcons.chevronLeft, size: 16, color: Colors.white70),
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
              decoration: const BoxDecoration(color: Color(0xFF1F1F25), shape: BoxShape.circle),
              child: IconButton(
                padding: EdgeInsets.zero,
                icon: const Icon(FontAwesomeIcons.gear, size: 16, color: Colors.white70),
                onPressed: () {
                  Navigator.of(context).push(MaterialPageRoute(builder: (context) => const DeviceSettings()));
                },
              ),
            ),
          ),
        ],
      ),
      body: Consumer2<OnboardingProvider, MetaWearablesProvider>(
        builder: (context, onboardingProvider, metaProvider, child) {
          final bleConnected = onboardingProvider.isConnected;
          final metaConnected = metaProvider.isRegistered && metaProvider.hasLinkedDevices;
          final anyConnected = bleConnected || metaConnected;
          final showScanner = !metaConnected || _connectAnotherDevice;
          return ListView(
            children: [
              const SizedBox(height: 16),
              Stack(
                alignment: Alignment.center,
                children: [
                  if (!anyConnected)
                    ScanningRippleWidget(
                      isScanning: !anyConnected,
                      size: MediaQuery.sizeOf(context).height <= 700 ? 280 : 360,
                    ),
                  DeviceAnimationWidget(
                    isConnected: anyConnected,
                    deviceName: bleConnected
                        ? onboardingProvider.deviceName
                        : (metaConnected
                            ? (metaProvider.selectedDevice?.name ?? context.l10n.metaGlasses)
                            : onboardingProvider.deviceName),
                    deviceType: bleConnected
                        ? onboardingProvider.deviceType
                        : (metaConnected ? DeviceType.metaWearables : onboardingProvider.deviceType),
                    animatedBackground: anyConnected,
                  ),
                ],
              ),
              if (metaConnected) _buildMetaGlassesConnectedCard(context, metaProvider),
              if (showScanner)
                FindDevicesPage(
                  isFromOnboarding: false,
                  goNext: () {
                    Logger.debug('onConnected from FindDevicesPage');
                    routeToPage(context, const HomePageWrapper(), replace: true);
                  },
                  includeSkip: false,
                )
              else
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
                  child: TextButton.icon(
                    onPressed: () => setState(() => _connectAnotherDevice = true),
                    icon: const Icon(Icons.add, size: 18, color: Colors.white70),
                    label: Text(
                      context.l10n.connectAnotherDevice,
                      style: const TextStyle(color: Colors.white70, fontSize: 15),
                    ),
                  ),
                ),
              if (!metaConnected) _buildMetaGlassesCard(context),
            ],
          );
        },
      ),
      bottomNavigationBar: Consumer2<OnboardingProvider, MetaWearablesProvider>(
        builder: (context, onboardingProvider, metaProvider, child) {
          // The guide follows the scanner: whenever the user is looking for a
          // device — including "connect another device" with glasses already
          // linked — the guide link stays available.
          final metaConnected = metaProvider.isRegistered && metaProvider.hasLinkedDevices;
          final scannerVisible = !metaConnected || _connectAnotherDevice;
          if (onboardingProvider.isConnected || !scannerVisible) {
            return const SizedBox.shrink();
          }
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
                    style: TextStyle(color: Colors.grey.shade400, fontSize: 13, fontWeight: FontWeight.w400),
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
