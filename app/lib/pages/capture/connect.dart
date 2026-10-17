import 'dart:async';

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/home/home_navigation.dart';
import 'package:omi/pages/onboarding/find_device/device_discovery_controller.dart';
import 'package:omi/pages/onboarding/find_device/page.dart';
import 'package:omi/pages/onboarding/find_device/pairing_failure_card.dart';
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';
import 'package:omi/utils/device.dart';
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
  const ConnectDevicePage({super.key, this.onConnected});

  /// Onboarding returns to its completion owner before Home can be entered.
  final VoidCallback? onConnected;

  @override
  State<ConnectDevicePage> createState() => _ConnectDevicePageState();
}

class _ConnectDevicePageState extends State<ConnectDevicePage> {
  late final DeviceDiscoveryController _discovery;
  late final NativeAssetUris _images;

  /// Set once the device list held an id the native rows cannot address (empty or repeated). The
  /// complete classic page then stays, with its own scan owner, instead of flapping back.
  bool _classicOnly = false;

  /// Onboarding hands a connected device to [ConnectDevicePage.onConnected]; opened from Home, the
  /// page returns there itself. Both presentations route through this one answer.
  bool get _isFromOnboarding => widget.onConnected != null;

  @override
  void initState() {
    super.initState();
    PlatformManager.instance.analytics.connectDevicePageOpened();
    _discovery = DeviceDiscoveryController(
      context: context,
      isFromOnboarding: _isFromOnboarding,
      goNext: _goNext,
      onRescan: _scanAgain,
    );
    _images = NativeAssetUris(() {
      if (mounted) setState(() {});
    });
  }

  @override
  void didUpdateWidget(ConnectDevicePage oldWidget) {
    super.didUpdateWidget(oldWidget);
    _discovery.isFromOnboarding = _isFromOnboarding;
  }

  @override
  void dispose() {
    _images.dispose();
    super.dispose();
  }

  void _goNext() {
    Logger.debug('onConnected from FindDevicesPage');
    final onConnected = widget.onConnected;
    if (onConnected != null) {
      onConnected();
      return;
    }
    // Back to the Home already underneath, not a second Home on top of it.
    HomeNavigation.returnHome(context);
  }

  Future<void> _scanAgain() async {
    if (!mounted) return;
    await _discovery.rescan(onReset: () => setState(() {}));
  }

  void _showConnectionGuide() {
    PlatformManager.instance.analytics.connectionGuideOpened();
    ConnectionGuideSheet.show(context);
  }

  @override
  Widget build(BuildContext context) {
    if (!nativePresentationEnabled || _classicOnly) return _classic(context);
    return Consumer<OnboardingProvider>(
      builder: (context, provider, child) {
        if (_classicOnly || !nativeDiscoveryIdsValid(provider.visibleDeviceList)) {
          _classicOnly = true;
          return _classic(context);
        }
        final l10n = context.l10n;
        return IosNativeSurface(
          title: l10n.connect,
          loading: _discoveryLoading(provider),
          loadingLabel: l10n.searchingForDevices,
          fallback: _classic(context),
          nativeOwner: _DiscoveryLifecycle(discovery: _discovery),
          toolbar: [
            NativeRow('connect_back', l10n.back,
                symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop()),
            NativeRow('connect_settings', l10n.deviceSettings,
                symbol: 'gearshape', action: (_) => routeToPage(context, const DeviceSettings())),
          ],
          sections: nativeDiscoverySections(
            context,
            provider,
            imageUri: (device) => _images[DeviceUtils.getDeviceImagePath(
              deviceType: device.type,
              modelNumber: device.modelNumber,
              deviceName: device.name,
            )],
            onTap: _discovery.tapVisible,
            onScanAgain: _scanAgain,
            onHowToPair: _showConnectionGuide,
            onContactSupport: () => launchUrl(Uri.parse('mailto:team@basedhardware.com')),
            onGetDevice: openOmiStore,
            onConnectionGuide: _showConnectionGuide,
          ),
        );
      },
    );
  }

  Widget _classic(BuildContext context) {
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
                      size: (MediaQuery.sizeOf(context).height <= 700 ? 280.0 : 360.0) *
                          (onboardingProvider.pairingFailureReason == null ? 1 : 0.5),
                    ),
                  DeviceAnimationWidget(
                    sizeMultiplier: onboardingProvider.pairingFailureReason == null ? 1 : 0.5,
                    isConnected: onboardingProvider.isConnected,
                    deviceName: onboardingProvider.deviceName,
                    deviceType: onboardingProvider.deviceType,
                    animatedBackground: onboardingProvider.isConnected,
                  ),
                ],
              ),
              FindDevicesPage(
                isFromOnboarding: _isFromOnboarding,
                goNext: _goNext,
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
                OmiButton(
                  variant: OmiButtonVariant.tertiary,
                  labelStyle: OmiType.callout.copyWith(
                      fontWeight: FontWeight.w600, fontFamily: Theme.of(context).textTheme.labelLarge?.fontFamily),
                  key: const Key('get_omi_device_button'),
                  label: context.l10n.getOmiDevice,
                  onPressed: openOmiStore,
                ),
                OmiButton(
                  variant: OmiButtonVariant.tertiary,
                  labelStyle: OmiType.callout.copyWith(
                      fontWeight: FontWeight.w600, fontFamily: Theme.of(context).textTheme.labelLarge?.fontFamily),
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

/// Native rows address devices by their place in the visible list, so every id must be present
/// and unique; otherwise the classic page keeps the list.
@visibleForTesting
bool nativeDiscoveryIdsValid(List<BtDevice> devices) {
  final ids = devices.map((device) => device.id).toList();
  return ids.every((id) => id.isNotEmpty) && ids.toSet().length == ids.length;
}

/// Longer device names are shortened, so a device's advertised name never invalidates the surface.
String _rowTitle(String title) => title.characters.length <= 120 ? title : '${title.characters.take(119)}…';

/// Whether the surface's own "Searching for devices" row stands in for the status line: nothing
/// found yet, no "nothing found" help and no pairing failure to recover from.
bool _discoveryLoading(OnboardingProvider provider) =>
    !provider.isConnected &&
    provider.visibleDeviceList.isEmpty &&
    !provider.enableInstructions &&
    provider.pairingFailureReason == null;

/// The Connect page's native sections, in the classic page's order: the status line, the inline
/// pairing failure, the device list, the "nothing found" help and the store/guide links. Only
/// display names, short ids, badges and battery cross; device ids stay here. Each device row
/// captures the id it projected and [onTap] receives it, so a tap reaches only a device that is
/// still visible.
@visibleForTesting
List<NativeSection> nativeDiscoverySections(
  BuildContext context,
  OnboardingProvider provider, {
  required String? Function(BtDevice device) imageUri,
  required Future<void> Function(String deviceId) onTap,
  required Future<void> Function() onScanAgain,
  required VoidCallback onHowToPair,
  required VoidCallback onContactSupport,
  required Future<void> Function() onGetDevice,
  required VoidCallback onConnectionGuide,
  bool includeSkip = false,
  VoidCallback? onNotNow,
}) {
  final l10n = context.l10n;
  final devices = provider.visibleDeviceList;
  // A pairing failure owns the status line's place until it is dismissed or resolved, as the
  // classic PairingFailureCard does; it never outlives a connection.
  final failure = provider.isConnected ? null : provider.pairingFailureReason;
  final cantFind = provider.deviceList.isEmpty && provider.enableInstructions && provider.pairingFailureReason == null;
  final battery = provider.batteryPercentage.clamp(0, 100);
  // While nothing is found the surface's own loading row already says "Searching for devices".
  final loading = _discoveryLoading(provider);
  return [
    NativeSection('connect_status', [
      if (!provider.isConnected && !cantFind && !loading && failure == null)
        NativeRow(
          'connect_searching',
          provider.nearbyDeviceCount == 0
              ? l10n.searchingForDevices
              : l10n.devicesFoundNearby(provider.nearbyDeviceCount),
          kind: 'label',
          symbol: 'antenna.radiowaves.left.and.right',
        ),
      if (provider.isConnected) ...[
        NativeRow('connect_paired', l10n.pairingSuccessful, kind: 'label', symbol: 'checkmark.circle'),
        NativeRow(
            'connect_device_name', _rowTitle(discoveryDeviceLabel(provider, provider.deviceName, provider.deviceId)),
            kind: 'label'),
        if (provider.batteryPercentage > 0)
          NativeRow('connect_battery', l10n.batteryLevelSemantics(battery),
              kind: 'label', symbol: battery <= 25 ? 'battery.25' : 'battery.100', destructive: battery <= 25),
      ],
    ]),
    if (failure != null)
      NativeSection('connect_pairing_failure', [
        NativeRow('connect_pairing_failure_message', pairingFailureCopy(l10n, failure),
            kind: 'label', symbol: 'exclamationmark.circle', destructive: true),
        NativeRow('connect_pairing_failure_retry', l10n.tryAgain,
            symbol: 'arrow.clockwise', action: (_) => onScanAgain()),
        NativeRow('connect_pairing_failure_guide', l10n.pairingHowTo,
            symbol: 'questionmark.circle', action: (_) => onHowToPair()),
        NativeRow('connect_pairing_failure_dismiss', l10n.close,
            symbol: 'xmark', action: (_) => provider.dismissPairingFailure()),
      ]),
    if (!provider.isConnected && devices.isNotEmpty)
      NativeSection('connect_devices', [
        for (final (index, device) in devices.indexed)
          () {
            final saved = provider.isSavedDevice(device);
            final offline = saved && !provider.isDeviceOnline(device);
            final id = device.id;
            return NativeRow(
              'connect_device:$index',
              _rowTitle(discoveryDeviceLabel(provider, device.name, device.id)),
              subtitle: [
                if (saved) offline ? l10n.offline : l10n.saved,
                if (provider.connectingToDeviceId == device.id) l10n.deviceConnecting,
              ].join(' · '),
              enabled: !provider.isClicked,
              imageUri: nativeImageUri(imageUri(device)),
              action: (_) => onTap(id),
            );
          }(),
      ]),
    if (cantFind)
      NativeSection('connect_none', title: l10n.findDeviceNoneTitle, footer: l10n.findDeviceNoneMessage, [
        NativeRow('connect_scan_again', l10n.scanAgain, symbol: 'arrow.clockwise', action: (_) => onScanAgain()),
        NativeRow('connect_how_to_pair', l10n.howToPair, symbol: 'questionmark.circle', action: (_) => onHowToPair()),
        if (includeSkip && onNotNow != null)
          NativeRow('connect_not_now', l10n.notNow, action: (_) {
            onNotNow();
            PlatformManager.instance.analytics.useWithoutDeviceOnboardingFindDevices();
          }),
        NativeRow('connect_contact_support', l10n.contactSupportAction,
            symbol: 'envelope', action: (_) => onContactSupport()),
      ]),
    if (!provider.isConnected)
      NativeSection('connect_more', [
        NativeRow('connect_get_device', l10n.getOmiDevice, symbol: 'safari', action: (_) => onGetDevice()),
        NativeRow('connect_guide', l10n.connectionGuide, symbol: 'info.circle', action: (_) => onConnectionGuide()),
      ]),
  ].where((section) => section.rows.isNotEmpty).toList();
}

/// The scan and connection owner while the native Connect surface is shown. It is mounted offstage
/// only when the native renderer is active; on the classic page [FindDevicesPage] and
/// [FoundDevices] own the same work, so there is only ever one scan owner. It starts the scan and
/// the device provider's connection on mount, cancels the scan on dispose, turns the provider's
/// messages into toasts and the DEVICE_CONNECTED pop, and reports each pairing failure shown.
class _DiscoveryLifecycle extends StatefulWidget {
  const _DiscoveryLifecycle({required this.discovery});

  final DeviceDiscoveryController discovery;

  @override
  State<_DiscoveryLifecycle> createState() => _DiscoveryLifecycleState();
}

class _DiscoveryLifecycleState extends State<_DiscoveryLifecycle> {
  OnboardingProvider? _provider;

  /// The pairing failure presentation already reported, by (version, reason).
  (int, DeviceConnectFailureShownFailureReason)? _reportedFailure;

  @override
  void initState() {
    super.initState();
    _provider = Provider.of<OnboardingProvider>(context, listen: false);
    // The classic order: FindDevicesPage scans, then FoundDevices starts the device connection.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      if (widget.discovery.isFromOnboarding) context.read<HomeProvider>().setupHasSpeakerProfile();
      unawaited(widget.discovery.scan());
      context.read<DeviceProvider>().initiateConnection('FoundDevices');
    });
  }

  @override
  void dispose() {
    _provider?.cancelActiveScan();
    _provider = null;
    super.dispose();
  }

  /// Reports a pairing failure after its first displayed frame, once per presentation and reason,
  /// exactly as the classic [PairingFailureCard] does for the same rows.
  void _reportPairingFailure(OnboardingProvider provider) {
    final reason = provider.pairingFailureReason;
    if (reason == null || provider.isConnected) return;
    final presentation = (provider.pairingFailureVersion, reason);
    if (_reportedFailure == presentation) return;
    _reportedFailure = presentation;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || provider.pairingFailureReason != reason) return;
      final platform = switch (Theme.of(context).platform) {
        TargetPlatform.iOS => DeviceConnectFailureShownPlatform.ios,
        TargetPlatform.android => DeviceConnectFailureShownPlatform.android,
        _ => DeviceConnectFailureShownPlatform.other,
      };
      const TypedEvents().emit(DeviceConnectFailureShown(failureReason: reason, platform: platform));
    });
  }

  @override
  Widget build(BuildContext context) {
    _reportPairingFailure(context.watch<OnboardingProvider>());
    return MessageListener<OnboardingProvider>(
      showError: (error) {
        // The pairing failure rows own connect-failure recovery and its shown event.
        if (error != 'DEVICE_CONNECT_FAILED') OmiFeedback.error(context, error);
      },
      showInfo: (info) {
        if (info == "DEVICE_CONNECTED") {
          if (mounted) Navigator.pop(context);
        } else {
          OmiFeedback.info(context, info);
        }
      },
      child: const SizedBox.shrink(),
    );
  }
}
