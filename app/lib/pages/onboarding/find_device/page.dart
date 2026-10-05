import 'dart:async';

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';

import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/services/devices/bluetooth_readiness.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/connection_guide_sheet.dart';
import 'found_devices.dart';

class FindDevicesPage extends StatefulWidget {
  final bool isFromOnboarding;
  final VoidCallback goNext;
  final VoidCallback? onSkip;
  final bool includeSkip;

  const FindDevicesPage({
    super.key,
    required this.goNext,
    this.includeSkip = true,
    this.isFromOnboarding = false,
    this.onSkip,
  });

  @override
  State<FindDevicesPage> createState() => _FindDevicesPageState();
}

class _FindDevicesPageState extends State<FindDevicesPage> {
  OnboardingProvider? _provider;

  @override
  void initState() {
    super.initState();
    _provider = Provider.of<OnboardingProvider>(context, listen: false);

    SchedulerBinding.instance.addPostFrameCallback((_) {
      if (widget.isFromOnboarding) {
        context.read<HomeProvider>().setupHasSpeakerProfile();
      }
      _scanDevices();
    });
  }

  @override
  dispose() {
    _provider?.cancelActiveScan();
    _provider = null;

    super.dispose();
  }

  /// A missing Bluetooth (or, on Android 11 and older, location) permission goes through the one
  /// global recovery prompt, [BluetoothGuidanceListener]: "Permissions required" with Open
  /// Settings. This page never draws its own Bluetooth dialog (onboarding-home #12).
  Future<void> _scanDevices() async {
    void publishGuidance() {
      if (mounted) unawaited(BluetoothReadiness.instance.ensureReady(BluetoothUse.discovery));
    }

    await _provider?.scanDevices(onShowDialog: publishGuidance, onShowLocationDialog: publishGuidance);
  }

  Future<void> _scanAgain() async {
    OmiHaptics.selection();
    _provider?.cancelActiveScan();
    _provider?.enableInstructions = false;
    setState(() {});
    await _scanDevices();
  }

  void _showConnectionGuide() {
    PlatformManager.instance.analytics.connectionGuideOpened();
    ConnectionGuideSheet.show(context);
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<OnboardingProvider>(
      builder: (context, provider, child) {
        final cantFind = provider.deviceList.isEmpty && provider.enableInstructions;
        final notNow = widget.includeSkip
            ? OmiButton.tertiary(
                key: const Key('find_devices_not_now'),
                label: context.l10n.notNow,
                onPressed: () {
                  if (widget.isFromOnboarding) {
                    widget.onSkip!();
                  } else {
                    widget.goNext();
                  }
                  PlatformManager.instance.analytics.useWithoutDeviceOnboardingFindDevices();
                },
              )
            : null;
        return Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            // Stays mounted: it owns the connection listener. Once the scan has ended with nothing
            // found it draws nothing, so "Searching for devices" does not sit above "No Omi Found".
            FoundDevices(
              goNext: widget.goNext,
              isFromOnboarding: widget.isFromOnboarding,
              onRescan: _scanAgain,
              showStatus: !cantFind,
            ),
            // Nothing found after a while: troubleshooting first, support last (onboarding-home #13).
            // The pairing guide has no support route, so Contact Support stays as a small link.
            if (cantFind)
              OmiEmptyState(
                key: const Key('find_devices_none'),
                glyph: Assets.images.omiWithoutRopeTurnedOff.image(width: 112, height: 112),
                title: context.l10n.findDeviceNoneTitle,
                message: context.l10n.findDeviceNoneMessage,
                action: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    OmiButton(
                      key: const Key('find_devices_scan_again'),
                      label: context.l10n.scanAgain,
                      icon: Icons.refresh,
                      onPressed: _scanAgain,
                    ),
                    const SizedBox(height: OmiSpacing.xs),
                    OmiButton.secondary(
                      key: const Key('find_devices_how_to_pair'),
                      label: context.l10n.howToPair,
                      onPressed: _showConnectionGuide,
                    ),
                    if (notNow != null) notNow,
                    Center(
                      child: TextButton(
                        key: const Key('find_devices_contact_support'),
                        onPressed: () => launchUrl(Uri.parse('mailto:team@basedhardware.com')),
                        style: TextButton.styleFrom(
                          foregroundColor: OmiColors.textSecondary,
                          minimumSize: const Size(kOmiMinTapTarget, kOmiMinTapTarget),
                          textStyle: OmiType.footnote,
                        ),
                        child: Text(context.l10n.contactSupportAction),
                      ),
                    ),
                  ],
                ),
              )
            else if (notNow != null)
              notNow,
          ],
        );
      },
    );
  }
}
