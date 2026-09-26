import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/pages/home/home_navigation.dart';
import 'package:omi/pages/onboarding/find_device/page.dart';
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/services/devices/bluetooth_readiness.dart';
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

/// Connect a wearable (Rev 3 Connect): the device with its live state, three steps — turn it on
/// and hold it close, allow Bluetooth, say something to test — and the devices found nearby.
///
/// With [onDone] (onboarding) the page stays after pairing so the live test can show real words;
/// Continue and Set up later both call [onDone]. Without it, pairing returns to where it was opened.
class ConnectDevicePage extends StatefulWidget {
  const ConnectDevicePage({super.key, this.onDone});

  final VoidCallback? onDone;

  @override
  State<ConnectDevicePage> createState() => _ConnectDevicePageState();
}

class _ConnectDevicePageState extends State<ConnectDevicePage> {
  @override
  void initState() {
    super.initState();
    PlatformManager.instance.analytics.connectDevicePageOpened();
  }

  /// What the connected device has heard so far this session (the live test's words).
  static String _heardWords(BuildContext context) {
    final capture = context.watch<CaptureProvider?>();
    if (capture == null) return '';
    return capture.segments.map((s) => s.text.trim()).where((t) => t.isNotEmpty).join(' ');
  }

  void _showConnectionGuide() {
    PlatformManager.instance.analytics.connectionGuideOpened();
    ConnectionGuideSheet.show(context);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: OmiColors.surface0,
      appBar: OmiAppBar(
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
      body: ListenableBuilder(
        // Bluetooth switched off or on from Control Center updates the steps at once.
        listenable: BluetoothReadiness.instance,
        builder: (context, _) => Consumer<OnboardingProvider>(
          builder: (context, onboardingProvider, child) {
            final bluetooth = BluetoothReadiness.instance.state;
            // Unknown until the first scan asks; a device already found or connected proves it is on.
            final bluetoothOn = bluetooth == BluetoothAdapterState.on ||
                (bluetooth == BluetoothAdapterState.unknown &&
                    (onboardingProvider.deviceList.isNotEmpty || onboardingProvider.isConnected));
            final connected = onboardingProvider.isConnected;
            return ListView(
              children: [
                const SizedBox(height: 8),
                Stack(
                  alignment: Alignment.center,
                  children: [
                    if (!connected)
                      ScanningRippleWidget(
                        isScanning: bluetoothOn,
                        size: MediaQuery.sizeOf(context).height <= 700 ? 220 : 280,
                      ),
                    // v2 Pairing: the Omi pendant is drawn (LED lit once connected); another kind of
                    // device keeps its photo.
                    if (onboardingProvider.deviceType == null || onboardingProvider.deviceType == DeviceType.omi)
                      OmiPendant(size: 130, lit: connected)
                    else
                      DeviceAnimationWidget(
                        isConnected: connected,
                        deviceName: onboardingProvider.deviceName,
                        deviceType: onboardingProvider.deviceType,
                        animatedBackground: connected,
                      ),
                  ],
                ),
                // The devices found nearby sit right under the device, where the tap to pair is
                // always on screen (below the steps they fell off the bottom of a tall phone).
                FindDevicesPage(
                  // Onboarding stays here after pairing (the live test); elsewhere pairing pops back.
                  isFromOnboarding: widget.onDone != null,
                  goNext: () {
                    Logger.debug('onConnected from FindDevicesPage');
                    if (widget.onDone != null) return;
                    // Back to the Home already underneath, not a second Home on top of it.
                    HomeNavigation.returnHome(context);
                  },
                  includeSkip: false,
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.lg, OmiSpacing.md, OmiSpacing.lg),
                  child: ConnectSteps(
                    // Each tick follows the live state: switching Bluetooth off clears the first two.
                    found: connected || (bluetoothOn && onboardingProvider.deviceList.isNotEmpty),
                    // iOS reports "on" only once Omi may use Bluetooth, so on means allowed and switched on.
                    bluetoothAllowed: connected || bluetoothOn,
                    connected: connected,
                    heard: connected ? _heardWords(context) : '',
                  ),
                ),
              ],
            );
          },
        ),
      ),
      bottomNavigationBar: Consumer<OnboardingProvider>(
        builder: (context, onboardingProvider, child) {
          final onDone = widget.onDone;
          if (onDone != null) {
            return Padding(
              padding: EdgeInsets.fromLTRB(
                OmiSpacing.md,
                OmiSpacing.sm,
                OmiSpacing.md,
                MediaQuery.of(context).padding.bottom + OmiSpacing.xs,
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  OmiButton(
                    key: const Key('connect_continue'),
                    label: context.l10n.continueButton,
                    expand: true,
                    onPressed: onboardingProvider.isConnected ? onDone : null,
                  ),
                  OmiButton.tertiary(
                    key: const Key('connect_set_up_later'),
                    label: context.l10n.setUpLater,
                    onPressed: onDone,
                  ),
                ],
              ),
            );
          }
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

/// The three steps every device shares (Rev 3 Connect), each ticked as it happens. The last one
/// shows the words the device hears, so the test proves real audio reaches Omi.
class ConnectSteps extends StatelessWidget {
  const ConnectSteps({
    super.key,
    required this.found,
    required this.bluetoothAllowed,
    required this.connected,
    this.heard = '',
  });

  final bool found;
  final bool bluetoothAllowed;
  final bool connected;

  /// The words the connected device has heard; empty until the first arrive.
  final String heard;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    // The latest words, so the line keeps up as the reader talks.
    final words = heard.length > 64 ? '…${heard.substring(heard.length - 64).trimLeft()}' : heard;
    return OmiCard(
      padding: const EdgeInsets.symmetric(vertical: OmiSpacing.xs),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _ConnectStep(number: 1, title: l10n.connectStepTurnOn, done: found),
          _ConnectStep(number: 2, title: l10n.connectStepAllowBluetooth, done: bluetoothAllowed),
          _ConnectStep(
            number: 3,
            title: l10n.connectStepTest,
            done: words.isNotEmpty,
            detail: !connected ? null : (words.isEmpty ? l10n.connectStepTestHint : '“$words”'),
          ),
        ],
      ),
    );
  }
}

class _ConnectStep extends StatelessWidget {
  const _ConnectStep({required this.number, required this.title, required this.done, this.detail});

  final int number;
  final String title;
  final bool done;
  final String? detail;

  @override
  Widget build(BuildContext context) {
    return MergeSemantics(
      child: Semantics(
        checked: done,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: 10),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              AnimatedContainer(
                duration: OmiMotion.of(context).quick,
                width: 26,
                height: 26,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: done ? OmiColors.accent : OmiColors.surface3,
                ),
                child: done
                    ? Icon(Icons.check_rounded, size: 16, color: OmiColors.onAccent)
                    : Text('$number', style: OmiType.footnote.copyWith(fontWeight: FontWeight.w700)),
              ),
              const SizedBox(width: OmiSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Padding(
                      padding: const EdgeInsets.only(top: 3),
                      child: Text(title, style: OmiType.callout.copyWith(fontWeight: FontWeight.w600)),
                    ),
                    if (detail != null) ...[
                      const SizedBox(height: 2),
                      Text(
                        detail!,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
